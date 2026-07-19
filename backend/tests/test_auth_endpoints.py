# backend/tests/test_auth_endpoints.py
"""Endpoints /api/v1/auth (PR-2): login/refresh/logout + cookie de refresh.

Se usa httpx.ASGITransport (async, mismo event loop) y se configuran los repos con
mongomock a mano (el lifespan real no corre en este transporte)."""

import httpx
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.main import create_app
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


@pytest_asyncio.fixture
async def api(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("COOKIE_SECURE", "False")
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()

    app = create_app()
    c = AsyncMongoMockClient()
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")
    await repository.create_user(
        User(
            email="a@roddos.com",
            password_hash=passwords.hash_password(PWD),
            rol=Role.admin,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def test_login_200_y_cookie_de_refresh(api):
    r = await api.post(
        "/api/v1/auth/login", json={"email": "a@roddos.com", "password": PWD}
    )
    assert r.status_code == 200
    assert r.json()["access_token"]
    set_cookie = " ".join(r.headers.get_list("set-cookie"))
    low = set_cookie.lower()
    assert "refresh=" in set_cookie
    assert "path=/api/v1/auth" in low
    assert "httponly" in low
    assert "samesite=strict" in low


async def test_login_401_password_mala(api):
    r = await api.post(
        "/api/v1/auth/login", json={"email": "a@roddos.com", "password": "mala"}
    )
    assert r.status_code == 401


async def test_refresh_por_cookie(api):
    await api.post(
        "/api/v1/auth/login", json={"email": "a@roddos.com", "password": PWD}
    )
    r = await api.post(
        "/api/v1/auth/refresh"
    )  # httpx reenvía la cookie (path coincide)
    assert r.status_code == 200
    assert r.json()["access_token"]


async def test_logout_revoca(api):
    login = await api.post(
        "/api/v1/auth/login", json={"email": "a@roddos.com", "password": PWD}
    )
    access = login.json()["access_token"]
    out = await api.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {access}"}
    )
    assert out.status_code == 200
    # tras logout, el refresh (cookie aún presente en el cliente) ya no sirve
    r = await api.post("/api/v1/auth/refresh")
    assert r.status_code == 401
