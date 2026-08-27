# backend/tests/test_caja_disponible.py
"""Saldo disponible EN VIVO (CEO 2026-08-24) — el número que el CEO quiere ver fijo y
siempre visible, actualizado cada vez que se cargan movimientos de banco.

El norte del módulo caja ya nombra las DOS entradas diarias: los movimientos del banco
y **el valor de la caja disponible**. Esto último, en vivo.

Definición (la MISMA que la conciliación del cierre y que el arranque del ciclo mensual
— para que nunca haya dos "saldos" distintos en la app):

    disponible(banco) = saldo reportado(banco) @ fecha_reporte
                        + Σ signo(movimientos de ese banco con fecha > fecha_reporte)
    total = Σ disponible(banco) + tránsito heredado (Wava)

Se verificó al peso contra el Excel del CEO (`Flujo de pagos deudas.xlsx`, ago-2026):
665.715.578 (cierre de julio) + neto de agosto = 697.232.181 = «Caja disponible total».

`saldo_disponible` NO toca el motor ni escribe estado: lectura pura. Reusa
`cierre.service.conciliacion` (no redefine el cálculo) y le agrega la FRESCURA: qué tan
viejo es el último movimiento por banco, para que el CEO sepa si el número está al día.
"""

from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.caja import service as caja_service
from app.config import get_settings
from app.core.time import today_bogota
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
    ]:
        await repository.create_user(
            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
        )
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


async def _token(ac, email="fin@roddos.com") -> dict:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _rubro(nombre) -> Rubro:
    return await Rubro.find_one(Rubro.nombre == nombre)


async def _mes(mes, estado, saldo_inicial="0", bancos=None, transito="0") -> MesControl:
    mc = MesControl(
        mes=mes,
        saldo_inicial_caja=Decimal(saldo_inicial),
        estado=estado,
        saldos_banco=bancos or [],
        transito_wava=Decimal(transito),
    )
    await mc.insert()
    return mc


async def _tx(mc, rubro, valor, tipo, banco="global66", fecha=None):
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


# ─────────────────────── el cálculo del saldo ───────────────────────


@pytest.mark.asyncio
async def test_disponible_por_banco_es_reportado_mas_movimientos_posteriores(api):
    """El caso real de agosto, a escala: reportado + lo que entró/salió después."""
    await _token(api)
    sb = SaldoBanco(
        banco="global66", saldo=Decimal("665715578"), fecha_reporte="2026-08-01"
    )
    mc = await _mes("2026-08-01", EstadoMes.EN_EJECUCION, "665715578", [sb])
    arr = await _rubro("Arriendos")
    await _tx(mc, arr, "222058008.78", "ingreso", fecha="2026-08-11")
    await _tx(mc, arr, "190541405.91", "egreso", fecha="2026-08-24")

    r = await caja_service.saldo_disponible()
    assert r["disponible"] is True
    g66 = next(b for b in r["por_banco"] if b["banco"] == "global66")
    # 665.715.578 + 222.058.008,78 − 190.541.405,91 = 697.232.180,87
    assert g66["saldo"] == "697232180.87"
    assert g66["reportado"] == "665715578.00"
    assert r["saldo_en_banco"] == "697232180.87"


@pytest.mark.asyncio
async def test_el_total_suma_el_transito_heredado_wava(api):
    """total = saldo en banco + Wava en tránsito (heredado del cierre). La MISMA
    definición que `caja_inicial_total` del ciclo y que «Banco + Wava» del Excel."""
    await _token(api)
    # julio cerró con 12.000.000 en tránsito Wava
    await _mes("2026-07-01", EstadoMes.CERRADO, "500000000", transito="12000000")
    sb = SaldoBanco(
        banco="global66", saldo=Decimal("665715578"), fecha_reporte="2026-08-01"
    )
    await _mes("2026-08-01", EstadoMes.EN_EJECUCION, "665715578", [sb])

    r = await caja_service.saldo_disponible()
    assert r["saldo_en_banco"] == "665715578.00"
    assert r["transito_wava"] == "12000000.00"
    assert r["total"] == "677715578.00"  # 665.715.578 + 12.000.000


