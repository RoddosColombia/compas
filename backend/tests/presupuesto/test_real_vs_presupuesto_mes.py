# backend/tests/presupuesto/test_real_vs_presupuesto_mes.py
"""Task 6 FABS inc4 rebanada 3 (tendencias) — `real_vs_presupuesto_mes`: real
ejecutado vs presupuesto aprobado del último mes CERRADO. Capa presupuesto/service.py
(dataclass plano, sin cfo/calc todavía — S1 aísla esa capa para una tarea posterior).

mongomock; patrón de la suite: init_beanie con DOMAIN_DOCUMENTS (ver
tests/cfo/test_calc_caja.py, tests/test_carga.py, tests/test_presupuesto_generar.py)."""

from decimal import Decimal

import app.presupuesto.service as presu_svc
import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.presupuesto import PresupuestoLinea
from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
from app.domain.transaccion import Transaccion
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield c


async def _mes(mesd: str, estado: EstadoMes) -> MesControl:
    mc = MesControl(mes=mesd, saldo_inicial_caja=Decimal("0"), estado=estado)
    await mc.insert()
    return mc


async def _rubro(nombre: str, orden: int, *, sistema: bool = False) -> Rubro:
    r = Rubro(
        grupo=RubroGrupo.OPERACION, nombre=nombre, orden=orden, es_sistema=sistema
    )
    await r.insert()
    return r


_SEQ = [0]


async def _tx(rubro_id, mc: MesControl, monto: str, *, tipo=TipoFlujo.EGRESO) -> None:
    _SEQ[0] += 1
    await Transaccion(
        fecha=f"{mc.mes[:7]}-15",
        descripcion="EJEC",
        valor=Decimal(monto),
        tipo_flujo=tipo,
        rubro_id=rubro_id,
        mes_id=mc.id,
        banco="manual",
        id_banco=f"MAN-EJEC-{_SEQ[0]}",
    ).insert()


async def _linea(mc: MesControl, rubro_id, monto_definido: str) -> PresupuestoLinea:
    ln = PresupuestoLinea(
        mes_id=mc.id,
        rubro_id=rubro_id,
        monto_sugerido=Decimal(monto_definido),
        prom_3m=Decimal(monto_definido),
        tendencia_mes=Decimal("0"),
        crec_pct=Decimal("0"),
        monto_definido=Decimal(monto_definido),
        historia_incompleta=False,
    )
    await ln.insert()
    return ln


@pytest.mark.asyncio
async def test_real_vs_presupuesto_mes_cerrado(db):
    jun = await _mes("2026-06-01", EstadoMes.CERRADO)
    ajuste = await _rubro("Ajuste de conciliación", 99, sistema=True)
    arriendos = await _rubro("Arriendos", 1)
    otros = await _rubro("Mercado y aseo", 2)
    await _tx(arriendos.id, jun, "1000000")
    await _tx(otros.id, jun, "500000")
    await _tx(ajuste.id, jun, "300000")  # excluido (Ajuste de conciliación)
    await _linea(jun, arriendos.id, "1200000")
    await _linea(jun, otros.id, "600000")

    out = await presu_svc.real_vs_presupuesto_mes()  # último cerrado = 2026-06
    assert out is not None
    assert out.mes == "2026-06"
    assert out.gasto_real == Decimal("1500000")  # 1.0M + 0.5M (ajuste excluido)
    assert out.presupuesto_aprobado == Decimal("1800000")  # 1.2M + 0.6M


@pytest.mark.asyncio
async def test_real_vs_presupuesto_mes_sin_cerrado(db):
    # sin MesControl cerrado sembrado
    await _rubro("Ajuste de conciliación", 99, sistema=True)
    assert await presu_svc.real_vs_presupuesto_mes() is None
