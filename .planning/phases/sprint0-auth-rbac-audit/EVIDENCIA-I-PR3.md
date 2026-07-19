# EVIDENCIA — I-PR3 (RBAC): fuentes íntegras + salidas


## archivo: backend/app/auth/permissions.py

```
# backend/app/auth/permissions.py
"""Config ÚNICO de permisos (RBAC) ≡ matriz Spec §4.1 + autoridad §2.4.

Fuente única de verdad: el navbar del frontend se derivará de aquí (GET
/auth/capabilities), y los endpoints de negocio usan `require_permission(cap)`.
`require_role` queda SOLO para administración de identidad (/users); prohibido en
negocio (Kimi H-1). La §2.4 se codifica como capacidades `ciclo:*` y MANDA sobre
cualquier otra redacción. `ciclo:reabrir` y `ciclo:config` exigirán step-up MFA
(Sprint 0b)."""

from app.auth.roles import Role

_TODOS = frozenset(Role)

PERMISSIONS: dict[str, frozenset[Role]] = {
    # ── Spec §4.1 (matriz permiso × endpoint) ──
    "dashboard:leer": _TODOS,
    "export:reportes": frozenset({Role.financiero, Role.directivo, Role.admin}),
    "archivos:descargar": frozenset({Role.financiero, Role.admin}),
    "cargas:gestionar": frozenset({Role.financiero, Role.admin}),
    "presupuesto:acotar": frozenset({Role.financiero, Role.directivo, Role.admin}),
    "facturas_emitidas:gestionar": frozenset({Role.financiero, Role.admin}),
    "evidencia:ver": frozenset({Role.financiero, Role.admin}),
    "capacidad_pago:ver": frozenset({Role.financiero, Role.directivo, Role.admin}),
    # ── Spec §2.4 (autoridad del ciclo mensual — manda sobre §4.1) ──
    "ciclo:abrir": frozenset({Role.financiero, Role.directivo, Role.admin}),
    "ciclo:proponer": frozenset({Role.financiero, Role.directivo, Role.admin}),
    "ciclo:aprobar": frozenset({Role.admin}),  # aprobador formal único
    "ciclo:cierre_operativo": frozenset({Role.financiero, Role.admin}),
    "ciclo:confirmar_cierre": frozenset({Role.admin}),
    "ciclo:reabrir": frozenset({Role.admin}),  # + step-up MFA (0b)
    "ciclo:config": frozenset({Role.admin}),  # + step-up MFA (0b)
}

CAPABILITIES: frozenset[str] = frozenset(PERMISSIONS)


def has_permission(rol: Role, capacidad: str) -> bool:
    return rol in PERMISSIONS.get(capacidad, frozenset())


def capabilities_for(rol: Role) -> list[str]:
    """Capacidades efectivas del rol (ordenadas). Lo consume el navbar (M13.1 #6:
    prohibido mapear rol→ítems en el frontend)."""
    return sorted(cap for cap, roles in PERMISSIONS.items() if rol in roles)
```


## archivo: backend/app/auth/deps.py

```
# backend/app/auth/deps.py
"""Dependencia get_current_user (base del RBAC de PR-3).

Extrae el access de Authorization: Bearer y lo valida (firma, tipo, denylist,
activo, token_version) vía service.authenticate."""

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request

from app.auth import service
from app.auth.models import User
from app.auth.permissions import has_permission
from app.auth.roles import Role
from app.config import Settings, get_settings


def _settings() -> Settings:
    return get_settings()


async def get_current_user(
    request: Request, settings: Settings = Depends(_settings)
) -> User:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    try:
        return await service.authenticate(settings, access_token=auth[7:])
    except service.AuthError as e:
        raise HTTPException(e.status, e.detail) from e


def require_permission(capacidad: str) -> Callable[..., Awaitable[User]]:
    """Dependencia RBAC para endpoints de NEGOCIO (fuente: config §4.1/§2.4)."""

    async def dep(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.rol, capacidad):
            raise HTTPException(403, "No autorizado para esta acción.")
        return user

    return dep


def require_role(*roles: Role) -> Callable[..., Awaitable[User]]:
    """SOLO para administración de identidad (/users); prohibido en negocio (H-1)."""

    async def dep(user: User = Depends(get_current_user)) -> User:
        if user.rol not in roles:
            raise HTTPException(403, "No autorizado.")
        return user

    return dep
```


## archivo: backend/app/auth/router.py

