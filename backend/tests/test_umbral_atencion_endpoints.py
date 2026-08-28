# backend/tests/test_umbral_atencion_endpoints.py
"""RF-F3 · P1 — endpoints admin del umbral de atención. RBAC: leer con
`dashboard:leer`; escribir con `proyeccion:gestionar` (= mueve la proyección)."""

from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.configuracion import ClaveConfig, Configuracion
from app.domain.parametros_proyeccion import ParametrosProyeccion
from app.main import create_app
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"
BASE = "/api/v1/configuracion/umbral-atencion"


async def _param(caja_minima: str) -> None:
    await ParametrosProyeccion(
        vigente_desde="2026-07-01",
        caja_inicial=Decimal("0"),
        caja_minima=Decimal(caja_minima),
        motos_base=0,
        crec_pct_mensual=Decimal("0"),
        horizonte_meses=2,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=0,
        base_auteco_dias=0,
        tasa_auteco=Decimal("0"),
        gastos_fijos=Decimal("0"),
        gps_moto=Decimal("0"),
        costo_moto_nueva=Decimal("0"),
        deuda=Decimal("0"),
        tasa_deuda=Decimal("0"),
        mes_inicio_deuda=0,
        meses_deuda=0,
        pct_mora=Decimal("0"),
        pct_recuperacion=Decimal("0"),
        pct_default=Decimal("0"),
        pct_provision=Decimal("0"),
    ).insert()


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
async def test_get_sin_config_devuelve_fallback_3x(api):
    await _param("30000000")
    h = await _token(api, "consulta@roddos.com")
    r = await api.get(BASE, headers=h)
    assert r.status_code == 200
    assert r.json() == {"critico": "30000000", "atencion": "90000000"}


@pytest.mark.asyncio
async def test_put_escribe_y_get_lo_devuelve(api):
    await _param("30000000")
    h = await _token(api)
    r = await api.put(BASE, json={"valor": "250000000"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["atencion"] == "250000000"
    assert body["critico"] == "30000000"
    # persistió
    fila = await Configuracion.find_one(
        Configuracion.clave == ClaveConfig.UMBRAL_ATENCION
    )
    assert fila is not None and fila.valor_decimal == Decimal("250000000")
    # get lo trae
    g = await api.get(BASE, headers=h)
    assert g.json()["atencion"] == "250000000"


@pytest.mark.asyncio
async def test_put_rechaza_valor_menor_o_igual_al_critico(api):
    await _param("30000000")
    h = await _token(api)
    r = await api.put(BASE, json={"valor": "30000000"}, headers=h)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_put_rechaza_no_gestor(api):
    await _param("30000000")
    h = await _token(api, "consulta@roddos.com")
    r = await api.put(BASE, json={"valor": "250000000"}, headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_sin_parametros_dice_409(api):
    h = await _token(api, "consulta@roddos.com")
    r = await api.get(BASE, headers=h)
    assert r.status_code == 409
