# backend/tests/cfo/telegram/test_router.py
"""T6 (inc3 Pieza B) · POST /api/v1/cfo/telegram/webhook (secret) + administración
de vínculos /api/v1/cfo/telegram/vinculos (RBAC).

Patrón de auth REUSADO de tests/cfo/agente/test_router.py: create_app() real +
mongomock para auth/audit + login real para obtener el token — NO
`dependency_overrides[require_permission(...)]` (`require_permission(cap)` fabrica
un `dep` NUEVO en cada llamada, así que un override "por identidad" contra esa
instancia nunca hace match con la que el router realmente resuelve en cada
request; ver el docstring de ese archivo para el detalle).

RBAC de /vinculos: el plan original de esta tarea sugería `require_role(Role.admin)`,
pero eso viola una regla ya existente del repo — `app/auth/deps.py` documenta que
`require_role` es "SOLO para administración de identidad (/users); prohibido en
negocio (H-1)", y el ÚNICO uso real de `require_role(` en todo el backend (fuera de
su propia definición) es un endpoint sintético de tests/test_rbac_endpoints.py: NINGÚN
router de negocio lo usa, todos gatean con `require_permission(cap)` (así lo hace el
propio app/cfo/router.py, hermano de este). Aquí se gatea con
`require_permission('cfo:telegram_administrar')` — capacidad nueva restringida a
Role.admin en app/auth/permissions.py — cumpliendo la Regla 9 de CLAUDE.md."""

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.cfo.telegram import repositorio
from app.config import get_settings
from app.main import create_app
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"
SECRET = "secreto-webhook-test"


@pytest_asyncio.fixture
async def api(monkeypatch):
    """App con el router telegram MONTADO (CFO_ENABLED=true) + un usuario por rol."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("COOKIE_SECURE", "False")
    monkeypatch.setenv("CFO_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()

    app = create_app()
    c = AsyncMongoMockClient()
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")
    for correo, rol in [
        ("fin@roddos.com", Role.financiero),
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


async def test_webhook_secret_invalido_403(api):
    r = await api.post(
        "/api/v1/cfo/telegram/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "otro-secreto"},
    )
    assert r.status_code == 403


async def test_webhook_sin_secret_403(api):
    r = await api.post("/api/v1/cfo/telegram/webhook", json={"update_id": 1})
    assert r.status_code == 403


async def test_admin_crea_vinculo_ok(api, monkeypatch):
    creados = []

    async def fake_vincular(telegram_id, user_id, admin_id):
        creados.append((telegram_id, user_id, admin_id))

    monkeypatch.setattr("app.cfo.telegram.router.vinculos.vincular", fake_vincular)
    tok = await _token(api, "admin@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.post(
        "/api/v1/cfo/telegram/vinculos",
        json={"telegram_id": 111, "user_id": "u1"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert creados[0][0] == 111
    assert creados[0][1] == "u1"


async def test_no_admin_403(api):
    tok = await _token(api, "fin@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.post(
        "/api/v1/cfo/telegram/vinculos",
        json={"telegram_id": 111, "user_id": "u1"},
        headers=h,
    )
    assert r.status_code == 403


async def test_sin_token_401(api):
    r = await api.post(
        "/api/v1/cfo/telegram/vinculos", json={"telegram_id": 111, "user_id": "u1"}
    )
    assert r.status_code == 401


def test_flag_off_rutas_ausentes(monkeypatch):
    """Flag-off = COMPAS byte-idéntico: verificación ESTRUCTURAL — con CFO_ENABLED
    ausente, create_app() no debe registrar NINGUNA ruta de cfo/telegram."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.delenv("CFO_ENABLED", raising=False)
    get_settings.cache_clear()

    app = create_app()
    rutas = {r.path for r in app.routes}
    assert "/api/v1/cfo/telegram/webhook" not in rutas
    assert "/api/v1/cfo/telegram/vinculos" not in rutas

    get_settings.cache_clear()


