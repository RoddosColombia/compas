# backend/tests/conftest.py
#
# ==========================================================================
#  ESTRATEGIA DE BASE DE DATOS EN TESTS  (Sprint 0, Sesión 1)
# ==========================================================================
# En esta sesión usamos mongomock-motor (AsyncMongoMockClient) para los
# tests que tocan Mongo (readiness /health/ready, init_beanie). Es rápido y
# no requiere un mongod local.
#
#  ⚠️  LÍMITE DELIBERADO — mongomock NO es suficiente a partir del Sprint 1:
#
#   • Sprint 1 — Deduplicación: el índice ÚNICO PARCIAL
#       (banco, id_banco) con partialFilterExpression {id_banco:{$type:'string'}}
#     (regla 5 de CLAUDE.md / Spec §2.3) NO está soportado por mongomock:
#     no valida unicidad parcial ni lanza DuplicateKeyError como el motor real.
#
#   • Sprint 4 — Transacciones multi-documento: las transacciones de MongoDB
#     (aprobación de presupuesto, finalización de carga, cierre de mes;
#     regla 8 / Spec §2.2.6) NO existen en mongomock (no hay sessions con
#     commit/abort ni TransientTransactionError).
#
#  Por eso, TODO test que dependa de esos dos comportamientos DEBE marcarse
#  con @pytest.mark.requires_real_mongo y correr contra un Mongo REAL
#  (mongod local o contenedor; se configurará en el CI del Sprint 1).
#  Estos tests se saltan por defecto y solo corren con:  pytest -m requires_real_mongo
#  (habiendo exportado COMPAS_TEST_MONGO_URI apuntando a un Mongo real).
# ==========================================================================

import os

import pytest
from app.deps import get_mongo_client
from app.main import create_app
from mongomock_motor import AsyncMongoMockClient


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_real_mongo: el test necesita un Mongo REAL (índice único "
        "parcial del Sprint 1 y/o transacciones multi-documento del Sprint 4). "
        "mongomock NO los soporta. Correr con: pytest -m requires_real_mongo",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Salta por defecto los tests que exigen Mongo real, salvo que se pidan
    explícitamente con `-m requires_real_mongo`."""
    marker_expr = config.getoption("-m")
    if "requires_real_mongo" in marker_expr:
        return  # el usuario los pidió explícitamente
    skip = pytest.mark.skip(
        reason="requiere Mongo real; correr con: pytest -m requires_real_mongo"
    )
    for item in items:
        if "requires_real_mongo" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Limpia el cache de get_settings antes y después de cada test — evita que un
    test que cambia env vars contamine a otro (Kimi Baja)."""
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def mock_mongo_client() -> AsyncMongoMockClient:
    """Cliente Mongo simulado para tests de esta sesión."""
    return AsyncMongoMockClient()


@pytest.fixture
def app(mock_mongo_client: AsyncMongoMockClient):
    """App FastAPI con el cliente Mongo real reemplazado por el mock.

    RUN_SCHEDULER queda en false (default): el servicio web NUNCA arranca el
    scheduler (regla 6 de CLAUDE.md)."""
    from app.config import get_settings

    os.environ.pop("RUN_SCHEDULER", None)
    get_settings.cache_clear()
    application = create_app()
    application.dependency_overrides[get_mongo_client] = lambda: mock_mongo_client
    return application
