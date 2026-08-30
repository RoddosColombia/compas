# backend/tests/cfo/agente/test_tools.py
from decimal import Decimal

import pytest
from app.cfo.agente import tools
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO


def _res(valor):
    return ResultadoCFO(
        concepto="caja_hoy",
        valor=valor,
        unidad="COP",
        disponible=valor is not None,
        evidencia=Evidencia(fuente="f", fecha_corte="2026-08-11", ref="2026-08"),
    )


def test_schema_tools_sin_parametros_siguen_sin_propiedades():
    # Las 3 tools de cero args de antes de T7 no cambian: siguen sin propiedades.
    # (La afirmación de set-igualdad completa de antes de T7 ahora vive partida
    # entre este test y test_schema_incluye_tools_de_escenario, porque T7 agrega
    # dos tools CON propiedades.)
    sin_args = {"caja_disponible_hoy", "runway_meses", "iva_del_cuatrimestre"}
    por_nombre = {t["name"]: t for t in tools.TOOLS_SCHEMA}
    assert sin_args <= por_nombre.keys()
    for nombre in sin_args:
        assert por_nombre[nombre]["input_schema"]["properties"] == {}


def test_schema_incluye_tools_de_escenario():
    nombres = {t["name"] for t in tools.TOOLS_SCHEMA}
    assert {"impacto_escenario", "motos_para_evitar_umbral"} <= nombres
    for nombre in ("impacto_escenario", "motos_para_evitar_umbral"):
        t = next(x for x in tools.TOOLS_SCHEMA if x["name"] == nombre)
        assert t["input_schema"]["additionalProperties"] is False
        assert set(t["input_schema"]["required"]) == {
            "naturaleza",
            "monto",
            "mes_inicio",
        }
        props = t["input_schema"]["properties"]
        assert props["naturaleza"]["enum"] == ["gasto", "ingreso"]
        assert props["monto"]["type"] == "string"
        assert props["mes_inicio"]["type"] == "string"
        assert props["mes_fin"]["type"] == "string"


def test_resultado_a_dict_no_expone_valor_ni_detalle():
    # inc3 Pieza A: el modelo ya no ve `valor` — cita conceptos con [[token]] y el
    # servicio sustituye el valor concept-bound tras verificar. Sin `valor` no puede
    # fabricar, mal-etiquetar ni calcular.
    d = tools.resultado_a_dict(_res(Decimal("704722003")))
    assert "valor" not in d
    assert "detalle" not in d
    assert d["concepto"] == "caja_hoy"
    assert d["disponible"] is True
    assert d["unidad"] == "COP"
    assert d["evidencia"] == {
        "fuente": "f",
        "fecha_corte": "2026-08-11",
        "ref": "2026-08",
    }


@pytest.mark.asyncio
async def test_ejecutar_tool_despacha(monkeypatch):
    async def fake():
        return _res(Decimal("123"))

    monkeypatch.setitem(tools.DISPATCH, "caja_disponible_hoy", fake)
    r = await tools.ejecutar_tool("caja_disponible_hoy")
    # inc4 T4: ejecutar_tool SIEMPRE devuelve lista; una calc de un solo concepto
    # (como esta, de cero args) se normaliza a [r].
    assert isinstance(r, list) and len(r) == 1
    assert r[0].valor == Decimal("123")


@pytest.mark.asyncio
async def test_ejecutar_tool_desconocida_falla():
    with pytest.raises(KeyError):
        await tools.ejecutar_tool("no_existe")


@pytest.mark.asyncio
async def test_ejecutar_tool_devuelve_lista(monkeypatch):
    r = await tools.ejecutar_tool("caja_disponible_hoy")
    assert isinstance(r, list) and all(isinstance(x, ResultadoCFO) for x in r)


@pytest.mark.asyncio
async def test_tool_desconocida_es_error():
    # Exception amplia a propósito (brief T4): el contrato es "cualquier error",
    # no un tipo específico — el dispatcher cerrado hoy usa KeyError, pero el
    # test no debe acoplarse a ese detalle de implementación.
    with pytest.raises(Exception):  # noqa: B017
        await tools.ejecutar_tool("no_existe")


