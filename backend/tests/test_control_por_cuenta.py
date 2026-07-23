# backend/tests/test_control_por_cuenta.py
"""C5 — vista combinada categoría × cuenta (GET /meses/{mes}/control/por-cuenta).

READ-ONLY → todo mongomock. Cubre: matriz rubro×banco, RECONCILIACIÓN con la Vista
Control (Σ_banco = ejecutado por rubro), totales por banco, guardas (404/409), RBAC,
serialización en strings (regla 1) y sin_presupuesto por cuenta (B-3)."""

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
    # la Vista Control (que C5 debe reconciliar) calcula caja y necesita el rubro
    # de sistema 'Ajuste de conciliación' (fail-loud, B-1 I-PR1).
    await Rubro(
        grupo="otros", nombre="Ajuste de conciliación", orden=97, es_sistema=True
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


async def _mes(estado=EstadoMes.EN_EJECUCION) -> MesControl:
    mc = MesControl(mes="2026-07-01", saldo_inicial_caja=Decimal("0"), estado=estado)
    await mc.insert()
    return mc


_ORD = [0]


async def _rubro(nombre, grupo="operacion", sistema=False) -> Rubro:
    _ORD[0] += 1
    r = Rubro(grupo=grupo, nombre=nombre, orden=_ORD[0], es_sistema=sistema)
    await r.insert()
    return r


async def _linea(mc, rubro, definido) -> None:
    await PresupuestoLinea(
        mes_id=mc.id,
        rubro_id=rubro.id,
        monto_sugerido=Decimal(definido),
        prom_3m=Decimal(definido),
        tendencia_mes=Decimal("0"),
        crec_pct=Decimal("0"),
        historia_incompleta=False,
        monto_definido=Decimal(definido),
    ).insert()


async def _tx(mc, rubro, valor, banco="bancolombia", tipo="egreso") -> None:
    import app.core.ulid as u

    await Transaccion(
        fecha=f"{mc.mes[:7]}-10",
        descripcion="mov",
        valor=Decimal(valor),
        tipo_flujo=tipo,
        rubro_id=rubro.id,
        mes_id=mc.id,
        banco=banco,
        id_banco=f"MAN-{u.new_ulid()}",
    ).insert()


def _fila(data, rubro_id):
    for g in data["grupos"]:
        for f in g["lineas"]:
            if f["rubro_id"] == rubro_id:
                return f
    raise AssertionError("rubro no encontrado")


async def test_matriz_rubro_por_banco(api):
    h = await _token(api)
    mc = await _mes()
    r = await _rubro("Arriendos")
    await _linea(mc, r, "1000000")
    await _tx(mc, r, "600000", banco="bancolombia")
    await _tx(mc, r, "300000", banco="global66")
    data = (await api.get("/api/v1/meses/2026-07/control/por-cuenta", headers=h)).json()
    assert set(data["bancos"]) == {"bancolombia", "global66"}
    f = _fila(data, str(r.id))
    assert f["por_banco"]["bancolombia"] == "600000.00"
    assert f["por_banco"]["global66"] == "300000.00"
    assert f["total"] == "900000.00"


async def test_reconcilia_con_vista_control(api):
    # C5 debe cuadrar con la Vista Control: Σ_banco(por_banco) == ejecutado del rubro.
    h = await _token(api)
    mc = await _mes()
    r = await _rubro("Cafetería")
    await _linea(mc, r, "500000")
    await _tx(mc, r, "120000", banco="bancolombia")
    await _tx(mc, r, "80000", banco="bbva")
    control = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
    cuenta = (
        await api.get("/api/v1/meses/2026-07/control/por-cuenta", headers=h)
    ).json()
    ejec_control = _fila(control, str(r.id))["ejecutado"]
    fila_cuenta = _fila(cuenta, str(r.id))
    assert ejec_control == "200000.00"
    assert fila_cuenta["total"] == ejec_control  # reconcilia
    assert cuenta["total"]["total"] == "200000.00"
    assert cuenta["total"]["por_banco"]["bancolombia"] == "120000.00"
    assert cuenta["total"]["por_banco"]["bbva"] == "80000.00"


async def test_rubro_sin_movimiento_en_un_banco_es_cero(api):
    h = await _token(api)
    mc = await _mes()
    r = await _rubro("Servicios")
    await _linea(mc, r, "100000")
    await _tx(mc, r, "50000", banco="bancolombia")  # Servicios solo en bancolombia
    r2 = await _rubro("Papelería")
    await _linea(mc, r2, "100000")
    await _tx(mc, r2, "10000", banco="global66")  # OTRO rubro usa global66
    data = (await api.get("/api/v1/meses/2026-07/control/por-cuenta", headers=h)).json()
    f = _fila(data, str(r.id))
    # global66 es columna (por Papelería) pero Servicios no lo usó → 0
    assert f["por_banco"]["global66"] == "0.00"


async def test_mes_inexistente_404(api):
    h = await _token(api)
    r = await api.get("/api/v1/meses/2026-07/control/por-cuenta", headers=h)
    assert r.status_code == 404


async def test_mes_sugerido_409(api):
    h = await _token(api)
    await _mes(estado=EstadoMes.SUGERIDO)
    r = await api.get("/api/v1/meses/2026-07/control/por-cuenta", headers=h)
    assert r.status_code == 409


async def test_consulta_puede_leer(api):
    # dashboard:leer lo tienen los 4 roles (read-only).
    h = await _token(api, "consulta@roddos.com")
    await _mes()
    r = await api.get("/api/v1/meses/2026-07/control/por-cuenta", headers=h)
    assert r.status_code == 200


async def test_sin_presupuesto_por_cuenta(api):
    # egreso en un rubro NO de sistema y sin línea vigente → informativo (B-3).
    h = await _token(api)
    mc = await _mes()
    r = await _rubro("Fletes")  # sin línea
    await _tx(mc, r, "70000", banco="bbva")
    data = (await api.get("/api/v1/meses/2026-07/control/por-cuenta", headers=h)).json()
    assert any(
        s["rubro"] == "Fletes" and s["por_banco"]["bbva"] == "70000.00"
        for s in data["sin_presupuesto"]
    )
