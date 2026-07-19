# backend/tests/test_domain_indexes.py
"""Unicidad de índices — SOLO contra Mongo REAL (mongomock no la exige).

Correr con:  pytest -m requires_real_mongo  (COMPAS_TEST_MONGO_URI apuntando a
un mongod real). En CI de la Sesión 3 (prerrequisito duro del Gate G1)."""

import os
from decimal import Decimal

import pytest
from app.domain import DOMAIN_DOCUMENTS
from app.domain.configuracion import Configuracion
from app.domain.rubro import Rubro
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

pytestmark = pytest.mark.requires_real_mongo


@pytest.fixture
async def real_db():
    uri = os.environ.get("COMPAS_TEST_MONGO_URI")
    if not uri:
        pytest.skip("COMPAS_TEST_MONGO_URI no configurado")
    client = AsyncIOMotorClient(uri, tz_aware=True)
    dbname = "compas_test_idx"
    await client.drop_database(dbname)
    database = client[dbname]
    await init_beanie(database=database, document_models=DOMAIN_DOCUMENTS)
    yield database
    await client.drop_database(dbname)
    client.close()


async def test_rubro_nombre_unico_por_grupo(real_db):
    await Rubro(grupo="operacion", nombre="Arriendos", orden=1).insert()
    with pytest.raises(DuplicateKeyError):
        await Rubro(grupo="operacion", nombre="Arriendos", orden=2).insert()


async def test_mismo_nombre_distinto_grupo_ok(real_db):
    await Rubro(grupo="operacion", nombre="Impuestos", orden=1).insert()
    await Rubro(grupo="otros", nombre="Impuestos", orden=2).insert()  # no colisiona


async def test_configuracion_clave_vigencia_unica(real_db):
    await Configuracion(
        clave="UMBRAL_DIF_BANCO_CIERRE",
        valor_decimal=Decimal("50000"),
        vigente_desde="2026-01-01",
    ).insert()
    with pytest.raises(DuplicateKeyError):
        await Configuracion(
            clave="UMBRAL_DIF_BANCO_CIERRE",
            valor_decimal=Decimal("60000"),
            vigente_desde="2026-01-01",
        ).insert()