# --- T7: tools de escenario (parametrizadas) --------------------------------
#
# Ruling-T7 (progress.md): el test ilustrativo del brief hace
# `monkeypatch.setitem(tools.DISPATCH, "impacto_escenario", None)` como
# "placeholder" — con el dispatcher real ese `None` rompería `ejecutar_tool`
# (inspect.signature(None) no es callable). El wrapper real en DISPATCH
# (`_impacto_escenario`/`_motos_para_evitar_umbral`) llama a
# `escenario.impacto_escenario`/`escenario.motos_para_evitar_umbral` por
# atributo de módulo (no `from ... import impacto_escenario`), así que basta
# monkeypatchear esos dos nombres en `app.cfo.calc.escenario` — se preserva la
# aserción del brief (monto parseado a Decimal) sin tocar DISPATCH.


@pytest.mark.asyncio
async def test_impacto_escenario_parsea_monto(monkeypatch):
    llamado = {}

    async def fake_calc(*, naturaleza, monto, mes_inicio, mes_fin=None):
        llamado.update(
            naturaleza=naturaleza, monto=monto, mes_inicio=mes_inicio, mes_fin=mes_fin
        )
        return []

    monkeypatch.setattr("app.cfo.calc.escenario.impacto_escenario", fake_calc)
    r = await tools.ejecutar_tool(
        "impacto_escenario",
        {"naturaleza": "gasto", "monto": "20000000", "mes_inicio": "2026-09"},
    )
    assert llamado["monto"] == Decimal("20000000")
    assert llamado["naturaleza"] == "gasto"
    assert llamado["mes_inicio"] == "2026-09"
    assert llamado["mes_fin"] is None
    assert r == []  # ejecutar_tool no reenvuelve una lista ya devuelta por la calc


@pytest.mark.asyncio
async def test_motos_para_evitar_umbral_parsea_monto_y_mes_fin(monkeypatch):
    llamado = {}

    async def fake_calc(*, naturaleza, monto, mes_inicio, mes_fin=None):
        llamado.update(monto=monto, mes_fin=mes_fin)
        return []

    monkeypatch.setattr("app.cfo.calc.escenario.motos_para_evitar_umbral", fake_calc)
    await tools.ejecutar_tool(
        "motos_para_evitar_umbral",
        {
            "naturaleza": "ingreso",
            "monto": "5000000",
            "mes_inicio": "2026-10",
            "mes_fin": "2026-12",
        },
    )
    assert llamado["monto"] == Decimal("5000000")
    assert llamado["mes_fin"] == "2026-12"


@pytest.mark.asyncio
async def test_naturaleza_invalida_falla_sin_llegar_a_la_calc(monkeypatch):
    # impactos._delta_flujo trata cualquier naturaleza != 'gasto' como 'ingreso'
    # SIN error — por eso el dispatcher debe rechazar un valor fuera del enum
    # antes de llamar la calc (que aquí ni se monkeypatchea: si el guard falla,
    # el intento de llamar la calc real revienta la conexión y el test lo nota).
    with pytest.raises(ValueError, match="naturaleza"):
        await tools.ejecutar_tool(
            "impacto_escenario",
            {"naturaleza": "gastoo", "monto": "1000", "mes_inicio": "2026-09"},
        )


@pytest.mark.asyncio
async def test_monto_invalido_falla():
    with pytest.raises(ValueError, match="monto"):
        await tools.ejecutar_tool(
            "impacto_escenario",
            {"naturaleza": "gasto", "monto": "no-es-numero", "mes_inicio": "2026-09"},
        )


@pytest.mark.asyncio
async def test_monto_no_finito_falla():
    # Decimal("Infinity")/("NaN") NO lanzan InvalidOperation al construirse — sin
    # este guard, envenenarían la caja acumulada aguas abajo (mismo hazard P1-8
    # de app.core.money).
    with pytest.raises(ValueError, match="monto"):
        await tools.ejecutar_tool(
            "impacto_escenario",
            {"naturaleza": "gasto", "monto": "Infinity", "mes_inicio": "2026-09"},
        )


