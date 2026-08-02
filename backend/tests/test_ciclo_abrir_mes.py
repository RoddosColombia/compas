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


# ── M-1 (Kimi): el saldo inicial se ARRASTRA del mes anterior (F-14/US-01) ──


async def test_arrastra_saldo_del_consolidado_anterior(api):
    # Abrir N+1 → saldo_inicial_caja == consolidado bancario de N (no input).
    ac, _ = api
    h = await _token(ac)
    await ac.post(
        "/api/v1/meses",
        json=_body(
            mes="2026-07-01",
            saldos_banco=[
                {
                    "banco": "bancolombia",
                    "saldo": "2500000",
                    "fecha_reporte": "2026-07-01",
                },
                {"banco": "bbva", "saldo": "500000", "fecha_reporte": "2026-07-01"},
            ],
        ),
        headers=h,
    )
    r = await ac.post(
        "/api/v1/meses",
        json={
            "mes": "2026-08-01",
            "saldos_banco": [
                {
                    "banco": "bancolombia",
                    "saldo": "3000000",
                    "fecha_reporte": "2026-08-01",
                }
            ],
        },
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["saldo_inicial_caja"] == "3000000.00"  # consolidado de N


async def test_saldo_explicito_con_predecesor_422(api):
    # Con mes anterior, digitar el saldo es override → ciclo:config+step-up (futuro).
    ac, _ = api
    h = await _token(ac)
    await ac.post("/api/v1/meses", json=_body(mes="2026-07-01"), headers=h)
    r = await ac.post(
        "/api/v1/meses", json=_body(mes="2026-08-01"), headers=h
    )  # trae saldo_inicial_caja
    assert r.status_code == 422
    assert "deriva" in r.json()["detail"].lower()


async def test_primer_mes_sin_saldo_422(api):
    ac, _ = api
    h = await _token(ac)
    body = _body()
    del body["saldo_inicial_caja"]
    r = await ac.post("/api/v1/meses", json=body, headers=h)
    assert r.status_code == 422


async def test_predecesor_sin_saldos_banco_422(api):
    # No se adivina (regla 7): si N no reportó saldos bancarios, no hay de dónde
    # arrastrar → error explícito, no 0.
    ac, _ = api
    h = await _token(ac)
    await ac.post(
        "/api/v1/meses", json=_body(mes="2026-07-01", saldos_banco=[]), headers=h
    )
    r = await ac.post(
        "/api/v1/meses", json={"mes": "2026-08-01", "saldos_banco": []}, headers=h
    )
    assert r.status_code == 422
    assert (
        "consolidado" in r.json()["detail"].lower()
        or "saldos" in r.json()["detail"].lower()
    )


async def test_mes_no_contiguo_422(api):
    # El ciclo es secuencial: el arrastre solo tiene sentido mes a mes.
    ac, _ = api
    h = await _token(ac)
    await ac.post("/api/v1/meses", json=_body(mes="2026-07-01"), headers=h)
    r = await ac.post(
        "/api/v1/meses", json={"mes": "2026-09-01", "saldos_banco": []}, headers=h
    )
    assert r.status_code == 422
    assert "2026-08" in r.json()["detail"]


async def test_manual_en_saldos_422(api):
    # B-2 (Kimi): 'manual' no es un banco de saldos (§1.3).
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
        "/api/v1/meses",
        json=_body(
            saldos_banco=[
                {"banco": "manual", "saldo": "1", "fecha_reporte": "2026-07-01"}
            ]
        ),
        headers=h,
    )
    assert r.status_code == 422


async def test_banco_repetido_en_apertura_422(api):
    # A-6 (parte 4): dedup de banco en la apertura (espejo de reportar_saldos,
    # caja/router.py). El mismo banco dos veces produciría un saldos_banco con
    # duplicados → rompe el dict de conciliación y los updates posicionales por
    # banco (uno se pisa en silencio). Fail-loud: 422 y no se crea el mes.
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
        "/api/v1/meses",
        json=_body(
            saldos_banco=[
                {"banco": "bancolombia", "saldo": "1", "fecha_reporte": "2026-07-01"},
                {"banco": "bancolombia", "saldo": "2", "fecha_reporte": "2026-07-01"},
            ]
        ),
        headers=h,
    )
    assert r.status_code == 422
    assert "repetido" in r.json()["detail"].lower()
    assert await MesControl.find_all().count() == 0


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
    # El 2º mes se abre SIN saldo (se arrastra del consolidado de junio, M-1).
    r2 = await ac.post(
        "/api/v1/meses", json={"mes": "2026-07-01", "saldos_banco": []}, headers=h
    )
    assert r2.status_code == 201
    r = await ac.get("/api/v1/meses", headers=h)
    assert r.status_code == 200
    meses = [m["mes"] for m in r.json()["items"]]
    assert meses == ["2026-07-01", "2026-06-01"]  # desc


async def test_listar_requiere_auth(api):
    ac, _ = api
    assert (await ac.get("/api/v1/meses")).status_code == 401
