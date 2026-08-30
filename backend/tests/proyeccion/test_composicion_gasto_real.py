# backend/tests/proyeccion/test_composicion_gasto_real.py
"""Task 1 FABS inc4 rebanada 4 (ratios/mix) — `composicion_gasto_real`: egreso REAL
agregado por RubroGrupo de gasto (los 5, sin ingresos_operativos), excluyendo el
rubro de sistema 'Ajuste de conciliación' (mismo criterio que `_caja_libro` /
`actuals_mensuales`, rebanada 3), y expandiendo `partes` en transacciones divididas
(PTS6-B) vía `pares_clasificacion`. mongomock; patrón de la suite (ver
tests/proyeccion/test_actuals_mensuales.py)."""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.rubro import Rubro
from app.domain.transaccion import ParteClasificacion, Transaccion
from app.proyeccion import service as svc
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    """DB con el rubro de sistema 'Ajuste de conciliación' + rubros normales en
    NOMINA/DEUDAS_OBLIGACIONES/OPERACION + un MesControl 2026-07-01 CERRADO."""
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    rubro_ajuste = await Rubro(
        grupo="otros",
        nombre="Ajuste de conciliación",
        tipo_flujo="egreso",
        orden=99,
        es_sistema=True,
    ).insert()
    rubro_nomina = await Rubro(
        grupo="nomina",
        nombre="Sueldos empleados",
        tipo_flujo="egreso",
        orden=1,
    ).insert()
    rubro_deudas = await Rubro(
        grupo="deudas_obligaciones",
        nombre="Préstamos",
        tipo_flujo="egreso",
        orden=2,
    ).insert()
    rubro_oper = await Rubro(
        grupo="operacion",
        nombre="Arriendos",
        tipo_flujo="egreso",
        orden=3,
    ).insert()
    mc_jul = await MesControl(
        mes="2026-07-01",
        estado=EstadoMes.CERRADO,
        saldo_inicial_caja=Decimal("0"),
    ).insert()
    yield {
        "ajuste_id": rubro_ajuste.id,
        "nomina_id": rubro_nomina.id,
        "deudas_id": rubro_deudas.id,
        "oper_id": rubro_oper.id,
        "jul_id": mc_jul.id,
    }


async def _tx(mes_id, fecha: str, valor: str, rubro_id, id_banco: str):
    await Transaccion(
        fecha=fecha,
        descripcion="tx composicion",
        valor=Decimal(valor),
        tipo_flujo="egreso",
        rubro_id=rubro_id,
        mes_id=mes_id,
        banco="global66",
        id_banco=id_banco,
    ).insert()


async def test_composicion_cerrado_por_grupo_excluye_ajuste_expande_partes(db):
    # 3M -> nomina
    await _tx(db["jul_id"], "2026-07-05", "3000000", db["nomina_id"], "COMP-1")
    # 1M -> deudas
    await _tx(db["jul_id"], "2026-07-06", "1000000", db["deudas_id"], "COMP-2")
    # split 1M: 600k operacion + 400k nomina (rubro_id primario = la parte mayor)
    await Transaccion(
        fecha="2026-07-07",
        descripcion="tx composicion split",
        valor=Decimal("1000000"),
        tipo_flujo="egreso",
        rubro_id=db["oper_id"],
        mes_id=db["jul_id"],
        banco="global66",
        id_banco="COMP-3",
        partes=[
            ParteClasificacion(rubro_id=db["oper_id"], valor=Decimal("600000")),
            ParteClasificacion(rubro_id=db["nomina_id"], valor=Decimal("400000")),
        ],
    ).insert()
    # 0.5M -> rubro ajuste (NO debe contar)
    await _tx(db["jul_id"], "2026-07-08", "500000", db["ajuste_id"], "COMP-4")

    c = await svc.composicion_gasto_real(ventana="cerrado")

    assert c.meses == ["2026-07"]
    assert c.por_grupo["nomina"] == Decimal("3400000")  # 3M + 400k del split
    assert c.por_grupo["deudas_obligaciones"] == Decimal("1000000")
    assert c.por_grupo["operacion"] == Decimal("600000")  # 600k del split
    assert c.total == Decimal("5000000")  # ajuste (0.5M) excluido
    assert "ingresos_operativos" not in c.por_grupo  # solo grupos de gasto


async def test_composicion_ventana_no_soportada_422(db):
    # `db` solo para inicializar beanie/mongomock en el event loop de este test
    # (composicion_gasto_real consulta MesControl.find_all() antes de validar
    # la ventana); el valor no se usa.
    with pytest.raises(svc.ProyeccionError) as exc:
        await svc.composicion_gasto_real(ventana="no-existe")
    assert exc.value.status == 422


async def test_composicion_sin_meses_409(db):
    # hay un MesControl pero sin movimientos: 'curso'/'acumulado' no encuentran
    # meses con Transaccion; 'cerrado' sí encuentra el MesControl CERRADO (sin
    # necesitar movimientos) — se usa 'curso' para forzar el camino sin meses.
    with pytest.raises(svc.ProyeccionError) as exc:
        await svc.composicion_gasto_real(ventana="curso")
    assert exc.value.status == 409