```
# backend/app/auth/router.py
"""Endpoints de auth bajo /api/v1/auth (Spec §4).

Cookie de refresh: HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth (Kimi A-01/E-2).
Verificación de Origin en las mutaciones fuera de dev (Kimi M-03/Spec §4)."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from app.auth import service
from app.auth.deps import get_current_user
from app.auth.models import User
from app.auth.permissions import capabilities_for
from app.config import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh"
COOKIE_PATH = "/api/v1/auth"


class LoginBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    email: str
    password: str


def _settings() -> Settings:
    return get_settings()


def verify_origin(request: Request, settings: Settings = Depends(_settings)) -> None:
    """Rechaza mutaciones con Origin ajeno (fuera de dev). Defensa CSRF adicional a
    SameSite=Strict (Spec §4)."""
    if settings.app_env == "development":
        return
    origin = request.headers.get("origin")
    if origin is not None and origin != settings.frontend_origin:
        raise HTTPException(403, "Origin no permitido.")


def client_ip(request: Request) -> str:
    """IP real del cliente tras Cloudflare→Render (Kimi L2). `request.client.host`
    a secas sería la IP del proxy → un solo bucket para todos (rate limit inútil y
    DoS colectivo). Preferimos `CF-Connecting-IP` (canónica de Cloudflare), luego el
    primer salto de `X-Forwarded-For`, y por último el peer. Requiere que el origen
    Render solo sea alcanzable vía Cloudflare + `uvicorn --proxy-headers` (RUNBOOK)."""
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _set_refresh_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=COOKIE_PATH,
    )


@router.post("/login")
async def login(
    body: LoginBody,
    request: Request,
    response: Response,
    settings: Settings = Depends(_settings),
    _: None = Depends(verify_origin),
):
    ip = client_ip(request)
    try:
        pair = await service.login(
            settings, email=body.email, password=body.password, ip=ip
        )
    except service.AuthError as e:
        raise HTTPException(e.status, e.detail) from e
    _set_refresh_cookie(response, settings, pair.refresh_token)
    return {"access_token": pair.access_token, "token_type": "bearer"}


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    settings: Settings = Depends(_settings),
    _: None = Depends(verify_origin),
):
    rt = request.cookies.get(REFRESH_COOKIE)
    if not rt:
        raise HTTPException(401, "No autenticado.")
    try:
        pair = await service.refresh(settings, refresh_token=rt)
    except service.AuthError as e:
        response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
        raise HTTPException(e.status, e.detail) from e
    _set_refresh_cookie(response, settings, pair.refresh_token)
    return {"access_token": pair.access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    settings: Settings = Depends(_settings),
    _: None = Depends(verify_origin),
):
    rt = request.cookies.get(REFRESH_COOKIE)
    auth = request.headers.get("authorization", "")
    at = auth[7:] if auth.startswith("Bearer ") else None
    await service.logout(settings, access_token=at, refresh_token=rt)
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return {"status": "ok"}


@router.get("/capabilities")
async def capabilities(user: User = Depends(get_current_user)):
    """Capacidades efectivas del usuario. El navbar del frontend renderiza desde aquí
    (M13.1 #6: prohibido mapear rol→ítems en el front). Fuente única §4.1/§2.4."""
    return {"rol": user.rol.value, "capabilities": capabilities_for(user.rol)}
```


## archivo: backend/tests/test_rbac_permissions.py

