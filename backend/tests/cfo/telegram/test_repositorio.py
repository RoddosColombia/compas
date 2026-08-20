# backend/tests/cfo/telegram/test_repositorio.py
"""FABS · Documents cfo_vinculos_telegram + cfo_hilos — unicidad SOLO contra Mongo
REAL (mongomock no la soporta; ver tests/test_domain_indexes.py, mismo patrón de
fixture). Vínculo uno-a-uno (B-3): único en telegram_id Y en user_id."""

import os

import pytest
from app.cfo.telegram import repositorio as repo
from app.cfo.telegram.modelos import HiloCFO, VinculoTelegram
from app.core.time import now_utc
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError


@pytest.fixture
async def mongo_real():
    uri = os.environ.get("COMPAS_TEST_MONGO_URI")
    if not uri:
        pytest.skip("COMPAS_TEST_MONGO_URI no configurado")
    client = AsyncIOMotorClient(uri, tz_aware=True)
    dbname = "compas_test_cfo_telegram"
    await client.drop_database(dbname)
    await init_beanie(database=client[dbname], document_models=DOMAIN_DOCUMENTS)
    yield client
    await client.drop_database(dbname)
    client.close()


@pytest.mark.requires_real_mongo
@pytest.mark.asyncio
async def test_vinculo_unico_y_resolver(mongo_real):
    v = VinculoTelegram(
        telegram_id=111, user_id="u1", creado_por="admin", creado_at=now_utc()
    )
    await repo.crear_vinculo(v)
    assert await repo.resolver_usuario(111) == "u1"
    assert await repo.resolver_usuario(999) is None
    # unicidad (B-3): otro vínculo con el mismo telegram_id o user_id falla
    with pytest.raises(DuplicateKeyError):
        await repo.crear_vinculo(
            VinculoTelegram(
                telegram_id=111, user_id="u2", creado_por="admin", creado_at=now_utc()
            )
        )


@pytest.mark.requires_real_mongo
@pytest.mark.asyncio
async def test_hilo_upsert(mongo_real):
    h = HiloCFO(
        user_id="u1",
        turnos=[{"rol": "user", "contenido": "q"}],
        ultimo_update_id=5,
        ultimo_envio="r",
        actualizado_at=now_utc(),
    )
    await repo.guardar_hilo(h)
    got = await repo.obtener_hilo("u1")
    assert got.ultimo_update_id == 5 and got.turnos[0]["contenido"] == "q"
