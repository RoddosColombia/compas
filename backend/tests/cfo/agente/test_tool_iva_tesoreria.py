# backend/tests/cfo/agente/test_tool_iva_tesoreria.py
"""FABS · tool `iva_tesoreria` (inc6 #1, T3): wrapper de orquestación en `tools.py`
que lee `proyectar_vigente` (fondo_provision del mes actual) + `iva.iva_cuatrimestre`
(próximo pago) + `_disponible_hoy` (mes EN_EJECUCION conciliado) y le pasa los cinco
insumos crudos a la calc pura `cfo.calc.iva_tesoreria.armar_conceptos` (S1, intocada:
no se testea aquí de nuevo, ver tests/cfo/calc/test_iva_tesoreria.py)."""

from decimal import Decimal

import pytest
from app.cfo.agente import tools
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.core.time import now_bogota
from app.proyeccion.service import ProyeccionError


def _mes_actual() -> str:
    ahora = now_bogota()
    return f"{ahora.year:04d}-{ahora.month:02d}"


def _iva_disponible(monto="3000", fecha="2027-01-14"):
    async def fake_iva():
        return ResultadoCFO(
            concepto="iva_cuatrimestre",
            valor=Decimal(monto),
            unidad="COP",
            disponible=True,
            evidencia=Evidencia(fuente="f", fecha_corte=fecha, ref="2027-C1"),
        )

    return fake_iva


def _iva_abstenida():
    async def fake_iva():
        return ResultadoCFO(
            concepto="iva_cuatrimestre",
            valor=None,
            unidad="COP",
            disponible=False,
            evidencia=Evidencia(fuente="f", fecha_corte=None, ref="sin-periodo"),
        )

    return fake_iva


# --- schema --------------------------------------------------------------


def test_schema_incluye_tool_iva_tesoreria():
    # Tool de CERO args, igual que rumbo_caja/mix_modelos/las 3 originales: sin
    # propiedades, additionalProperties False.
    nombres = {t["name"] for t in tools.TOOLS_SCHEMA}
    assert "iva_tesoreria" in nombres
    t = next(x for x in tools.TOOLS_SCHEMA if x["name"] == "iva_tesoreria")
    assert t["input_schema"]["properties"] == {}
    assert t["input_schema"]["additionalProperties"] is False
    assert t["description"]


def test_dispatch_incluye_iva_tesoreria():
    assert "iva_tesoreria" in tools.DISPATCH


# --- wrapper: camino feliz -------------------------------------------------


@pytest.mark.asyncio
async def test_wrapper_arma_conceptos(monkeypatch):
    mes_actual = _mes_actual()

    async def fake_proy(**k):
        return {
            "fondo_provision": [
                {"mes": mes_actual, "reserva": "250", "pago": "0", "saldo": "1000"},
            ]
        }

    monkeypatch.setattr(tools.proy_service, "proyectar_vigente", fake_proy)
    monkeypatch.setattr(tools.iva, "iva_cuatrimestre", _iva_disponible())

    async def fake_disp():
        return Decimal("600")

    monkeypatch.setattr(tools, "_disponible_hoy", fake_disp)

    res = await tools._iva_tesoreria({})
    by = {r.concepto: r for r in res}

    assert by.keys() == {
        "ivates_reserva_objetivo",
        "ivates_reserva_mes",
        "ivates_proximo_pago",
        "ivates_disponible_neto",
        "ivates_faltante",
    }
    assert by["ivates_reserva_objetivo"].valor == Decimal("1000")
    assert by["ivates_reserva_objetivo"].disponible is True
    assert by["ivates_reserva_mes"].valor == Decimal("250")
    assert by["ivates_proximo_pago"].valor == Decimal("3000")
    assert by["ivates_proximo_pago"].evidencia.fecha_corte == "2027-01-14"
    # disponible(600) - reserva_objetivo(1000) => -400 (neto negativo, no clampeado)
    assert by["ivates_disponible_neto"].valor == Decimal("-400")
    # faltante = max(0, 1000-600) = 400
    assert by["ivates_faltante"].valor == Decimal("400")


@pytest.mark.asyncio
async def test_wrapper_ejecutar_tool_despacha(monkeypatch):
    mes_actual = _mes_actual()

    async def fake_proy(**k):
        return {
            "fondo_provision": [
                {"mes": mes_actual, "reserva": "100", "pago": "0", "saldo": "500"},
            ]
        }

    monkeypatch.setattr(tools.proy_service, "proyectar_vigente", fake_proy)
    monkeypatch.setattr(tools.iva, "iva_cuatrimestre", _iva_abstenida())

    async def fake_disp():
        return None

    monkeypatch.setattr(tools, "_disponible_hoy", fake_disp)

    res = await tools.ejecutar_tool("iva_tesoreria")
    assert isinstance(res, list) and all(isinstance(r, ResultadoCFO) for r in res)
    by = {r.concepto: r for r in res}
    assert by["ivates_reserva_objetivo"].valor == Decimal("500")
    # iva_cuatrimestre abstuvo -> proximo_pago sin valor
    assert by["ivates_proximo_pago"].disponible is False
    # sin disponible_hoy -> neto/faltante no se pueden derivar
    assert by["ivates_disponible_neto"].disponible is False
    assert by["ivates_faltante"].disponible is False


