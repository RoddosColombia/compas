# backend/tests/test_transacciones_guard_sistema.py
"""FIX-A / A-1 (P0-1): guard es_sistema en las vías de clasificación.

MARCADO PARA AUDITORÍA KIMI (gate PR-FIX-A; hallazgo P0-1).

El rubro 'Ajuste de conciliación' (es_sistema, EGRESO) es la LLAVE DE EXCLUSIÓN de
_caja_libro y de Vista Control. Clasificar una transacción real hacia él la hace
desaparecer del libro y sube la caja en silencio. Ninguna de las 3 vías (crear
manual, reclasificar, reglas) lo impedía. El guard rechaza rubros es_sistema salvo
una lista blanca explícita {Recaudo de cartera, Tránsito Wava mes anterior}.
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
from app.domain.mes_control import MesControl
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion
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
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")
    await repository.create_user(
        User(
            email="fin@roddos.com",
            password_hash=passwords.hash_password(PWD),
            rol=Role.financiero,
        )
    )
    # Rubros de sistema (la clave del hallazgo) + uno normal de negocio.
    await Rubro(
        grupo="otros", nombre="Por clasificar", orden=97, es_sistema=True
    ).insert()
    await Rubro(
        grupo="otros",
        nombre="Recaudo de cartera",
        tipo_flujo="ingreso",
        orden=98,
        es_sistema=True,
    ).insert()
    await Rubro(
        grupo="otros",
        nombre="Ajuste de conciliación",
        tipo_flujo="egreso",
        orden=99,
        es_sistema=True,
    ).insert()
    await Rubro(grupo="operacion", nombre="Cafetería", orden=1).insert()
    await MesControl(mes="2026-03-01", saldo_inicial_caja=Decimal("0")).insert()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, c
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _token(ac) -> dict:
    r = await ac.post(
        "/api/v1/auth/login", json={"email": "fin@roddos.com", "password": PWD}
    )
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _tx(tipo="egreso") -> Transaccion:
    pc = await Rubro.find_one(Rubro.nombre == "Por clasificar")
    mc = await MesControl.find_one(MesControl.mes == "2026-03-01")
    tx = Transaccion(
        fecha="2026-03-15",
        descripcion="COMPRA REAL QUE NO DEBE DESAPARECER",
        valor=Decimal("1000000"),
        tipo_flujo=tipo,
        rubro_id=pc.id,
        mes_id=mc.id,
        banco="manual",
        id_banco="MAN-GUARD-001",
    )
    await tx.insert()
    return tx


# ─────────────────────── vía 1: reclasificar (PATCH) ───────────────────────


async def test_reclasificar_a_ajuste_rechazado_caja_inmovil(api):
    # EL P0: un egreso real reclasificado a 'Ajuste de conciliación' → rechazo,
    # y la transacción NO cambia de rubro (la caja del libro no se mueve).
    ac, _ = api
    h = await _token(ac)
    tx = await _tx()
    pc = await Rubro.find_one(Rubro.nombre == "Por clasificar")
    ajuste = await Rubro.find_one(Rubro.nombre == "Ajuste de conciliación")
    r = await ac.patch(
        f"/api/v1/transacciones/{tx.id}/clasificar",
        json={"rubro_id": str(ajuste.id)},
        headers=h,
    )
    assert r.status_code in (409, 422)
    assert (await Transaccion.get(tx.id)).rubro_id == pc.id  # inmóvil


async def test_reclasificar_a_recaudo_cartera_whitelist_ok(api):
    # La lista blanca deja pasar 'Recaudo de cartera' (destino manual legítimo).
    ac, _ = api
    h = await _token(ac)
    tx = await _tx(tipo="ingreso")
    recaudo = await Rubro.find_one(Rubro.nombre == "Recaudo de cartera")
    r = await ac.patch(
        f"/api/v1/transacciones/{tx.id}/clasificar",
        json={"rubro_id": str(recaudo.id)},
        headers=h,
    )
    assert r.status_code == 200
    assert (await Transaccion.get(tx.id)).rubro_id == recaudo.id


async def test_reclasificar_a_por_clasificar_desclasificar_ok(api):
    # Corrección Kimi (gate FIX-A): 'Por clasificar' está en la lista blanca porque
    # es el destino de DES-clasificar (devolver la tx a la bandeja). Debe permitirse.
    ac, _ = api
    h = await _token(ac)
    tx = await _tx(tipo="egreso")
    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
    pc = await Rubro.find_one(Rubro.nombre == "Por clasificar")
    # primero clasifico a un rubro real...
    r1 = await ac.patch(
        f"/api/v1/transacciones/{tx.id}/clasificar",
        json={"rubro_id": str(caf.id)},
        headers=h,
    )
    assert r1.status_code == 200
    # ...y luego la devuelvo a la bandeja (des-clasificar) → permitido.
    r2 = await ac.patch(
        f"/api/v1/transacciones/{tx.id}/clasificar",
        json={"rubro_id": str(pc.id)},
        headers=h,
    )
    assert r2.status_code == 200
    assert (await Transaccion.get(tx.id)).rubro_id == pc.id


# ─────────────────────── vía 2: crear manual (POST) ───────────────────────


async def test_crear_manual_a_ajuste_rechazado(api):
    ac, _ = api
    h = await _token(ac)
    ajuste = await Rubro.find_one(Rubro.nombre == "Ajuste de conciliación")
    r = await ac.post(
        "/api/v1/transacciones",
        json={
            "fecha": "2026-03-15",
            "descripcion": "EGRESO QUE NO DEBE EVADIRSE",
            "valor": "1000000",
            "tipo_flujo": "egreso",
            "rubro_id": str(ajuste.id),
        },
        headers={**h, "Idempotency-Key": "guard-001"},
    )
    assert r.status_code in (409, 422)
    assert await Transaccion.find_one() is None  # no se creó nada
