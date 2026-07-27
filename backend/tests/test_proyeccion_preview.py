# backend/tests/test_proyeccion_preview.py
"""C3 §5.1 — POST /api/v1/proyeccion/preview (compute-only, sin persistencia).

Reglas cubiertas:
  - PARIDAD AL PESO: preview con los parámetros vigentes == GET /proyeccion
    (misma tubería: cartera previa + IVA + motor; la red de seguridad del sprint).
  - Sin persistencia: un preview con cambios NO toca la vigencia ni la proyección.
  - RBAC: mismo permiso que edita parámetros (`proyeccion:gestionar`);
    consulta/directivo → 403.
  - Fail-closed: sin modelos activos → 409 (no se inventan cifras).
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


def _params(vigente=True):
    body = {
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
    if vigente:
        body["vigente_desde"] = "2026-07-01"
    return body


async def _setup_config(ac):
    h = await _token(ac)
    r1 = await ac.post("/api/v1/modelos-moto", json=_modelo_body(), headers=h)
    assert r1.status_code == 201
    r2 = await ac.put("/api/v1/parametros-proyeccion", json=_params(), headers=h)
    assert r2.status_code == 200
    return h


def _preview_body(**cambios):
    body = {"parametros": {**_params(vigente=False), **cambios}}
    return body


@pytest.mark.asyncio
async def test_preview_con_vigentes_es_identico_a_proyeccion(api):
    """La red de seguridad del sprint: preview(vigentes) == GET /proyeccion AL PESO."""
    h = await _setup_config(api)
    vigente = await api.get(
        "/api/v1/proyeccion?horizonte_meses=12&mes_inicio=2026-07", headers=h
    )
    assert vigente.status_code == 200
    preview = await api.post(
        "/api/v1/proyeccion/preview?horizonte_meses=12&mes_inicio=2026-07",
        json=_preview_body(),
        headers=h,
    )
    assert preview.status_code == 200
    assert preview.json() == vigente.json()  # bit a bit, montos string incluidos


@pytest.mark.asyncio
async def test_preview_no_persiste_nada(api):
    h = await _setup_config(api)
    antes = await api.get("/api/v1/parametros-proyeccion", headers=h)
    r = await api.post(
        "/api/v1/proyeccion/preview?horizonte_meses=12&mes_inicio=2026-07",
        json=_preview_body(gastos_fijos="200000000"),
        headers=h,
    )
    assert r.status_code == 200
    despues = await api.get("/api/v1/parametros-proyeccion", headers=h)
    assert antes.json() == despues.json()  # la vigencia quedó intacta


@pytest.mark.asyncio
async def test_preview_cambia_el_resultado_sin_tocar_el_vigente(api):
    h = await _setup_config(api)
    base = await api.post(
        "/api/v1/proyeccion/preview?horizonte_meses=12&mes_inicio=2026-07",
        json=_preview_body(),
        headers=h,
    )
    duro = await api.post(
        "/api/v1/proyeccion/preview?horizonte_meses=12&mes_inicio=2026-07",
        json=_preview_body(gastos_fijos="200000000"),
        headers=h,
    )
    assert base.status_code == duro.status_code == 200
    # más gasto fijo → peor piso (comparación como Decimal vía float solo en test)
    assert float(duro.json()["piso_caja"]) < float(base.json()["piso_caja"])
    # y la proyección vigente sigue siendo la de siempre
    vigente = await api.get(
        "/api/v1/proyeccion?horizonte_meses=12&mes_inicio=2026-07", headers=h
    )
    assert vigente.json() == base.json()


@pytest.mark.asyncio
async def test_preview_rbac_mismo_permiso_que_editar(api):
    await _setup_config(api)
    h_consulta = await _token(api, "consulta@roddos.com")
    r = await api.post(
        "/api/v1/proyeccion/preview",
        json=_preview_body(),
        headers=h_consulta,
    )
    assert r.status_code == 403  # dashboard:leer NO basta: es proyeccion:gestionar


@pytest.mark.asyncio
async def test_preview_sin_modelos_es_409(api):
    h = await _token(api)
    r = await api.post(
        "/api/v1/proyeccion/preview",
        json=_preview_body(),
        headers=h,
    )
    assert r.status_code == 409  # fail-closed, como GET /proyeccion


@pytest.mark.asyncio
async def test_preview_valida_decimales(api):
    h = await _setup_config(api)
    r = await api.post(
        "/api/v1/proyeccion/preview",
        json=_preview_body(gastos_fijos="no-es-numero"),
        headers=h,
    )
    assert r.status_code == 422
