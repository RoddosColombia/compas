# backend/tests/test_d1_aceptacion.py
"""D1 — criterios de aceptación (brief §4.5 + prueba de terminado de la spec).

Los 4 casos literales del §4.5 (arriendos +$ desde X, salarios +% desde Y, publicidad
+$, ingreso ±%) corren de punta a punta por la API. Y la PRUEBA DE TERMINADO única:
"arriendos +$3 M desde sep-2026 → curva nueva + valle movido + delta → guardar escenario
→ goal seek de venta necesaria" completa sin que el motor cambie.
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
    assert (
        await ac.post("/api/v1/modelos-moto", json=modelo, headers=h)
    ).status_code == 201
    params = {
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
    assert (
        await ac.put("/api/v1/parametros-proyeccion", json=params, headers=h)
    ).status_code == 200
    return h


async def _impacto(ac, h, ajustes: list[dict]) -> dict:
    r = await ac.post(
        f"/api/v1/proyeccion/impactos?{_Q}", json={"ajustes": ajustes}, headers=h
    )
    assert r.status_code == 200, r.text
    return r.json()


def _piso(d: dict, clave: str) -> float:
    return float(d[clave]["piso_caja"])


# ── §4.5 — los 4 casos literales ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_45_arriendos_mas_pesos_desde_un_mes(api):
    h = await _setup(api)
    d = await _impacto(
        api,
        h,
        [
            {
                "nombre": "Arriendo",
                "naturaleza": "gasto",
                "modo": "absoluto",
                "valor": "3000000",
                "mes_inicio": "2026-09",
            }
        ],
    )
    assert _piso(d, "ajustada") < _piso(d, "base")  # más gasto => peor piso


@pytest.mark.asyncio
async def test_45_salarios_mas_porcentaje_desde_un_mes(api):
    h = await _setup(api)
    d = await _impacto(
        api,
        h,
        [
            {
                "nombre": "Salarios +10%",
                "naturaleza": "gasto",
                "modo": "porcentaje",
                "valor": "0.10",
                "mes_inicio": "2026-10",
            }
        ],
    )
    assert _piso(d, "ajustada") < _piso(d, "base")


@pytest.mark.asyncio
async def test_45_publicidad_mas_pesos(api):
    h = await _setup(api)
    d = await _impacto(
        api,
        h,
        [
            {
                "nombre": "Publicidad",
                "naturaleza": "gasto",
                "modo": "absoluto",
                "valor": "5000000",
                "mes_inicio": "2026-08",
            }
        ],
    )
    assert _piso(d, "ajustada") < _piso(d, "base")


@pytest.mark.asyncio
async def test_45_ingreso_mas_y_menos_porcentaje(api):
    h = await _setup(api)
    baja = await _impacto(
        api,
        h,
        [
            {
                "nombre": "Ventas -10%",
                "naturaleza": "ingreso",
                "modo": "porcentaje",
                "valor": "-0.10",
                "mes_inicio": "2026-08",
            }
        ],
    )
    assert _piso(baja, "ajustada") < _piso(baja, "base")  # menos ingreso => peor
    sube = await _impacto(
        api,
        h,
        [
            {
                "nombre": "Ventas +10%",
                "naturaleza": "ingreso",
                "modo": "porcentaje",
                "valor": "0.10",
                "mes_inicio": "2026-08",
            }
        ],
    )
    assert _piso(sube, "ajustada") > _piso(sube, "base")  # más ingreso => mejor


# ── Prueba de terminado (única) ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prueba_de_terminado_flujo_completo(api):
    h = await _setup(api)
    arriendo = {
        "nombre": "Arriendo sede nueva",
        "naturaleza": "gasto",
        "modo": "absoluto",
        "valor": "3000000",
        "mes_inicio": "2026-09",
        "mes_fin": None,
    }

    # 1) arriendos +$3 M desde sep-2026 → curva nueva + valle + delta
    imp = await _impacto(api, h, [arriendo])
    assert _piso(imp, "ajustada") < _piso(imp, "base")  # curva peor
    assert len(imp["valles_ajustada"]) >= 1  # hay valle
    # delta del saldo final != 0 (el arriendo mueve la caja)
    assert imp["base"]["caja_final"] != imp["ajustada"]["caja_final"]
    assert any(v != "0.00" for v in imp["delta_por_mes"])

    # 2) guardar como escenario "Sede nueva"
    guardado = await api.post(
        "/api/v1/escenarios-impacto",
        json={"nombre": "Sede nueva", "ajustes": [arriendo]},
        headers=h,
    )
    assert guardado.status_code == 201
    assert guardado.json()["nombre"] == "Sede nueva"

    # 3) goal seek: cuánto vender para que el piso suba $10 M sobre el del escenario
    objetivo = _piso(imp, "ajustada") + 10_000_000
    gs = await api.post(
        f"/api/v1/proyeccion/resolver?{_Q}",
        json={
            "objetivo": "goal_seek",
            "ajustes": [arriendo],
            "variable": "ingreso_absoluto",
            "objetivo_caja": str(int(objetivo)),
        },
        headers=h,
    )
    assert gs.status_code == 200
    data = gs.json()
    assert data["alcanzable"] is True
    assert data["valor"] is not None and float(data["valor"]) > 0  # un número de venta
