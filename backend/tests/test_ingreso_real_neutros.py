# backend/tests/test_ingreso_real_neutros.py
"""FIX-B: `ingreso_real` EXCLUYE los rubros neutros.

Dinero que volvió a la cuenta (reversas de GMF, devoluciones, reembolsos) entra como
INGRESO pero NO es recaudo: si sumara en `ingreso_real` inflaría el cumplimiento de la
meta. El set de rubros neutros nace con 'Reversas y devoluciones' (FIX-B) y CR-WAVA lo
extenderá con 'Tránsito Wava mes anterior' y 'Ajuste de conciliación' — sin duplicar.
"""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.domain.bancos import Banco
from app.domain.mes_control import MesControl
from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
from app.domain.transaccion import Transaccion
from app.metas_ingreso.service import ingreso_real
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

MES = "2026-07"


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield c


async def _mes() -> MesControl:
    mc = MesControl(mes=f"{MES}-01", saldo_inicial_caja=Decimal("0"))
    await mc.insert()
    return mc


async def _rubro(grupo: RubroGrupo, nombre: str) -> Rubro:
    r = Rubro(grupo=grupo, nombre=nombre, tipo_flujo=TipoFlujo.INGRESO, orden=1)
    await r.insert()
    return r


async def _tx(mc: MesControl, rubro: Rubro, valor: str, ordinal: int) -> None:
    await Transaccion(
        fecha=f"{MES}-10",
        descripcion="mov",
        valor=Decimal(valor),
        tipo_flujo=TipoFlujo.INGRESO,
        rubro_id=rubro.id,
        mes_id=mc.id,
        banco=Banco.GLOBAL66,
        id_banco=f"REF-{ordinal}|1",
    ).insert()


@pytest.mark.asyncio
async def test_reversas_no_suma_pero_recaudo_si(db):
    mc = await _mes()
    recaudo = await _rubro(RubroGrupo.INGRESOS_OPERATIVOS, "Recaudo")
    reversas = await _rubro(RubroGrupo.OTROS, "Reversas y devoluciones")
    await _tx(mc, recaudo, "100", 1)
    await _tx(mc, reversas, "43", 2)
    # solo el recaudo cuenta; la reversa (rubro neutro) se excluye
    assert await ingreso_real(MES) == Decimal("100")


@pytest.mark.asyncio
async def test_recaudo_solo_cuenta_completo(db):
    mc = await _mes()
    recaudo = await _rubro(RubroGrupo.INGRESOS_OPERATIVOS, "Recaudo")
    await _tx(mc, recaudo, "250", 1)
    await _tx(mc, recaudo, "50", 2)
    assert await ingreso_real(MES) == Decimal("300")


@pytest.mark.asyncio
async def test_sin_mes_control_es_none(db):
    assert await ingreso_real("2099-01") is None


# ── CR-WAVA §2 (P-1): el set neutro crece con 'Tránsito Wava mes anterior' y
# 'Ajuste de conciliación' (contra-asiento INGRESO de reapertura). Exclusión por
# rubro_id, nunca por grupo ni por es_sistema. ──


@pytest.mark.asyncio
async def test_transito_wava_no_suma_ingreso_real(db):
    mc = await _mes()
    recaudo = await _rubro(RubroGrupo.INGRESOS_OPERATIVOS, "Recaudo de cartera")
    transito = await _rubro(RubroGrupo.OTROS, "Tránsito Wava mes anterior")
    await _tx(mc, recaudo, "100", 1)
    await _tx(mc, transito, "37", 2)  # depósito Wava del mes anterior que aterrizó
    # el depósito de tránsito NO es recaudo del mes → excluido
    assert await ingreso_real(MES) == Decimal("100")


@pytest.mark.asyncio
async def test_ajuste_conciliacion_no_suma_ingreso_real(db):
    mc = await _mes()
    recaudo = await _rubro(RubroGrupo.INGRESOS_OPERATIVOS, "Recaudo de cartera")
    ajuste = await _rubro(RubroGrupo.OTROS, "Ajuste de conciliación")
    await _tx(mc, recaudo, "200", 1)
    await _tx(mc, ajuste, "15", 2)  # contra-asiento INGRESO de reapertura
    # el contra-asiento de reapertura no es ingreso real → excluido
    assert await ingreso_real(MES) == Decimal("200")
