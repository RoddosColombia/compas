# backend/tests/test_modelos_planes.py
"""PLAN-52 (CEO 2026-08-11) — segundo plan de pago por modelo de moto.

Cada modelo puede ofrecer DOS planes (p. ej. 78 y 52 semanas) con su propia cuota
semanal; comparten precio, cuota inicial, matrícula y costo Auteco. El reparto entre
planes es POR MODELO y editable (`peso_plan1`, fracción 0..1; arranque 70/30).

El MOTOR CERTIFICADO NO SE TOCA: el puente `_modelo_a_lineas` expande cada modelo en
una línea de motor por plan con mix = participación × peso. Candados:
  - Sin plan 2 → UNA línea idéntica a la de siempre (golden master intacto).
  - Plan 2 idéntico al 1 → proyección EXACTAMENTE igual a la de un solo plan
    (la partición no inventa ni pierde plata).
  - Validaciones fail-closed: plan 2 incompleto, peso fuera de 0..1, peso < 1 sin
    plan 2 → 422.
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
from app.domain.modelo_moto import ModeloMoto
from app.main import create_app
from app.proyeccion.service import _modelo_a_lineas
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


def _modelo(**extra) -> ModeloMoto:
    base = dict(
        nombre="Raider",
        costo_auteco=Decimal("5000000"),
        precio_venta_con_iva=Decimal("8000000"),
        cuota_inicial=Decimal("1620000"),
        cuota_semanal=Decimal("184900"),
        plazo_semanas=78,
        matricula=Decimal("0"),
        participacion_mix=Decimal("0.35"),
        orden=1,
    )
    base.update(extra)
    return ModeloMoto(**base)


# ── Puente (compute-only): expansión modelo → líneas de plan ──


def test_sin_plan2_una_linea_identica():
    """Candado golden-master: un modelo sin plan 2 produce UNA línea con los mismos
    valores de siempre (nombre sin sufijo, mix completo)."""
    (linea,) = _modelo_a_lineas(_modelo())
    assert linea.nombre == "Raider"
    assert linea.cuota_semanal == Decimal("184900")
    assert linea.plazo_semanas == 78
    assert linea.mix == Decimal("0.35")
    assert linea.cuota_inicial == Decimal("1620000")
    assert linea.costo_moto == Decimal("5000000")


def test_con_plan2_dos_lineas_con_mix_repartido():
    m = _modelo(
        plan2_plazo_semanas=52,
        plan2_cuota_semanal=Decimal("214900"),
        peso_plan1=Decimal("0.70"),
    )
    l1, l2 = _modelo_a_lineas(m)
    assert l1.nombre == "Raider · 78 sem"
    assert l1.cuota_semanal == Decimal("184900")
    assert l1.plazo_semanas == 78
    assert l1.mix == Decimal("0.35") * Decimal("0.70")  # 0.245
    assert l2.nombre == "Raider · 52 sem"
    assert l2.cuota_semanal == Decimal("214900")
    assert l2.plazo_semanas == 52
    assert l2.mix == Decimal("0.35") * Decimal("0.30")  # 0.105
    # los planes comparten inicial y costo (decisión CEO: solo cambia cuota+plazo)
    for ln in (l1, l2):
        assert ln.cuota_inicial == Decimal("1620000")
        assert ln.costo_moto == Decimal("5000000")
    # el mix del modelo se conserva completo entre sus líneas
    assert l1.mix + l2.mix == Decimal("0.35")


# ── API: CRUD con plan 2 + validaciones + proyección end-to-end ──


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


def _body(nombre="Raider", mix="1", **extra) -> dict:
    b = {
        "nombre": nombre,
        "costo_auteco": "5000000",
        "precio_venta_con_iva": "8000000",
        "cuota_inicial": "1620000",
        "cuota_semanal": "184900",
        "plazo_semanas": 78,
        "matricula": "0",
        "participacion_mix": mix,
    }
    b.update(extra)
    return b


def _params_body() -> dict:
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


@pytest.mark.asyncio
async def test_crear_con_plan2_y_serializacion(api):
    h = await _token(api)
    r = await api.post(
        "/api/v1/modelos-moto",
        json=_body(
            plan2_plazo_semanas=52,
            plan2_cuota_semanal="214900",
            peso_plan1="0.70",
        ),
        headers=h,
    )
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["plan2_plazo_semanas"] == 52
    assert d["plan2_cuota_semanal"] == "214900"
    assert d["peso_plan1"] == "0.70"


@pytest.mark.asyncio
async def test_crear_sin_plan2_serializa_defaults(api):
    h = await _token(api)
    r = await api.post("/api/v1/modelos-moto", json=_body(), headers=h)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["plan2_plazo_semanas"] is None
    assert d["plan2_cuota_semanal"] is None
    assert d["peso_plan1"] == "1"


@pytest.mark.asyncio
async def test_plan2_incompleto_es_422(api):
    h = await _token(api)
    r = await api.post(
        "/api/v1/modelos-moto",
        json=_body(plan2_plazo_semanas=52),  # sin cuota del plan 2
        headers=h,
    )
    assert r.status_code == 422
    assert "plan 2" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_peso_fuera_de_rango_es_422(api):
    h = await _token(api)
    r = await api.post(
        "/api/v1/modelos-moto",
        json=_body(
            plan2_plazo_semanas=52,
            plan2_cuota_semanal="214900",
            peso_plan1="1.2",
        ),
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_peso_menor_a_uno_sin_plan2_es_422(api):
    h = await _token(api)
    r = await api.post(
        "/api/v1/modelos-moto", json=_body(peso_plan1="0.70"), headers=h
    )
    assert r.status_code == 422
    assert "plan" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_editar_agrega_y_quita_plan2(api):
    h = await _token(api)
    r = await api.post("/api/v1/modelos-moto", json=_body(), headers=h)
    mid = r.json()["id"]

    # agregar el plan 2 con su peso
    r = await api.patch(
        f"/api/v1/modelos-moto/{mid}",
        json={
            "plan2_plazo_semanas": 52,
            "plan2_cuota_semanal": "214900",
            "peso_plan1": "0.70",
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["plan2_plazo_semanas"] == 52
    assert r.json()["peso_plan1"] == "0.70"

    # quitarlo: vuelve a un solo plan y el peso regresa a 1
    r = await api.patch(
        f"/api/v1/modelos-moto/{mid}", json={"quitar_plan2": True}, headers=h
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["plan2_plazo_semanas"] is None
    assert d["plan2_cuota_semanal"] is None
    assert d["peso_plan1"] == "1"


@pytest.mark.asyncio
async def test_editar_dejando_plan2_incompleto_es_422(api):
    h = await _token(api)
    r = await api.post("/api/v1/modelos-moto", json=_body(), headers=h)
    mid = r.json()["id"]
    r = await api.patch(
        f"/api/v1/modelos-moto/{mid}",
        json={"plan2_cuota_semanal": "214900"},  # sin plazo del plan 2
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_proyeccion_con_dos_planes_particion_no_inventa_plata(api):
    """Candado de partición: un modelo dividido en dos planes IDÉNTICOS (misma cuota y
    plazo) con peso 0.70 proyecta lo MISMO que sin dividir. Exacto en cuotas
    iniciales (camino fraccionario `total×mix×inicial`); en el recaudo la igualdad es
    APROXIMADA (≤0.5% mensual) porque el motor certificado coloca las ALTAS en
    semanas enteras por línea — repartir n motos en dos grupos mueve algunas altas de
    semana (mismo efecto tendría el artefacto con dos filas). Partir el mix no crea
    ni pierde plata más allá de ese corrimiento semanal."""
    h = await _token(api)
    r = await api.post("/api/v1/modelos-moto", json=_body(), headers=h)
    assert r.status_code == 201
    mid = r.json()["id"]
    r = await api.put(
        "/api/v1/parametros-proyeccion", json=_params_body(), headers=h
    )
    assert r.status_code == 200

    base = await api.get("/api/v1/proyeccion?horizonte_meses=12", headers=h)
    assert base.status_code == 200

    r = await api.patch(
        f"/api/v1/modelos-moto/{mid}",
        json={
            "plan2_plazo_semanas": 78,  # plan 2 idéntico al 1
            "plan2_cuota_semanal": "184900",
            "peso_plan1": "0.70",
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    dividido = await api.get("/api/v1/proyeccion?horizonte_meses=12", headers=h)
    assert dividido.status_code == 200

    for m_base, m_div in zip(
        base.json()["meses"], dividido.json()["meses"], strict=True
    ):
        # cuotas iniciales: camino fraccionario → igualdad EXACTA
        assert m_base["cuotas_iniciales"] == m_div["cuotas_iniciales"]
        # recaudo: igualdad aproximada (corrimiento de altas por semanas enteras)
        rb = Decimal(m_base["recaudo_credito"])
        rd = Decimal(m_div["recaudo_credito"])
        assert abs(rb - rd) <= abs(rb) * Decimal("0.005"), (
            f"recaudo se desvía más de 0.5%: base {rb} vs dividido {rd}"
        )
