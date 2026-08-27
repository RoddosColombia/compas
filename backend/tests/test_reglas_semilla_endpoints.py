# backend/tests/test_reglas_semilla_endpoints.py
"""RF-F1 paso 3 — endpoints de la semilla: GET /semilla (reporte, lectura pura) y
POST /semilla/sembrar (crea APRENDIDAS inactivas). RBAC `reglas:gestionar` (financiero/
admin); el GET reporta, el POST siembra sin activar (exigen aprobación aparte)."""

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
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion
from app.main import create_app
from beanie import PydanticObjectId, init_beanie
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"
BASE = "/api/v1/reglas-clasificacion"


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
    for correo, rol in [
        ("consulta@roddos.com", Role.consulta),
        ("fin@roddos.com", Role.financiero),
    ]:
        await repository.create_user(
            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
        )
    await Rubro(
        grupo="otros", nombre="Por clasificar", orden=97, es_sistema=True
    ).insert()
    caf = Rubro(grupo="operacion", nombre="Cafetería", orden=1)
    await caf.insert()
    # curaduría: 3 movimientos con "cafeteria" clasificados a Cafetería
    import app.core.ulid as u

    for i in range(3):
        await Transaccion(
            fecha="2026-08-10",
            descripcion=f"Compra en cafeteria local {i}",
            valor=Decimal("10000"),
            tipo_flujo="egreso",
            rubro_id=caf.id,
            mes_id=PydanticObjectId(),
            banco="global66",
            id_banco=f"MAN-{u.new_ulid()}",
        ).insert()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _token(ac, email="fin@roddos.com") -> dict:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _caf_id(ac, h) -> str:
    r = await ac.get(f"{BASE}/semilla", headers=h)
    return next(p for p in r.json()["propuestas"] if p["patron"] == "cafeteria")[
        "rubro_id"
    ]


@pytest.mark.asyncio
async def test_get_semilla_reporta_propuestas(api):
    h = await _token(api)
    r = await api.get(f"{BASE}/semilla?min_evidencia=3", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["total_movimientos"] == 3
    p = next(x for x in body["propuestas"] if x["patron"] == "cafeteria")
    assert p["rubro"] == "Cafetería" and p["evidencia"] == 3 and p["colisiona"] is False


@pytest.mark.asyncio
async def test_get_semilla_rbac(api):
    h = await _token(api, "consulta@roddos.com")
    r = await api.get(f"{BASE}/semilla", headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_semilla_min_pureza_invalida(api):
    h = await _token(api)
    assert (
        await api.get(f"{BASE}/semilla?min_pureza=abc", headers=h)
    ).status_code == 422
    assert (await api.get(f"{BASE}/semilla?min_pureza=2", headers=h)).status_code == 422


@pytest.mark.asyncio
async def test_sembrar_crea_inactivas(api):
    h = await _token(api)
    rid = await _caf_id(api, h)
    r = await api.post(
        f"{BASE}/semilla/sembrar",
        json={
            "reglas": [{"patron": "cafeteria", "rubro_id": rid, "tipo_flujo": "egreso"}]
        },
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["creadas"] == 1
    # queda INACTIVA (no clasifica hasta aprobar)
    lst = await api.get(f"{BASE}?activa=false", headers=h)
    patrones = [x["patron_normalizado"] for x in lst.json()]
    assert "cafeteria" in patrones
    activas = await api.get(f"{BASE}?activa=true", headers=h)
    assert all(x["patron_normalizado"] != "cafeteria" for x in activas.json())


@pytest.mark.asyncio
async def test_sembrar_idempotente(api):
    h = await _token(api)
    rid = await _caf_id(api, h)
    body = {
        "reglas": [{"patron": "cafeteria", "rubro_id": rid, "tipo_flujo": "egreso"}]
    }
    await api.post(f"{BASE}/semilla/sembrar", json=body, headers=h)
    r2 = await api.post(f"{BASE}/semilla/sembrar", json=body, headers=h)
    assert r2.json()["creadas"] == 0 and r2.json()["ya_existian"] == 1


@pytest.mark.asyncio
async def test_sembrar_rbac(api):
    h = await _token(api, "consulta@roddos.com")
    r = await api.post(
        f"{BASE}/semilla/sembrar",
        json={
            "reglas": [
                {
                    "patron": "cafeteria",
                    "rubro_id": str(PydanticObjectId()),
                    "tipo_flujo": "egreso",
                }
            ]
        },
        headers=h,
    )
    assert r.status_code == 403


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
