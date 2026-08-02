# backend/tests/test_cierre_conciliacion.py
"""Conciliación por banco + guardas del cierre/reapertura — parte mongomock.

MARCADO PARA AUDITORÍA KIMI (regla 8 + §2.4 + M-3 conciliación).

La conciliación es compute-only (mongomock la soporta): ancla por banco, 'sin dato'
(regla 7), exclusión del rubro de ajuste. La transacción multi-doc del cierre y la
convergencia viven en el archivo real-mongo hermano; aquí las GUARDAS (RBAC/estado/
M+1/umbral) que retornan ANTES de la transacción."""

from decimal import Decimal

import httpx
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.cierre import service
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.configuracion import Configuracion
from app.domain.mes_control import EstadoMes, MesControl, SaldoBanco
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion
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
        ("admin@roddos.com", Role.admin),
    ]:
        await repository.create_user(
            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
        )
    # semilla: umbral + rubros (sistema 'Ajuste de conciliación' + uno operativo)
    await Configuracion(
        clave="UMBRAL_DIF_BANCO_CIERRE",
        valor_decimal=Decimal("50000"),
        vigente_desde="2026-01-01",
    ).insert()
    await Rubro(
        grupo="otros", nombre="Ajuste de conciliación", orden=98, es_sistema=True
    ).insert()
    await Rubro(
        grupo="operacion", nombre="Arriendos", orden=4, es_sistema=False
    ).insert()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _token(ac, email="admin@roddos.com") -> dict:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _rubro(nombre) -> Rubro:
    return await Rubro.find_one(Rubro.nombre == nombre)


async def _mes(mes, estado, saldo_inicial="100", bancos=None) -> MesControl:
    mc = MesControl(
        mes=mes,
        saldo_inicial_caja=Decimal(saldo_inicial),
        estado=estado,
        saldos_banco=bancos or [],
    )
    await mc.insert()
    return mc


async def _tx(mc, rubro, valor, tipo, banco="bancolombia", fecha=None):
    import app.core.ulid as u

    await Transaccion(
        fecha=fecha or f"{mc.mes[:7]}-10",
        descripcion="mov",
        valor=Decimal(valor),
        tipo_flujo=tipo,
        rubro_id=rubro.id,
        mes_id=mc.id,
        banco=banco,
        id_banco=f"MAN-{u.new_ulid()}",
    ).insert()


# ── CONCILIACIÓN (compute-only) ─────────────────────────────────────────────


