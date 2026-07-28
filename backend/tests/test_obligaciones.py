# backend/tests/test_obligaciones.py
"""CRUD de Obligacion + FacturaObligacion (D2 §2, CR-D2) — auditado, saga O1."""

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
        yield ac, c
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _token(ac, email="fin@roddos.com") -> dict:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _facturacion(**over):
    body = {
        "nombre": "Auteco",
        "acreedor": "Auteco S.A.S.",
        "naturaleza": "facturacion",
        "plazo_base_dias": 90,
        "plazo_max_dias": 150,
        "tasa_excedente_mensual": "0.016",
    }
    body.update(over)
    return body


def _cuotas(**over):
    body = {
        "nombre": "Crédito inversores",
        "acreedor": "Inversor X",
        "naturaleza": "cuotas",
        "monto_total": "28527080",
        "n_cuotas": 14,
        "periodicidad_meses": 1,
        "tasa_mensual": "0.011",
        "fecha_inicio": "2026-09-01",
        "meses_gracia": 0,
    }
    body.update(over)
    return body


@pytest.mark.asyncio
async def test_crear_facturacion_y_listar(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post("/api/v1/obligaciones", json=_facturacion(), headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["naturaleza"] == "facturacion"
    assert r.json()["tasa_excedente_mensual"] == "0.016"  # sin cuantizar
    lst = await ac.get("/api/v1/obligaciones", headers=h)
    assert [o["nombre"] for o in lst.json()["items"]] == ["Auteco"]


@pytest.mark.asyncio
async def test_crear_cuotas(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post("/api/v1/obligaciones", json=_cuotas(), headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["n_cuotas"] == 14
    assert r.json()["tasa_mensual"] == "0.011"


@pytest.mark.asyncio
async def test_crear_cuotas_incompleta_es_422(api):
    ac, _ = api
    h = await _token(ac)
    body = _cuotas()
    del body["monto_total"]  # falta un campo requerido de la naturaleza
    r = await ac.post("/api/v1/obligaciones", json=body, headers=h)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_facturacion_plazo_max_menor_que_base_es_422(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
        "/api/v1/obligaciones",
        json=_facturacion(plazo_base_dias=150, plazo_max_dias=90),
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_crear_emite_evento(api):
    ac, c = api
    h = await _token(ac)
    await ac.post("/api/v1/obligaciones", json=_facturacion(), headers=h)
    ev = await c["compas_test"]["audit_log"].find_one({"evento": "obligacion.creada"})
    assert ev is not None


@pytest.mark.asyncio
async def test_editar_y_eliminar(api):
    ac, _ = api
    h = await _token(ac)
    oid = (
        await ac.post("/api/v1/obligaciones", json=_facturacion(), headers=h)
    ).json()["id"]
    r = await ac.patch(
        f"/api/v1/obligaciones/{oid}", json={"acreedor": "Auteco Colombia"}, headers=h
    )
    assert r.status_code == 200
    assert r.json()["acreedor"] == "Auteco Colombia"
    d = await ac.delete(f"/api/v1/obligaciones/{oid}", headers=h)
    assert d.status_code == 204
    assert (await ac.get("/api/v1/obligaciones?activo=true", headers=h)).json()[
        "items"
    ] == []


@pytest.mark.asyncio
async def test_registrar_factura_valida_plazo(api):
    ac, _ = api
    h = await _token(ac)
    oid = (
        await ac.post("/api/v1/obligaciones", json=_facturacion(), headers=h)
    ).json()["id"]
    # plazo dentro de rango
    ok = await ac.post(
        f"/api/v1/obligaciones/{oid}/facturas",
        json={
            "fecha_factura": "2026-08-15",
            "valor": "180000000",
            "plazo_elegido_dias": 150,
        },
        headers=h,
    )
    assert ok.status_code == 201, ok.text
    # plazo fuera de rango => 422
    mal = await ac.post(
        f"/api/v1/obligaciones/{oid}/facturas",
        json={"fecha_factura": "2026-08-15", "valor": "1", "plazo_elegido_dias": 200},
        headers=h,
    )
    assert mal.status_code == 422
    # plazo = base (sin excedente) => OK
    base = await ac.post(
        f"/api/v1/obligaciones/{oid}/facturas",
        json={"fecha_factura": "2026-08-15", "valor": "1", "plazo_elegido_dias": 90},
        headers=h,
    )
    assert base.status_code == 201


@pytest.mark.asyncio
async def test_no_se_registran_facturas_en_cuotas(api):
    ac, _ = api
    h = await _token(ac)
    oid = (await ac.post("/api/v1/obligaciones", json=_cuotas(), headers=h)).json()[
        "id"
    ]
    r = await ac.post(
        f"/api/v1/obligaciones/{oid}/facturas",
        json={"fecha_factura": "2026-08-15", "valor": "1", "plazo_elegido_dias": 90},
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_anular_factura(api):
    ac, _ = api
    h = await _token(ac)
    oid = (
        await ac.post("/api/v1/obligaciones", json=_facturacion(), headers=h)
    ).json()["id"]
    fid = (
        await ac.post(
            f"/api/v1/obligaciones/{oid}/facturas",
            json={
                "fecha_factura": "2026-08-15",
                "valor": "1",
                "plazo_elegido_dias": 90,
            },
            headers=h,
        )
    ).json()["id"]
    d = await ac.delete(f"/api/v1/obligaciones/facturas/{fid}", headers=h)
    assert d.status_code == 204
    assert (await ac.get(f"/api/v1/obligaciones/{oid}/facturas", headers=h)).json()[
        "items"
    ] == []


@pytest.mark.asyncio
async def test_rbac_consulta_no_crea(api):
    ac, _ = api
    h = await _token(ac, "consulta@roddos.com")
    r = await ac.post("/api/v1/obligaciones", json=_facturacion(), headers=h)
    assert r.status_code == 403
    assert (await ac.get("/api/v1/obligaciones", headers=h)).status_code == 200