```
# backend/tests/test_rbac_permissions.py
"""Config único de permisos ≡ matriz Spec §4.1 + autoridad §2.4 (PR-3).

Test de completitud TRIPLE (Kimi M-10):
(a) toda capacidad usada tiene roles no vacíos; (b) el config ≡ la matriz canónica
congelada aquí; (c) sin capacidades huérfanas ni roles que no aparezcan en ninguna."""

from app.auth import permissions as perms
from app.auth.roles import Role

# Matriz canónica CONGELADA (Spec §4.1 + §2.4). Si el código cambia, este test cae:
# es la fuente de verdad del test contra el config de la app.
CANONICA: dict[str, set[Role]] = {
    # §4.1
    "dashboard:leer": {Role.consulta, Role.financiero, Role.directivo, Role.admin},
    "export:reportes": {Role.financiero, Role.directivo, Role.admin},
    "archivos:descargar": {Role.financiero, Role.admin},
    "cargas:gestionar": {Role.financiero, Role.admin},
    "presupuesto:acotar": {Role.financiero, Role.directivo, Role.admin},
    "facturas_emitidas:gestionar": {Role.financiero, Role.admin},
    "evidencia:ver": {Role.financiero, Role.admin},
    "capacidad_pago:ver": {Role.financiero, Role.directivo, Role.admin},
    # §2.4 — autoridad del ciclo (manda sobre §4.1)
    "ciclo:abrir": {Role.financiero, Role.directivo, Role.admin},
    "ciclo:proponer": {Role.financiero, Role.directivo, Role.admin},
    "ciclo:aprobar": {Role.admin},
    "ciclo:cierre_operativo": {Role.financiero, Role.admin},
    "ciclo:confirmar_cierre": {Role.admin},
    "ciclo:reabrir": {Role.admin},  # + step-up MFA (Sprint 0b)
    "ciclo:config": {Role.admin},  # + step-up MFA (Sprint 0b)
}


def test_config_igual_a_la_matriz_canonica():
    # (b)
    actual = {cap: set(roles) for cap, roles in perms.PERMISSIONS.items()}
    assert actual == CANONICA


def test_ninguna_capacidad_sin_roles():
    # (a)
    for cap, roles in perms.PERMISSIONS.items():
        assert roles, f"capacidad huérfana sin roles: {cap}"


def test_todos_los_roles_aparecen():
    # (c)
    cubiertos = {r for roles in perms.PERMISSIONS.values() for r in roles}
    assert cubiertos == set(Role)


def test_consulta_no_puede_exportar():
    # DoD #1: export denegado a Consulta.
    assert not perms.has_permission(Role.consulta, "export:reportes")
    assert perms.has_permission(Role.financiero, "export:reportes")


def test_aprobar_solo_admin():
    # §2.4: solo Admin aprueba (Directivo acota, no aprueba).
    assert perms.has_permission(Role.admin, "ciclo:aprobar")
    assert not perms.has_permission(Role.directivo, "ciclo:aprobar")
    assert not perms.has_permission(Role.financiero, "ciclo:aprobar")


def test_capabilities_for_consulta_solo_lectura():
    caps = perms.capabilities_for(Role.consulta)
    assert caps == ["dashboard:leer"]


def test_capacidad_desconocida_es_falsa():
    assert not perms.has_permission(Role.admin, "capacidad.inventada")


def test_toda_capacidad_usada_en_decoradores_existe_en_config():
    # (a) guardián: ninguna require_permission("X") con X fuera del config (drift).
    import pathlib
    import re

    app_dir = pathlib.Path(__file__).resolve().parents[1] / "app"
    usados: set[str] = set()
    for py in app_dir.rglob("*.py"):
        texto = py.read_text(encoding="utf-8")
        usados.update(re.findall(r'require_permission\(\s*["\']([^"\']+)["\']', texto))
    faltan = usados - set(perms.CAPABILITIES)
    assert not faltan, f"capacidades usadas sin definir en el config: {faltan}"
```


## archivo: backend/tests/test_rbac_endpoints.py

```
# backend/tests/test_rbac_endpoints.py
"""RBAC extremo a extremo (PR-3): routers solo-test que ejercen require_permission
y require_role; negativos por rol (DoD #1, incl. export de Consulta denegado) y
GET /auth/capabilities."""

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.deps import require_permission, require_role
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.main import create_app
from fastapi import APIRouter, Depends
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


def _test_router() -> APIRouter:
    tr = APIRouter()

    @tr.get("/_test/export")
    async def _export(_: User = Depends(require_permission("export:reportes"))):
        return {"ok": True}

    @tr.get("/_test/solo-admin")
    async def _admin(_: User = Depends(require_role(Role.admin))):
        return {"ok": True}

    return tr


@pytest_asyncio.fixture
async def api(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("COOKIE_SECURE", "False")
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()

    app = create_app()
    app.include_router(_test_router(), prefix="/api/v1")
    c = AsyncMongoMockClient()
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
    "email,esperado",
    [("consulta@roddos.com", 403), ("fin@roddos.com", 200), ("admin@roddos.com", 200)],
)
async def test_export_por_rol(api, email, esperado):
    # DoD #1: Consulta NO exporta; Financiero/Admin sí.
    tok = await _token(api, email)
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.get("/api/v1/_test/export", headers=h)
    assert r.status_code == esperado


@pytest.mark.parametrize(
    "email,esperado",
    [("consulta@roddos.com", 403), ("fin@roddos.com", 403), ("admin@roddos.com", 200)],
)
async def test_require_role_admin(api, email, esperado):
    tok = await _token(api, email)
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.get("/api/v1/_test/solo-admin", headers=h)
    assert r.status_code == esperado


async def test_sin_token_es_401(api):
    r = await api.get("/api/v1/_test/export")
    assert r.status_code == 401


async def test_capabilities_endpoint(api):
    tok = await _token(api, "consulta@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.get("/api/v1/auth/capabilities", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["rol"] == "consulta"
    assert body["capabilities"] == ["dashboard:leer"]
```


