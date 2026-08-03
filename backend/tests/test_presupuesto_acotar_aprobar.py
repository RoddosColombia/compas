# backend/tests/test_presupuesto_acotar_aprobar.py
"""Acotamiento (§2.4) + guardas de aprobación — parte mongomock.

MARCADO PARA AUDITORÍA KIMI (tabla de autoridad §2.4 + saga O1).

Cubre acotar END-TO-END (mongomock lo soporta: no usa transacción Mongo): happy,
comentario persistido, M-1 (sugerido→propuesto), M-2 (compensación si el emit de
auditoría falla), RBAC y guardas de estado. La transacción multi-doc de la
aprobación (regla 8) y su convergencia viven en el archivo real-mongo hermano; aquí
solo se prueban las GUARDAS de aprobar (RBAC/estado), que retornan ANTES de la
transacción."""

from decimal import Decimal

import httpx
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.presupuesto import PresupuestoLinea
from app.domain.rubro import Rubro
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


async def _mes(mesd: str, estado: EstadoMes) -> MesControl:
    mc = MesControl(mes=mesd, saldo_inicial_caja=Decimal("0"), estado=estado)
    await mc.insert()
    return mc


async def _rubro(nombre: str, orden: int) -> Rubro:
    r = Rubro(grupo="operacion", nombre=nombre, orden=orden, es_sistema=False)
    await r.insert()
    return r


async def _linea(
    mes_id, rubro_id, sugerido="1000000", definido=None
) -> PresupuestoLinea:
    ln = PresupuestoLinea(
        mes_id=mes_id,
        rubro_id=rubro_id,
        monto_sugerido=Decimal(sugerido),
        prom_3m=Decimal(sugerido),
        tendencia_mes=Decimal("0"),
        crec_pct=Decimal("0"),
        historia_incompleta=False,
        monto_definido=Decimal(definido) if definido is not None else None,
    )
    await ln.insert()
    return ln


# ── ACOTAR (solo guardas; happy path + convergencia en real-mongo, S4-00) ──


async def test_acotar_consulta_403(api):
    h = await _token(api, "consulta@roddos.com")
    mc = await _mes("2026-07-01", EstadoMes.SUGERIDO)
    rubro = await _rubro("Arriendos", 4)
    await _linea(mc.id, rubro.id)
    r = await api.patch(
        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
        json={"monto_definido": "1"},
        headers=h,
    )
    assert r.status_code == 403


async def test_acotar_mes_cerrado_409(api):
    h = await _token(api)
    mc = await _mes("2026-07-01", EstadoMes.CERRADO)
    rubro = await _rubro("Arriendos", 4)
    await _linea(mc.id, rubro.id)
    r = await api.patch(
        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
        json={"monto_definido": "1"},
        headers=h,
    )
    assert r.status_code == 409


async def test_acotar_mes_definido_409(api):
    h = await _token(api)
    mc = await _mes("2026-07-01", EstadoMes.DEFINIDO)
    rubro = await _rubro("Arriendos", 4)
    await _linea(mc.id, rubro.id)
    r = await api.patch(
        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
        json={"monto_definido": "1"},
        headers=h,
    )
    assert r.status_code == 409


async def test_acotar_sin_linea_404(api):
    h = await _token(api)
    await _mes("2026-07-01", EstadoMes.SUGERIDO)
    rubro = await _rubro("Arriendos", 4)  # sin línea creada
    r = await api.patch(
        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
        json={"monto_definido": "1"},
        headers=h,
    )
    assert r.status_code == 404


async def test_acotar_monto_negativo_422(api):
    h = await _token(api)
    mc = await _mes("2026-07-01", EstadoMes.SUGERIDO)
    rubro = await _rubro("Arriendos", 4)
    await _linea(mc.id, rubro.id)
    r = await api.patch(
        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
        json={"monto_definido": "-5"},
        headers=h,
    )
    assert r.status_code == 422


