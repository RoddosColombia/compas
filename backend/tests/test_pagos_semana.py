# backend/tests/test_pagos_semana.py
"""C9/S5-01 — Pagos de la semana: CRUD, guardas y veredicto (parte mongomock).

MARCADO PARA AUDITORÍA KIMI (CR-S7 + D1/D2/D3/D4 + regla 4).

Cubre lo que NO necesita transacción Mongo: crear/editar/cancelar (insert+emit),
listar, guardas (RBAC, 404, 409 mes cerrado, 422 D1 rubro no-egreso/inactivo), y el
veredicto `pagos-semana` (compute-only sobre find). `marcar-pagado` (multi-doc,
regla 8) vive en el archivo real-mongo hermano."""

from datetime import timedelta
from decimal import Decimal

import httpx
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.core.time import today_bogota
from app.domain import DOMAIN_DOCUMENTS
from app.domain.configuracion import Configuracion
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.rubro import Rubro
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"
HOY = today_bogota().isoformat()
EN_SEMANA = (today_bogota() + timedelta(days=3)).isoformat()
FUERA = (today_bogota() + timedelta(days=30)).isoformat()
AYER = (today_bogota() - timedelta(days=1)).isoformat()


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
    # Insumos del veredicto (D4): umbral no hace falta; sí el rubro de sistema 'Ajuste'
    await Configuracion(
        clave="UMBRAL_DIF_BANCO_CIERRE",
        valor_decimal=Decimal("50000"),
        vigente_desde="2026-01-01",
    ).insert()
    await Rubro(
        grupo="otros", nombre="Ajuste de conciliación", orden=99, es_sistema=True
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


async def _mes(estado=EstadoMes.EN_EJECUCION, saldo="1000000") -> MesControl:
    mc = MesControl(
        mes=f"{HOY[:7]}-01", saldo_inicial_caja=Decimal(saldo), estado=estado
    )
    await mc.insert()
    return mc


async def _rubro(nombre="Proveedores", tipo="egreso", activo=True) -> Rubro:
    r = Rubro(
        grupo="deudas_obligaciones",
        nombre=nombre,
        tipo_flujo=tipo,
        orden=50,
        activo=activo,
    )
    await r.insert()
    return r


def _body(rubro_id, monto="100000", fecha=EN_SEMANA):
    return {
        "concepto": "Cuota proveedor",
        "acreedor": "Auteco",
        "monto": monto,
        "fecha_programada": fecha,
        "rubro_id": str(rubro_id),
    }


def _mescorto() -> str:
    return HOY[:7]


# ── Crear + RBAC + guardas ──


async def test_crear_ok(api):
    h = await _token(api)
    await _mes()
    r = await _rubro()
    resp = await api.post(
        f"/api/v1/meses/{_mescorto()}/pagos-planeados", json=_body(r.id), headers=h
    )
    assert resp.status_code == 201
    assert resp.json()["estado"] == "pendiente"
    assert resp.json()["monto"] == "100000.00"


async def test_crear_consulta_403(api):
    h = await _token(api, "consulta@roddos.com")
    await _mes()
    r = await _rubro()
    resp = await api.post(
        f"/api/v1/meses/{_mescorto()}/pagos-planeados", json=_body(r.id), headers=h
    )
    assert resp.status_code == 403


async def test_crear_mes_inexistente_404(api):
    h = await _token(api)
    r = await _rubro()
    resp = await api.post(
        f"/api/v1/meses/{_mescorto()}/pagos-planeados", json=_body(r.id), headers=h
    )
    assert resp.status_code == 404


async def test_crear_mes_cerrado_409(api):
    h = await _token(api)
    await _mes(estado=EstadoMes.CERRADO)
    r = await _rubro()
    resp = await api.post(
        f"/api/v1/meses/{_mescorto()}/pagos-planeados", json=_body(r.id), headers=h
    )
    assert resp.status_code == 409


async def test_crear_rubro_ingreso_422(api):
    # D1: el destino debe ser EGRESO.
    h = await _token(api)
    await _mes()
    r = await _rubro(nombre="Recaudo", tipo="ingreso")
    resp = await api.post(
        f"/api/v1/meses/{_mescorto()}/pagos-planeados", json=_body(r.id), headers=h
    )
    assert resp.status_code == 422


async def test_crear_rubro_inactivo_422(api):
    h = await _token(api)
    await _mes()
    r = await _rubro(activo=False)
    resp = await api.post(
        f"/api/v1/meses/{_mescorto()}/pagos-planeados", json=_body(r.id), headers=h
    )
    assert resp.status_code == 422


async def test_crear_monto_cero_422(api):
    h = await _token(api)
    await _mes()
    r = await _rubro()
    resp = await api.post(
        f"/api/v1/meses/{_mescorto()}/pagos-planeados",
        json=_body(r.id, monto="0"),
        headers=h,
    )
    assert resp.status_code == 422


async def test_crear_monto_numero_422(api):
    # Regla 1: monto como string; strict rechaza el number del JSON.
    h = await _token(api)
    await _mes()
    r = await _rubro()
    body = _body(r.id)
    body["monto"] = 100000
    resp = await api.post(
        f"/api/v1/meses/{_mescorto()}/pagos-planeados", json=body, headers=h
    )
    assert resp.status_code == 422


# ── Editar / cancelar ──


async def _crear(api, h, rubro_id, **kw) -> str:
    resp = await api.post(
        f"/api/v1/meses/{_mescorto()}/pagos-planeados",
        json=_body(rubro_id, **kw),
        headers=h,
    )
    return resp.json()["id"]


async def test_editar_monto_ok(api):
    h = await _token(api)
    await _mes()
    r = await _rubro()
    pid = await _crear(api, h, r.id)
    resp = await api.patch(
        f"/api/v1/pagos-planeados/{pid}", json={"monto": "250000"}, headers=h
    )
    assert resp.status_code == 200
    assert resp.json()["monto"] == "250000.00"


async def test_cancelar_ok_y_luego_editar_409(api):
    h = await _token(api)
    await _mes()
    r = await _rubro()
    pid = await _crear(api, h, r.id)
    resp = await api.post(f"/api/v1/pagos-planeados/{pid}/cancelar", headers=h)
    assert resp.status_code == 200
    assert resp.json()["estado"] == "cancelado"
    # un pago cancelado ya no se edita
    resp2 = await api.patch(
        f"/api/v1/pagos-planeados/{pid}", json={"monto": "1"}, headers=h
    )
    assert resp2.status_code == 409


# ── Veredicto (D2/D3/D4) ──


async def test_veredicto_alcanza(api):
    h = await _token(api)
    await _mes(saldo="1000000")
    r = await _rubro()
    await _crear(api, h, r.id, monto="300000", fecha=EN_SEMANA)
    resp = await api.get(f"/api/v1/meses/{_mescorto()}/pagos-semana", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert data["caja_hoy"] == "1000000.00"
    assert data["total_semana"] == "300000.00"
    assert data["caja_proyectada"] == "700000.00"
    assert data["veredicto"] == "alcanza"
    assert len(data["pagos"]) == 1


async def test_veredicto_no_alcanza(api):
    h = await _token(api)
    await _mes(saldo="100000")
    r = await _rubro()
    await _crear(api, h, r.id, monto="300000", fecha=EN_SEMANA)
    resp = await api.get(f"/api/v1/meses/{_mescorto()}/pagos-semana", headers=h)
    data = resp.json()
    assert data["caja_proyectada"] == "-200000.00"
    assert data["veredicto"] == "no_alcanza"


async def test_veredicto_excluye_fuera_de_ventana_y_lista_vencidos(api):
    # D2: un pago a 30 días NO entra en la semana. D3: uno de ayer va a 'vencidos'.
    h = await _token(api)
    await _mes(saldo="1000000")
    r = await _rubro()
    await _crear(api, h, r.id, monto="300000", fecha=EN_SEMANA)  # dentro
    await _crear(api, h, r.id, monto="500000", fecha=FUERA)  # fuera de ventana
    await _crear(api, h, r.id, monto="90000", fecha=AYER)  # vencido
    resp = await api.get(f"/api/v1/meses/{_mescorto()}/pagos-semana", headers=h)
    data = resp.json()
    assert data["total_semana"] == "300000.00"  # solo el de la semana
    assert len(data["pagos"]) == 1
    assert len(data["vencidos"]) == 1
    assert data["vencidos"][0]["monto"] == "90000.00"


async def test_marcar_pagado_pago_inexistente_404(api):
    # guarda que retorna antes de la transacción (mongomock)
    h = await _token(api)
    await _mes()
    resp = await api.post(
        "/api/v1/pagos-planeados/64b7f0000000000000000000/marcar-pagado",
        json={"transaccion_id": "64b7f0000000000000000001"},
        headers=h,
    )
    assert resp.status_code == 404
