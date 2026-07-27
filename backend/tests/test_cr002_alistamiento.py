# backend/tests/test_cr002_alistamiento.py
"""CR-002 — Costos de alistamiento por moto vendida, desglosados por componente.

Reglas cubiertas:
  - `componentes_alistamiento` embebido en ParametrosProyeccion: PUT los guarda,
    GET los devuelve, y `costo_moto_nueva` = Σ de los ACTIVOS (autoridad server-side;
    el motor sigue recibiendo UN solo Decimal — motor.py intacto).
  - Componentes inactivos NO suman.
  - PARIDAD: con componentes cuya Σ == el costo previo, la proyección es bit a bit
    idéntica a la de antes del desglose (la migración no puede mover la caja).
  - Desactivar un componente MEJORA el piso (menos egreso por moto).
  - Sin componentes (None/[]), `costo_moto_nueva` explícito sigue mandando (compat).
"""

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

# El desglose real del CR-002: Σ = 692.005 EXACTO (el costo vigente en prod).
COMPONENTES_CR002 = [
    {"nombre": "Matrícula (trámite)", "valor": "227800", "activo": True, "orden": 1},
    {"nombre": "Instalación GPS", "valor": "83000", "activo": True, "orden": 2},
    {"nombre": "SOAT", "valor": "363300", "activo": True, "orden": 3},
    {"nombre": "Colchón/otros", "valor": "17905", "activo": True, "orden": 4},
]


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


async def _token(ac) -> dict:
    r = await ac.post(
        "/api/v1/auth/login", json={"email": "fin@roddos.com", "password": PWD}
    )
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _modelo_body():
    return {
        "nombre": "Raider",
        "costo_auteco": "5000000",
        "precio_venta_con_iva": "8000000",
        "cuota_inicial": "1000000",
        "cuota_semanal": "164900",
        "plazo_semanas": 78,
        "matricula": "500000",
        "participacion_mix": "1",
    }


def _params_body(componentes=None, costo="692005"):
    body = {
        "vigente_desde": "2026-07-01",
        "caja_inicial": "24000000",
        "caja_minima": "125000000",
        "motos_base": 50,
        "crec_pct_mensual": "0.01",
        "horizonte_meses": 12,
        "adelanto_auteco": "970000",
        "plazo_auteco_dias": 150,
        "base_auteco_dias": 90,
        "tasa_auteco": "0.016",
        "gastos_fijos": "125000000",
        "gps_moto": "33201",
        "costo_moto_nueva": costo,
        "deuda": "28527080",
        "tasa_deuda": "0.011",
        "mes_inicio_deuda": 2,
        "meses_deuda": 14,
        "pct_mora": "0.03",
        "pct_recuperacion": "0.40",
        "pct_default": "0.03",
        "pct_provision": "0.02",
    }
    if componentes is not None:
        body["componentes_alistamiento"] = componentes
    return body


async def _setup(ac, componentes=None, costo="692005"):
    h = await _token(ac)
    r1 = await ac.post("/api/v1/modelos-moto", json=_modelo_body(), headers=h)
    assert r1.status_code == 201
    r2 = await ac.put(
        "/api/v1/parametros-proyeccion",
        json=_params_body(componentes, costo),
        headers=h,
    )
    assert r2.status_code == 200, r2.text
    return h


@pytest.mark.asyncio
async def test_put_guarda_componentes_y_deriva_el_total(api):
    h = await _setup(api, componentes=COMPONENTES_CR002, costo="1")  # costo ignorado
    r = await api.get("/api/v1/parametros-proyeccion", headers=h)
    data = r.json()
    assert len(data["componentes_alistamiento"]) == 4
    # autoridad server-side: el total ES la suma de los activos, no lo enviado
    assert data["costo_moto_nueva"] == "692005"
    assert data["componentes_alistamiento"][0]["nombre"] == "Matrícula (trámite)"
    assert data["componentes_alistamiento"][0]["valor"] == "227800"


@pytest.mark.asyncio
async def test_componente_inactivo_no_suma(api):
    comps = [dict(c) for c in COMPONENTES_CR002]
    comps[3]["activo"] = False  # Colchón/otros $ 17.905 fuera
    h = await _setup(api, componentes=comps)
    r = await api.get("/api/v1/parametros-proyeccion", headers=h)
    assert r.json()["costo_moto_nueva"] == "674100"  # 692005 - 17905


@pytest.mark.asyncio
async def test_paridad_desglose_vs_costo_plano(api):
    """La migración no puede mover la caja: Σ componentes == costo previo →
    proyección bit a bit idéntica."""
    h = await _setup(api, componentes=None, costo="692005")
    plano = await api.get(
        "/api/v1/proyeccion?horizonte_meses=12&mes_inicio=2026-07", headers=h
    )
    r = await api.put(
        "/api/v1/parametros-proyeccion",
        json=_params_body(COMPONENTES_CR002),
        headers=h,
    )
    assert r.status_code == 200
    desglosado = await api.get(
        "/api/v1/proyeccion?horizonte_meses=12&mes_inicio=2026-07", headers=h
    )
    assert plano.json() == desglosado.json()


@pytest.mark.asyncio
async def test_desactivar_componente_mejora_el_piso(api):
    h = await _setup(api, componentes=COMPONENTES_CR002)
    base = await api.get(
        "/api/v1/proyeccion?horizonte_meses=12&mes_inicio=2026-07", headers=h
    )
    comps = [dict(c) for c in COMPONENTES_CR002]
    comps[3]["activo"] = False
    r = await api.put(
        "/api/v1/parametros-proyeccion", json=_params_body(comps), headers=h
    )
    assert r.status_code == 200
    mejor = await api.get(
        "/api/v1/proyeccion?horizonte_meses=12&mes_inicio=2026-07", headers=h
    )
    assert float(mejor.json()["piso_caja"]) > float(base.json()["piso_caja"])


@pytest.mark.asyncio
async def test_sin_componentes_manda_el_costo_plano(api):
    h = await _setup(api, componentes=None, costo="700000")
    r = await api.get("/api/v1/parametros-proyeccion", headers=h)
    assert r.json()["costo_moto_nueva"] == "700000"
    assert r.json()["componentes_alistamiento"] is None


@pytest.mark.asyncio
async def test_componente_con_valor_invalido_es_422(api):
    comps = [dict(COMPONENTES_CR002[0], valor="no-numero")]
    h = await _token(api)
    await api.post("/api/v1/modelos-moto", json=_modelo_body(), headers=h)
    r = await api.put(
        "/api/v1/parametros-proyeccion", json=_params_body(comps), headers=h
    )
    assert r.status_code == 422
