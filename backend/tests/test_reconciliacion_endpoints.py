# backend/tests/test_reconciliacion_endpoints.py
"""D2 §4 end-to-end: una factura registrada reconcilia la proyección vigente — la
ventana queda marcada y el interés de obligaciones aparece separado."""

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
_Q = "horizonte_meses=12&mes_inicio=2026-07"


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
    await repository.create_user(
        User(
            email="fin@roddos.com",
            password_hash=passwords.hash_password(PWD),
            rol=Role.financiero,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _setup(ac) -> dict:
    r = await ac.post(
        "/api/v1/auth/login", json={"email": "fin@roddos.com", "password": PWD}
    )
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    modelo = {
        "nombre": "Raider",
        "costo_auteco": "5000000",
        "precio_venta_con_iva": "8000000",
        "cuota_inicial": "1000000",
        "cuota_semanal": "164900",
        "plazo_semanas": 78,
        "matricula": "500000",
        "participacion_mix": "1",
    }
    await ac.post("/api/v1/modelos-moto", json=modelo, headers=h)
    params = {
        "vigente_desde": "2026-07-01",
        "caja_inicial": "24000000",
        "caja_minima": "125000000",
        "motos_base": 50,
        "crec_pct_mensual": "0.01",
        "horizonte_meses": 12,
        "adelanto_auteco": "0",
        "plazo_auteco_dias": 150,
        "base_auteco_dias": 90,
        "tasa_auteco": "0.016",
        "gastos_fijos": "125000000",
        "gps_moto": "33201",
        "costo_moto_nueva": "692005",
        "deuda": "28527080",
        "tasa_deuda": "0.011",
        "mes_inicio_deuda": 2,
        "meses_deuda": 14,
        "pct_mora": "0.03",
        "pct_recuperacion": "0.40",
        "pct_default": "0.03",
        "pct_provision": "0.02",
    }
    await ac.put("/api/v1/parametros-proyeccion", json=params, headers=h)
    return h


@pytest.mark.asyncio
async def test_sin_facturas_proyeccion_no_marca_ventana(api):
    h = await _setup(api)
    r = await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)
    assert r.status_code == 200
    assert r.json()["ventana_reconciliada"] is None
    assert r.json()["interes_obligaciones"] == {}


@pytest.mark.asyncio
async def test_una_factura_reconcilia_la_proyeccion(api):
    h = await _setup(api)
    base = await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)

    oid = (
        await api.post(
            "/api/v1/obligaciones",
            json={
                "nombre": "Auteco",
                "acreedor": "Auteco S.A.S.",
                "naturaleza": "facturacion",
                "plazo_base_dias": 90,
                "plazo_max_dias": 150,
                "tasa_excedente_mensual": "0.016",
            },
            headers=h,
        )
    ).json()["id"]
    reg = await api.post(
        f"/api/v1/obligaciones/{oid}/facturas",
        json={
            "fecha_factura": "2026-08-15",
            "valor": "180000000",
            "plazo_elegido_dias": 150,
        },
        headers=h,
    )
    assert reg.status_code == 201

    con = await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)
    data = con.json()
    # el pago real de la factura cae en 2027-01 (15-ago + 5 meses)
    assert data["ventana_reconciliada"] == ["2027-01", "2027-01"]
    # el interés de la obligación aparece SEPARADO: 180 M × 1,6% × 2 = 5,76 M
    assert data["interes_obligaciones"]["2027-01"] == "5760000.00"
    # la serie cambió respecto a la base (se reconcilió)
    assert data["meses"] != base.json()["meses"]
