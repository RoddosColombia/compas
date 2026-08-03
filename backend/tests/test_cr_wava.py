# backend/tests/test_cr_wava.py
"""CR-WAVA: dinero en tránsito (Wava) en el cierre y la apertura.

Tests unitarios (mongomock) del dominio y del remanente derivado. La captura en el
cierre (hash/persistencia/O1/reapertura) y la trampa completa viven en el archivo
real-mongo del cierre (necesitan transacción). Ver I-PLAN docs/COMPAS_IPLAN_CR-WAVA.md.
"""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.cierre.transito import transito_heredado, transito_remanente
from app.domain import DOMAIN_DOCUMENTS
from app.domain.bancos import Banco
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
from app.domain.transaccion import Transaccion
from beanie import PydanticObjectId, init_beanie
from mongomock_motor import AsyncMongoMockClient

RUBRO_TRANSITO = "Tránsito Wava mes anterior"


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield c


async def _mes_cerrado(mes: str, transito: str) -> MesControl:
    mc = MesControl(
        mes=mes,
        saldo_inicial_caja=Decimal("0"),
        estado=EstadoMes.CERRADO,
        transito_wava=Decimal(transito),
    )
    await mc.insert()
    return mc


async def _rubro_transito() -> Rubro:
    r = Rubro(
        grupo=RubroGrupo.OTROS,
        nombre=RUBRO_TRANSITO,
        tipo_flujo=TipoFlujo.INGRESO,
        orden=99,
        es_sistema=True,
    )
    await r.insert()
    return r


async def _llegada(rubro: Rubro, fecha: str, valor: str, ordinal: int) -> None:
    """Depósito Wava que aterriza: tx INGRESO al rubro tránsito (mes_id es indiferente
    para el cálculo del remanente, que agrupa por rubro_id + fecha)."""
    await Transaccion(
        fecha=fecha,
        descripcion="deposito wava",
        valor=Decimal(valor),
        tipo_flujo=TipoFlujo.INGRESO,
        rubro_id=rubro.id,
        mes_id=PydanticObjectId(),
        banco=Banco.GLOBAL66,
        id_banco=f"WAVA-{ordinal}|1",
    ).insert()


# ── §1 dominio ──


@pytest.mark.asyncio
async def test_mescontrol_transito_wava_default_cero(db):
    mc = MesControl(mes="2026-07-01", saldo_inicial_caja=Decimal("0"))
    assert mc.transito_wava == Decimal("0")
    await mc.insert()
    releido = await MesControl.get(mc.id)
    assert releido.transito_wava == Decimal("0")


@pytest.mark.asyncio
async def test_mescontrol_transito_wava_acepta_valor(db):
    mc = MesControl(
        mes="2026-07-01",
        saldo_inicial_caja=Decimal("0"),
        transito_wava=Decimal("37280415"),
    )
    await mc.insert()
    releido = await MesControl.get(mc.id)
    assert releido.transito_wava == Decimal("37280415")


# ── §4 remanente derivado (compute-only) ──


@pytest.mark.asyncio
async def test_transito_heredado_del_mes_anterior(db):
    await _mes_cerrado("2026-07-01", "37280415")
    assert await transito_heredado("2026-08-01") == Decimal("37280415")


@pytest.mark.asyncio
async def test_transito_heredado_cero_si_no_hay(db):
    assert await transito_heredado("2026-08-01") == Decimal("0")


@pytest.mark.asyncio
async def test_remanente_llegada_parcial(db):
    await _mes_cerrado("2026-07-01", "100")
    r = await _rubro_transito()
    await _llegada(r, "2026-08-10", "60", 1)
    assert await transito_remanente("2026-08-01") == Decimal("40")


@pytest.mark.asyncio
async def test_remanente_sobrellegada_clamp_cero(db):
    await _mes_cerrado("2026-07-01", "100")
    r = await _rubro_transito()
    await _llegada(r, "2026-08-10", "120", 1)
    assert await transito_remanente("2026-08-01") == Decimal("0")


@pytest.mark.asyncio
async def test_remanente_roll_forward_en_m2(db):
    await _mes_cerrado("2026-07-01", "100")
    r = await _rubro_transito()
    await _llegada(r, "2026-08-10", "30", 1)
    await _llegada(r, "2026-09-10", "40", 2)  # M+2 sigue descontando del mismo Y
    assert await transito_remanente("2026-09-01") == Decimal("30")


@pytest.mark.asyncio
async def test_remanente_sin_declaracion_es_cero(db):
    assert await transito_remanente("2026-08-01") == Decimal("0")
