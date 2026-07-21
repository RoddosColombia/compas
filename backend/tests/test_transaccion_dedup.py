# backend/tests/test_transaccion_dedup.py
"""Deduplicación de Transaccion — SOLO contra Mongo REAL (regla 5, DoD F-04).

El índice ÚNICO PARCIAL (banco, id_banco) con partialFilterExpression
{id_banco:{$type:'string'}} NO lo soporta mongomock. Verifica:
  - '0 duplicados en solape': re-insertar el mismo (banco, id_banco) → DuplicateKey.
  - coexistencia de 2 manuales (F-04): id_banco 'MAN-' distinto, ambos entran.

Correr con:  pytest -m requires_real_mongo  (COMPAS_TEST_MONGO_URI a un Mongo real).
"""

import os
from decimal import Decimal

import pytest
from app.domain import DOMAIN_DOCUMENTS
from app.domain.bancos import Banco
from app.domain.rubro import TipoFlujo
from app.domain.transaccion import Transaccion
from beanie import PydanticObjectId, init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

pytestmark = pytest.mark.requires_real_mongo


@pytest.fixture
async def real_db():
    uri = os.environ.get("COMPAS_TEST_MONGO_URI")
    if not uri:
        pytest.skip("COMPAS_TEST_MONGO_URI no configurado")
    client = AsyncIOMotorClient(uri, tz_aware=True)
    dbname = "compas_test_dedup"
    await client.drop_database(dbname)
    await init_beanie(database=client[dbname], document_models=DOMAIN_DOCUMENTS)
    yield client[dbname]
    await client.drop_database(dbname)
    client.close()


def _tx(id_banco: str, banco: Banco = Banco.BBVA) -> Transaccion:
    return Transaccion(
        fecha="2026-03-15",
        descripcion="MOVIMIENTO",
        valor=Decimal("50000"),
        tipo_flujo=TipoFlujo.EGRESO,
        rubro_id=PydanticObjectId(),
        mes_id=PydanticObjectId(),
        banco=banco,
        id_banco=id_banco,
    )


async def test_solape_no_duplica(real_db):
    """Mismo (banco, id_banco) dos veces → el 2º lanza DuplicateKeyError."""
    await _tx("HUELLA-1").insert()
    with pytest.raises(DuplicateKeyError):
        await _tx("HUELLA-1").insert()


async def test_mismo_banco_distinto_idbanco_ok(real_db):
    await _tx("HUELLA-A").insert()
    await _tx("HUELLA-B").insert()  # no colisiona


async def test_dos_manuales_coexisten(real_db):
    """F-04: dos transacciones manuales del mismo día no chocan (id_banco distinto)."""
    await _tx("MAN-01HAAAAAAAAAAAAAAAAAAAAA", banco=Banco.MANUAL).insert()
    await _tx("MAN-01HBBBBBBBBBBBBBBBBBBBBB", banco=Banco.MANUAL).insert()