## salida: pytest -q

```
...........sss.....s......s............................................. [ 83%]
........s.....                                                           [100%]
=========================== short test summary info ===========================
SKIPPED [3] tests\test_audit_immutable.py: requiere Mongo real; correr con: pytest -m requires_real_mongo
SKIPPED [1] tests\test_auth_concurrency.py: requiere Mongo real; correr con: pytest -m requires_real_mongo
SKIPPED [1] tests\test_auth_indexes.py: requiere Mongo real; correr con: pytest -m requires_real_mongo
SKIPPED [1] tests\test_real_mongo_marker.py:11: requiere Mongo real; correr con: pytest -m requires_real_mongo
80 passed, 6 skipped in 18.00s
```


## salida: pytest -q -m requires_real_mongo

```
FFFFFF                                                                   [100%]
================================== FAILURES ===================================
________________ test_update_sobre_audit_log_falla_con_rol_app ________________

    def test_update_sobre_audit_log_falla_con_rol_app():
        # Con la conexión general de la app (sin update), un update_one sobre audit_log
        # debe lanzar OperationFailure (code 13, Unauthorized).
>       raise AssertionError("Pendiente CI Sesión 3: requiere mongod real con roles.")
E       AssertionError: Pendiente CI Sesión 3: requiere mongod real con roles.

tests\test_audit_immutable.py:24: AssertionError
________________ test_remove_sobre_audit_log_falla_con_rol_app ________________

    def test_remove_sobre_audit_log_falla_con_rol_app():
>       raise AssertionError("Pendiente CI Sesión 3: requiere mongod real con roles.")
E       AssertionError: Pendiente CI Sesión 3: requiere mongod real con roles.

tests\test_audit_immutable.py:28: AssertionError
_______________ test_insert_y_find_como_compas_audit_funcionan ________________

    def test_insert_y_find_como_compas_audit_funcionan():
        # Test POSITIVO: sin él, un rol roto sin insert pasaría el negativo y el audit
        # moriría en silencio.
>       raise AssertionError("Pendiente CI Sesión 3: requiere mongod real con roles.")
E       AssertionError: Pendiente CI Sesión 3: requiere mongod real con roles.

tests\test_audit_immutable.py:34: AssertionError
_______________ test_rotacion_exactamente_una_bajo_concurrencia _______________

    def test_rotacion_exactamente_una_bajo_concurrencia():
>       raise AssertionError("Pendiente CI Sesión 3: requiere mongod real (atomicidad).")
E       AssertionError: Pendiente CI Sesión 3: requiere mongod real (atomicidad).

tests\test_auth_concurrency.py:17: AssertionError
_________________ test_indices_de_auth_existen_tras_el_script _________________

    def test_indices_de_auth_existen_tras_el_script():
        # Verificará: users.email único; refresh_sessions.jti único + family_id + TTL;
        # jwt_denylist.jti único + TTL; login_throttle TTL (expireAfterSeconds:0).
>       raise AssertionError(
            "Pendiente CI Sesión 3: requiere mongod real + create_auth_indexes.py."
        )
E       AssertionError: Pendiente CI Sesión 3: requiere mongod real + create_auth_indexes.py.

tests\test_auth_indexes.py:16: AssertionError
_________________ test_placeholder_dedup_indice_unico_parcial _________________

    @pytest.mark.requires_real_mongo
    def test_placeholder_dedup_indice_unico_parcial():
        # Sprint 1: aquí irá el test del índice único parcial (banco, id_banco)
        # con partialFilterExpression {id_banco:{$type:'string'}} + DuplicateKeyError.
        # mongomock NO lo soporta → debe correr contra Mongo real.
>       raise AssertionError(
            "Este test no debería ejecutarse sin `-m requires_real_mongo`."
        )
E       AssertionError: Este test no debería ejecutarse sin `-m requires_real_mongo`.

tests\test_real_mongo_marker.py:16: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_audit_immutable.py::test_update_sobre_audit_log_falla_con_rol_app
FAILED tests/test_audit_immutable.py::test_remove_sobre_audit_log_falla_con_rol_app
FAILED tests/test_audit_immutable.py::test_insert_y_find_como_compas_audit_funcionan
FAILED tests/test_auth_concurrency.py::test_rotacion_exactamente_una_bajo_concurrencia
FAILED tests/test_auth_indexes.py::test_indices_de_auth_existen_tras_el_script
FAILED tests/test_real_mongo_marker.py::test_placeholder_dedup_indice_unico_parcial
6 failed, 80 deselected in 0.21s
```


## salida: ruff check .

```
All checks passed!
```