async def test_conciliacion_reporte_y_diferencia(api):
    h = await _token(api, "fin@roddos.com")
    sb = SaldoBanco(
        banco="bancolombia", saldo=Decimal("118"), fecha_reporte="2026-07-31"
    )
    mc = await _mes("2026-07-01", EstadoMes.EN_EJECUCION, "100", [sb])
    arr = await _rubro("Arriendos")
    await _tx(mc, arr, "50", "ingreso")
    await _tx(mc, arr, "30", "egreso")
    r = await api.post("/api/v1/meses/2026-07/cierre/conciliacion", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["caja_libro"] == "120.00"  # 100 + 50 − 30
    assert d["consolidado_reportado"] == "118.00"
    assert d["diferencia"] == "-2.00"  # 118 − 120
    assert d["dentro_de_umbral"] is True
    assert d["sin_dato"] == []


async def test_conciliacion_excluye_rubro_ajuste(api):
    h = await _token(api, "fin@roddos.com")
    sb = SaldoBanco(
        banco="bancolombia", saldo=Decimal("120"), fecha_reporte="2026-07-31"
    )
    mc = await _mes("2026-07-01", EstadoMes.EN_EJECUCION, "100", [sb])
    arr = await _rubro("Arriendos")
    aj = await _rubro("Ajuste de conciliación")
    await _tx(mc, arr, "50", "ingreso")
    await _tx(mc, arr, "30", "egreso")
    await _tx(mc, aj, "999", "egreso")  # NO debe contar en la caja del libro
    r = await api.post("/api/v1/meses/2026-07/cierre/conciliacion", headers=h)
    assert r.json()["caja_libro"] == "120.00"  # el ajuste de 999 se excluye


async def test_conciliacion_sin_dato_por_banco(api):
    h = await _token(api, "fin@roddos.com")
    sb = SaldoBanco(
        banco="bancolombia", saldo=Decimal("100"), fecha_reporte="2026-07-31"
    )
    mc = await _mes("2026-07-01", EstadoMes.EN_EJECUCION, "100", [sb])
    arr = await _rubro("Arriendos")
    await _tx(mc, arr, "10", "egreso", banco="bbva")  # bbva sin saldo reportado
    r = await api.post("/api/v1/meses/2026-07/cierre/conciliacion", headers=h)
    d = r.json()
    assert "bbva" in d["sin_dato"]
    assert d["dentro_de_umbral"] is False  # no se puede conciliar bbva


# ── A-2: MANUAL fuera de la conciliación (D-FIX-1: manual = banco omitido) ───


async def test_conciliacion_tx_manual_no_exige_saldo_ni_mueve_diferencia(api):
    # P1-5: una tx manual ya NO deja 'manual' en sin_dato → el mes puede cerrar.
    # Y la diferencia es idéntica al baseline (el mismo egreso como bancolombia da
    # -2.00): relabelar una tx como manual no mueve R_M ni C_M, solo quita el
    # falso sin_dato y expone manual_neto.
    h = await _token(api, "fin@roddos.com")
    sb = SaldoBanco(
        banco="bancolombia", saldo=Decimal("118"), fecha_reporte="2026-07-31"
    )
    mc = await _mes("2026-07-01", EstadoMes.EN_EJECUCION, "100", [sb])
    arr = await _rubro("Arriendos")
    await _tx(mc, arr, "50", "ingreso")  # bancolombia
    await _tx(mc, arr, "30", "egreso", banco="manual")  # el egreso es MANUAL
    r = await api.post("/api/v1/meses/2026-07/cierre/conciliacion", headers=h)
    d = r.json()
    assert d["caja_libro"] == "120.00"  # 100 + 50 − 30 (manual cuenta en C_M)
    assert d["consolidado_reportado"] == "118.00"  # manual no es banco reportado
    assert d["diferencia"] == "-2.00"  # invariante: no se mueve por lo manual
    assert "manual" not in d["sin_dato"]  # ya no exige saldo 'manual'
    assert d["dentro_de_umbral"] is True
    assert d["manual_neto"] == "-30.00"  # egreso manual = negativo
    assert d["aviso_manual"] is False  # |30| < umbral 50000


async def test_conciliacion_manual_neto_signo_ingreso(api):
    h = await _token(api, "fin@roddos.com")
    sb = SaldoBanco(
        banco="bancolombia", saldo=Decimal("100"), fecha_reporte="2026-07-31"
    )
    mc = await _mes("2026-07-01", EstadoMes.EN_EJECUCION, "100", [sb])
    arr = await _rubro("Arriendos")
    await _tx(mc, arr, "30", "ingreso", banco="manual")
    r = await api.post("/api/v1/meses/2026-07/cierre/conciliacion", headers=h)
    assert r.json()["manual_neto"] == "30.00"  # ingreso manual = positivo


async def test_conciliacion_manual_neto_grande_dispara_aviso(api):
    # |manual_neto| > umbral → aviso_manual visible, aunque la diferencia cuadre.
    h = await _token(api, "fin@roddos.com")
    sb = SaldoBanco(
        banco="bancolombia", saldo=Decimal("40000"), fecha_reporte="2026-07-31"
    )
    mc = await _mes("2026-07-01", EstadoMes.EN_EJECUCION, "100000", [sb])
    arr = await _rubro("Arriendos")
    await _tx(mc, arr, "60000", "egreso", banco="manual")
    r = await api.post("/api/v1/meses/2026-07/cierre/conciliacion", headers=h)
    d = r.json()
    assert d["manual_neto"] == "-60000.00"
    assert d["aviso_manual"] is True  # |60000| > 50000
    assert d["dentro_de_umbral"] is True  # diff = 40000 − 40000 = 0


async def test_conciliacion_no_en_ejecucion_409(api):
    h = await _token(api, "fin@roddos.com")
    await _mes("2026-07-01", EstadoMes.SUGERIDO)
    r = await api.post("/api/v1/meses/2026-07/cierre/conciliacion", headers=h)
    assert r.status_code == 409


async def test_cierre_operativo_consulta_403(api):
    h = await _token(api, "consulta@roddos.com")
    await _mes("2026-07-01", EstadoMes.EN_EJECUCION)
    r = await api.post("/api/v1/meses/2026-07/cierre/conciliacion", headers=h)
    assert r.status_code == 403


# ── CONFIRMAR CIERRE — guardas (antes de la transacción) ────────────────────


async def test_confirmar_no_admin_403(api):
    for email in ("fin@roddos.com", "consulta@roddos.com"):
        h = await _token(api, email)
        r = await api.post(
            "/api/v1/meses/2026-07/cierre/confirmar",
            headers={**h, "Idempotency-Key": f"k-{email}"},
        )
        assert r.status_code == 403, email


async def test_confirmar_mes_inexistente_404(api):
    h = await _token(api)
    r = await api.post(
        "/api/v1/meses/2026-07/cierre/confirmar", headers={**h, "Idempotency-Key": "k1"}
    )
    assert r.status_code == 404


async def test_confirmar_no_en_ejecucion_409(api):
    h = await _token(api)
    await _mes("2026-07-01", EstadoMes.SUGERIDO)
    r = await api.post(
        "/api/v1/meses/2026-07/cierre/confirmar", headers={**h, "Idempotency-Key": "k1"}
    )
    assert r.status_code == 409


async def test_confirmar_sin_mes_siguiente_409(api):
    h = await _token(api)
    sb = SaldoBanco(
        banco="bancolombia", saldo=Decimal("100"), fecha_reporte="2026-07-31"
    )
    await _mes("2026-07-01", EstadoMes.EN_EJECUCION, "100", [sb])
    r = await api.post(
        "/api/v1/meses/2026-07/cierre/confirmar", headers={**h, "Idempotency-Key": "k1"}
    )
    assert r.status_code == 409  # agosto no está abierto (D2)


async def test_confirmar_diferencia_supera_umbral_409(api):
    h = await _token(api)
    # umbral chico → la diferencia de 2 lo supera
    await Configuracion(
        clave="UMBRAL_DIF_BANCO_CIERRE",
        valor_decimal=Decimal("1"),
        vigente_desde="2026-06-01",
    ).insert()
    sb = SaldoBanco(
        banco="bancolombia", saldo=Decimal("118"), fecha_reporte="2026-07-31"
    )
    mc = await _mes("2026-07-01", EstadoMes.EN_EJECUCION, "100", [sb])
    await _mes("2026-08-01", EstadoMes.SUGERIDO, "0")  # M+1 abierto
    arr = await _rubro("Arriendos")
    await _tx(mc, arr, "50", "ingreso")
    await _tx(mc, arr, "30", "egreso")  # C_M=120, R_M=118, dif=-2 > umbral 1
    r = await api.post(
        "/api/v1/meses/2026-07/cierre/confirmar", headers={**h, "Idempotency-Key": "k1"}
    )
    assert r.status_code == 409


# ── REAPERTURA — guardas ────────────────────────────────────────────────────


async def test_reabrir_no_cerrado_409_service(api):
    # guarda de estado a nivel de servicio (retorna antes de cualquier transacción).
    await _mes("2026-07-01", EstadoMes.EN_EJECUCION)
    try:
        await service.reabrir_mes(mes="2026-07-01", usuario_id="u1")
        raise AssertionError("debió fallar")
    except service.CierreError as e:
        assert e.status == 409


async def test_reabrir_no_admin_403(api):
    h = await _token(api, "fin@roddos.com")
    await _mes("2026-07-01", EstadoMes.CERRADO)
    r = await api.post("/api/v1/meses/2026-07/reabrir", headers=h)
    assert r.status_code == 403


async def test_reabrir_admin_sin_step_up_403(api):
    # S4-06/B-3 (Kimi I-PR1 cierre): POST /reabrir exige step-up MFA — un admin
    # SIN 2º factor reciente es rechazado. Este test BLINDA el `require_step_up`
    # del router contra una refactorización que lo quite sin que CI lo note.
    h = await _token(api, "admin@roddos.com")  # login sin MFA → sin mfa_at
    await _mes("2026-07-01", EstadoMes.CERRADO)
    r = await api.post("/api/v1/meses/2026-07/reabrir", headers=h)
    assert r.status_code == 403
    assert "Step-up" in r.json()["detail"]
    # y el mes NO se tocó
    mc = await MesControl.find_one(MesControl.mes == "2026-07-01")
    assert mc.estado is EstadoMes.CERRADO
