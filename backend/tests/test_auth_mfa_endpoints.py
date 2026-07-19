# backend/tests/test_auth_mfa_endpoints.py
"""Endpoints MFA /api/v1/auth/mfa/* (PR-2): enrolamiento, login 2 pasos, step-up."""

import httpx
import pyotp
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.main import create_app
from cryptography.fernet import Fernet
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


@pytest_asyncio.fixture
async def api(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("MFA_ENC_KEY", Fernet.generate_key().decode())
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


async def _login(api) -> str:
    r = await api.post(
        "/api/v1/auth/login", json={"email": "a@roddos.com", "password": PWD}
    )
    return r.json()["access_token"]


async def test_enrolamiento_y_login_2_pasos(api):
    access = await _login(api)
    h = {"Authorization": f"Bearer {access}"}

    # setup (protegido por contraseña)
    r = await api.post("/api/v1/auth/mfa/setup", json={"password": PWD}, headers=h)
    assert r.status_code == 200
    secret = r.json()["secret"]
    assert r.json()["otpauth_uri"].startswith("otpauth://")

    # activate con TOTP → códigos de respaldo
    r = await api.post(
        "/api/v1/auth/mfa/activate",
        json={"code": pyotp.TOTP(secret).now()},
        headers=h,
    )
    assert r.status_code == 200
    assert len(r.json()["backup_codes"]) == 10

    # ahora el login pide 2º factor
    r = await api.post(
        "/api/v1/auth/login", json={"email": "a@roddos.com", "password": PWD}
    )
    assert r.status_code == 200
    assert r.json()["mfa_required"] is True
    mfa_token = r.json()["mfa_token"]
    assert "access_token" not in r.json()

    # verify → tokens + cookie de refresh
    r = await api.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": pyotp.TOTP(secret).now()},
    )
    assert r.status_code == 200
    assert r.json()["access_token"]
    assert "refresh=" in " ".join(r.headers.get_list("set-cookie"))


async def test_setup_password_malo_401(api):
    access = await _login(api)
    r = await api.post(
        "/api/v1/auth/mfa/setup",
        json={"password": "incorrecta"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 401


async def test_step_up_bloquea_sin_mfa_reciente(api):
    # Un access SIN mfa_at (usuario sin MFA) no puede hacer /mfa/reset.
    access = await _login(api)
    r = await api.post(
        "/api/v1/auth/mfa/reset", headers={"Authorization": f"Bearer {access}"}
    )
    assert r.status_code == 403


async def test_step_up_ok_tras_verify(api):
    # Enrolar, hacer login+verify → el access trae mfa_at reciente → /mfa/reset pasa.
    access = await _login(api)
    h = {"Authorization": f"Bearer {access}"}
    r = await api.post("/api/v1/auth/mfa/setup", json={"password": PWD}, headers=h)
    secret = r.json()["secret"]
    await api.post(
        "/api/v1/auth/mfa/activate",
        json={"code": pyotp.TOTP(secret).now()},
        headers=h,
    )
    r = await api.post(
        "/api/v1/auth/login", json={"email": "a@roddos.com", "password": PWD}
    )
    mfa_token = r.json()["mfa_token"]
    r = await api.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": pyotp.TOTP(secret).now()},
    )
    fresh = r.json()["access_token"]
    r = await api.post(
        "/api/v1/auth/mfa/reset", headers={"Authorization": f"Bearer {fresh}"}
    )
    assert r.status_code == 200
