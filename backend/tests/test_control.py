# backend/tests/test_control.py
"""Vista Control — % ejecutado / disponible / semáforo (los 8 tests del gate I-PR1).

MARCADO PARA AUDITORÍA KIMI (% ejecutado — DoD #3). READ-ONLY → todo mongomock.
Cubre: dorado de celda · bordes del semáforo (sobre pct cuantizado, B-1) · caja con
el ajuste excluido y 'Por clasificar' incluido · guardas · RBAC 4 roles · equivalencia
$group · linealidad de subtotales · serialización (strings, B-2) · sin_presupuesto B-3.
"""

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
        ("dir@roddos.com", Role.directivo),
        ("admin@roddos.com", Role.admin),
    ]:
        await repository.create_user(
            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
        )
    await Rubro(
        grupo="otros", nombre="Ajuste de conciliación", orden=98, es_sistema=True
    ).insert()
    await Rubro(
        grupo="otros", nombre="Por clasificar", orden=99, es_sistema=True
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


async def _mes(
    mes="2026-07-01", estado=EstadoMes.EN_EJECUCION, saldo="0"
) -> MesControl:
    mc = MesControl(mes=mes, saldo_inicial_caja=Decimal(saldo), estado=estado)
    await mc.insert()
    return mc


_ORD = [0]


async def _rubro(nombre, grupo="operacion", sistema=False) -> Rubro:
    _ORD[0] += 1
    r = Rubro(grupo=grupo, nombre=nombre, orden=_ORD[0], es_sistema=sistema)
    await r.insert()
    return r


async def _linea(mc, rubro, definido) -> PresupuestoLinea:
    ln = PresupuestoLinea(
        mes_id=mc.id,
        rubro_id=rubro.id,
        monto_sugerido=Decimal(definido),
        prom_3m=Decimal(definido),
        tendencia_mes=Decimal("0"),
        crec_pct=Decimal("0"),
        historia_incompleta=False,
        monto_definido=Decimal(definido),
    )
    await ln.insert()
    return ln


async def _tx(mc, rubro, valor, tipo="egreso"):
    import app.core.ulid as u

    await Transaccion(
        fecha=f"{mc.mes[:7]}-10",
        descripcion="mov",
        valor=Decimal(valor),
        tipo_flujo=tipo,
        rubro_id=rubro.id,
        mes_id=mc.id,
        banco="bancolombia",
        id_banco=f"MAN-{u.new_ulid()}",
    ).insert()


def _fila(data, rubro_id):
    for g in data["grupos"]:
        for f in g["lineas"]:
            if f["rubro_id"] == rubro_id:
                return f
    raise AssertionError("rubro no encontrado en la respuesta")


# ── 1. Dorado de celda ──────────────────────────────────────────────────────


async def test_dorado_celda(api):
    h = await _token(api)
    mc = await _mes()
    r = await _rubro("Arriendos")
    await _linea(mc, r, "1000000")
    await _tx(mc, r, "900000")  # 90%
    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
    f = _fila(data, str(r.id))
    assert f["definido"] == "1000000.00"
    assert f["ejecutado"] == "900000.00"
    assert f["disponible"] == "100000.00"
    assert f["pct_ejecutado"] == "90.00"
    assert f["semaforo"] == "verde"


# ── 2. Bordes del semáforo (sobre pct cuantizado, B-1) ──────────────────────


async def test_bordes_semaforo(api):
    h = await _token(api)
    mc = await _mes()
    casos = [
        ("r90", "10000", "9000", "90.00", "verde"),
        ("r9001", "10000", "9001", "90.01", "amarillo"),
        ("r100", "10000", "10000", "100.00", "amarillo"),
        ("r10001", "10000", "10001", "100.01", "rojo"),
    ]
    ids = {}
    for nombre, defi, ejec, _, _ in casos:
        ru = await _rubro(nombre)
        await _linea(mc, ru, defi)
        await _tx(mc, ru, ejec)
        ids[nombre] = str(ru.id)
    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
    for nombre, _, _, pct, sem in casos:
        f = _fila(data, ids[nombre])
        assert f["pct_ejecutado"] == pct, nombre
        assert f["semaforo"] == sem, nombre


async def test_linea_de_rubro_inactivo_se_conserva(api):
    # B-2c (Kimi PLAN-I C1): desactivar un rubro NO borra su línea del ciclo en
    # curso — la Vista Control sigue mostrando el histórico (itera por líneas).
    h = await _token(api)
    mc = await _mes()
    ru = await _rubro("Renting")
    await _linea(mc, ru, "800000")
    await _tx(mc, ru, "300000")
    ru.activo = False  # baja lógica DESPUÉS de tener línea + ejecutado
    await ru.save()
    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
    f = _fila(data, str(ru.id))
    assert f["definido"] == "800000.00"
    assert f["ejecutado"] == "300000.00"


async def test_semaforo_definido_cero(api):
    h = await _token(api)
    mc = await _mes()
    con_gasto = await _rubro("SinPresupConGasto")
    sin_gasto = await _rubro("SinPresupSinGasto")
    await _linea(mc, con_gasto, "0")
    await _linea(mc, sin_gasto, "0")
    await _tx(mc, con_gasto, "500")
    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
    fc = _fila(data, str(con_gasto.id))
    assert fc["pct_ejecutado"] is None and fc["semaforo"] == "rojo"
    fs = _fila(data, str(sin_gasto.id))
    assert fs["pct_ejecutado"] is None and fs["semaforo"] == "verde"


# ── 3. Caja: excluye ajuste, incluye 'Por clasificar' ───────────────────────


async def test_caja_excluye_ajuste_incluye_por_clasificar(api):
    h = await _token(api)
    mc = await _mes(saldo="100000")
    arr = await _rubro("Arriendos")
    ajuste = await Rubro.find_one(Rubro.nombre == "Ajuste de conciliación")
    porclas = await Rubro.find_one(Rubro.nombre == "Por clasificar")
    await _linea(mc, arr, "50000")
    await _tx(mc, arr, "30000", "egreso")  # cuenta
    await _tx(mc, porclas, "20000", "egreso")  # cuenta en caja (dinero real)
    await _tx(mc, ajuste, "999999", "egreso")  # NO cuenta en caja
    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
    # caja = 100000 − 30000 − 20000 = 50000 (el ajuste de 999999 se excluye)
    assert data["caja_disponible"] == "50000.00"


# ── 4. Guardas ──────────────────────────────────────────────────────────────


async def test_mes_sugerido_409(api):
    h = await _token(api)
    await _mes(estado=EstadoMes.SUGERIDO)
    r = await api.get("/api/v1/meses/2026-07/control", headers=h)
    assert r.status_code == 409


async def test_mes_inexistente_404(api):
    h = await _token(api)
    r = await api.get("/api/v1/meses/2026-07/control", headers=h)
    assert r.status_code == 404


# ── 5. RBAC 4 roles (dashboard:leer) ────────────────────────────────────────


async def test_rbac_cuatro_roles(api):
    await _mes()
    for email in (
        "consulta@roddos.com",
        "fin@roddos.com",
        "dir@roddos.com",
        "admin@roddos.com",
    ):
        h = await _token(api, email)
        r = await api.get("/api/v1/meses/2026-07/control", headers=h)
        assert r.status_code == 200, email


# ── 6. Equivalencia $group (suma de varias tx) ──────────────────────────────


async def test_group_suma_multiples_tx(api):
    h = await _token(api)
    mc = await _mes()
    r = await _rubro("Arriendos")
    await _linea(mc, r, "1000000")
    await _tx(mc, r, "300000")
    await _tx(mc, r, "250000")
    await _tx(mc, r, "50000")  # total ejecutado 600000
    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
    assert _fila(data, str(r.id))["ejecutado"] == "600000.00"


# ── 7. Linealidad de subtotales y total ─────────────────────────────────────


async def test_linealidad_subtotales(api):
    h = await _token(api)
    mc = await _mes()
    r1 = await _rubro("A", grupo="operacion")
    r2 = await _rubro("B", grupo="operacion")
    r3 = await _rubro("C", grupo="nomina")
    for ru, defi, ejec in [(r1, "100", "40"), (r2, "200", "250"), (r3, "500", "100")]:
        await _linea(mc, ru, defi)
        await _tx(mc, ru, ejec)
    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
    for g in data["grupos"]:
        st = g["subtotal"]
        assert Decimal(st["disponible"]) == Decimal(st["definido"]) - Decimal(
            st["ejecutado"]
        )
    t = data["total"]
    assert Decimal(t["disponible"]) == Decimal(t["definido"]) - Decimal(t["ejecutado"])
    assert Decimal(t["definido"]) == Decimal("800")  # 100+200+500
    assert Decimal(t["ejecutado"]) == Decimal("390")  # 40+250+100


# ── 8. Serialización (strings, B-2) ─────────────────────────────────────────


async def test_serializacion_strings(api):
    h = await _token(api)
    mc = await _mes()
    r = await _rubro("Arriendos")
    await _linea(mc, r, "1000000")
    await _tx(mc, r, "500000")
    f = _fila(
        (await api.get("/api/v1/meses/2026-07/control", headers=h)).json(), str(r.id)
    )
    for k in ("definido", "ejecutado", "disponible", "pct_ejecutado"):
        assert isinstance(f[k], str), k


# ── B-3: egresos en rubro sin línea vigente (informativo) ───────────────────


async def test_sin_presupuesto_informativo(api):
    h = await _token(api)
    mc = await _mes()
    con = await _rubro("ConLinea")
    sin = await _rubro("SinLinea")  # egreso sin línea de presupuesto
    porclas = await Rubro.find_one(Rubro.nombre == "Por clasificar")
    await _linea(mc, con, "1000")
    await _tx(mc, con, "500")
    await _tx(mc, sin, "700")
    await _tx(mc, porclas, "300", "egreso")  # sistema: NO va a sin_presupuesto
    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
    nombres = {x["rubro"] for x in data["sin_presupuesto"]}
    assert "SinLinea" in nombres
    assert "Por clasificar" not in nombres  # de sistema, excluido
    assert "ConLinea" not in nombres  # tiene línea
