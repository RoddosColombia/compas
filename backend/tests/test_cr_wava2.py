# backend/tests/test_cr_wava2.py
"""CR-WAVA-2: hook estado-dependiente de clasificación de depósitos Wava.

Tests unitarios (mongomock) del matcher puro `es_transito_wava` y del
`AsignadorTransito` (cache + descuento en batch). El cableado en la carga y en
`aplicar_pendientes` (transacción real) vive en el archivo real-mongo.
Ver docs/superpowers/specs/2026-08-03-cr-wava-2-hook-clasificacion-wava-design.md.
"""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.cierre.transito import AsignadorTransito, es_transito_wava
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


# ── matcher puro (sin DB) ──


@pytest.mark.parametrize(
    "desc",
    [
        "Recibido de WAVA Technologie",
        "recibido de wava",
        "RECIBIDO DE WAVA TECHNOLOGIE S.A.S",
        "  Recíbido de Wává  ",  # tildes + espacios: normalizador comparte
    ],
)
def test_es_transito_wava_matchea(desc):
    assert es_transito_wava(desc) is True


@pytest.mark.parametrize(
    "desc",
    [
        "Recibido de Éxito",
        "Recibido de Juan Perez",
        "Pago a Wava por comision",  # 'wava' sí, pero no 'recibido de wava'
        "Transferencia Bancolombia",
        "",
    ],
)
def test_es_transito_wava_no_matchea(desc):
    assert es_transito_wava(desc) is False


# ── AsignadorTransito (cache + descuento en batch) ──


@pytest.mark.asyncio
async def test_asigna_ingreso_wava_con_remanente(db):
    await _mes_cerrado("2026-07-01", "100")
    await _rubro_transito()
    a = AsignadorTransito()
    ok = await a.asigna(
        descripcion="Recibido de WAVA Technologie",
        mes="2026-08-01",
        tipo_flujo=TipoFlujo.INGRESO,
        valor=Decimal("60"),
    )
    assert ok is True


@pytest.mark.asyncio
async def test_asigna_descuenta_en_batch(db):
    """Tres depósitos Wava en la MISMA corrida: el gate es `remanente > 0` ANTES del
    depósito, con descuento en batch. Igual que cargas secuenciales: el 2º cruza y
    agota (40>0 → tránsito), el 3º llega con remanente ya en 0 → recaudo."""
    await _mes_cerrado("2026-07-01", "100")
    await _rubro_transito()
    a = AsignadorTransito()
    k = dict(
        mes="2026-08-01", tipo_flujo=TipoFlujo.INGRESO, descripcion="recibido de wava"
    )
    assert (
        await a.asigna(valor=Decimal("60"), **k) is True
    )  # 100>0 -> transito; 100->40
    assert await a.asigna(valor=Decimal("40"), **k) is True  # 40>0 -> transito; 40->0
    assert await a.asigna(valor=Decimal("10"), **k) is False  # 0 no >0 -> recaudo


@pytest.mark.asyncio
async def test_asigna_egreso_wava_no_dispara(db):
    await _mes_cerrado("2026-07-01", "100")
    await _rubro_transito()
    a = AsignadorTransito()
    ok = await a.asigna(
        descripcion="recibido de wava",
        mes="2026-08-01",
        tipo_flujo=TipoFlujo.EGRESO,
        valor=Decimal("10"),
    )
    assert ok is False


@pytest.mark.asyncio
async def test_asigna_remanente_cero_no_dispara(db):
    await _mes_cerrado("2026-07-01", "100")
    r = await _rubro_transito()
    await _llegada(r, "2026-08-10", "100", 1)  # ya agotado
    a = AsignadorTransito()
    ok = await a.asigna(
        descripcion="recibido de wava",
        mes="2026-08-01",
        tipo_flujo=TipoFlujo.INGRESO,
        valor=Decimal("10"),
    )
    assert ok is False


@pytest.mark.asyncio
async def test_asigna_sin_declaracion_no_dispara(db):
    await _rubro_transito()  # no hay mes cerrado con transito
    a = AsignadorTransito()
    ok = await a.asigna(
        descripcion="recibido de wava",
        mes="2026-08-01",
        tipo_flujo=TipoFlujo.INGRESO,
        valor=Decimal("10"),
    )
    assert ok is False


@pytest.mark.asyncio
async def test_asigna_no_wava_no_dispara(db):
    await _mes_cerrado("2026-07-01", "100")
    await _rubro_transito()
    a = AsignadorTransito()
    ok = await a.asigna(
        descripcion="Recibido de Éxito",
        mes="2026-08-01",
        tipo_flujo=TipoFlujo.INGRESO,
        valor=Decimal("10"),
    )
    assert ok is False
