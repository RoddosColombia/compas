# backend/tests/test_escenarios_impacto.py
"""D1 §2 — CRUD de escenarios de impacto nombrados (auditado, CR-D1).

Guardar un escenario es EXPLÍCITO y versionado (simular no escribe; esto sí, con
auditoría fail-closed). RBAC = proyeccion:gestionar (como preview/impactos). Los ajustes
guardan `valor` con precisión completa (un % como 0.016 NO se cuantiza a 2 decimales).
"""

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
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
    for correo, rol in [
        ("consulta@roddos.com", Role.consulta),
        ("fin@roddos.com", Role.financiero),
    ]:
        await repository.create_user(
            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
        )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, c
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _token(ac, email="fin@roddos.com") -> dict:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _body(nombre="Sede nueva", **over):
    body = {
        "nombre": nombre,
        "descripcion": "arriendo de la nueva sede",
        "ajustes": [
            {
                "nombre": "Arriendo",
                "naturaleza": "gasto",
                "modo": "absoluto",
                "valor": "3000000",
                "mes_inicio": "2026-09",
                "mes_fin": None,
                "rubro_id": None,
            }
        ],
    }
    body.update(over)
    return body


@pytest.mark.asyncio
async def test_crear_y_listar(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post("/api/v1/escenarios-impacto", json=_body(), headers=h)
    assert r.status_code == 201
    creado = r.json()
    assert creado["nombre"] == "Sede nueva"
    assert creado["activo"] is True
    assert len(creado["ajustes"]) == 1
    assert creado["ajustes"][0]["valor"] == "3000000"

    lst = await ac.get("/api/v1/escenarios-impacto", headers=h)
    assert lst.status_code == 200
    assert [e["nombre"] for e in lst.json()["items"]] == ["Sede nueva"]


@pytest.mark.asyncio
async def test_crear_emite_evento_auditoria(api):
    ac, c = api
    h = await _token(ac)
    await ac.post("/api/v1/escenarios-impacto", json=_body(), headers=h)
    ev = await c["compas_test"]["audit_log"].find_one(
        {"evento": "escenario_impacto.creado"}
    )
    assert ev is not None


@pytest.mark.asyncio
async def test_nombre_duplicado_es_409(api):
    ac, _ = api
    h = await _token(ac)
    assert (
        await ac.post("/api/v1/escenarios-impacto", json=_body(), headers=h)
    ).status_code == 201
    r = await ac.post("/api/v1/escenarios-impacto", json=_body(), headers=h)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_editar_renombra_y_cambia_ajustes(api):
    ac, _ = api
    h = await _token(ac)
    creado = (
        await ac.post("/api/v1/escenarios-impacto", json=_body(), headers=h)
    ).json()
    eid = creado["id"]
    r = await ac.patch(
        f"/api/v1/escenarios-impacto/{eid}",
        json={"nombre": "Sede + ventas", "ajustes": []},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["nombre"] == "Sede + ventas"
    assert r.json()["ajustes"] == []


@pytest.mark.asyncio
async def test_editar_inexistente_es_404(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.patch(
        "/api/v1/escenarios-impacto/000000000000000000000000",
        json={"nombre": "x"},
        headers=h,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_eliminar_logico_sale_de_activos(api):
    ac, _ = api
    h = await _token(ac)
    eid = (await ac.post("/api/v1/escenarios-impacto", json=_body(), headers=h)).json()[
        "id"
    ]
    r = await ac.delete(f"/api/v1/escenarios-impacto/{eid}", headers=h)
    assert r.status_code == 204
    lst = await ac.get("/api/v1/escenarios-impacto", headers=h)
    assert lst.json()["items"] == []
    # el mismo nombre se puede volver a usar tras la baja lógica
    assert (
        await ac.post("/api/v1/escenarios-impacto", json=_body(), headers=h)
    ).status_code == 201


@pytest.mark.asyncio
async def test_valor_porcentaje_preserva_precision(api):
    ac, _ = api
    h = await _token(ac)
    body = _body(
        nombre="Ventas -1.6%",
        ajustes=[
            {
                "nombre": "Ventas",
                "naturaleza": "ingreso",
                "modo": "porcentaje",
                "valor": "0.016",
                "mes_inicio": "2026-09",
            }
        ],
    )
    r = await ac.post("/api/v1/escenarios-impacto", json=body, headers=h)
    assert r.status_code == 201
    # NO se cuantiza a 2 decimales (0.016 != 0.02)
    assert r.json()["ajustes"][0]["valor"] == "0.016"


@pytest.mark.asyncio
async def test_rbac_consulta_no_crea_pero_lista(api):
    ac, _ = api
    h = await _token(ac, "consulta@roddos.com")
    r = await ac.post("/api/v1/escenarios-impacto", json=_body(), headers=h)
    assert r.status_code == 403  # proyeccion:gestionar, no dashboard:leer
    assert (await ac.get("/api/v1/escenarios-impacto", headers=h)).status_code == 200


@pytest.mark.asyncio
async def test_valor_invalido_es_422(api):
    ac, _ = api
    h = await _token(ac)
    body = _body(
        ajustes=[
            {
                "nombre": "x",
                "naturaleza": "gasto",
                "modo": "absoluto",
                "valor": "no-numero",
                "mes_inicio": "2026-09",
            }
        ]
    )
    r = await ac.post("/api/v1/escenarios-impacto", json=body, headers=h)
    assert r.status_code == 422
