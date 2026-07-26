# backend/tests/test_proyeccion_endpoints.py
"""COCK-01/02 — /api/v1/modelos-moto, /parametros-proyeccion, /proyeccion (CR-COCK).

Reglas cubiertas:
  - RBAC: GET con `dashboard:leer` (todos); mutaciones con `proyeccion:gestionar` =
    {financiero, admin}; consulta/directivo → 403 al mutar.
  - Fail-closed: GET /proyeccion sin parámetros o sin modelos activos → 409 (no se
    inventan cifras).
  - Flujo completo: crear modelo + cargar parámetros → proyección con ingreso
    DISCRIMINADO (recaudo_credito vs cuotas_iniciales) + KPIs + caja veraz.
  - Escenario: pesimista deja menos caja que optimista.
  - Modelo: baja lógica + reactivación (B-3); montos como string (regla 1).
"""

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
        ("dir@roddos.com", Role.directivo),
        ("admin@roddos.com", Role.admin),
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


def _modelo_body(nombre="Raider", mix="1"):
    return {
        "nombre": nombre,
        "costo_auteco": "5000000",
        "precio_venta_con_iva": "8000000",
        "cuota_inicial": "1000000",
        "cuota_semanal": "164900",
        "plazo_semanas": 78,
        "matricula": "500000",
        "participacion_mix": mix,
    }


def _params_body():
    # cifras ILUSTRATIVAS solo para probar la lógica (el CEO carga las reales).
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


async def _setup_config(ac):
    h = await _token(ac, "fin@roddos.com")
    r1 = await ac.post("/api/v1/modelos-moto", json=_modelo_body(), headers=h)
    assert r1.status_code == 201
    r2 = await ac.put("/api/v1/parametros-proyeccion", json=_params_body(), headers=h)
    assert r2.status_code == 200
    return h


@pytest.mark.asyncio
async def test_proyeccion_sin_config_es_409(api):
    h = await _token(api, "fin@roddos.com")
    r = await api.get("/api/v1/proyeccion", headers=h)
    assert r.status_code == 409  # fail-closed: sin parámetros no se inventa nada


@pytest.mark.asyncio
async def test_flujo_completo_ingreso_discriminado_y_kpis(api):
    await _setup_config(api)
    h = await _token(api, "consulta@roddos.com")  # dashboard:leer basta para ver
    r = await api.get("/api/v1/proyeccion?horizonte_meses=12", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert len(data["meses"]) == 12
    assert data["escenario"] == "base"
    # el umbral (caja mínima) viaja para la curva del front
    assert data["caja_minima"] == "125000000.00"
    # montos como string (regla 1) + KPIs presentes
    assert isinstance(data["piso_caja"], str)
    assert "mes_mas_ajustado" in data and "capital_requerido" in data
    m0 = data["meses"][0]
    # ingreso DISCRIMINADO: bruto = recaudo_credito + cuotas_iniciales
    assert Decimal(m0["ingreso_bruto"]) == Decimal(m0["recaudo_credito"]) + Decimal(
        m0["cuotas_iniciales"]
    )
    # provisión informativa presente pero fuera del flujo (caja veraz)
    assert "provision" in m0


@pytest.mark.asyncio
async def test_operacion_cartera_por_anada_y_colocacion(api):
    # DASH-01: /proyeccion/operacion desglosa la cartera por AÑADA y expone colocación.
    await _setup_config(api)
    h = await _token(api, "consulta@roddos.com")  # dashboard:leer basta
    r = await api.get("/api/v1/proyeccion/operacion?horizonte_meses=12", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert len(data["meses"]) == 12
    m0 = data["meses"][0]
    assert m0["colocacion"] == 50  # motos_base
    # la suma del desglose por añada iguala la cartera activa del mes (invariante)
    suma = sum(a["activos"] for a in m0["por_anada"])
    assert suma == m0["cartera"]
    # el primer mes solo tiene la añada de su propio mes
    assert [a["anada"] for a in m0["por_anada"]] == [m0["mes"]]


@pytest.mark.asyncio
async def test_operacion_sin_config_es_409(api):
    h = await _token(api, "fin@roddos.com")
    r = await api.get("/api/v1/proyeccion/operacion", headers=h)
    assert r.status_code == 409  # fail-closed igual que /proyeccion


@pytest.mark.asyncio
async def test_escenario_pesimista_menos_caja_que_optimista(api):
    await _setup_config(api)
    h = await _token(api, "fin@roddos.com")
    pes = (await api.get("/api/v1/proyeccion?escenario=pesimista", headers=h)).json()
    opt = (await api.get("/api/v1/proyeccion?escenario=optimista", headers=h)).json()
    assert Decimal(pes["caja_final"]) < Decimal(opt["caja_final"])


@pytest.mark.asyncio
async def test_rbac_mutaciones_solo_gestionar(api):
    # consulta y directivo NO pueden crear modelos (proyeccion:gestionar excluye ambos)
    for email in ("consulta@roddos.com", "dir@roddos.com"):
        h = await _token(api, email)
        r = await api.post("/api/v1/modelos-moto", json=_modelo_body("X"), headers=h)
        assert r.status_code == 403, email
    # admin sí
    h = await _token(api, "admin@roddos.com")
    r = await api.post("/api/v1/modelos-moto", json=_modelo_body("Sport"), headers=h)
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_modelo_baja_logica_y_reactivar(api):
    h = await _token(api, "fin@roddos.com")
    created = (
        await api.post("/api/v1/modelos-moto", json=_modelo_body("Apache"), headers=h)
    ).json()
    mid = created["id"]
    # desactivar → activo=false
    r = await api.post(f"/api/v1/modelos-moto/{mid}/desactivar", headers=h)
    assert r.status_code == 200 and r.json()["activo"] is False
    # reactivar via PATCH activo:true (B-3)
    r = await api.patch(f"/api/v1/modelos-moto/{mid}", json={"activo": True}, headers=h)
    assert r.status_code == 200 and r.json()["activo"] is True
    # PATCH activo:false → 422 (la baja va por /desactivar)
    r = await api.patch(
        f"/api/v1/modelos-moto/{mid}", json={"activo": False}, headers=h
    )
    assert r.status_code == 422
