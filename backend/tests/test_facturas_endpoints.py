# backend/tests/test_facturas_endpoints.py
"""IVA C11 (PR-2a) — /api/v1/facturas (carga de facturas + liquidación cuatrimestral).

RBAC: GET con `dashboard:leer` (todos); mutaciones con `iva:gestionar` = {financiero,
admin} → consulta/directivo reciben 403. Montos como string (regla 1). La liquidación
se calcula en el backend y se sirve por GET /facturas/liquidacion (lo consume la vista).
"""

import httpx
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
        ("admin@roddos.com", Role.admin),
    ]:
        await repository.create_user(
            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
        )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, c
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _token(ac, email="fin@roddos.com") -> dict:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _compra(**kw) -> dict:
    body = {
        "tipo": "compra",
        "origen": "auteco",
        "numero": "FC-001",
        "tercero_nombre": "Auteco S.A.S.",
        "tercero_nit": "860024781",
        "fecha": "2026-02-10",
        "base_gravable": "1000000",
        "tarifa_iva": "0.19",
        "deducible": True,
    }
    body.update(kw)
    return body


async def test_crear_factura_201_calcula_iva(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post("/api/v1/facturas", json=_compra(), headers=h)
    assert r.status_code == 201
    data = r.json()
    assert data["iva_valor"] == "190000.00"
    assert data["total"] == "1190000.00"
    assert data["periodo"] == "2026-C1"  # derivado de la fecha (cuatrimestral default)


async def test_crear_factura_consulta_es_403(api):
    ac, _ = api
    h = await _token(ac, "consulta@roddos.com")
    r = await ac.post("/api/v1/facturas", json=_compra(), headers=h)
    assert r.status_code == 403


async def test_crear_factura_duplicada_409(api):
    ac, _ = api
    h = await _token(ac)
    r1 = await ac.post("/api/v1/facturas", json=_compra(), headers=h)
    assert r1.status_code == 201
    r = await ac.post("/api/v1/facturas", json=_compra(), headers=h)
    assert r.status_code == 409


async def test_listar_y_anular(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post("/api/v1/facturas", json=_compra(), headers=h)
    fid = r.json()["id"]
    # anular
    ra = await ac.post(f"/api/v1/facturas/{fid}/anular", headers=h)
    assert ra.status_code == 200
    assert ra.json()["activo"] is False
    # listar activas → vacío
    rl = await ac.get("/api/v1/facturas?activo=true", headers=h)
    assert rl.status_code == 200
    assert rl.json() == []


async def test_liquidacion_cuatrimestral(api):
    ac, _ = api
    h = await _token(ac)
    # venta C1: genera 190000
    await ac.post(
        "/api/v1/facturas",
        json={
            "tipo": "venta",
            "origen": "moto",
            "numero": "FV-1",
            "tercero_nombre": "Cliente",
            "tercero_nit": "79",
            "fecha": "2026-02-01",
            "base_gravable": "1000000",
            "tarifa_iva": "0.19",
            "deducible": False,
        },
        headers=h,
    )
    # compra deducible C1: descontable 95000 → neto 95000
    await ac.post(
        "/api/v1/facturas",
        json=_compra(numero="FC-9", base_gravable="500000"),
        headers=h,
    )
    r = await ac.get("/api/v1/facturas/liquidacion", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["periodicidad"] == "cuatrimestral"
    periodos = data["periodos"]
    assert len(periodos) == 1
    c = periodos[0]
    assert c["anio"] == 2026
    assert c["periodo"] == 1
    assert c["etiqueta"] == "2026-C1"
    assert c["generado"] == "190000.00"
    assert c["descontable"] == "95000.00"
    assert c["neto_a_pagar"] == "95000.00"
