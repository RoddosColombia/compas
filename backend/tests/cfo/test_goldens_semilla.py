import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield c


@pytest.mark.asyncio
async def test_sembrar_idempotente(db):
    from app.cfo.goldens.modelo import CFOGolden
    from app.cfo.goldens.semilla import sembrar_semilla

    ins1, dup1 = await sembrar_semilla()
    ins2, dup2 = await sembrar_semilla()  # segunda vez no duplica
    assert ins1 >= 1 and dup1 == 0
    assert ins2 == 0 and dup2 == ins1
    # todos los conceptos sembrados existen
    assert await CFOGolden.find_all().count() == ins1
