# backend/tests/cfo/agente/test_router.py
"""T11 · POST /api/v1/cfo — doble barrera (router condicional + guard 404) y RBAC
`cfo:consultar`.

Patrón de auth REUSADO de tests/test_rbac_endpoints.py: create_app() real +
mongomock para auth/audit + login real para obtener el token. NO usamos
`dependency_overrides[require_permission(...)]` (el plan original lo sugería):
`require_permission(cap)` fabrica una función `dep` NUEVA en cada llamada, así que
un override "por identidad" contra esa instancia nunca hace match con la que el
router realmente resuelve en cada request — `dependency_overrides` se queda ciego.
`get_current_user`, en cambio, es una única función de módulo reusada tal cual
dentro de `dep`; overridearla ahí sí tendría efecto, pero aquí preferimos ir con
login real (mismo patrón ya probado por PR-3) para ejercer el stack RBAC completo,
incluido `str(user.id)` con un id real de Mongo (mongomock)."""

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.cfo.agente.modelos import RespuestaCFO, UsoLLM
from app.config import get_settings
from app.main import create_app
from mongomock_motor import AsyncMongoMockClient
from tests.conftest import rutas_registradas

PWD = "clave-larga-1234"

RESPUESTA_FAKE = RespuestaCFO(
    texto="ok",
    abstuvo=False,
    texto_crudo="ok",
    uso=UsoLLM(modelo="m", tokens_in=1, tokens_out=1, iteraciones=1),
)


async def _fake_consultar(
    pregunta: str, *, actor_id: str, cliente=None, historial=None
) -> RespuestaCFO:
    return RESPUESTA_FAKE


@pytest_asyncio.fixture
async def api(monkeypatch):
    """App con el router cfo MONTADO (CFO_ENABLED=true) + un usuario por rol.
    `servicio.consultar` queda monkeypatcheado (ningún test aquí toca un LLM real)."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("COOKIE_SECURE", "False")
    monkeypatch.setenv("CFO_ENABLED", "true")
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()

    import app.cfo.router as cfo_router_module

    monkeypatch.setattr(cfo_router_module.servicio, "consultar", _fake_consultar)

    app = create_app()
    c = AsyncMongoMockClient()
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


async def _token(ac, email) -> str:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.mark.parametrize(
    "email", ["fin@roddos.com", "dir@roddos.com", "admin@roddos.com"]
)
async def test_responde_ok_con_flag_on_y_rol_autorizado(api, email):
    tok = await _token(api, email)
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.post(
        "/api/v1/cfo", json={"pregunta": "¿cuánta caja hay hoy?"}, headers=h
    )
    assert r.status_code == 200
    body = r.json()
    assert body["texto"] == "ok"
    assert body["abstuvo"] is False
    assert body["uso"]["modelo"] == "m"


async def test_rol_consulta_no_autorizado_403(api):
    tok = await _token(api, "consulta@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.post("/api/v1/cfo", json={"pregunta": "¿caja?"}, headers=h)
    assert r.status_code == 403


async def test_sin_token_es_401(api):
    r = await api.post("/api/v1/cfo", json={"pregunta": "¿caja?"})
    assert r.status_code == 401


async def test_body_extra_forbidden_422(api):
    # Regla 3 (Pydantic strict=True/extra=forbid): campo no declarado se rechaza.
    tok = await _token(api, "admin@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.post(
        "/api/v1/cfo", json={"pregunta": "¿caja?", "campo_extra": 1}, headers=h
    )
    assert r.status_code == 422


async def test_guard_defensivo_404_si_flag_se_apaga_en_runtime(api, monkeypatch):
    # Barrera 2: el router YA está montado (flag=true al construir la app), pero si
    # alguien apaga CFO_ENABLED en caliente (sin reiniciar el proceso) el guard
    # dentro del handler debe cortar en 404 — cfo_enabled() relee el entorno en cada
    # llamada (sin cache), así que este flip toma efecto en la MISMA request.
    tok = await _token(api, "admin@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    monkeypatch.setenv("CFO_ENABLED", "false")
    r = await api.post("/api/v1/cfo", json={"pregunta": "¿caja?"}, headers=h)
    assert r.status_code == 404
    assert r.json()["detail"] == "No encontrado."


async def test_historial_devuelve_lista_para_rol_autorizado(api):
    # Nivel HTTP (Task-2 §9): a diferencia de tests/cfo/test_router_chat.py
    # (llama cfo_router.historial(user=_U()) directo, saltándose
    # require_permission), este va por el stack ASGI real — login → JWT →
    # dependencia RBAC → handler.
    tok = await _token(api, "admin@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    await api.post("/api/v1/cfo", json={"pregunta": "¿cuánta caja hay hoy?"}, headers=h)
    r = await api.get("/api/v1/cfo/historial", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert any(t["texto"] == "¿cuánta caja hay hoy?" for t in body)


async def test_historial_rol_consulta_no_autorizado_403(api):
    tok = await _token(api, "consulta@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.get("/api/v1/cfo/historial", headers=h)
    assert r.status_code == 403


async def test_historial_sin_token_es_401(api):
    r = await api.get("/api/v1/cfo/historial")
    assert r.status_code == 401


async def test_historial_guard_defensivo_404_si_flag_se_apaga_en_runtime(
    api, monkeypatch
):
    # Barrera 2 del GET (mismo guard que el POST, mismo patrón de flip en
    # caliente que test_guard_defensivo_404_si_flag_se_apaga_en_runtime).
    tok = await _token(api, "admin@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    monkeypatch.setenv("CFO_ENABLED", "false")
    r = await api.get("/api/v1/cfo/historial", headers=h)
    assert r.status_code == 404
    assert r.json()["detail"] == "No encontrado."


async def test_ruta_ausente_si_flag_apagado_al_construir_la_app(monkeypatch):
    # Barrera 1: con el flag apagado desde el arranque, create_app() NUNCA monta el
    # router — la ruta no existe (404 genérico de FastAPI, no el guard del handler).
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.delenv("CFO_ENABLED", raising=False)
    get_settings.cache_clear()

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/api/v1/cfo", json={"pregunta": "¿caja?"})
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}
    get_settings.cache_clear()


def test_flag_off_no_monta_router_en_app_routes(monkeypatch):
    """T12 (cierre inc2) · flag-off = COMPAS byte-idéntico: verificación
    ESTRUCTURAL, no solo conductual — con CFO_ENABLED ausente/false,
    create_app() no debe registrar /api/v1/cfo en app.routes en absoluto (el
    router nunca se incluye; no es que responda 404, es que la ruta no existe
    como tal). Complementa la prueba conductual de arriba (barrera 1)."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.delenv("CFO_ENABLED", raising=False)
    get_settings.cache_clear()

    app = create_app()
    rutas = rutas_registradas(app)
    assert "/api/v1/cfo" not in rutas

    get_settings.cache_clear()
