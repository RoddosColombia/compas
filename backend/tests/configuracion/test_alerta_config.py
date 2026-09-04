import pytest
import pytest_asyncio
from app.configuracion.service import (
    escribir_alerta_caja_activa,
    escribir_alerta_horizonte_meses,
    leer_alerta_caja_activa,
    leer_alerta_horizonte_meses,
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
async def test_defaults_sin_config(db):
    assert await leer_alerta_caja_activa() is False
    assert await leer_alerta_horizonte_meses() == 6


@pytest.mark.asyncio
async def test_escribir_y_leer_vigencia(db):
    await escribir_alerta_caja_activa(activa=True, usuario_id="andres")
    await escribir_alerta_horizonte_meses(meses=9, usuario_id="andres")
    assert await leer_alerta_caja_activa() is True
    assert await leer_alerta_horizonte_meses() == 9


@pytest.mark.asyncio
async def test_horizonte_invalido_cae_al_default(db):
    await escribir_alerta_horizonte_meses(meses=9, usuario_id="andres")
    # una fila posterior con dato malo no debe romper: el resolver valida > 0 int
    from app.domain.configuracion import ClaveConfig, Configuracion

    await Configuracion(
        clave=ClaveConfig.ALERTA_CAJA_HORIZONTE_MESES,
        valor_json={"meses": 0},
        vigente_desde="2999-01-01",
    ).insert()
    assert await leer_alerta_horizonte_meses() == 6
