# backend/tests/configuracion/test_alerta_iva_config.py
import pytest
import pytest_asyncio
from app.configuracion.service import (
    escribir_alerta_iva_activa,
    escribir_alerta_iva_dias,
    leer_alerta_iva_activa,
    leer_alerta_iva_dias,
)
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=client["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield client


@pytest.mark.asyncio
async def test_defaults(db):
    assert await leer_alerta_iva_activa() is False
    assert await leer_alerta_iva_dias() == 30


@pytest.mark.asyncio
async def test_escribir_y_leer(db):
    await escribir_alerta_iva_activa(activa=True, usuario_id="a")
    await escribir_alerta_iva_dias(dias=15, usuario_id="a")
    assert await leer_alerta_iva_activa() is True
    assert await leer_alerta_iva_dias() == 15
