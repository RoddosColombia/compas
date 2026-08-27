# backend/tests/cfo/test_escenario_golden.py
"""FABS · golden de referencia para el escenario "bodega 20M" (inc4 T9, cierre).

A diferencia de `tests/cfo/calc/test_escenario.py` (cobertura por caso), este archivo
fija UN escenario de referencia — "¿qué pasa si arriendo una bodega de $20M/mes desde
septiembre?" — cuyos 4 números (piso_sin, piso_con, mes de quiebre, unidades_extra +
piso_con_unidades) se conocen "al peso" (calculados a mano en los comentarios, no
re-derivados con la misma fórmula que el código bajo prueba — eso sería tautológico).
Sirve de regresión: si alguien cambia `escenario.py`/`solver_unidades.py` y estos
números se mueven sin que el escenario de entrada cambie, el golden lo atrapa.

No requiere Mongo real: fake en la frontera exacta que cada tool usa (`proyectar_
impactos` para `impacto_escenario`; `_proyectar_fn_para` para `motos_para_evitar_
umbral`, dejando correr el solver DE VERDAD — ver golden 2)."""

from decimal import Decimal

import pytest
from app.cfo.calc import escenario
from app.core.time import now_bogota
from app.proyeccion.motor import MesProyeccion, ResultadoProyeccion

# El escenario de referencia: "arriendo una bodega de $20M/mes desde septiembre".
NATURALEZA = "gasto"
MONTO = Decimal("20000000")
MES_INICIO = "2026-09"


def _ref_horizonte() -> str:
    ahora = now_bogota()
    return f"{ahora.year:04d}-{ahora.month:02d}"


def _fake_vigente(
    *, caja_minima: Decimal, motos_base: int = 78, horizonte_meses: int = 1
):
    from types import SimpleNamespace

    vig = SimpleNamespace(
        caja_minima=caja_minima, motos_base=motos_base, horizonte_meses=horizonte_meses
    )

    async def _obtener():
        return vig

    return _obtener


@pytest.mark.asyncio
async def test_golden_impacto_escenario_bodega_20m(monkeypatch):
    """Golden 1: `impacto_escenario` — piso_sin/piso_con/mes de quiebre/impacto_mensual
    "al peso" para el escenario de referencia. `proyectar_impactos` se fakea con la
    salida EXACTA que produciría el motor para esta bodega sobre una proyección base
    conocida (piso base $100M; con la bodega, cae a $40M y cruza el umbral en
    2026-11, el 3er mes de la serie ajustada) — números fijados a mano, no derivados."""

    async def fake_proyectar_impactos(
        *, ajustes, escenario, mes_inicio, horizonte_meses
    ):
        assert ajustes[0].naturaleza == NATURALEZA
        assert ajustes[0].valor == MONTO
        assert ajustes[0].mes_inicio == MES_INICIO
        return {
            "base": {"piso_caja": "100000000"},
            "ajustada": {
                "piso_caja": "40000000",
                "meses": [
                    {"mes": "2026-09", "estado": "ok"},
                    {"mes": "2026-10", "estado": "ok"},
                    {"mes": "2026-11", "estado": "critico"},
                ],
            },
            "delta_por_mes": ["-20000000", "-20000000", "-20000000"],
        }

    monkeypatch.setattr(
        escenario.proy_service, "proyectar_impactos", fake_proyectar_impactos
    )
    rs = await escenario.impacto_escenario(
        naturaleza=NATURALEZA, monto=MONTO, mes_inicio=MES_INICIO
    )
    by = {r.concepto: r for r in rs}

    # GOLDEN — valores "al peso" del escenario de referencia:
    assert by["piso_sin"].valor == Decimal("100000000")
    assert by["piso_con"].valor == Decimal("40000000")
    assert by["piso_con"].evidencia.ref == "quiebre:2026-11"
    assert by["impacto_mensual"].valor == Decimal("20000000")
    assert all(r.disponible for r in rs)
    ref_horizonte = _ref_horizonte()
    assert by["piso_sin"].evidencia.ref == ref_horizonte
    assert by["impacto_mensual"].evidencia.ref == ref_horizonte


