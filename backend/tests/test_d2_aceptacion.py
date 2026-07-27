# backend/tests/test_d2_aceptacion.py
"""D2 — prueba de terminado del §1 por API: factura Auteco $180 M 15-ago plazo 150 →
pago ene-27 con interés 1,6% separado; cambiar a plazo 90 → pago nov-26 sin interés.
Todo sin que el motor cambie."""

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
    await ac.post(
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
    await ac.put(
        "/api/v1/parametros-proyeccion",
        json={
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
        },
        headers=h,
    )
    oid = (
        await ac.post(
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
    return h, oid


@pytest.mark.asyncio
async def test_prueba_de_terminado_d2(api):
    h, oid = await _setup(api)

    # 1) factura $180 M, 15-ago, plazo 150 → paga ene-27 con interés separado
    f150 = await api.post(
        f"/api/v1/obligaciones/{oid}/facturas",
        json={
            "fecha_factura": "2026-08-15",
            "valor": "180000000",
            "plazo_elegido_dias": 150,
        },
        headers=h,
    )
    fid = f150.json()["id"]
    p = await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)
    d = p.json()
    assert d["ventana_reconciliada"] == ["2027-01", "2027-01"]
    assert d["interes_obligaciones"]["2027-01"] == "5760000.00"  # 180M × 1,6% × 2

    # 2) cambiar el plazo a 90 → paga nov-26 y el interés desaparece
    await api.delete(f"/api/v1/obligaciones/facturas/{fid}", headers=h)
    await api.post(
        f"/api/v1/obligaciones/{oid}/facturas",
        json={
            "fecha_factura": "2026-08-15",
            "valor": "180000000",
            "plazo_elegido_dias": 90,
        },
        headers=h,
    )
    p2 = await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)
    d2 = p2.json()
    assert d2["ventana_reconciliada"] == ["2026-11", "2026-11"]  # 15-ago + 3 meses
    assert d2["interes_obligaciones"]["2026-11"] == "0.00"  # plazo==base → sin interés
    # motor intacto: la estructura de la serie sigue siendo la misma forma
    assert len(d2["meses"]) == 12


@pytest.mark.asyncio
async def test_simulador_de_plazos(api):
    h, oid = await _setup(api)
    await api.post(
        f"/api/v1/obligaciones/{oid}/facturas",
        json={
            "fecha_factura": "2026-08-15",
            "valor": "180000000",
            "plazo_elegido_dias": 90,
        },
        headers=h,
    )
    # §5: simular 90 vs 150 — el 150 cuesta más interés (alivia caja, cuesta financiero)
    s90 = (
        await api.post(
            f"/api/v1/proyeccion/simular-plazo?{_Q}",
            json={"plazo_dias": 90},
            headers=h,
        )
    ).json()
    s150 = (
        await api.post(
            f"/api/v1/proyeccion/simular-plazo?{_Q}",
            json={"plazo_dias": 150},
            headers=h,
        )
    ).json()
    assert s90["interes_total"] == "0.00"  # plazo == base
    assert float(s150["interes_total"]) > float(s90["interes_total"])  # 150 cuesta más
