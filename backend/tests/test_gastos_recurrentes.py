# backend/tests/test_gastos_recurrentes.py
"""Módulo de gastos recurrentes (plantilla administrable) — decisión CEO 2026-07-26.

Es INFORMATIVO (no alimenta el motor): plantilla persistente de los gastos fijos
mensuales, cada uno apuntado a un rubro existente (hereda grupo/código del Plan de
Cuentas). Reglas cubiertas: dinero=Decimal, frecuencia→equivalente mensual, el rubro
debe existir, resumen mensual por grupo. Sin eventos de auditoría (catálogo cerrado,
regla 11): es config informativa, no un flujo de dinero/decisión.
"""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.domain.gasto_recurrente import Frecuencia, GastoRecurrente
from app.domain.rubro import Rubro
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    # rubros mínimos (grupo operación y nómina)
    r_op = await Rubro(
        grupo="operacion", nombre="Arriendos", codigo="2010", orden=1
    ).insert()
    r_nom = await Rubro(
        grupo="nomina", nombre="Sueldos empleados", codigo="3010", orden=2
    ).insert()
    return {"op": r_op, "nom": r_nom}


# ── Dominio: frecuencia → equivalente mensual ──


@pytest.mark.parametrize(
    ("frecuencia", "monto", "esperado"),
    [
        (Frecuencia.MENSUAL, "100000", "100000.00"),
        (Frecuencia.BIMESTRAL, "200000", "100000.00"),
        (Frecuencia.TRIMESTRAL, "300000", "100000.00"),
        (Frecuencia.CUATRIMESTRAL, "400000", "100000.00"),
        (Frecuencia.SEMESTRAL, "600000", "100000.00"),
        (Frecuencia.ANUAL, "1200000", "100000.00"),
    ],
)
def test_monto_mensual_por_frecuencia(frecuencia, monto, esperado):
    g = GastoRecurrente(
        rubro_id="000000000000000000000001",
        descripcion="x",
        monto=Decimal(monto),
        frecuencia=frecuencia,
        orden=1,
    )
    assert g.monto_mensual == Decimal(esperado)


def test_monto_debe_ser_decimal_no_float():
    with pytest.raises(ValueError):
        GastoRecurrente(
            rubro_id="000000000000000000000001",
            descripcion="x",
            monto=100000.0,  # float → rechazado (regla 1)
            orden=1,
        )


def test_hasta_formato_mes():
    g = GastoRecurrente(
        rubro_id="000000000000000000000001",
        descripcion="Liquidación",
        monto=Decimal("500000"),
        hasta="2026-08",
        orden=1,
    )
    assert g.hasta == "2026-08"
    with pytest.raises(ValueError):
        GastoRecurrente(
            rubro_id="000000000000000000000001",
            descripcion="x",
            monto=Decimal("1"),
            hasta="2026-13",  # mes inválido
            orden=1,
        )


# ── Servicio ──


@pytest.mark.asyncio
async def test_crear_gasto_ok(db):
    from app.gastos_recurrentes import service

    g = await service.crear_gasto(
        rubro_id=str(db["op"].id),
        descripcion="Arriendo oficina",
        monto=Decimal("3614953"),
        frecuencia=Frecuencia.MENSUAL,
        dia_pago=5,
        notas="Contrato a 1 año, renovable",
        usuario_id="u1",
    )
    assert g.descripcion == "Arriendo oficina"
    assert g.monto == Decimal("3614953")
    assert g.dia_pago == 5


@pytest.mark.asyncio
async def test_crear_gasto_rubro_inexistente_falla(db):
    from app.gastos_recurrentes import service

    with pytest.raises(service.GastosError) as exc:
        await service.crear_gasto(
            rubro_id="000000000000000000000099",
            descripcion="x",
            monto=Decimal("1000"),
            frecuencia=Frecuencia.MENSUAL,
            dia_pago=None,
            notas=None,
            usuario_id="u1",
        )
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_listar_y_resumen_por_grupo(db):
    from app.gastos_recurrentes import service

    await service.crear_gasto(
        rubro_id=str(db["op"].id),
        descripcion="Arriendo",
        monto=Decimal("3000000"),
        frecuencia=Frecuencia.MENSUAL,
        dia_pago=None,
        notas=None,
        usuario_id="u1",
    )
    # anual 1.2M → 100k/mes
    await service.crear_gasto(
        rubro_id=str(db["op"].id),
        descripcion="Renovación dominio",
        monto=Decimal("1200000"),
        frecuencia=Frecuencia.ANUAL,
        dia_pago=None,
        notas=None,
        usuario_id="u1",
    )
    await service.crear_gasto(
        rubro_id=str(db["nom"].id),
        descripcion="Salario",
        monto=Decimal("4500000"),
        frecuencia=Frecuencia.MENSUAL,
        dia_pago=None,
        notas=None,
        usuario_id="u1",
    )

    gastos = await service.listar_gastos()
    assert len(gastos) == 3

    resumen = await service.resumen_mensual(gastos)
    # operación = 3.000.000 + 100.000 = 3.100.000 ; nómina = 4.500.000
    assert resumen["por_grupo"]["operacion"] == Decimal("3100000.00")
    assert resumen["por_grupo"]["nomina"] == Decimal("4500000.00")
    assert resumen["total"] == Decimal("7600000.00")


@pytest.mark.asyncio
async def test_editar_y_eliminar(db):
    from app.gastos_recurrentes import service

    g = await service.crear_gasto(
        rubro_id=str(db["op"].id),
        descripcion="Aseo",
        monto=Decimal("400000"),
        frecuencia=Frecuencia.MENSUAL,
        dia_pago=None,
        notas=None,
        usuario_id="u1",
    )
    g2 = await service.editar_gasto(
        gasto_id=str(g.id), monto=Decimal("450000"), notas="subió 2026"
    )
    assert g2.monto == Decimal("450000")
    assert g2.notas == "subió 2026"

    await service.eliminar_gasto(gasto_id=str(g.id))
    assert await service.listar_gastos() == []


@pytest.mark.asyncio
async def test_resumen_excluye_gastos_vencidos(db):
    from app.gastos_recurrentes import service

    # gasto que terminó en junio → no cuenta en julio
    await service.crear_gasto(
        rubro_id=str(db["nom"].id),
        descripcion="Liquidación Liliana",
        monto=Decimal("500000"),
        frecuencia=Frecuencia.MENSUAL,
        dia_pago=None,
        notas=None,
        hasta="2026-06",
        usuario_id="u1",
    )
    # gasto sin fin → sí cuenta
    await service.crear_gasto(
        rubro_id=str(db["op"].id),
        descripcion="Arriendo",
        monto=Decimal("3000000"),
        frecuencia=Frecuencia.MENSUAL,
        dia_pago=None,
        notas=None,
        hasta=None,
        usuario_id="u1",
    )
    resumen = await service.resumen_mensual(
        await service.listar_gastos(), mes_ref="2026-07"
    )
    assert resumen["total"] == Decimal("3000000.00")


@pytest.mark.asyncio
async def test_resumen_solo_cuenta_activos(db):
    from app.gastos_recurrentes import service

    g = await service.crear_gasto(
        rubro_id=str(db["op"].id),
        descripcion="Servicio pausado",
        monto=Decimal("500000"),
        frecuencia=Frecuencia.MENSUAL,
        dia_pago=None,
        notas=None,
        usuario_id="u1",
    )
    await service.editar_gasto(gasto_id=str(g.id), activo=False)
    resumen = await service.resumen_mensual(await service.listar_gastos())
    assert resumen["total"] == Decimal("0.00")