@pytest.mark.asyncio
async def test_el_calculado_NO_DIVERGE_de_la_conciliacion(api):
    """Candado anti-divergencia: el saldo del widget debe ser EXACTAMENTE el `calculado`
    de la conciliación del cierre. Si algún día difieren, hay dos 'saldos' en la app —
    justo lo que este diseño evita."""
    from app.cierre.service import conciliacion

    await _token(api)
    sb = SaldoBanco(
        banco="global66", saldo=Decimal("100000000"), fecha_reporte="2026-08-01"
    )
    mc = await _mes("2026-08-01", EstadoMes.EN_EJECUCION, "100000000", [sb])
    arr = await _rubro("Arriendos")
    await _tx(mc, arr, "5000000", "ingreso", fecha="2026-08-15")

    disp = await caja_service.saldo_disponible()
    conc = await conciliacion("2026-08-01")
    g_disp = next(b for b in disp["por_banco"] if b["banco"] == "global66")
    g_conc = next(b for b in conc["por_banco"] if b["banco"] == "global66")
    assert g_disp["saldo"] == g_conc["calculado"]
    assert disp["saldo_en_banco"] == conc["consolidado_reportado"]


# ─────────────────────── la frescura ───────────────────────


@pytest.mark.asyncio
async def test_frescura_al_dia_cuando_el_ultimo_movimiento_es_hoy(api):
    await _token(api)
    hoy = today_bogota().isoformat()
    sb = SaldoBanco(banco="global66", saldo=Decimal("100"), fecha_reporte="2026-08-01")
    mc = await _mes("2026-08-01", EstadoMes.EN_EJECUCION, "100", [sb])
    arr = await _rubro("Arriendos")
    await _tx(mc, arr, "10", "ingreso", fecha=hoy)

    r = await caja_service.saldo_disponible()
    g66 = next(b for b in r["por_banco"] if b["banco"] == "global66")
    assert g66["ultimo_movimiento"] == hoy
    assert g66["dias_sin_registrar"] == 0
    assert r["frescura"]["estado"] == "al_dia"


@pytest.mark.asyncio
async def test_frescura_atrasada_avisa_cuando_faltan_dias(api):
    await _token(api)
    hace_cinco = (today_bogota() - timedelta(days=5)).isoformat()
    sb = SaldoBanco(banco="global66", saldo=Decimal("100"), fecha_reporte="2026-08-01")
    mc = await _mes(f"{hace_cinco[:7]}-01", EstadoMes.EN_EJECUCION, "100", [sb])
    arr = await _rubro("Arriendos")
    await _tx(mc, arr, "10", "ingreso", fecha=hace_cinco)

    r = await caja_service.saldo_disponible()
    assert r["frescura"]["dias"] >= 5
    assert r["frescura"]["estado"] == "atrasado"


# ─────────────────────── honestidad y casos borde ───────────────────────


@pytest.mark.asyncio
async def test_banco_con_movimientos_sin_saldo_reportado_va_a_sin_dato(api):
    """Regla 7: un banco con movimientos pero sin saldo reportado NO se calcula contra
    0 — se reporta aparte para que el CEO sepa que falta reportarlo."""
    await _token(api)
    sb = SaldoBanco(banco="global66", saldo=Decimal("100"), fecha_reporte="2026-08-01")
    mc = await _mes("2026-08-01", EstadoMes.EN_EJECUCION, "100", [sb])
    arr = await _rubro("Arriendos")
    await _tx(mc, arr, "50", "egreso", banco="bbva", fecha="2026-08-10")

    r = await caja_service.saldo_disponible()
    assert "bbva" in r["sin_dato"]
    assert all(b["banco"] != "bbva" for b in r["por_banco"])


@pytest.mark.asyncio
async def test_sin_mes_en_ejecucion_responde_sin_reventar(api):
    """No hay mes operando: la respuesta lo dice, no inventa un saldo."""
    await _token(api)
    await _mes("2026-07-01", EstadoMes.CERRADO, "100")
    r = await caja_service.saldo_disponible()
    assert r["disponible"] is False
    assert r["motivo"] == "sin_mes_en_ejecucion"


# ─────────────────────── el endpoint ───────────────────────


@pytest.mark.asyncio
async def test_endpoint_devuelve_el_saldo_con_permiso_de_lectura(api):
    h = await _token(api, "consulta@roddos.com")  # dashboard:leer basta
    sb = SaldoBanco(
        banco="global66", saldo=Decimal("665715578"), fecha_reporte="2026-08-01"
    )
    await _mes("2026-08-01", EstadoMes.EN_EJECUCION, "665715578", [sb])
    r = await api.get("/api/v1/caja/disponible", headers=h)
    assert r.status_code == 200
    assert r.json()["saldo_en_banco"] == "665715578.00"


@pytest.mark.asyncio
async def test_endpoint_exige_autenticacion(api):
    r = await api.get("/api/v1/caja/disponible")
    assert r.status_code == 401
