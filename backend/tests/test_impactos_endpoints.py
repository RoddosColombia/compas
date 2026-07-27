# backend/tests/test_impactos_endpoints.py
"""D1 §2 — POST /api/v1/proyeccion/impactos y GET /api/v1/proyeccion/valles.

Compute-only (SIMULAR NUNCA ESCRIBE): un impacto no toca la vigencia ni la proyección.
Regla de oro: impactos con lista vacía == la proyección base, bit a bit.
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


def _params():
    return {
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


async def _setup(ac):
    h = await _token(ac)
    assert (
        await ac.post("/api/v1/modelos-moto", json=_modelo_body(), headers=h)
    ).status_code == 201
    assert (
        await ac.put("/api/v1/parametros-proyeccion", json=_params(), headers=h)
    ).status_code == 200
    return h


_Q = "horizonte_meses=12&mes_inicio=2026-07"


@pytest.mark.asyncio
async def test_impactos_vacio_es_la_base_bit_a_bit(api):
    h = await _setup(api)
    vigente = await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)
    r = await api.post(
        f"/api/v1/proyeccion/impactos?{_Q}", json={"ajustes": []}, headers=h
    )
    assert r.status_code == 200
    data = r.json()
    assert data["base"] == vigente.json()  # base == GET /proyeccion
    assert data["ajustada"] == data["base"]  # sin ajustes: ajustada == base
    assert all(m == "0.00" for m in data["delta_por_mes"])


@pytest.mark.asyncio
async def test_impacto_gasto_absoluto_empeora_el_piso(api):
    h = await _setup(api)
    r = await api.post(
        f"/api/v1/proyeccion/impactos?{_Q}",
        json={
            "ajustes": [
                {
                    "nombre": "Arriendo sede nueva",
                    "naturaleza": "gasto",
                    "modo": "absoluto",
                    "valor": "3000000",
                    "mes_inicio": "2026-09",
                    "mes_fin": None,
                }
            ]
        },
        headers=h,
    )
    assert r.status_code == 200
    data = r.json()
    assert float(data["ajustada"]["piso_caja"]) < float(data["base"]["piso_caja"])


@pytest.mark.asyncio
async def test_impactos_no_persiste_nada(api):
    h = await _setup(api)
    antes = await api.get("/api/v1/parametros-proyeccion", headers=h)
    r = await api.post(
        f"/api/v1/proyeccion/impactos?{_Q}",
        json={
            "ajustes": [
                {
                    "nombre": "x",
                    "naturaleza": "gasto",
                    "modo": "absoluto",
                    "valor": "9000000",
                    "mes_inicio": "2026-08",
                }
            ]
        },
        headers=h,
    )
    assert r.status_code == 200
    despues = await api.get("/api/v1/parametros-proyeccion", headers=h)
    assert antes.json() == despues.json()  # simular NUNCA escribe


@pytest.mark.asyncio
async def test_impactos_rbac_mismo_permiso_que_preview(api):
    await _setup(api)
    h = await _token(api, "consulta@roddos.com")
    r = await api.post("/api/v1/proyeccion/impactos", json={"ajustes": []}, headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_impactos_valor_no_decimal_es_422(api):
    h = await _setup(api)
    r = await api.post(
        "/api/v1/proyeccion/impactos",
        json={
            "ajustes": [
                {
                    "nombre": "x",
                    "naturaleza": "gasto",
                    "modo": "absoluto",
                    "valor": "no-numero",
                    "mes_inicio": "2026-08",
                }
            ]
        },
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_impactos_mes_mal_formado_es_422(api):
    h = await _setup(api)
    r = await api.post(
        "/api/v1/proyeccion/impactos",
        json={
            "ajustes": [
                {
                    "nombre": "x",
                    "naturaleza": "gasto",
                    "modo": "absoluto",
                    "valor": "1000",
                    "mes_inicio": "2026/08",
                }
            ]
        },
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_valles_endpoint_devuelve_lista_con_causas(api):
    h = await _setup(api)
    r = await api.get(f"/api/v1/proyeccion/valles?{_Q}", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert "valles" in data and isinstance(data["valles"], list)
    # caja_minima 125M y caja inicial 24M => hay meses ajustados => >= 1 valle
    assert len(data["valles"]) >= 1
    v = data["valles"][0]
    assert {
        "mes",
        "caja",
        "distancia_al_umbral",
        "meses_para_prepararse",
        "causas",
    } <= set(v)


@pytest.mark.asyncio
async def test_valles_lo_ve_consulta(api):
    await _setup(api)
    h = await _token(api, "consulta@roddos.com")
    r = await api.get(f"/api/v1/proyeccion/valles?{_Q}", headers=h)
    assert r.status_code == 200  # dashboard:leer basta (es lectura)
