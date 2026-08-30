# backend/tests/proyeccion/test_actuals_mensuales.py
"""Task 1 FABS inc4 rebanada 3 — `actuals_mensuales`: ingreso/gasto/caja REALES
por mes (Transaccion), excluyendo el rubro 'Ajuste de conciliación' del gasto
(mismo criterio que `_caja_libro`). mongomock; patrón de la suite: init_beanie
con DOMAIN_DOCUMENTS (ver tests/cfo/test_calc_caja.py, tests/test_carga.py)."""

from decimal import Decimal

import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.rubro import Rubro, TipoFlujo
from app.domain.transaccion import Transaccion
from app.proyeccion import service as svc
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    """DB con el rubro de sistema 'Ajuste de conciliación' + un rubro INGRESO y un
    rubro EGRESO normales + dos MesControl cerrados (jun/jul 2026)."""
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    rubro_ajuste = await Rubro(
        grupo="otros",
        nombre="Ajuste de conciliación",
        tipo_flujo="egreso",
        orden=99,
        es_sistema=True,
    ).insert()
    rubro_ingreso = await Rubro(
        grupo="ingresos_operativos",
        nombre="Cuotas iniciales",
        tipo_flujo="ingreso",
        orden=1,
    ).insert()
    rubro_egreso = await Rubro(
        grupo="operacion",
        nombre="Arriendos",
        tipo_flujo="egreso",
        orden=2,
    ).insert()
    mc_jun = await MesControl(
        mes="2026-06-01",
        estado=EstadoMes.CERRADO,
        saldo_inicial_caja=Decimal("0"),
    ).insert()
    mc_jul = await MesControl(
        mes="2026-07-01",
        estado=EstadoMes.CERRADO,
        saldo_inicial_caja=Decimal("0"),
    ).insert()
    yield {
        "ajuste_id": rubro_ajuste.id,
        "ingreso_id": rubro_ingreso.id,
        "egreso_id": rubro_egreso.id,
        "jun_id": mc_jun.id,
        "jul_id": mc_jul.id,
    }


async def _tx(
    ids, mes_id_key: str, fecha: str, valor: str, tipo: str, rubro_id_key: str
):
    await Transaccion(
        fecha=fecha,
        descripcion="tx actuals",
        valor=Decimal(valor),
        tipo_flujo=tipo,
        rubro_id=ids[rubro_id_key],
        mes_id=ids[mes_id_key],
        banco="global66",
        id_banco=f"ACT-{fecha}-{valor}-{tipo}",
    ).insert()


async def test_actuals_mensuales_suma_por_tipo_excluye_ajuste(db):
    # jun: ingreso 3M, egreso 1M, + egreso 0.5M AL RUBRO AJUSTE (NO debe contar)
    await _tx(db, "jun_id", "2026-06-05", "3000000", TipoFlujo.INGRESO, "ingreso_id")
    await _tx(db, "jun_id", "2026-06-10", "1000000", TipoFlujo.EGRESO, "egreso_id")
    await _tx(db, "jun_id", "2026-06-15", "500000", TipoFlujo.EGRESO, "ajuste_id")
    # jul: ingreso 5M, egreso 2M
    await _tx(db, "jul_id", "2026-07-05", "5000000", TipoFlujo.INGRESO, "ingreso_id")
    await _tx(db, "jul_id", "2026-07-10", "2000000", TipoFlujo.EGRESO, "egreso_id")

    out = await svc.actuals_mensuales(meses=3)
    by = {a.mes: a for a in out}

    assert by["2026-06"].ingreso_real == Decimal("3000000")
    # el 0.5M del ajuste NO cuenta
    assert by["2026-06"].gasto_real == Decimal("1000000")
    assert by["2026-07"].ingreso_real == Decimal("5000000")
    assert by["2026-07"].gasto_real == Decimal("2000000")
    assert [a.mes for a in out] == ["2026-06", "2026-07"]  # cronológico asc


async def test_actuals_mensuales_respeta_limite_meses(db):
    # 3 meses con movimientos; meses=2 → solo los DOS más recientes, cronológico asc.
    await _tx(db, "jun_id", "2026-06-05", "1000000", TipoFlujo.INGRESO, "ingreso_id")
    await _tx(db, "jul_id", "2026-07-05", "2000000", TipoFlujo.INGRESO, "ingreso_id")
    mc_ago = await MesControl(
        mes="2026-08-01",
        estado=EstadoMes.CERRADO,
        saldo_inicial_caja=Decimal("0"),
    ).insert()
    ids = {**db, "ago_id": mc_ago.id}
    await _tx(ids, "ago_id", "2026-08-05", "4000000", TipoFlujo.INGRESO, "ingreso_id")

    out = await svc.actuals_mensuales(meses=2)
    assert [a.mes for a in out] == ["2026-07", "2026-08"]
