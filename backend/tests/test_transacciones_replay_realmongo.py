# backend/tests/test_transacciones_replay_realmongo.py
"""FIX-A / A-4 (P1-9): replay de tx manual tras expirar el TTL de la marca.

MARCADO PARA AUDITORÍA KIMI (gate PR-FIX-A). SOLO Mongo REAL: la convergencia vive
en el índice único parcial (banco, id_banco) — mongomock NO lo soporta.

Escenario: una tx manual se crea; la marca de idempotencia expira (TTL 24h,
simulado borrándola); el mismo request (misma key + mismo payload) NO debe crear una
SEGUNDA tx. El id_banco determinista (MAN-sha256(usuario|endpoint|key)[:24]) colisiona
en el índice → el servicio devuelve la tx existente con replay:true.
"""

import os
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.idempotency import IdempotencyKey
from app.domain.mes_control import MesControl
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

pytestmark = pytest.mark.requires_real_mongo
PWD = "clave-larga-1234"
BODY = {
    "fecha": "2026-03-15",
    "descripcion": "EGRESO EFECTIVO CAJA",
    "valor": "50000",
    "tipo_flujo": "egreso",
}


@pytest_asyncio.fixture
async def api(monkeypatch):
    uri = os.environ.get("COMPAS_TEST_MONGO_URI")
    if not uri:
        pytest.skip("COMPAS_TEST_MONGO_URI no configurado")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("COOKIE_SECURE", "False")
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    client = AsyncIOMotorClient(uri, tz_aware=True)
    dbname = "compas_test_replay"
    await client.drop_database(dbname)
    db = client[dbname]
    await init_beanie(database=db, document_models=DOMAIN_DOCUMENTS)
    repository.configure_auth(client, dbname)
    configure_audit(client, dbname)
    await repository.create_user(
        User(
            email="fin@roddos.com",
            password_hash=passwords.hash_password(PWD),
            rol=Role.financiero,
        )
    )
    await Rubro(
        grupo="otros", nombre="Por clasificar", orden=97, es_sistema=True
    ).insert()
    await MesControl(mes="2026-03-01", saldo_inicial_caja=Decimal("0")).insert()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, db
    repository.reset_auth()
    reset_audit()
    await client.drop_database(dbname)
    client.close()
    get_settings.cache_clear()


async def _token(ac) -> dict:
    r = await ac.post(
        "/api/v1/auth/login", json={"email": "fin@roddos.com", "password": PWD}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _post(ac, h, key, body=None):
    return await ac.post(
        "/api/v1/transacciones",
        json=body or BODY,
        headers={**h, "Idempotency-Key": key},
    )


async def test_replay_tras_ttl_no_duplica_y_marca_replay(api):
    ac, _ = api
    h = await _token(ac)
    r1 = await _post(ac, h, "ttl-1")
    assert r1.status_code == 201
    id_banco = r1.json()["id_banco"]

    # simula la expiración del TTL: la marca desaparece, la tx queda.
    await IdempotencyKey.find(IdempotencyKey.key == "ttl-1").delete()

    r2 = await _post(ac, h, "ttl-1")  # mismo request, marca ya no está
    assert r2.status_code == 200  # replay convergente, no 201
    assert r2.json()["replay"] is True
    assert r2.json()["id_banco"] == id_banco  # la MISMA tx
    assert await Transaccion.count() == 1  # nunca una segunda


async def test_replay_tras_ttl_payload_distinto_no_convergente(api):
    # Con la marca viva, misma key + payload distinto → 422 (request_hash). Este
    # test fija que el camino de seguridad no se rompió con el id_banco determinista.
    ac, _ = api
    h = await _token(ac)
    assert (await _post(ac, h, "ttl-2")).status_code == 201
    r = await _post(ac, h, "ttl-2", {**BODY, "valor": "99999"})
    assert r.status_code == 422
    assert await Transaccion.count() == 1
