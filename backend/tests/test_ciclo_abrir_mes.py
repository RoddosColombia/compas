# backend/tests/test_ciclo_abrir_mes.py
"""POST /api/v1/meses — apertura del mes (US-01, Spec §1.3/§2.4).

MARCADO PARA AUDITORÍA KIMI (flujo del ciclo mensual).

Reglas cubiertas:
  - §2.4: `ciclo:abrir` = financiero/directivo/admin; consulta → 403.
  - Regla 1: montos como STRING (number → 422); respuesta con money_str.
  - Regla 2: mes normalizado al día 1 (YYYY-MM-01); otro día → 422.
  - US-01 / regla 11: evento `mes.creado` en el catálogo; si el audit falla,
    la apertura se COMPENSA (no queda mes sin rastro — política Kimi O1).
  - Unicidad: mes ya abierto → 409 (índice único `mes_unico` en real).
"""

import httpx
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import MesControl
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
    c = AsyncMongoMockClient()
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
        yield ac, c
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _token(ac, email="fin@roddos.com") -> dict:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _body(**over):
    base = {
        "mes": "2026-07-01",
        "saldo_inicial_caja": "1500000",
        "saldos_banco": [
            {"banco": "bancolombia", "saldo": "2500000", "fecha_reporte": "2026-07-01"},
        ],
    }
    base.update(over)
    return base


async def test_abrir_mes_201(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post("/api/v1/meses", json=_body(), headers=h)
    assert r.status_code == 201
    d = r.json()
    assert d["mes"] == "2026-07-01"
    assert d["estado"] == "sugerido"
    assert d["saldo_inicial_caja"] == "1500000.00"  # string (regla 1)
    assert d["saldos_banco"][0]["saldo"] == "2500000.00"
    assert await MesControl.find_all().count() == 1


async def test_mes_duplicado_409(api):
    ac, _ = api
    h = await _token(ac)
    await ac.post("/api/v1/meses", json=_body(), headers=h)
    r = await ac.post("/api/v1/meses", json=_body(), headers=h)
    assert r.status_code == 409
    assert await MesControl.find_all().count() == 1


async def test_mes_no_normalizado_422(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post("/api/v1/meses", json=_body(mes="2026-07-15"), headers=h)
    assert r.status_code == 422


async def test_saldo_como_number_422(api):
    # Regla 1: montos string; un number JSON se rechaza.
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
        "/api/v1/meses", json=_body(saldo_inicial_caja=1500000.0), headers=h
    )
    assert r.status_code == 422


async def test_banco_invalido_422(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
        "/api/v1/meses",
        json=_body(
            saldos_banco=[
                {"banco": "davivienda", "saldo": "1", "fecha_reporte": "2026-07-01"}
            ]
        ),
        headers=h,
    )
    assert r.status_code == 422


async def test_consulta_403(api):
    ac, _ = api
    h = await _token(ac, "consulta@roddos.com")
    r = await ac.post("/api/v1/meses", json=_body(), headers=h)
    assert r.status_code == 403


async def test_emite_mes_creado(api):
    ac, c = api
    h = await _token(ac)
    r = await ac.post("/api/v1/meses", json=_body(), headers=h)
    ev = await c["compas_test"]["audit_log"].find_one({"evento": "mes.creado"})
    assert ev is not None
    assert ev["entidad_id"] == r.json()["id"]


async def test_audit_caido_compensa(api, monkeypatch):
    # Política O1: sin auditoría no hay operación de ciclo → si emit falla,
    # la apertura se revierte (no queda mes fantasma sin rastro). El error se
    # propaga (ASGITransport lo re-lanza; en producción uvicorn responde 500).
    import pytest
    from app.ciclo import service as ciclo_service

    async def _explota(*a, **k):
        raise RuntimeError("audit caído")

    monkeypatch.setattr(ciclo_service, "emit_audit", _explota)
    ac, _ = api
    h = await _token(ac)
    with pytest.raises(RuntimeError, match="audit caído"):
        await ac.post("/api/v1/meses", json=_body(), headers=h)
    assert await MesControl.find_all().count() == 0  # compensado


async def test_listar_meses(api):
    ac, _ = api
    h = await _token(ac)
    await ac.post("/api/v1/meses", json=_body(mes="2026-06-01"), headers=h)
    await ac.post("/api/v1/meses", json=_body(mes="2026-07-01"), headers=h)
    r = await ac.get("/api/v1/meses", headers=h)
    assert r.status_code == 200
    meses = [m["mes"] for m in r.json()["items"]]
    assert meses == ["2026-07-01", "2026-06-01"]  # desc


async def test_listar_requiere_auth(api):
    ac, _ = api
    assert (await ac.get("/api/v1/meses")).status_code == 401
