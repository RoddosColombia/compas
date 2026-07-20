# backend/tests/test_auth_indexes.py
"""Índices de auth contra Mongo REAL (Kimi L4).

mongomock NO exige índices → un CI solo-mongomock daría verde aunque falten (y el TTL
del rate-limit por IP no expiraría: 429 permanente). Este test crea los índices desde
la MISMA fuente de verdad que el script (`AUTH_INDEXES`) y verifica que existen y que
la UNICIDAD se aplica de verdad (DuplicateKeyError). Corre en el CI de la Sesión 3.

Sin `COMPAS_TEST_MONGO_URI` se salta (no falla): el CI la provee."""

import os

import pytest
from app.auth.models import AUTH_INDEXES, USERS_COLLECTION
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

pytestmark = pytest.mark.requires_real_mongo


@pytest.fixture
async def db():
    uri = os.environ.get("COMPAS_TEST_MONGO_URI")
    if not uri:
        pytest.skip("COMPAS_TEST_MONGO_URI no configurado")
    client = AsyncIOMotorClient(uri, tz_aware=True)
    dbname = "compas_test_auth_idx"
    await client.drop_database(dbname)
    database = client[dbname]
    # Mismo recorrido que scripts/create_auth_indexes.py (fuente única AUTH_INDEXES).
    for coleccion, indices in AUTH_INDEXES.items():
        for idx in indices:
            kwargs: dict = {"name": idx["name"]}
            if idx.get("unique"):
                kwargs["unique"] = True
            if "expireAfterSeconds" in idx:
                kwargs["expireAfterSeconds"] = idx["expireAfterSeconds"]
            await database[coleccion].create_index(idx["keys"], **kwargs)
    yield database
    await client.drop_database(dbname)
    client.close()


async def test_todos_los_indices_de_auth_existen(db):
    for coleccion, indices in AUTH_INDEXES.items():
        info = await db[coleccion].index_information()
        for idx in indices:
            assert idx["name"] in info, f"falta índice {coleccion}.{idx['name']}"


async def test_email_unico_se_aplica(db):
    await db[USERS_COLLECTION].insert_one({"email": "a@roddos.com"})
    with pytest.raises(DuplicateKeyError):
        await db[USERS_COLLECTION].insert_one({"email": "a@roddos.com"})


async def test_ttl_configurado_en_login_throttle(db):
    info = await db["login_throttle"].index_information()
    ttl = next(v for k, v in info.items() if k == "ttl_ventana")
    assert ttl.get("expireAfterSeconds") == 0
