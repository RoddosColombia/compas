# backend/tests/test_rbac_endpoints.py
"""RBAC extremo a extremo (PR-3): routers solo-test que ejercen require_permission
y require_role; negativos por rol (DoD #1, incl. export de Consulta denegado) y
GET /auth/capabilities."""

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.deps import require_permission, require_role
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.main import create_app
from fastapi import APIRouter, Depends
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


def _test_router() -> APIRouter:
    tr = APIRouter()

    @tr.get("/_test/export")
    async def _export(_: User = Depends(require_permission("export:reportes"))):
        return {"ok": True}

    @tr.get("/_test/solo-admin")
    async def _admin(_: User = Depends(require_role(Role.admin))):
        return {"ok": True}

    return tr


@pytest_asyncio.fixture
async def api(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("COOKIE_SECURE", "False")
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()

    app = create_app()
    app.include_router(_test_router(), prefix="/api/v1")
    c = AsyncMongoMockClient()
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")
    for correo, rol in [
        ("consulta@roddos.com", Role.consulta),
        ("fin@roddos.com", Role.financiero),
        ("admin@roddos.com", Role.admin),
    ]:
        await repository.create_user(
            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
        )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _token(ac, email) -> str:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.mark.parametrize(
    "email,esperado",
    [("consulta@roddos.com", 403), ("fin@roddos.com", 200), ("admin@roddos.com", 200)],
)
async def test_export_por_rol(api, email, esperado):
    # DoD #1: Consulta NO exporta; Financiero/Admin sí.
    tok = await _token(api, email)
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.get("/api/v1/_test/export", headers=h)
    assert r.status_code == esperado


@pytest.mark.parametrize(
    "email,esperado",
    [("consulta@roddos.com", 403), ("fin@roddos.com", 403), ("admin@roddos.com", 200)],
)
async def test_require_role_admin(api, email, esperado):
    tok = await _token(api, email)
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.get("/api/v1/_test/solo-admin", headers=h)
    assert r.status_code == esperado


async def test_sin_token_es_401(api):
    r = await api.get("/api/v1/_test/export")
    assert r.status_code == 401


async def test_capabilities_endpoint(api):
    tok = await _token(api, "consulta@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.get("/api/v1/auth/capabilities", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["rol"] == "consulta"
    assert body["capabilities"] == ["dashboard:leer"]