@pytest.mark.asyncio
async def test_monto_numero_crudo_falla():
    # El input_schema declara `monto` como string (regla 1); si el modelo manda un
    # número JSON crudo en vez de string, se rechaza explícito en vez de aceptar
    # silenciosamente un float en el camino a un Ajuste de caja.
    with pytest.raises(ValueError, match="monto"):
        await tools.ejecutar_tool(
            "impacto_escenario",
            {"naturaleza": "gasto", "monto": 20000000, "mes_inicio": "2026-09"},
        )


# --- T3 (rebanada 2): tool simular_palanca -----------------------------------


def test_schema_incluye_tool_simular_palanca():
    nombres = {t["name"] for t in tools.TOOLS_SCHEMA}
    assert "simular_palanca" in nombres
    t = next(x for x in tools.TOOLS_SCHEMA if x["name"] == "simular_palanca")
    assert t["input_schema"]["additionalProperties"] is False
    assert set(t["input_schema"]["required"]) == {"palanca", "nuevo_valor"}
    props = t["input_schema"]["properties"]
    assert props["palanca"]["enum"] == [
        "plazo_semanas",
        "cuota_inicial",
        "cuota_semanal",
    ]
    assert props["nuevo_valor"]["type"] == "string"
    assert props["modelo"]["enum"] == ["Raider", "Apache", "Sport", "todos"]


@pytest.mark.asyncio
async def test_simular_palanca_parsea_nuevo_valor_y_default_modelo(monkeypatch):
    llamado = {}

    async def fake_calc(*, palanca, nuevo_valor, modelo="todos"):
        llamado.update(palanca=palanca, nuevo_valor=nuevo_valor, modelo=modelo)
        return []

    monkeypatch.setattr("app.cfo.calc.palanca.impacto_palanca", fake_calc)
    r = await tools.ejecutar_tool(
        "simular_palanca", {"palanca": "plazo_semanas", "nuevo_valor": "78"}
    )
    assert llamado["palanca"] == "plazo_semanas"
    assert llamado["nuevo_valor"] == Decimal("78")
    assert llamado["modelo"] == "todos"
    assert r == []


@pytest.mark.asyncio
async def test_simular_palanca_respeta_modelo_explicito(monkeypatch):
    llamado = {}

    async def fake_calc(*, palanca, nuevo_valor, modelo="todos"):
        llamado.update(palanca=palanca, nuevo_valor=nuevo_valor, modelo=modelo)
        return []

    monkeypatch.setattr("app.cfo.calc.palanca.impacto_palanca", fake_calc)
    await tools.ejecutar_tool(
        "simular_palanca",
        {"palanca": "cuota_semanal", "nuevo_valor": "150000", "modelo": "Raider"},
    )
    assert llamado["modelo"] == "Raider"


@pytest.mark.asyncio
async def test_simular_palanca_invalida_falla_sin_llegar_a_la_calc():
    with pytest.raises(ValueError, match="palanca"):
        await tools.ejecutar_tool(
            "simular_palanca", {"palanca": "no_existe", "nuevo_valor": "78"}
        )


@pytest.mark.asyncio
async def test_simular_palanca_modelo_invalido_falla():
    with pytest.raises(ValueError, match="modelo"):
        await tools.ejecutar_tool(
            "simular_palanca",
            {"palanca": "plazo_semanas", "nuevo_valor": "78", "modelo": "Ducati"},
        )


@pytest.mark.asyncio
async def test_simular_palanca_nuevo_valor_invalido_falla():
    with pytest.raises(ValueError, match="nuevo_valor"):
        await tools.ejecutar_tool(
            "simular_palanca",
            {"palanca": "plazo_semanas", "nuevo_valor": "no-es-numero"},
        )


@pytest.mark.asyncio
async def test_simular_palanca_nuevo_valor_no_finito_falla():
    with pytest.raises(ValueError, match="nuevo_valor"):
        await tools.ejecutar_tool(
            "simular_palanca",
            {"palanca": "plazo_semanas", "nuevo_valor": "Infinity"},
        )


@pytest.mark.asyncio
async def test_simular_palanca_nuevo_valor_numero_crudo_falla():
    with pytest.raises(ValueError, match="nuevo_valor"):
        await tools.ejecutar_tool(
            "simular_palanca", {"palanca": "plazo_semanas", "nuevo_valor": 78}
        )
