# backend/tests/test_proyeccion_version_endpoints.py
"""RF-F2 — endpoints de la serie versionada (`GET /proyeccion/version` y
`GET /proyeccion/version/diff`). RBAC `dashboard:leer` (todos leen)."""

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.rubro import Rubro
from app.main import create_app
from app.proyeccion.versionado import _persistir_version
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"
BASE = "/api/v1/proyeccion"


@pytest_asyncio.fixture
async def api(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("COOKIE_SECURE", "False")
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()

    app = create_app()
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")
    for correo, rol in [("consulta@roddos.com", Role.consulta)]:
        await repository.create_user(
            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
        )
    await Rubro(
        grupo="otros", nombre="Por clasificar", orden=97, es_sistema=True
    ).insert()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _token(ac, email="consulta@roddos.com") -> dict:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _serie(piso="100000000", mes="2027-05"):
    return {
        "escenario": "base",
        "caja_minima": "125000000",
        "piso_caja": piso,
        "mes_mas_ajustado": mes,
        "horizonte_meses": 3,
        "meses": [{"mes": "2026-05", "caja": "24000000"}],
    }


# ─────────────────────── GET /proyeccion/version ───────────────────────


@pytest.mark.asyncio
async def test_version_sin_ninguna_dice_disponible_false(api):
    h = await _token(api)
    r = await api.get(f"{BASE}/version", headers=h)
    assert r.status_code == 200
    assert r.json() == {"disponible": False}


@pytest.mark.asyncio
async def test_version_devuelve_la_vigente(api):
    h = await _token(api)
    await _persistir_version(
        serie=_serie(piso="80000000"),
        valles=[],
        mes_aprobado="2026-07-01",
        usuario_id="u1",
    )
    v2 = await _persistir_version(
        serie=_serie(piso="120000000"),
        valles=[{"mes": "2027-05"}],
        mes_aprobado="2026-08-01",
        usuario_id="u1",
    )
    r = await api.get(f"{BASE}/version", headers=h)
    body = r.json()
    assert body["disponible"] is True
    assert body["version"] == v2.version
    assert body["piso_caja"] == "120000000"
    assert body["serie"]["meses"][0]["caja"] == "24000000"  # serie fiel


@pytest.mark.asyncio
async def test_version_exige_autenticacion(api):
    r = await api.get(f"{BASE}/version")
    assert r.status_code == 401
