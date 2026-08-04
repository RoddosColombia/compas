# backend/tests/test_saldo_inicial.py
"""FIX-F — editar el saldo inicial de caja desde la app.

PATCH /api/v1/meses/{mes}/saldo-inicial (ciclo:config + step-up MFA + verify_origin).
Emite `saldo_inicial.editado` (anterior→nuevo + motivo); saga O1: si el emit falla, el
saldo se revierte. El histórico (mes cerrado) es inmutable (regla 4) → 409.

Lógica de dominio con mongomock (service directo, incl. la compensación O1); RBAC,
step-up y validación de body por el endpoint (app + auth). No requiere transacción.
"""

from decimal import Decimal

import httpx
import pyotp
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.ciclo import service
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import EstadoMes, MesControl
from app.main import create_app
from beanie import init_beanie
from cryptography.fernet import Fernet
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


@pytest_asyncio.fixture
async def api(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("MFA_ENC_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("COOKIE_SECURE", "False")
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()

    app = create_app()
    c = AsyncMongoMockClient()
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")
    for correo, rol in [
        ("admin@roddos.com", Role.admin),
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


async def _token(ac, email="admin@roddos.com") -> dict:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _token_step_up(ac, email="admin@roddos.com") -> dict:
    """Access con mfa_at reciente: enrola + activa + login 2 pasos + verify."""
    h = await _token(ac, email)
    r = await ac.post("/api/v1/auth/mfa/setup", json={"password": PWD}, headers=h)
    secret = r.json()["secret"]
    await ac.post(
        "/api/v1/auth/mfa/activate",
        json={"code": pyotp.TOTP(secret).now()},
        headers=h,
    )
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    mfa_token = r.json()["mfa_token"]
    r = await ac.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": pyotp.TOTP(secret).now()},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _mes(
    mes="2026-08-01", estado=EstadoMes.EN_EJECUCION, saldo="100"
) -> MesControl:
    mc = MesControl(mes=mes, saldo_inicial_caja=Decimal(saldo), estado=estado)
    await mc.insert()
    return mc


# ── Servicio (mongomock) ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_editar_saldo_mes_inexistente_404(api):
    with pytest.raises(service.SaldoInicialError) as exc:
        await service.editar_saldo_inicial(
            mes="2026-08-01",
            saldo_inicial_caja=Decimal("200"),
            motivo="corrección",
            usuario_id="u1",
        )
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_editar_saldo_mes_cerrado_409(api):
    await _mes(estado=EstadoMes.CERRADO)
    with pytest.raises(service.SaldoInicialError) as exc:
        await service.editar_saldo_inicial(
            mes="2026-08-01",
            saldo_inicial_caja=Decimal("200"),
            motivo="corrección",
            usuario_id="u1",
        )
    assert exc.value.status == 409


@pytest.mark.asyncio
async def test_editar_saldo_ok_emite_evento(api):
    _, c = api
    mc = await _mes(saldo="100")
    out = await service.editar_saldo_inicial(
        mes="2026-08-01",
        saldo_inicial_caja=Decimal("250.50"),
        motivo="ajuste de apertura",
        usuario_id="u1",
    )
    assert out.saldo_inicial_caja == Decimal("250.50")
    releido = await MesControl.get(mc.id)
    assert releido.saldo_inicial_caja == Decimal("250.50")
    ev = await c["compas_test"]["audit_log"].find_one(
        {"evento": "saldo_inicial.editado"}
    )
    assert ev is not None
    assert ev["metadata"]["anterior"] == "100.00"
    assert ev["metadata"]["nuevo"] == "250.50"
    assert ev["metadata"]["motivo"] == "ajuste de apertura"


@pytest.mark.asyncio
async def test_editar_saldo_o1_compensa_si_emit_falla(api, monkeypatch):
    mc = await _mes(saldo="100")

    async def _boom(*a, **k):
        raise RuntimeError("audit caído")

    monkeypatch.setattr("app.ciclo.service.emit_audit", _boom)
    with pytest.raises(RuntimeError):
        await service.editar_saldo_inicial(
            mes="2026-08-01",
            saldo_inicial_caja=Decimal("999"),
            motivo="x",
            usuario_id="u1",
        )
    # O1: el saldo volvió al anterior (sin rastro no hay edición).
    releido = await MesControl.get(mc.id)
    assert releido.saldo_inicial_caja == Decimal("100")


# ── Endpoint (RBAC + step-up + validación) ────────────────────────────────


async def test_endpoint_no_admin_403(api):
    ac, _ = api
    await _mes()
    h = await _token(ac, "fin@roddos.com")
    r = await ac.patch(
        "/api/v1/meses/2026-08/saldo-inicial",
        json={"saldo_inicial_caja": "200", "motivo": "x"},
        headers=h,
    )
    assert r.status_code == 403


async def test_endpoint_sin_step_up_403(api):
    ac, _ = api
    await _mes()
    h = await _token(ac)  # admin SIN MFA reciente
    r = await ac.patch(
        "/api/v1/meses/2026-08/saldo-inicial",
        json={"saldo_inicial_caja": "200", "motivo": "x"},
        headers=h,
    )
    assert r.status_code == 403


async def test_endpoint_saldo_invalido_422(api):
    ac, _ = api
    await _mes()
    h = await _token_step_up(ac)
    r = await ac.patch(
        "/api/v1/meses/2026-08/saldo-inicial",
        json={"saldo_inicial_caja": "abc", "motivo": "x"},
        headers=h,
    )
    assert r.status_code == 422


async def test_endpoint_motivo_vacio_422(api):
    ac, _ = api
    await _mes()
    h = await _token_step_up(ac)
    r = await ac.patch(
        "/api/v1/meses/2026-08/saldo-inicial",
        json={"saldo_inicial_caja": "200", "motivo": "   "},
        headers=h,
    )
    assert r.status_code == 422


async def test_endpoint_ok_200_cambia_saldo(api):
    ac, _ = api
    await _mes(saldo="100")
    h = await _token_step_up(ac)
    r = await ac.patch(
        "/api/v1/meses/2026-08/saldo-inicial",
        json={"saldo_inicial_caja": "777.77", "motivo": "corrección real"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["saldo_inicial_caja"] == "777.77"
    assert (
        await MesControl.find_one(MesControl.mes == "2026-08-01")
    ).saldo_inicial_caja == Decimal("777.77")
