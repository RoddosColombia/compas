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
    # unicidad (B-3), mitad telegram_id: mismo telegram_id, distinto user_id → choca
    # por telegram_id_unico.
    with pytest.raises(DuplicateKeyError):
        await repo.crear_vinculo(
            VinculoTelegram(
                telegram_id=111, user_id="u2", creado_por="admin", creado_at=now_utc()
            )
        )
    # unicidad (B-3), mitad user_id: mismo user_id="u1", distinto telegram_id → esta
    # es la única prueba que aísla si user_id_unico se aplica de verdad (sin ella, si
    # el índice se cayera en silencio, el bloque anterior seguiría en verde igual).
    with pytest.raises(DuplicateKeyError):
        await repo.crear_vinculo(
            VinculoTelegram(
                telegram_id=222, user_id="u1", creado_por="admin", creado_at=now_utc()
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


@pytest.mark.requires_real_mongo
@pytest.mark.asyncio
async def test_hilo_guardar_dos_veces_actualiza_no_duplica(mongo_real):
    """Rama UPDATE de guardar_hilo: la 2a llamada con el mismo user_id sobre-escribe
    el hilo existente (no revienta, no crea un segundo documento)."""
    await repo.guardar_hilo(
        HiloCFO(
            user_id="u1",
            turnos=[{"rol": "user", "contenido": "q1"}],
            ultimo_update_id=5,
            ultimo_envio="r1",
            actualizado_at=now_utc(),
        )
    )
    await repo.guardar_hilo(
        HiloCFO(
            user_id="u1",
            turnos=[
                {"rol": "user", "contenido": "q1"},
                {"rol": "asst", "contenido": "r1"},
            ],
            ultimo_update_id=6,
            ultimo_envio="r2",
            actualizado_at=now_utc(),
        )
    )
    got = await repo.obtener_hilo("u1")
    assert got.ultimo_update_id == 6
    assert got.ultimo_envio == "r2"
    assert len(got.turnos) == 2
    assert await HiloCFO.find(HiloCFO.user_id == "u1").count() == 1
