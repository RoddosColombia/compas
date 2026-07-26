# backend/tests/test_loantape_endpoints.py
"""Aging SISMO-V3 — /api/v1/loantape (carga del LoanTape semanal + aging por tramo).

RBAC: carga con `cargas:gestionar` (financiero/admin); aging con `dashboard:leer`.
El upload acepta CSV (contrato docs/CONTRATO-SISMO-V3-LOANTAPE.md); fila ambigua → 422
(el parser transforma, no adivina).
"""

import httpx
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

_HEADER = (
    "credito_id,fecha_corte,cliente_id,modelo,fecha_desembolso,monto_financiado,"
    "plazo_semanas,cuota_semanal,cuotas_pagadas,cuotas_vencidas,dias_mora,"
    "saldo_en_mora,saldo_pendiente,fecha_ultimo_pago,estado"
)


def _csv(*filas: str) -> bytes:
    return ("\n".join([_HEADER, *filas]) + "\n").encode("utf-8")


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


async def test_cargar_csv_y_ver_aging(api):
    h = await _token(api)
    csv = _csv(
        "A,2026-07-22,CLI1,Raider,2026-01-14,6435000.00,78,164900.00,20,3,45,"
        "494700.00,9000000.00,2026-06-20,en_mora",
        "B,2026-07-22,CLI2,Apache,2026-02-01,7000000.00,78,209900.00,30,0,0,"
        "0.00,8000000.00,2026-07-20,vigente",
    )
    r = await api.post(
        "/api/v1/loantape/carga",
        files={"archivo": ("loantape.csv", csv, "text/csv")},
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["cargados"] == 2

    h2 = await _token(api, "consulta@roddos.com")
    ra = await api.get("/api/v1/loantape/aging", headers=h2)
    assert ra.status_code == 200
    data = ra.json()
    assert data["fecha_corte"] == "2026-07-22"
    por = {t["tramo"]: t for t in data["tramos"]}
    assert por["31_60"]["n_creditos"] == 1  # A (45 días)
    assert por["31_60"]["saldo_en_mora"] == "494700.00"
    assert por["al_dia"]["n_creditos"] == 1  # B


async def test_cargar_fila_ambigua_es_422(api):
    h = await _token(api)
    csv = _csv(
        "A,2026-07-22,CLI1,Raider,2026-01-14,6435000.00,78,164900.00,20,3,45,"
        "N/D,9000000.00,2026-06-20,en_mora",  # saldo_en_mora no numérico
    )
    r = await api.post(
        "/api/v1/loantape/carga",
        files={"archivo": ("loantape.csv", csv, "text/csv")},
        headers=h,
    )
    assert r.status_code == 422


async def test_carga_rbac_consulta_es_403(api):
    h = await _token(api, "consulta@roddos.com")
    r = await api.post(
        "/api/v1/loantape/carga",
        files={"archivo": ("loantape.csv", _csv(), "text/csv")},
        headers=h,
    )
    assert r.status_code == 403
