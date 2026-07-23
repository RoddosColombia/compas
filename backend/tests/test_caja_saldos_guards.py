# backend/tests/test_caja_saldos_guards.py
"""C4 — reporte diario de saldos por banco: GUARDAS (parte mongomock).

MARCADO PARA AUDITORÍA KIMI (CR-S6 + D2/D3 + regla 9).

Cubre lo que retorna ANTES de cualquier escritura: RBAC (`caja:reportar`), 404,
409 parametrizado (D3: sugerido/propuesto/cerrado), 422 banco desconocido/manual,
422 saldo no decimal, 422 banco repetido en el body, y las guardas de fecha D2
(fecha < día 1 del mes, fecha futura, no-retroceso por banco). El UPSERT atómico
posicional (B-1), la conciliación en la respuesta (D4), la auditoría por banco y la
saga O1 viven en el archivo real-mongo hermano (mongomock no implementa el operador
posicional `$` con fidelidad)."""

from decimal import Decimal

import httpx
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.bancos import Banco
from app.domain.mes_control import EstadoMes, MesControl, SaldoBanco
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

    from app.main import create_app

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
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _mes(
    estado=EstadoMes.EN_EJECUCION, saldos: list[SaldoBanco] | None = None
) -> MesControl:
    mc = MesControl(
        mes="2026-07-01",
        saldo_inicial_caja=Decimal("0"),
        estado=estado,
        saldos_banco=saldos or [],
    )
    await mc.insert()
    return mc


def _body(banco="global66", saldo="1000000.00", fecha="2026-07-15"):
    return {"saldos": [{"banco": banco, "saldo": saldo, "fecha_reporte": fecha}]}


# ── RBAC (caja:reportar = {financiero, admin}) ──


async def test_consulta_403(api):
    h = await _token(api, "consulta@roddos.com")
    await _mes()
    r = await api.patch("/api/v1/meses/2026-07/saldos", json=_body(), headers=h)
    assert r.status_code == 403


async def test_directivo_403(api):
    h = await _token(api, "dir@roddos.com")
    await _mes()
    r = await api.patch("/api/v1/meses/2026-07/saldos", json=_body(), headers=h)
    assert r.status_code == 403


# ── 404 / 409 (D3) ──


async def test_mes_inexistente_404(api):
    h = await _token(api)
    r = await api.patch("/api/v1/meses/2026-07/saldos", json=_body(), headers=h)
    assert r.status_code == 404


async def test_estado_no_en_ejecucion_409(api):
    # D3: el reporte diario es del mes OPERANDO; los demás estados → 409.
    for estado in (EstadoMes.SUGERIDO, EstadoMes.PROPUESTO, EstadoMes.CERRADO):
        mc = await _mes(estado=estado)
        h = await _token(api)
        r = await api.patch("/api/v1/meses/2026-07/saldos", json=_body(), headers=h)
        assert r.status_code == 409, estado
        await mc.delete()


# ── 422 banco / saldo / body ──


async def test_banco_desconocido_422(api):
    h = await _token(api)
    await _mes()
    r = await api.patch(
        "/api/v1/meses/2026-07/saldos", json=_body(banco="daviplata"), headers=h
    )
    assert r.status_code == 422


async def test_banco_manual_422(api):
    # 'manual' no es un banco de saldos (§1.3), igual que en la apertura.
    h = await _token(api)
    await _mes()
    r = await api.patch(
        "/api/v1/meses/2026-07/saldos", json=_body(banco="manual"), headers=h
    )
    assert r.status_code == 422


async def test_saldo_no_decimal_422(api):
    h = await _token(api)
    await _mes()
    r = await api.patch(
        "/api/v1/meses/2026-07/saldos", json=_body(saldo="mil"), headers=h
    )
    assert r.status_code == 422


async def test_saldo_como_numero_422(api):
    # Regla 1: el saldo viaja como STRING; strict rechaza el number del JSON.
    h = await _token(api)
    await _mes()
    r = await api.patch(
        "/api/v1/meses/2026-07/saldos",
        json={
            "saldos": [
                {"banco": "global66", "saldo": 1000000, "fecha_reporte": "2026-07-15"}
            ]
        },
        headers=h,
    )
    assert r.status_code == 422


async def test_banco_repetido_en_body_422(api):
    # Regla 7: dos entradas del mismo banco en una llamada = ambigüedad → 422.
    h = await _token(api)
    await _mes()
    r = await api.patch(
        "/api/v1/meses/2026-07/saldos",
        json={
            "saldos": [
                {"banco": "global66", "saldo": "1", "fecha_reporte": "2026-07-15"},
                {"banco": "global66", "saldo": "2", "fecha_reporte": "2026-07-16"},
            ]
        },
        headers=h,
    )
    assert r.status_code == 422


async def test_body_vacio_422(api):
    h = await _token(api)
    await _mes()
    r = await api.patch("/api/v1/meses/2026-07/saldos", json={"saldos": []}, headers=h)
    assert r.status_code == 422


# ── D2 — guardas de fecha (retornan antes de escribir) ──


async def test_fecha_antes_del_dia1_422(api):
    # Una fecha < día 1 contaría TODO el mes como "posterior" en la conciliación.
    h = await _token(api)
    await _mes()
    r = await api.patch(
        "/api/v1/meses/2026-07/saldos", json=_body(fecha="2026-06-30"), headers=h
    )
    assert r.status_code == 422


async def test_fecha_futura_422(api):
    # today_bogota() es 2026-07-22/23 en esta sesión; una fecha del futuro → 422.
    h = await _token(api)
    await _mes()
    r = await api.patch(
        "/api/v1/meses/2026-07/saldos", json=_body(fecha="2026-12-31"), headers=h
    )
    assert r.status_code == 422


async def test_fecha_mal_formada_422(api):
    h = await _token(api)
    await _mes()
    r = await api.patch(
        "/api/v1/meses/2026-07/saldos", json=_body(fecha="15/07/2026"), headers=h
    )
    assert r.status_code == 422


async def test_no_retroceso_por_banco_422(api):
    # No-retroceso: retrasar fecha_reporte re-incluiría movimientos viejos como
    # "posteriores" sin rastro → fail-loud (regla 7).
    await _mes(
        saldos=[
            SaldoBanco(
                banco=Banco.GLOBAL66, saldo=Decimal("5"), fecha_reporte="2026-07-10"
            )
        ]
    )
    h = await _token(api)
    r = await api.patch(
        "/api/v1/meses/2026-07/saldos", json=_body(fecha="2026-07-05"), headers=h
    )
    assert r.status_code == 422
