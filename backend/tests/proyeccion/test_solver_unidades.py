# backend/tests/proyeccion/test_solver_unidades.py
from dataclasses import dataclass
from decimal import Decimal

import pytest
from app.proyeccion.solver_unidades import (
    _piso_con_ajustes,
    resolver_unidades_para_umbral,
)


# Fake mínimo de ResultadoProyeccion: el solver solo necesita que aplicar_impactos
# corra sobre él. Para aislar el solver de aplicar_impactos, monkeypatcheamos el piso.
@dataclass
class _R:  # sustituto de ResultadoProyeccion para el fake
    piso: Decimal


async def _piso_lineal(n: int) -> _R:
    # piso sube 1.000.000 por unidad extra, arranca en -5.000.000 (bajo el umbral 0)
    return _R(piso=Decimal(-5_000_000) + Decimal(1_000_000) * n)


@pytest.mark.asyncio
async def test_encuentra_minimo_de_unidades(monkeypatch):
    # aplicar_impactos(r, ajustes, caja_minima).kpis.piso_caja == r.piso (fake)
    monkeypatch.setattr(
        "app.proyeccion.solver_unidades._piso_con_ajustes",
        lambda r, ajustes, caja_minima: r.piso,
    )
    res = await resolver_unidades_para_umbral(
        _piso_lineal, ajustes=[], caja_minima=Decimal("0")
    )
    assert res.alcanzable is True
    assert res.unidades_extra == 5  # -5M + 5*1M = 0 >= umbral 0
    assert res.piso_resultante == Decimal("0")


@pytest.mark.asyncio
async def test_ya_cumple_con_cero(monkeypatch):
    monkeypatch.setattr(
        "app.proyeccion.solver_unidades._piso_con_ajustes",
        lambda r, ajustes, caja_minima: r.piso,
    )

    async def _proyectar_fn(n: int) -> _R:
        return _R(piso=Decimal(10_000_000))

    res = await resolver_unidades_para_umbral(
        _proyectar_fn, ajustes=[], caja_minima=Decimal("0")
    )
    assert res.unidades_extra == 0 and res.alcanzable is True


@pytest.mark.asyncio
async def test_no_alcanzable_dentro_del_tope(monkeypatch):
    monkeypatch.setattr(
        "app.proyeccion.solver_unidades._piso_con_ajustes",
        lambda r, ajustes, caja_minima: r.piso,
    )

    async def _proyectar_fn(n: int) -> _R:
        # piso jamás sube (aunque haya más unidades) → no alcanzable
        return _R(piso=Decimal(-1))

    res = await resolver_unidades_para_umbral(
        _proyectar_fn,
        ajustes=[],
        caja_minima=Decimal("0"),
        cap_unidades=100,
    )
    assert res.alcanzable is False and res.unidades_extra == 0


# ---------------------------------------------------------------------------
# Fix round 1 (Task 1) — regresión: la búsqueda debe quedar ACOTADA a [0, cap_unidades].
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_minimo_en_el_borde_del_cap_es_alcanzable(monkeypatch):
    # Escalón: piso < meta para n<10, piso == meta desde n=10 — el mínimo real
    # CAE justo en el cap. Bug original: la fase de duplicado saltaba 8→16 y
    # declaraba "no alcanzable" aunque 10 <= cap_unidades=10 (Escenario A).
    monkeypatch.setattr(
        "app.proyeccion.solver_unidades._piso_con_ajustes",
        lambda r, ajustes, caja_minima: r.piso,
    )

    async def _proyectar_fn(n: int) -> _R:
        return _R(piso=Decimal("0") if n >= 10 else Decimal("-1"))

    res = await resolver_unidades_para_umbral(
        _proyectar_fn,
        ajustes=[],
        caja_minima=Decimal("0"),
        cap_unidades=10,
    )
    assert res.alcanzable is True
    assert res.unidades_extra == 10
    assert res.piso_resultante == Decimal("0")