@pytest.mark.asyncio
async def test_golden_motos_para_evitar_umbral_bodega_20m(monkeypatch):
    """Golden 2: `motos_para_evitar_umbral` sobre el MISMO escenario de referencia —
    el solver (`resolver_unidades_para_umbral`) corre DE VERDAD (no se fakea), solo se
    fakea la fuente de la proyección por candidato N (`_proyectar_fn_para`), con una
    forma ANALÍTICA cuyo piso(N) se conoce en cerrado.

    Matemática "al peso" (recalculada a mano UNA vez aquí, no re-derivada con la
    fórmula del código bajo prueba):
      - Mes único "2026-09". Arranque de caja A = $100.000.000 (constante en N: el
        proyectar_fn de cada candidato construye caja=A+flujo(N), así que
        aplicar_impactos —con `primer_mes_acumula=True`— recalcula
        caja_prev = caja(N) - flujo(N) = A, SIEMPRE, sin importar N).
      - Flujo base (sin bodega) por candidato: flujo(N) = -$10.000.000 + N×$1.000.000
        (cada moto extra aporta $1M de flujo/mes).
      - Ajuste bodega (gasto absoluto $20M desde 2026-09, sin mes_fin): delta de flujo
        = -$20.000.000 (constante, no depende de N).
      - piso(N) = caja_prev + flujo(N) + delta = $100.000.000
                  + (-$10.000.000 + N×$1.000.000) + (-$20.000.000)
                  = $70.000.000 + N×$1.000.000.
      - meta = caja_minima ($82.000.000) + colchón ($0) = $82.000.000.
      - piso(N) >= meta  ⇔  N >= 12 (piso(12)=$82.000.000 exacto; piso(11)=$81.000.000
        < meta). Mínimo N entero: 12.
    El solver (bisección real, `solver_unidades.py`) DEBE converger a exactamente
    N=12, piso_resultante=$82.000.000 — si no, hay una regresión real en el algoritmo
    o en la fórmula de `_piso_con_ajustes`/`aplicar_impactos`."""

    ARRANQUE = Decimal("100000000")
    FLUJO_BASE = Decimal("-10000000")
    PASO_POR_MOTO = Decimal("1000000")
    CAJA_MINIMA = Decimal("82000000")
    N_ESPERADO = 12
    PISO_ESPERADO = Decimal("82000000")

    def _mes_para(n: int) -> MesProyeccion:
        flujo = FLUJO_BASE + n * PASO_POR_MOTO
        caja = ARRANQUE + flujo
        return MesProyeccion(
            mes=MES_INICIO,
            motos=78 + n,
            cartera=78 + n,
            recaudo_credito=Decimal("0"),
            cuotas_iniciales=Decimal("0"),
            ingreso_bruto=Decimal("0"),
            neto=Decimal("0"),
            provision=Decimal("0"),
            gastos_fijos=Decimal("0"),
            gps=Decimal("0"),
            costo_nueva=Decimal("0"),
            adelanto=Decimal("0"),
            pago_inventario=Decimal("0"),
            fondeo=Decimal("0"),
            int_deuda=Decimal("0"),
            iva=Decimal("0"),
            egresos=Decimal("0"),
            flujo=flujo,
            caja=caja,
            estado="ok",
        )

    async def fake_proyectar_fn_para(vig, esc, mi, hm):
        async def proyectar_fn(n: int) -> ResultadoProyeccion:
            mes = _mes_para(n)
            return ResultadoProyeccion(
                meses=[mes],
                piso_caja=mes.caja,
                mes_mas_ajustado=mes.mes,
                meses_bajo_minimo=0,
                caja_final=mes.caja,
                capital_requerido=Decimal("0"),
                runway_meses=None,
            )

        return proyectar_fn

    monkeypatch.setattr(escenario, "_proyectar_fn_para", fake_proyectar_fn_para)
    monkeypatch.setattr(
        escenario.params_service,
        "obtener_vigente",
        _fake_vigente(caja_minima=CAJA_MINIMA),
    )

    rs = await escenario.motos_para_evitar_umbral(
        naturaleza=NATURALEZA, monto=MONTO, mes_inicio=MES_INICIO
    )
    by = {r.concepto: r for r in rs}

    # GOLDEN — valores "al peso" del escenario de referencia (ver matemática arriba):
    assert by["unidades_extra"].valor == Decimal(N_ESPERADO)
    assert by["unidades_extra"].unidad == "unidades"
    assert by["piso_con_unidades"].valor == PISO_ESPERADO
    assert by["unidades_extra"].disponible and by["piso_con_unidades"].disponible
    ref_horizonte = _ref_horizonte()
    assert by["unidades_extra"].evidencia.ref == ref_horizonte
    assert by["piso_con_unidades"].evidencia.ref == ref_horizonte
