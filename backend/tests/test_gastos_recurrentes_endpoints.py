# backend/tests/test_gastos_recurrentes_endpoints.py
"""/api/v1/gastos-recurrentes — RBAC + contrato de API (CEO 2026-07-26).

Cubre: RBAC `rubros:gestionar` en mutaciones (consulta → 403); montos como STRING
(regla 1: un number en `monto` → 422); GET devuelve items + resumen con el grupo del
rubro apuntado (el cruce con el Plan de Cuentas).
"""

import httpx
import pytest_asyncio
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.rubro import Rubro
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
    for correo, rol in [
        ("consulta@roddos.com", Role.consulta),
        ("fin@roddos.com", Role.financiero),
    ]:
        await repository.create_user(
            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
        )
    rubro = await Rubro(
        grupo="operacion", nombre="Arriendos", codigo="2010", orden=1
    ).insert()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, str(rubro.id)
    repository.reset_auth()
    get_settings.cache_clear()


async def _token(ac, email="fin@roddos.com") -> dict:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_crear_y_listar(api):
    ac, rubro_id = api
    h = await _token(ac)
    r = await ac.post(
        "/api/v1/gastos-recurrentes",
        json={
            "rubro_id": rubro_id,
            "descripcion": "Arriendo oficina",
            "monto": "3614953",
            "frecuencia": "mensual",
            "dia_pago": 5,
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["monto"] == "3614953.00"  # string (regla 1)
    assert body["monto_mensual"] == "3614953.00"
    assert body["rubro_grupo"] == "operacion"

    r = await ac.get("/api/v1/gastos-recurrentes", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 1
    assert data["resumen"]["total"] == "3614953.00"
    assert data["resumen"]["por_grupo"]["operacion"] == "3614953.00"


async def test_monto_number_rechazado(api):
    ac, rubro_id = api
    h = await _token(ac)
    r = await ac.post(
        "/api/v1/gastos-recurrentes",
        json={"rubro_id": rubro_id, "descripcion": "x", "monto": 3614953},
        headers=h,
    )
    assert r.status_code == 422  # number → strict lo rechaza (regla 1)


async def test_consulta_no_puede_crear(api):
    ac, rubro_id = api
    h = await _token(ac, "consulta@roddos.com")
    r = await ac.post(
        "/api/v1/gastos-recurrentes",
        json={"rubro_id": rubro_id, "descripcion": "x", "monto": "1000"},
        headers=h,
    )
    assert r.status_code == 403