@pytest.mark.asyncio
async def test_minimo_en_mitad_superior_del_cap_default_es_alcanzable(monkeypatch):
    # Lineal con cero en n=9000 (> cap_unidades/2 = 5000, usando el cap DEFAULT
    # 10.000, sin pasarlo explícito). Reproduce el Escenario A al valor LITERAL
    # del default: la duplicación 8192→16384 se pasaba del cap y perdía el 9000,
    # que sí era alcanzable.
    monkeypatch.setattr(
        "app.proyeccion.solver_unidades._piso_con_ajustes",
        lambda r, ajustes, caja_minima: r.piso,
    )

    async def _proyectar_fn(n: int) -> _R:
        return _R(piso=Decimal(1_000) * (n - 9000))

    res = await resolver_unidades_para_umbral(
        _proyectar_fn, ajustes=[], caja_minima=Decimal("0")
    )
    assert res.alcanzable is True
    assert res.unidades_extra == 9000
    assert res.piso_resultante == Decimal("0")


@pytest.mark.asyncio
async def test_cap_cero_bloquea_unidad_que_si_alcanzaria(monkeypatch):
    # true N=1 (piso(0) < meta <= piso(1)) pero cap_unidades=0 prohíbe CUALQUIER
    # unidad extra. Bug original (Escenario B): el chequeo del cap vivía DENTRO
    # del while de duplicado, que nunca se ejecutaba porque piso(1) ya cumplía
    # la meta en el primer chequeo — el cap quedaba sin aplicar.
    monkeypatch.setattr(
        "app.proyeccion.solver_unidades._piso_con_ajustes",
        lambda r, ajustes, caja_minima: r.piso,
    )

    async def _proyectar_fn(n: int) -> _R:
        return _R(piso=Decimal("-1") + Decimal("2") * n)

    res = await resolver_unidades_para_umbral(
        _proyectar_fn,
        ajustes=[],
        caja_minima=Decimal("0"),
        cap_unidades=0,
    )
    assert res.alcanzable is False
    assert res.unidades_extra == 0


# ---------------------------------------------------------------------------
# Fix round 1 (Task 6 de inc4) — _piso_con_ajustes debe usar primer_mes_acumula=True,
# la MISMA convención que impacto_escenario/proyectar_impactos, para que los dos
# caminos reconcilien en el caso más común (un ajuste que arranca en el primer mes
# del horizonte — motos_para_evitar_umbral siempre ancla el horizonte a HOY).
# ---------------------------------------------------------------------------


def test_piso_con_ajustes_acumula_desde_el_primer_mes():
    from app.proyeccion.impactos import Ajuste
    from app.proyeccion.motor import MesProyeccion, ResultadoProyeccion

    def _mes(mes: str, flujo: Decimal, caja: Decimal) -> MesProyeccion:
        return MesProyeccion(
            mes=mes,
            motos=10,
            cartera=10,
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

    base = ResultadoProyeccion(
        meses=[
            _mes("2026-09", Decimal("-2000000"), Decimal("98000000")),
            _mes("2026-10", Decimal("-3000000"), Decimal("95000000")),
        ],
        piso_caja=Decimal("95000000"),
        mes_mas_ajustado="2026-10",
        meses_bajo_minimo=0,
        caja_final=Decimal("95000000"),
        capital_requerido=Decimal("0"),
        runway_meses=None,
    )
    ajuste = Ajuste(
        nombre="Escenario FABS",
        naturaleza="gasto",
        modo="absoluto",
        valor=Decimal("10000000"),
        mes_inicio="2026-09",  # el PRIMER mes del horizonte
    )
    # A mano (reacumular con primer_mes_acumula=True): arranque = 98M - (-2M) = 100M;
    # mes0 = 100M + (-2M - 10M) = 88M; mes1 = 88M + (-3M - 10M) = 75M; piso = 75M.
    # Con primer_mes_acumula=False (el bug de antes de este fix) el mes0 se hubiera
    # quedado fijo en 98M y el piso habría dado 85M — 10M de diferencia, no un
    # redondeo.
    piso = _piso_con_ajustes(base, [ajuste], Decimal("50000000"))
    assert piso == Decimal("75000000.00")
