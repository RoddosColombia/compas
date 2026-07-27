# backend/tests/test_metas_ingreso.py
"""Metas de ingreso (D2 §6, CR-D2) — CRUD auditado, informativo (no toca el motor)."""

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.main import create_app
from beanie import init_beanie
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
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")
    for correo, rol in [
        ("consulta@roddos.com", Role.consulta),
        ("fin@roddos.com", Role.financiero),
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


async def _token(ac, email="fin@roddos.com") -> dict:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_crear_listar_meta(api):
    h = await _token(api)
    r = await api.post(
        "/api/v1/metas-ingreso",
        json={
            "mes": "2026-09",
            "valor": "300000000",
            "lineas": [{"nombre": "Motos nuevas", "valor": "250000000"}],
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["mes"] == "2026-09"
    # sin MesControl del mes, el real es null (aún no se abrió el ciclo)
    assert r.json()["real_ejecutado"] is None
    lst = await api.get("/api/v1/metas-ingreso", headers=h)
    assert [m["mes"] for m in lst.json()["items"]] == ["2026-09"]


@pytest.mark.asyncio
async def test_una_meta_por_mes(api):
    h = await _token(api)
    base = {"mes": "2026-09", "valor": "1", "lineas": []}
    assert (
        await api.post("/api/v1/metas-ingreso", json=base, headers=h)
    ).status_code == 201
    r = await api.post("/api/v1/metas-ingreso", json=base, headers=h)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_editar_y_eliminar(api):
    h = await _token(api)
    mid = (
        await api.post(
            "/api/v1/metas-ingreso",
            json={"mes": "2026-09", "valor": "100", "lineas": []},
            headers=h,
        )
    ).json()["id"]
    r = await api.patch(
        f"/api/v1/metas-ingreso/{mid}", json={"valor": "200"}, headers=h
    )
    assert r.status_code == 200
    assert r.json()["valor"] == "200.00"
    assert (
        await api.delete(f"/api/v1/metas-ingreso/{mid}", headers=h)
    ).status_code == 204
    assert (await api.get("/api/v1/metas-ingreso", headers=h)).json()["items"] == []


@pytest.mark.asyncio
async def test_mes_mal_formado_422(api):
    h = await _token(api)
    r = await api.post(
        "/api/v1/metas-ingreso",
        json={"mes": "2026/09", "valor": "1", "lineas": []},
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_rbac(api):
    h = await _token(api, "consulta@roddos.com")
    r = await api.post(
        "/api/v1/metas-ingreso",
        json={"mes": "2026-09", "valor": "1", "lineas": []},
        headers=h,
    )
    assert r.status_code == 403
    assert (await api.get("/api/v1/metas-ingreso", headers=h)).status_code == 200