# --- wrapper: sin fila del mes actual en fondo_provision --------------------


@pytest.mark.asyncio
async def test_wrapper_sin_fila_del_mes_actual(monkeypatch):
    async def fake_proy(**k):
        return {
            "fondo_provision": [
                {"mes": "2020-01", "reserva": "999", "pago": "0", "saldo": "999"},
            ]
        }

    monkeypatch.setattr(tools.proy_service, "proyectar_vigente", fake_proy)
    monkeypatch.setattr(tools.iva, "iva_cuatrimestre", _iva_disponible())

    async def fake_disp():
        return Decimal("600")

    monkeypatch.setattr(tools, "_disponible_hoy", fake_disp)

    res = await tools._iva_tesoreria({})
    by = {r.concepto: r for r in res}
    assert by["ivates_reserva_objetivo"].disponible is False
    assert by["ivates_reserva_mes"].disponible is False
    # sin reserva_objetivo, neto/faltante tampoco se pueden derivar
    assert by["ivates_disponible_neto"].disponible is False
    assert by["ivates_faltante"].disponible is False
    # el próximo pago no depende del fondo -- sigue disponible
    assert by["ivates_proximo_pago"].disponible is True


# --- wrapper: ProyeccionError => abstención TOTAL ---------------------------


@pytest.mark.asyncio
async def test_wrapper_proyeccion_error_es_abstencion_total(monkeypatch):
    async def fake_proy(**k):
        raise ProyeccionError("sin config", 409)

    def _no_debe_llamarse():
        raise AssertionError("no debe llamarse tras ProyeccionError (abstención total)")

    async def fake_iva_no_llamado():
        _no_debe_llamarse()

    async def fake_disp_no_llamado():
        _no_debe_llamarse()

    monkeypatch.setattr(tools.proy_service, "proyectar_vigente", fake_proy)
    monkeypatch.setattr(tools.iva, "iva_cuatrimestre", fake_iva_no_llamado)
    monkeypatch.setattr(tools, "_disponible_hoy", fake_disp_no_llamado)

    res = await tools._iva_tesoreria({})
    assert len(res) == 5
    assert all(r.disponible is False and r.valor is None for r in res)
    assert {r.concepto for r in res} == {
        "ivates_reserva_objetivo",
        "ivates_reserva_mes",
        "ivates_proximo_pago",
        "ivates_disponible_neto",
        "ivates_faltante",
    }


# --- _disponible_hoy: helper de módulo (vía cierre.service.mes_en_ejecucion, ------
# SIN importar MesControl -- agente/ está en la frontera S1, ver
# tests/cfo/test_s1_aislamiento.py) ------------------------------------------


@pytest.mark.asyncio
async def test_disponible_hoy_sin_mes_en_ejecucion(monkeypatch):
    async def fake_mes_en_ejecucion():
        return None

    monkeypatch.setattr(tools, "mes_en_ejecucion", fake_mes_en_ejecucion)
    assert await tools._disponible_hoy() is None


@pytest.mark.asyncio
async def test_disponible_hoy_cierre_error_es_none(monkeypatch):
    async def fake_mes_en_ejecucion():
        return "2026-08-01"

    async def fake_conciliacion(mes):
        raise tools.CierreError("no en ejecución", 409)

    monkeypatch.setattr(tools, "mes_en_ejecucion", fake_mes_en_ejecucion)
    monkeypatch.setattr(tools, "conciliacion", fake_conciliacion)
    assert await tools._disponible_hoy() is None


@pytest.mark.asyncio
async def test_disponible_hoy_sin_dato_es_none(monkeypatch):
    async def fake_mes_en_ejecucion():
        return "2026-08-01"

    async def fake_conciliacion(mes):
        return {"consolidado_reportado": "123", "sin_dato": ["bancolombia"]}

    monkeypatch.setattr(tools, "mes_en_ejecucion", fake_mes_en_ejecucion)
    monkeypatch.setattr(tools, "conciliacion", fake_conciliacion)
    assert await tools._disponible_hoy() is None


@pytest.mark.asyncio
async def test_disponible_hoy_ok(monkeypatch):
    async def fake_mes_en_ejecucion():
        return "2026-08-01"

    async def fake_conciliacion(mes):
        assert mes == "2026-08-01"
        return {"consolidado_reportado": "704722003", "sin_dato": []}

    monkeypatch.setattr(tools, "mes_en_ejecucion", fake_mes_en_ejecucion)
    monkeypatch.setattr(tools, "conciliacion", fake_conciliacion)
    assert await tools._disponible_hoy() == Decimal("704722003")


# --- conceptos.py: ivates_proximo_pago comparte el formato de iva_cuatrimestre --


def test_formatear_ivates_proximo_pago_muestra_vencimiento():
    from datetime import date

    from app.cfo.agente.conceptos import formatear

    r = ResultadoCFO(
        concepto="ivates_proximo_pago",
        valor=Decimal("3000000"),
        unidad="COP",
        disponible=True,
        evidencia=Evidencia(fuente="f", fecha_corte="2027-01-14", ref="proximo:pago"),
    )
    out = formatear(r, hoy=date(2026, 8, 31))
    assert "vence el 2027-01-14" in out
    assert "días" in out