# FIX-G1: re-acotación en ejecución. El mes en_ejecucion ES acotable (ajuste del
# presupuesto ya aprobado), pero SOLO con comentario que lo justifique (todo cambio
# post-aprobación queda auditado). Sin comentario → 422 (guarda, antes de la sesión).


async def test_acotar_en_ejecucion_sin_comentario_422(api):
    h = await _token(api)
    mc = await _mes("2026-07-01", EstadoMes.EN_EJECUCION)
    rubro = await _rubro("Arriendos", 4)
    await _linea(mc.id, rubro.id, definido="1000000")
    r = await api.patch(
        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
        json={"monto_definido": "1200000"},  # sin comentario
        headers=h,
    )
    assert r.status_code == 422


async def test_acotar_en_ejecucion_comentario_en_blanco_422(api):
    h = await _token(api)
    mc = await _mes("2026-07-01", EstadoMes.EN_EJECUCION)
    rubro = await _rubro("Arriendos", 4)
    await _linea(mc.id, rubro.id, definido="1000000")
    r = await api.patch(
        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
        json={"monto_definido": "1200000", "comentario": "   "},  # solo espacios
        headers=h,
    )
    assert r.status_code == 422


# La compensación O1 del acotar (emit falla → revierte) migró a
# test_presupuesto_acotar_realmongo.py: S4-00 volvió transaccional el acotar y
# mongomock no soporta sesiones.


# ── APROBAR (solo guardas; happy path + convergencia en real-mongo) ─────────


async def test_aprobar_no_admin_403(api):
    for email in ("fin@roddos.com", "dir@roddos.com", "consulta@roddos.com"):
        h = await _token(api, email)
        r = await api.post(
            "/api/v1/meses/2026-07/presupuesto/aprobar",
            headers={**h, "Idempotency-Key": f"k-{email}"},
        )
        assert r.status_code == 403, email


async def test_aprobar_mes_inexistente_404(api):
    h = await _token(api, "admin@roddos.com")
    r = await api.post(
        "/api/v1/meses/2026-07/presupuesto/aprobar",
        headers={**h, "Idempotency-Key": "k1"},
    )
    assert r.status_code == 404


async def test_aprobar_mes_cerrado_409(api):
    h = await _token(api, "admin@roddos.com")
    await _mes("2026-07-01", EstadoMes.CERRADO)
    r = await api.post(
        "/api/v1/meses/2026-07/presupuesto/aprobar",
        headers={**h, "Idempotency-Key": "k1"},
    )
    assert r.status_code == 409


async def test_aprobar_mes_ya_definido_409(api):
    h = await _token(api, "admin@roddos.com")
    await _mes("2026-07-01", EstadoMes.DEFINIDO)
    r = await api.post(
        "/api/v1/meses/2026-07/presupuesto/aprobar",
        headers={**h, "Idempotency-Key": "k1"},
    )
    assert r.status_code == 409


async def test_aprobar_sin_lineas_409(api):
    h = await _token(api, "admin@roddos.com")
    await _mes("2026-07-01", EstadoMes.PROPUESTO)  # sin líneas
    r = await api.post(
        "/api/v1/meses/2026-07/presupuesto/aprobar",
        headers={**h, "Idempotency-Key": "k1"},
    )
    assert r.status_code == 409


async def test_aprobar_peticion_fallida_no_quema_la_key(api):
    # una guarda fallida borra la marca → se puede reintentar con la misma key.
    h = await _token(api, "admin@roddos.com")
    await _mes("2026-07-01", EstadoMes.DEFINIDO)
    r1 = await api.post(
        "/api/v1/meses/2026-07/presupuesto/aprobar",
        headers={**h, "Idempotency-Key": "k1"},
    )
    assert r1.status_code == 409
    r2 = await api.post(
        "/api/v1/meses/2026-07/presupuesto/aprobar",
        headers={**h, "Idempotency-Key": "k1"},
    )
    assert r2.status_code == 409  # no 422 "key con payload distinto"
