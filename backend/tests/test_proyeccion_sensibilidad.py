# backend/tests/test_proyeccion_sensibilidad.py
"""C3 §5.2 — GET /api/v1/proyeccion/sensibilidad: el tornado "¿qué mueve mi umbral?".

Para cada variable principal, cuánto se mueve el piso de caja ante una variación
natural (±10 %, ±1 punto, ±30 días, ±$100 mil). Compute-only sobre el set vigente;
las variaciones se aplican al ParametrosMotor YA armado (post-preset de escenario:
mutar params crudos sería inútil para la mora, que el preset sobrescribe).

Reglas cubiertas: shape del contrato, semántica (más gasto → peor piso), RBAC
dashboard:leer (panel de lectura), fail-closed 409 sin configuración.
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

VARIABLES_ESPERADAS = {
    "motos_base",
    "crec_pct_mensual",
    "cuota_semanal",
    "gastos_fijos",
    "pct_mora",
    "plazo_auteco_dias",
    "costo_alistamiento",
}


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


async def _setup_config(ac):
    h = await _token(ac)
    r1 = await ac.post(
        "/api/v1/modelos-moto",
        json={
            "nombre": "Raider",
            "costo_auteco": "5000000",
            "precio_venta_con_iva": "8000000",
            "cuota_inicial": "1000000",
            "cuota_semanal": "164900",
            "plazo_semanas": 78,
            "matricula": "500000",
            "participacion_mix": "1",
        },
        headers=h,
    )
    assert r1.status_code == 201
    r2 = await ac.put(
        "/api/v1/parametros-proyeccion",
        json={
            "vigente_desde": "2026-07-01",
            "caja_inicial": "24000000",
            "caja_minima": "125000000",
            "motos_base": 50,
            "crec_pct_mensual": "0.01",
            "horizonte_meses": 24,
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
        },
        headers=h,
    )
    assert r2.status_code == 200
    return h


@pytest.mark.asyncio
async def test_sensibilidad_shape_y_semantica(api):
    h = await _setup_config(api)
    r = await api.get("/api/v1/proyeccion/sensibilidad?mes_inicio=2026-07", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "piso_base" in data
    variables = {v["variable"]: v for v in data["variables"]}
    assert set(variables) == VARIABLES_ESPERADAS
    for v in data["variables"]:
        assert set(v) >= {
            "variable",
            "etiqueta",
            "variacion",
            "piso_base",
            "piso_mas",
            "piso_menos",
        }
        # montos como string (regla 1)
        assert isinstance(v["piso_mas"], str)

    # semántica: MÁS gasto fijo → PEOR piso; MENOS → mejor
    gf = variables["gastos_fijos"]
    assert float(gf["piso_mas"]) < float(gf["piso_base"])
    assert float(gf["piso_menos"]) > float(gf["piso_base"])
    # más costo de alistamiento → peor piso
    ca = variables["costo_alistamiento"]
    assert float(ca["piso_mas"]) < float(ca["piso_base"])


@pytest.mark.asyncio
async def test_sensibilidad_es_lectura_para_todos(api):
    await _setup_config(api)
    h = await _token(api, "consulta@roddos.com")
    r = await api.get("/api/v1/proyeccion/sensibilidad?mes_inicio=2026-07", headers=h)
    assert r.status_code == 200  # dashboard:leer basta (panel de lectura)


@pytest.mark.asyncio
async def test_sensibilidad_sin_config_es_409(api):
    h = await _token(api)
    r = await api.get("/api/v1/proyeccion/sensibilidad", headers=h)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_sensibilidad_mide_la_misma_pista_que_la_pantalla(api):
    """Bug CEO 2026-08-11 ('el tornado quedó todo en $0'): el tornado corría el motor
    CRUDO, sin las capas que GET /proyeccion sí aplica (E1 anclaje + D2
    reconciliación). Cuando las capas arrastran el mínimo de la curva a un mes
    futuro, el piso crudo queda clavado en la caja del arranque y ninguna variable
    lo mueve → deltas $0 engañosos. Contrato: (a) el piso base del tornado ==
    el piso de la pantalla a 60 meses; (b) una factura real de obligación (D2)
    cambia el piso del tornado (el cache no puede servir el mundo sin factura)."""
    h = await _setup_config(api)

    r0 = await api.get(
        "/api/v1/proyeccion/sensibilidad?mes_inicio=2026-07", headers=h
    )
    piso_sin_factura = r0.json()["piso_base"]

    # obligación de facturación + factura grande que golpea la caja en nov-2026
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
    rf = await api.post(
        f"/api/v1/obligaciones/{oid}/facturas",
        json={
            "fecha_factura": "2026-08-15",
            "valor": "500000000",
            "plazo_elegido_dias": 90,
        },
        headers=h,
    )
    assert rf.status_code in (200, 201), rf.text

    p = await api.get(
        "/api/v1/proyeccion?mes_inicio=2026-07&horizonte_meses=60", headers=h
    )
    assert p.status_code == 200, p.text
    s = await api.get(
        "/api/v1/proyeccion/sensibilidad?mes_inicio=2026-07", headers=h
    )
    assert s.status_code == 200, s.text

    # (a) misma pista que la pantalla
    assert s.json()["piso_base"] == p.json()["piso_caja"]
    # (b) la factura D2 SÍ movió el piso del tornado (y el cache no sirvió lo viejo)
    assert s.json()["piso_base"] != piso_sin_factura


@pytest.mark.asyncio
async def test_editar_dos_veces_el_mismo_dia_no_sirve_cache_viejo(api):
    """Bug QA C3: el upsert por vigente_desde deja id/fecha/autor idénticos al
    guardar dos veces el mismo día → el fingerprint debe cubrir los VALORES,
    no solo la identidad de la fila."""
    h = await _setup_config(api)
    r1 = await api.get("/api/v1/proyeccion/sensibilidad?mes_inicio=2026-07", headers=h)
    assert r1.status_code == 200
    base_antes = r1.json()["piso_base"]

    # segunda edición del MISMO día (misma vigente_desde → upsert, mismo id)
    body = {
        "vigente_desde": "2026-07-01",
        "caja_inicial": "24000000",
        "caja_minima": "125000000",
        "motos_base": 50,
        "crec_pct_mensual": "0.01",
        "horizonte_meses": 24,
        "adelanto_auteco": "970000",
        "plazo_auteco_dias": 150,
        "base_auteco_dias": 90,
        "tasa_auteco": "0.016",
        "gastos_fijos": "200000000",  # ← el cambio
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
    r = await api.put("/api/v1/parametros-proyeccion", json=body, headers=h)
    assert r.status_code == 200

    r2 = await api.get("/api/v1/proyeccion/sensibilidad?mes_inicio=2026-07", headers=h)
    assert r2.status_code == 200
    base_despues = r2.json()["piso_base"]
    # más gasto fijo → peor piso; si el cache sirviera lo viejo, serían iguales
    assert float(base_despues) < float(base_antes)