# ─────────────── FIX ROUND (auditoría Kimi, gate de código T6) ───────────────
#
# Fix 1 (Important): antes, el handler de POST /vinculos atrapaba `except
# Exception` alrededor de `vinculos.vincular(...)`, así que un fallo REAL de
# `emit_audit` (posterior a un `crear_vinculo` que sí insertó) se disfrazaba de
# 409 "ya vinculado" -- un vínculo recién creado con su rastro de auditoría
# perdido, reportado como si nunca se hubiera creado. El fix traduce el
# DuplicateKeyError del driver a `repositorio.VinculoDuplicado` en la frontera
# del repositorio (S1) y el router solo atrapa ESA excepción de dominio.


async def test_admin_crea_vinculo_fallo_audit_no_enmascara_409(api, monkeypatch):
    """RED antes del fix / GREEN después: crear_vinculo inserta bien (el vínculo
    SÍ se crea) pero emit_audit revienta -- el router NO debe mentir con un 409
    "ya vinculado". Debe propagar el fallo real, nunca esconderlo detrás de un
    409 falso. Mismo patrón que B-5 en tests/test_rubros_endpoints.py: con
    raise_app_exceptions=True (default de httpx.ASGITransport) el transport
    re-lanza la excepción no manejada en vez de convertirla en una Response --
    en producción, Starlette sí la convertiría en 500. Lo que fija este test es
    que NO llega a ser un 409, no el código exacto que ve el cliente HTTP real."""

    async def fake_crear_vinculo(v):
        pass  # el insert en Mongo funcionó de verdad

    async def fake_emit_que_falla(
        evento, entidad, entidad_id=None, actor_id=None, metadata=None
    ):
        raise RuntimeError("audit no configurado")

    monkeypatch.setattr(
        "app.cfo.telegram.vinculos.repositorio.crear_vinculo", fake_crear_vinculo
    )
    monkeypatch.setattr("app.cfo.telegram.vinculos.emit_audit", fake_emit_que_falla)
    tok = await _token(api, "admin@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    with pytest.raises(RuntimeError):
        await api.post(
            "/api/v1/cfo/telegram/vinculos",
            json={"telegram_id": 555, "user_id": "u5"},
            headers=h,
        )


async def test_admin_crea_vinculo_duplicado_409(api, monkeypatch):
    """Fix 1: el ÚNICO caso que debe traducirse a 409 es el dominio real de
    duplicado (repositorio.VinculoDuplicado) -- narrow catch en el router, ya
    no `except Exception`."""

    async def fake_vincular(telegram_id, user_id, admin_id):
        raise repositorio.VinculoDuplicado("telegram_id o user_id ya vinculado")

    monkeypatch.setattr("app.cfo.telegram.router.vinculos.vincular", fake_vincular)
    tok = await _token(api, "admin@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.post(
        "/api/v1/cfo/telegram/vinculos",
        json={"telegram_id": 111, "user_id": "u1"},
        headers=h,
    )
    assert r.status_code == 409


async def test_webhook_secret_ok_sin_bot_token_503(api, monkeypatch):
    """Fix 3 (Minor b): secret válido pero el canal de SALIDA no está
    configurado (TELEGRAM_BOT_TOKEN ausente -> crear_cliente_telegram() = None)
    -> falla cerrado con 503, nunca procesa el update a ciegas sin forma de
    responderle a Telegram."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    r = await api.post(
        "/api/v1/cfo/telegram/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    assert r.status_code == 503


async def test_admin_borra_vinculo_inexistente_404(api, monkeypatch):
    """Fix 3 (Minor b): borrar un telegram_id sin vínculo (desvincular ->
    False) -> 404, no un 200 silencioso."""

    async def fake_desvincular(telegram_id, admin_id):
        return False

    monkeypatch.setattr(
        "app.cfo.telegram.router.vinculos.desvincular", fake_desvincular
    )
    tok = await _token(api, "admin@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.delete(
        "/api/v1/cfo/telegram/vinculos/999",
        headers=h,
    )
    assert r.status_code == 404
