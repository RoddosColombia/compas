# EVIDENCIA — I-PR2 (auth): fuentes íntegras + salidas

Paquete de código para la auditoría de PR-2 (evidencia > descripción).


## archivo: backend/app/auth/roles.py

```
# backend/app/auth/roles.py
"""Roles de COMPAS (Spec §1.1). Catálogo cerrado de 4 — no hay "superadmin"."""

from enum import StrEnum


class Role(StrEnum):
    admin = "admin"
    directivo = "directivo"
    financiero = "financiero"
    consulta = "consulta"
```


## archivo: backend/app/auth/passwords.py

```
# backend/app/auth/passwords.py
"""Hashing bcrypt + política de contraseñas (Spec §1.1 / §8.1).

Costo fijo rounds=12 (no solo longitud). Política de LONGITUD: 12 para admin/directivo,
10 para el resto. HIBP y expiración quedan para Sprint 0b (fuera de PR-2)."""

import bcrypt

from app.auth.roles import Role

ROUNDS = 12
_LARGOS = {Role.admin: 12, Role.directivo: 12, Role.financiero: 10, Role.consulta: 10}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=ROUNDS)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def password_meets_policy(password: str, rol: Role) -> bool:
    return len(password) >= _LARGOS[rol]


# Hash dummy para comparar cuando el email no existe → login de tiempo/forma uniforme
# (anti-enumeración, Kimi M-04). Se computa una vez al importar.
DUMMY_HASH = hash_password("dummy-password-anti-enumeration-000")
```


## archivo: backend/app/auth/tokens.py

```
# backend/app/auth/tokens.py
"""JWT access/refresh endurecido (Spec §4 / §8.1; cripto Kimi Bajas 3/4).

- `algorithms=['HS256']` explícito en decode (defensa alg=none).
- `leeway=30s`; `jti` uuid4 (≥128 bits) en access y refresh.
- Claims: sub (usuario_id), tv (token_version), type (access|refresh), jti, iat, exp;
  el refresh añade family_id. Tiempos UTC-aware (regla A-04)."""

from datetime import timedelta
from uuid import uuid4

import jwt

from app.core.time import now_utc

ALGO = "HS256"
LEEWAY = 30
ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=30)


class TokenError(Exception):
    """Token inválido (firma, expiración, tipo o algoritmo)."""


def _new_jti() -> str:
    return uuid4().hex


def create_access_token(
    secret: str,
    *,
    sub: str,
    tv: int,
    jti: str | None = None,
    ttl: timedelta = ACCESS_TTL,
) -> str:
    now = now_utc()
    claims = {
        "sub": sub,
        "tv": tv,
        "type": "access",
        "jti": jti or _new_jti(),
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(claims, secret, algorithm=ALGO)


def create_refresh_token(
    secret: str,
    *,
    sub: str,
    tv: int,
    family_id: str,
    jti: str | None = None,
    ttl: timedelta = REFRESH_TTL,
) -> str:
    now = now_utc()
    claims = {
        "sub": sub,
        "tv": tv,
        "type": "refresh",
        "family_id": family_id,
        "jti": jti or _new_jti(),
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(claims, secret, algorithm=ALGO)


def decode_token(
    secret: str, token: str, *, expected_type: str, verify_exp: bool = True
) -> dict:
    """`verify_exp=False` (solo para logout, Kimi H-6): decodifica con firma válida
    un access ya expirado para extraer jti/exp y denegarlo hasta su exp natural."""
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[ALGO],
            leeway=LEEWAY,
            options={"verify_exp": verify_exp},
        )
    except jwt.PyJWTError as e:
        raise TokenError(str(e)) from e
    if claims.get("type") != expected_type:
        raise TokenError(f"tipo inesperado: {claims.get('type')} != {expected_type}")
    return claims
```


## archivo: backend/app/auth/models.py

```
# backend/app/auth/models.py
"""Esquemas de auth (Pydantic strict). Spec §1.1 / §2.3.

Como en audit, son Pydantic planos: la persistencia va por repositorios con Motor
crudo (no Beanie ODM). Tiempos UTC-aware (regla A-04)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.roles import Role
from app.core.time import now_utc

USERS_COLLECTION = "users"
REFRESH_SESSIONS_COLLECTION = "refresh_sessions"
JWT_DENYLIST_COLLECTION = "jwt_denylist"
LOGIN_THROTTLE_COLLECTION = "login_throttle"

AUTH_INDEXES = {
    USERS_COLLECTION: [{"keys": [("email", 1)], "name": "email_unico", "unique": True}],
    REFRESH_SESSIONS_COLLECTION: [
        {"keys": [("jti", 1)], "name": "jti_unico", "unique": True},
        {"keys": [("family_id", 1)], "name": "por_familia"},
        # TTL familia (refresh_ttl_days): mecanismo expireAfterSeconds:0 + expires_at
        {"keys": [("expires_at", 1)], "name": "ttl_familia", "expireAfterSeconds": 0},
    ],
    JWT_DENYLIST_COLLECTION: [
        {"keys": [("jti", 1)], "name": "jti_unico", "unique": True},
        {"keys": [("expires_at", 1)], "name": "ttl_por_tipo", "expireAfterSeconds": 0},
    ],
    LOGIN_THROTTLE_COLLECTION: [
        {"keys": [("expires_at", 1)], "name": "ttl_ventana", "expireAfterSeconds": 0},
    ],
}


class User(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: str | None = None
    email: str  # normalizado strip().lower() en el servicio; unicidad por índice
    password_hash: str
    rol: Role
    token_version: int = 1
    activo: bool = True
    failed_attempts: int = 0
    locked_until: datetime | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    @field_validator("rol", mode="before")
    @classmethod
    def _cast_rol(cls, v: object) -> Role:
        return v if isinstance(v, Role) else Role(v)  # str→Role al leer de Mongo

    @field_validator("locked_until", "created_at", "updated_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("datetime debe ser UTC-aware (regla A-04)")
        return v


class RefreshSession(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    jti: str
    usuario_id: str
    family_id: str
    family_created_at: datetime = Field(default_factory=now_utc)  # inmutable, heredado
    ultimo_uso: datetime = Field(default_factory=now_utc)
    expires_at: datetime  # family_created_at + refresh_ttl_days (para el TTL)
    rotado: bool = False
    revocado: bool = False
```


## archivo: backend/app/auth/repository.py

```
# backend/app/auth/repository.py
"""Persistencia de auth con Motor crudo (como audit; sin Beanie ODM).

Colecciones: users, refresh_sessions, jwt_denylist, login_throttle.
`configure_auth(client)` se llama en el lifespan; en tests se inyecta mongomock."""

from datetime import UTC, datetime, timedelta
from typing import Any

from app.auth.models import (
    JWT_DENYLIST_COLLECTION,
    LOGIN_THROTTLE_COLLECTION,
    REFRESH_SESSIONS_COLLECTION,
    USERS_COLLECTION,
    RefreshSession,
    User,
)
from app.core.time import now_utc

_db: Any = None


def configure_auth(client: Any, db_name: str = "compas") -> None:
    global _db
    _db = client[db_name]


def reset_auth() -> None:
    global _db
    _db = None


def _col(name: str) -> Any:
    if _db is None:
        raise RuntimeError("auth no configurado: llamar configure_auth(client) primero")
    return _db[name]


def _awaken(doc: dict) -> dict:
    """Normaliza datetimes naive a UTC-aware. BSON guarda UTC; con tz_aware=True el
    driver real ya devuelve aware, pero mongomock (y drivers sin tz_aware) devuelven
    naive. Tratamos lo almacenado como UTC (el validator del modelo sigue rechazando
    naive en construcción directa en código — Kimi H-05)."""
    for k, v in doc.items():
        if isinstance(v, datetime) and v.tzinfo is None:
            doc[k] = v.replace(tzinfo=UTC)
    return doc


def _to_user(doc: dict | None) -> User | None:
    if not doc:
        return None
    d = _awaken(dict(doc))
    _id = d.pop("_id", None)
    return User(id=str(_id) if _id is not None else None, **d)


# ── Users ──────────────────────────────────────────────────────────────
async def get_user_by_email(email: str) -> User | None:
    return _to_user(await _col(USERS_COLLECTION).find_one({"email": email}))


async def get_user_by_id(user_id: str) -> User | None:
    from bson import ObjectId

    try:
        oid = ObjectId(user_id)
    except Exception:  # noqa: BLE001 — id malformado = usuario inexistente
        return None
    return _to_user(await _col(USERS_COLLECTION).find_one({"_id": oid}))


async def create_user(user: User) -> str:
    payload = user.model_dump(mode="python", exclude={"id"})
    payload["rol"] = user.rol.value
    res = await _col(USERS_COLLECTION).insert_one(payload)
    return str(res.inserted_id)


async def set_token_version(user_id: str, token_version: int) -> None:
    from bson import ObjectId

    await _col(USERS_COLLECTION).update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"token_version": token_version, "updated_at": now_utc()}},
    )


async def register_failed_login(
    user_id: str, *, max_intentos: int, lock_min: int
) -> None:
    """Incrementa failed_attempts; si alcanza el máximo, fija locked_until."""
    from bson import ObjectId

    col = _col(USERS_COLLECTION)
    doc = await col.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$inc": {"failed_attempts": 1}, "$set": {"updated_at": now_utc()}},
        return_document=True,
    )
    if doc and doc.get("failed_attempts", 0) >= max_intentos:
        await col.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"locked_until": now_utc() + timedelta(minutes=lock_min)}},
        )


async def reset_failed_login(user_id: str) -> None:
    from bson import ObjectId

    await _col(USERS_COLLECTION).update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"failed_attempts": 0, "locked_until": None, "updated_at": now_utc()}},
    )


# ── Refresh sessions ───────────────────────────────────────────────────
async def create_refresh_session(session: RefreshSession) -> None:
    await _col(REFRESH_SESSIONS_COLLECTION).insert_one(
        session.model_dump(mode="python")
    )


async def get_refresh_session(jti: str) -> RefreshSession | None:
    doc = await _col(REFRESH_SESSIONS_COLLECTION).find_one({"jti": jti})
    if not doc:
        return None
    doc = _awaken(dict(doc))
    doc.pop("_id", None)
    return RefreshSession(**doc)


async def rotate_refresh_session(jti: str) -> bool:
    """Marca rotado=true de forma ATÓMICA. Devuelve True si ganó la carrera
    (rotado pasó de false→true), False si el jti ya estaba rotado/no existe → reuso."""
    doc = await _col(REFRESH_SESSIONS_COLLECTION).find_one_and_update(
        {"jti": jti, "rotado": False, "revocado": False},
        {"$set": {"rotado": True, "ultimo_uso": now_utc()}},
    )
    return doc is not None


async def revoke_family(family_id: str) -> None:
    await _col(REFRESH_SESSIONS_COLLECTION).update_many(
        {"family_id": family_id}, {"$set": {"revocado": True}}
    )


# ── Denylist ───────────────────────────────────────────────────────────
async def denylist_add(jti: str, expires_at: datetime) -> None:
    await _col(JWT_DENYLIST_COLLECTION).update_one(
        {"jti": jti}, {"$set": {"jti": jti, "expires_at": expires_at}}, upsert=True
    )


async def denylist_contains(jti: str) -> bool:
    return await _col(JWT_DENYLIST_COLLECTION).find_one({"jti": jti}) is not None


# ── Rate limit por IP ──────────────────────────────────────────────────
async def register_ip_attempt(ip: str, *, window_min: int) -> int:
    """Incrementa el contador de intentos de la IP en la ventana y devuelve el total."""
    col = _col(LOGIN_THROTTLE_COLLECTION)
    doc = await col.find_one_and_update(
        {"_id": f"ip:{ip}"},
        {
            "$inc": {"count": 1},
            "$setOnInsert": {"expires_at": now_utc() + timedelta(minutes=window_min)},
        },
        upsert=True,
        return_document=True,
    )
    return doc.get("count", 1) if doc else 1
```


## archivo: backend/app/auth/service.py

```
# backend/app/auth/service.py
"""Flujos de auth: login, refresh (rotación atómica + detección de reuso), logout,
authenticate. Spec §4 / §8.1. Tiempos UTC-aware; eventos por emit_audit.

Política de auditoría (O1): los eventos de auth NO son operaciones de estado del
ciclo → se emiten fire-and-forget (try/except + log); un fallo del canal de audit no
debe tumbar el login (evita DoS). Las operaciones del ciclo (aprobar/cerrar/…) sí
fallan cerrado — eso vive en sus propios módulos."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.auth import passwords, repository, tokens
from app.auth.models import RefreshSession, User
from app.config import Settings
from app.core.time import now_utc

logger = logging.getLogger("compas.auth")


class AuthError(Exception):
    def __init__(self, detail: str, status: int = 401):
        super().__init__(detail)
        self.detail = detail
        self.status = status


# Mensaje ÚNICO para cualquier fallo de credenciales (anti-enumeración, uniforme).
_INVALID = "Credenciales inválidas."


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    refresh_expires_at: datetime


async def _safe_emit(evento: AuditEvento, **kw) -> None:
    try:
        await emit_audit(evento, **kw)
    except Exception:  # noqa: BLE001 — auth no debe fallar por el canal de audit (O1)
        logger.error("no se pudo emitir %s", evento, exc_info=True)


def _issue_pair(
    settings: Settings, user: User, family_id: str, family_created_at: datetime
) -> tuple[TokenPair, RefreshSession]:
    secret = settings.jwt_secret
    access = tokens.create_access_token(
        secret,
        sub=user.id,
        tv=user.token_version,
        ttl=timedelta(minutes=settings.access_ttl_min),
    )
    jti = uuid4().hex
    refresh = tokens.create_refresh_token(
        secret,
        sub=user.id,
        tv=user.token_version,
        family_id=family_id,
        jti=jti,
        ttl=timedelta(days=settings.refresh_ttl_days),
    )
    expires_at = family_created_at + timedelta(days=settings.refresh_ttl_days)
    session = RefreshSession(
        jti=jti,
        usuario_id=user.id,
        family_id=family_id,
        family_created_at=family_created_at,
        ultimo_uso=now_utc(),
        expires_at=expires_at,
    )
    return TokenPair(access, refresh, expires_at), session


async def login(settings: Settings, *, email: str, password: str, ip: str) -> TokenPair:
    if not settings.jwt_secret:
        raise AuthError("servicio de auth no configurado", status=500)

    # Rate limit por IP (además del backoff por cuenta) — Kimi M-05.
    count = await repository.register_ip_attempt(
        ip, window_min=settings.login_ip_window_min
    )
    if count > settings.login_ip_max:
        raise AuthError("Demasiados intentos. Intente más tarde.", status=429)

    email = email.strip().lower()
    user = await repository.get_user_by_email(email)

    # Anti-enumeración: si no existe, gastamos el mismo tiempo con el hash dummy.
    if user is None:
        passwords.verify_password(password, passwords.DUMMY_HASH)
        await _safe_emit(
            AuditEvento.user_login_fallido, entidad="user", metadata={"email": email}
        )
        raise AuthError(_INVALID)

    bloqueado = user.locked_until is not None and user.locked_until > now_utc()
    if (
        bloqueado
        or not user.activo
        or not passwords.verify_password(password, user.password_hash)
    ):
        # Solo cuenta como fallo real (no si ya estaba bloqueado/inactivo).
        if user.activo and not bloqueado:
            await repository.register_failed_login(
                user.id,
                max_intentos=settings.login_max_intentos,
                lock_min=settings.login_lock_min,
            )
            refreshed = await repository.get_user_by_email(email)
            if (
                refreshed
                and refreshed.locked_until
                and refreshed.failed_attempts >= settings.login_max_intentos
            ):
                await _safe_emit(
                    AuditEvento.user_bloqueado, entidad="user", entidad_id=user.id
                )
        await _safe_emit(
            AuditEvento.user_login_fallido, entidad="user", entidad_id=user.id
        )
        raise AuthError(_INVALID)

    # Éxito.
    await repository.reset_failed_login(user.id)
    family_id = uuid4().hex
    pair, session = _issue_pair(settings, user, family_id, now_utc())
    await repository.create_refresh_session(session)
    await _safe_emit(
        AuditEvento.user_login,
        entidad="user",
        entidad_id=user.id,
        actor_id=user.id,
        metadata={"ip": ip},
    )
    return pair


async def refresh(settings: Settings, *, refresh_token: str) -> TokenPair:
    if not settings.jwt_secret:
        raise AuthError("servicio de auth no configurado", status=500)
    try:
        claims = tokens.decode_token(
            settings.jwt_secret, refresh_token, expected_type="refresh"
        )
    except tokens.TokenError as e:
        raise AuthError(_INVALID) from e

    jti, family_id, sub, tv = (
        claims["jti"],
        claims["family_id"],
        claims["sub"],
        claims["tv"],
    )

    if await repository.denylist_contains(jti):
        raise AuthError(_INVALID)

    session = await repository.get_refresh_session(jti)
    if session is None or session.revocado:
        # jti desconocido o familia revocada → tratar como reuso: revocar familia.
        await repository.revoke_family(family_id)
        await _safe_emit(
            AuditEvento.user_bloqueado,
            entidad="user",
            entidad_id=sub,
            metadata={"motivo": "reuso_refresh"},
        )
        raise AuthError(_INVALID)

    now = now_utc()
    idle_limit = session.ultimo_uso + timedelta(hours=settings.refresh_idle_hours)
    if now > idle_limit or now > session.expires_at:
        raise AuthError(_INVALID)

    user = await repository.get_user_by_id(sub)
    if user is None or not user.activo or user.token_version != tv:
        raise AuthError(_INVALID)

    # Rotación ATÓMICA. Si perdemos (ya rotado) → REUSO → revocar familia.
    gano = await repository.rotate_refresh_session(jti)
    if not gano:
        await repository.revoke_family(family_id)
        await _safe_emit(
            AuditEvento.user_bloqueado,
            entidad="user",
            entidad_id=sub,
            metadata={"motivo": "reuso_refresh"},
        )
        raise AuthError(_INVALID)

    # Nueva sesión en la MISMA familia (family_created_at heredado → TTL estable).
    pair, new_session = _issue_pair(
        settings, user, family_id, session.family_created_at
    )
    await repository.create_refresh_session(new_session)
    return pair


async def logout(
    settings: Settings, *, access_token: str | None, refresh_token: str | None
) -> None:
    secret = settings.jwt_secret
    # Access: verify_exp=False para denegar su jti hasta su exp natural (H-6).
    if access_token:
        try:
            c = tokens.decode_token(
                secret, access_token, expected_type="access", verify_exp=False
            )
            await repository.denylist_add(c["jti"], _exp_dt(c))
        except tokens.TokenError:
            pass
    if refresh_token:
        try:
            c = tokens.decode_token(secret, refresh_token, expected_type="refresh")
            await repository.denylist_add(c["jti"], _exp_dt(c))
            await repository.revoke_family(c["family_id"])
        except tokens.TokenError:
            pass


async def authenticate(settings: Settings, *, access_token: str) -> User:
    """Valida el access por request: firma, tipo, denylist, activo y token_version."""
    try:
        claims = tokens.decode_token(
            settings.jwt_secret, access_token, expected_type="access"
        )
    except tokens.TokenError as e:
        raise AuthError("No autenticado.") from e
    if await repository.denylist_contains(claims["jti"]):
        raise AuthError("Sesión revocada.")
    user = await repository.get_user_by_id(claims["sub"])
    if user is None or not user.activo or user.token_version != claims["tv"]:
        raise AuthError("Sesión revocada.")
    return user


def _exp_dt(claims: dict) -> datetime:
    from datetime import UTC

    return datetime.fromtimestamp(claims["exp"], tz=UTC)
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
    ip = request.client.host if request.client else "unknown"
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
```


## archivo: backend/app/auth/deps.py

```
# backend/app/auth/deps.py
"""Dependencia get_current_user (base del RBAC de PR-3).

Extrae el access de Authorization: Bearer y lo valida (firma, tipo, denylist,
activo, token_version) vía service.authenticate."""

from fastapi import Depends, HTTPException, Request

from app.auth import service
from app.auth.models import User
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
```


## archivo: backend/app/config.py

```
# backend/app/config.py
"""Configuración de la app vía Pydantic Settings.

Regla 12 de CLAUDE.md / STACK §5.1: las env vars son SOLO para secretos y
conexiones. Las reglas de negocio parametrizables (umbrales, calendario DIAN)
NO viven aquí: van en la colección `configuracion` (Spec §1.10), y se
implementan desde el Sprint 0b.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignora env vars ajenas (Render/OS inyectan muchas)
        case_sensitive=False,
    )

    # ── Entorno ────────────────────────────────────────────────────────
    # Literal (Kimi Baja): un typo en APP_ENV falla al validar, no en runtime.
    app_env: Literal["development", "staging", "production"] = "development"
    # Zona horaria única de la app (regla 2). La región cloud es otra cosa
    # (se hereda de SISMO; ver RUNBOOK §0).
    tz: str = "America/Bogota"

    # ── Scheduler (regla 6) ────────────────────────────────────────────
    # false en el servicio web SIEMPRE; true SOLO en el worker compas-jobs.
    run_scheduler: bool = False

    # ── Conexión a Mongo (secreto: sync=false en render.yaml) ──────────
    mongodb_uri_compas: str = "mongodb://localhost:27017"
    mongodb_db: str = "compas"
    # Segunda cadena a la MISMA database `compas`, usuario `compas_audit`
    # (rol audit_writer). Inmutabilidad del audit_log (DoD #6; errata E-7 en
    # docs/COMPAS_ERRATA_PENDIENTE_v1_1_3.md). Opcional en dev; obligatoria fuera.
    mongodb_uri_audit: str | None = None

    # ── Auth / sesiones (Spec §4/§8.1) ────────────────────────────────
    access_ttl_min: int = 15  # access token (memoria SPA)
    refresh_ttl_days: int = 30  # vida máxima de la familia de refresh
    refresh_idle_hours: int = 12  # idle máximo del refresh
    login_max_intentos: int = 5  # backoff por cuenta
    login_lock_min: int = 15  # bloqueo tras superar intentos
    login_ip_max: int = 20  # rate limit por IP en la ventana
    login_ip_window_min: int = 15
    cookie_secure: bool = True  # false solo para pruebas locales sin TLS
    frontend_origin: str = "https://compas.roddos.com"  # CORS + verificación de Origin

    # ── Secretos (opcionales en dev/skeleton; obligatorios en prod) ────
    jwt_secret: str | None = None
    sentry_dsn: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    s3_bucket: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Instancia única de Settings (cacheada). Los tests que cambian env vars
    deben llamar `get_settings.cache_clear()`."""
    return Settings()
```


## archivo: backend/app/main.py

```
# backend/app/main.py
"""Punto de entrada del servicio web FastAPI (compas-api).

Regla 6 de CLAUDE.md: el servicio web NUNCA arranca el scheduler. El lifespan
falla en duro si detecta RUN_SCHEDULER=true (defensa contra un despliegue mal
configurado)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_router
from app.audit import service as audit_service
from app.auth import repository as auth_repository
from app.config import get_settings
from app.db import mongo

logger = logging.getLogger("compas")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Regla 6: el web jamás corre el scheduler.
    if settings.run_scheduler:
        raise RuntimeError(
            "RUN_SCHEDULER=true en el servicio web: prohibido (regla 6). "
            "Los jobs viven solo en el worker compas-jobs."
        )

    # Cliente Motor perezoso (no conecta hasta el primer comando) → el web
    # arranca aunque Mongo esté caído; la liveness no depende de la BD.
    client = mongo.create_client(settings.mongodb_uri_compas)
    app.state.mongo_client = client
    app.state.settings = settings
    # NOTA (Sprint 0b): cuando existan document models, llamar aquí
    #   await mongo.init_beanie_for(client, settings.mongodb_db)

    # Conexión DEDICADA de auditoría (DoD #6). MONGODB_URI_AUDIT usa el usuario
    # `compas_audit` (audit_writer). FAIL-FAST fuera de dev (Kimi C-01): un warning
    # no es un control — degradar el canal de auditoría en prod es degradación
    # silenciosa de un requisito de primera clase. Solo dev cae a la conexión general.
    if settings.mongodb_uri_audit:
        audit_client = mongo.create_client(settings.mongodb_uri_audit)
    elif settings.app_env == "development":
        audit_client = client  # fallback SOLO en dev (sin separación de privilegios)
        logger.warning(
            "audit por conexión general (dev): sin separación de privilegios."
        )
    else:
        raise RuntimeError(
            "MONGODB_URI_AUDIT requerido fuera de dev: el canal de auditoría no "
            "puede degradarse silenciosamente (DoD #6, Kimi C-01)."
        )
    app.state.audit_client = audit_client
    audit_service.configure_audit(audit_client, settings.mongodb_db)

    # Auth usa la conexión GENERAL de la app (no la de auditoría).
    auth_repository.configure_auth(client, settings.mongodb_db)

    try:
        yield
    finally:
        audit_service.reset_audit()
        auth_repository.reset_auth()
        if audit_client is not client:
            audit_client.close()
        client.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="COMPAS API",
        version=__version__,
        lifespan=lifespan,
    )

    # CORS: origen exacto del frontend + credenciales (cookie de refresh). Spec §4.
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["health"])
    def liveness() -> dict[str, str]:
        """Liveness — SIN tocar la BD. Es el healthCheckPath de render.yaml."""
        return {"status": "ok", "service": "compas-api", "version": __version__}

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
```


## archivo: backend/app/api/v1/__init__.py

```
# backend/app/api/v1/__init__.py
"""Router raíz de la API v1 (regla: API bajo /api/v1)."""

from fastapi import APIRouter

from app.api.v1 import health
from app.auth.router import router as auth_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth_router)
```


## archivo: backend/tests/test_auth_passwords.py

```
# backend/tests/test_auth_passwords.py
"""Hashing y política de contraseñas (PR-2). Spec §1.1 / §8.1."""

import time

import pytest
from app.auth import passwords
from app.auth.roles import Role


def test_hash_y_verify_ok():
    h = passwords.hash_password("una-clave-larga-123")
    assert h != "una-clave-larga-123"
    assert passwords.verify_password("una-clave-larga-123", h)
    assert not passwords.verify_password("otra", h)


def test_bcrypt_cost_12():
    # Kimi Baja: fijar el costo (no solo longitud). bcrypt guarda el cost: $2b$12$
    h = passwords.hash_password("clave-larga-1234")
    assert h.split("$")[2] == "12"


def test_hash_latencia_bajo_1s():
    t0 = time.perf_counter()
    passwords.hash_password("clave-larga-1234")
    assert (time.perf_counter() - t0) < 1.0


@pytest.mark.parametrize(
    "rol,largo,ok",
    [
        (Role.admin, 12, True),
        (Role.admin, 11, False),
        (Role.directivo, 12, True),
        (Role.directivo, 11, False),
        (Role.financiero, 10, True),
        (Role.financiero, 9, False),
        (Role.consulta, 10, True),
        (Role.consulta, 9, False),
    ],
)
def test_politica_de_longitud_por_rol(rol, largo, ok):
    assert passwords.password_meets_policy("x" * largo, rol) is ok


def test_dummy_hash_para_anti_enumeracion():
    # verify contra el hash dummy nunca acierta, pero cuesta ~lo mismo (constant-time).
    assert passwords.verify_password("lo-que-sea", passwords.DUMMY_HASH) is False
```


## archivo: backend/tests/test_auth_tokens.py

```
# backend/tests/test_auth_tokens.py
"""JWT access/refresh (PR-2). Cripto endurecida (Kimi): HS256 explícito, leeway,
jti uuid4 en ambos, claims token_version/type/family_id."""

from datetime import timedelta

import jwt
import pytest
from app.auth import tokens

SECRET = "x" * 40  # >= 32 bytes


def test_access_token_claims():
    tok = tokens.create_access_token(SECRET, sub="u1", tv=1)
    claims = tokens.decode_token(SECRET, tok, expected_type="access")
    assert claims["sub"] == "u1"
    assert claims["tv"] == 1
    assert claims["type"] == "access"
    assert len(claims["jti"]) >= 32  # uuid4 hex


def test_refresh_token_lleva_family_id_y_jti():
    tok = tokens.create_refresh_token(SECRET, sub="u1", tv=1, family_id="fam1")
    claims = tokens.decode_token(SECRET, tok, expected_type="refresh")
    assert claims["type"] == "refresh"
    assert claims["family_id"] == "fam1"
    assert claims["jti"]


def test_decode_rechaza_tipo_incorrecto():
    tok = tokens.create_access_token(SECRET, sub="u1", tv=1)
    with pytest.raises(tokens.TokenError):
        tokens.decode_token(SECRET, tok, expected_type="refresh")


def test_decode_rechaza_firma_invalida():
    tok = tokens.create_access_token(SECRET, sub="u1", tv=1)
    with pytest.raises(tokens.TokenError):
        tokens.decode_token(
            "otro-secreto-distinto-de-32-bytes-abcd", tok, expected_type="access"
        )


def test_decode_rechaza_expirado():
    tok = tokens.create_access_token(
        SECRET, sub="u1", tv=1, ttl=timedelta(seconds=-120)
    )
    with pytest.raises(tokens.TokenError):
        tokens.decode_token(SECRET, tok, expected_type="access")


def test_algoritmo_fijado_hs256_no_none():
    # Defensa contra el ataque alg=none: decode exige HS256.
    payload = {"sub": "u1", "type": "access", "tv": 1, "jti": "x"}
    tok_none = jwt.encode(payload, key="", algorithm="none")
    with pytest.raises(tokens.TokenError):
        tokens.decode_token(SECRET, tok_none, expected_type="access")
```


## archivo: backend/tests/test_auth_service.py

```
# backend/tests/test_auth_service.py
"""Lógica de auth (PR-2) con mongomock: login/backoff/anti-enumeración,
token_version, rotación de refresh + detección de reuso, logout, rate limit IP.

La CONCURRENCIA real de la rotación (dos refresh simultáneos → exactamente una
rotación) va en test_auth_concurrency.py con @requires_real_mongo."""

import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository, service, tokens
from app.auth.models import User
from app.auth.roles import Role
from app.config import Settings
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


def _settings(**kw) -> Settings:
    base = dict(
        jwt_secret="x" * 40,
        cookie_secure=False,
        app_env="development",
        login_ip_max=1000,
    )
    base.update(kw)
    return Settings(**base)


@pytest_asyncio.fixture
async def client():
    c = AsyncMongoMockClient()
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")
    u = User(
        email="a@roddos.com", password_hash=passwords.hash_password(PWD), rol=Role.admin
    )
    await repository.create_user(u)
    yield c
    repository.reset_auth()
    reset_audit()


async def test_login_ok_emite_evento_y_da_tokens(client):
    s = _settings()
    pair = await service.login(s, email="A@Roddos.com", password=PWD, ip="1.1.1.1")
    claims = tokens.decode_token(
        s.jwt_secret, pair.access_token, expected_type="access"
    )
    assert claims["type"] == "access"
    audit = await client["compas_test"]["audit_log"].find_one({"evento": "user.login"})
    assert audit is not None


async def test_login_password_incorrecta_es_uniforme(client):
    s = _settings()
    with pytest.raises(service.AuthError) as ei:
        await service.login(s, email="a@roddos.com", password="mala", ip="1.1.1.1")
    assert ei.value.status == 401
    assert ei.value.detail == service._INVALID


async def test_login_email_desconocido_mismo_mensaje(client):
    s = _settings()
    with pytest.raises(service.AuthError) as ei:
        await service.login(s, email="nadie@roddos.com", password="x", ip="1.1.1.1")
    assert ei.value.detail == service._INVALID  # anti-enumeración


async def test_lockout_tras_5_fallos_y_evento_bloqueado(client):
    s = _settings(login_max_intentos=5, login_lock_min=15)
    for _ in range(5):
        with pytest.raises(service.AuthError):
            await service.login(s, email="a@roddos.com", password="mala", ip="1.1.1.1")
    # aun con la clave correcta, queda bloqueado (uniforme 401)
    with pytest.raises(service.AuthError):
        await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    ev = await client["compas_test"]["audit_log"].find_one({"evento": "user.bloqueado"})
    assert ev is not None


async def test_token_version_revoca_access(client):
    s = _settings()
    pair = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    u = await repository.get_user_by_email("a@roddos.com")
    await repository.set_token_version(u.id, u.token_version + 1)
    with pytest.raises(service.AuthError):
        await service.authenticate(s, access_token=pair.access_token)


async def test_refresh_rota_y_detecta_reuso(client):
    s = _settings()
    pair = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    # primer refresh: ok, nuevos tokens
    pair2 = await service.refresh(s, refresh_token=pair.refresh_token)
    assert pair2.access_token
    # REUSO del refresh viejo → detecta y revoca la familia
    with pytest.raises(service.AuthError):
        await service.refresh(s, refresh_token=pair.refresh_token)
    # el refresh "bueno" (pair2) también cae porque la familia quedó revocada
    with pytest.raises(service.AuthError):
        await service.refresh(s, refresh_token=pair2.refresh_token)


async def test_logout_revoca_access_y_refresh(client):
    s = _settings()
    pair = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    await service.logout(
        s, access_token=pair.access_token, refresh_token=pair.refresh_token
    )
    with pytest.raises(service.AuthError):
        await service.authenticate(s, access_token=pair.access_token)
    with pytest.raises(service.AuthError):
        await service.refresh(s, refresh_token=pair.refresh_token)


async def test_rate_limit_por_ip(client):
    s = _settings(login_ip_max=2)
    for _ in range(2):
        with pytest.raises(service.AuthError):
            await service.login(s, email="a@roddos.com", password="mala", ip="9.9.9.9")
    with pytest.raises(service.AuthError) as ei:
        await service.login(s, email="a@roddos.com", password=PWD, ip="9.9.9.9")
    assert ei.value.status == 429  # bloqueado por IP antes de validar credenciales
```


## archivo: backend/tests/test_auth_endpoints.py

```
# backend/tests/test_auth_endpoints.py
"""Endpoints /api/v1/auth (PR-2): login/refresh/logout + cookie de refresh.

Se usa httpx.ASGITransport (async, mismo event loop) y se configuran los repos con
mongomock a mano (el lifespan real no corre en este transporte)."""

import httpx
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.main import create_app
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
    c = AsyncMongoMockClient()
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")
    await repository.create_user(
        User(
            email="a@roddos.com",
            password_hash=passwords.hash_password(PWD),
            rol=Role.admin,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def test_login_200_y_cookie_de_refresh(api):
    r = await api.post(
        "/api/v1/auth/login", json={"email": "a@roddos.com", "password": PWD}
    )
    assert r.status_code == 200
    assert r.json()["access_token"]
    set_cookie = " ".join(r.headers.get_list("set-cookie"))
    low = set_cookie.lower()
    assert "refresh=" in set_cookie
    assert "path=/api/v1/auth" in low
    assert "httponly" in low
    assert "samesite=strict" in low


async def test_login_401_password_mala(api):
    r = await api.post(
        "/api/v1/auth/login", json={"email": "a@roddos.com", "password": "mala"}
    )
    assert r.status_code == 401


async def test_refresh_por_cookie(api):
    await api.post(
        "/api/v1/auth/login", json={"email": "a@roddos.com", "password": PWD}
    )
    r = await api.post(
        "/api/v1/auth/refresh"
    )  # httpx reenvía la cookie (path coincide)
    assert r.status_code == 200
    assert r.json()["access_token"]


async def test_logout_revoca(api):
    login = await api.post(
        "/api/v1/auth/login", json={"email": "a@roddos.com", "password": PWD}
    )
    access = login.json()["access_token"]
    out = await api.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {access}"}
    )
    assert out.status_code == 200
    # tras logout, el refresh (cookie aún presente en el cliente) ya no sirve
    r = await api.post("/api/v1/auth/refresh")
    assert r.status_code == 401
```


## archivo: backend/tests/test_auth_concurrency.py

```
# backend/tests/test_auth_concurrency.py
"""Concurrencia de la rotación de refresh contra Mongo REAL (Kimi A-02/H-4).

mongomock NO garantiza la atomicidad de findOneAndUpdate bajo concurrencia real, así
que este test corre contra un mongod REAL en el CI de la Sesión 3.

Criterio (H-4): dos refresh SIMULTÁNEOS del mismo jti → exactamente UNA rotación (un
solo par de tokens nuevo); el perdedor recibe 401 y la familia se revoca (reuso). Un
test aparte cubre el replay dentro del leeway cuando se implemente en el servidor."""

import pytest

pytestmark = pytest.mark.requires_real_mongo


def test_rotacion_exactamente_una_bajo_concurrencia():
    raise AssertionError("Pendiente CI Sesión 3: requiere mongod real (atomicidad).")
```


## salida: pytest -q

```
..........sss.....s...................................s....              [100%]
=========================== short test summary info ===========================
SKIPPED [3] tests\test_audit_immutable.py: requiere Mongo real; correr con: pytest -m requires_real_mongo
SKIPPED [1] tests\test_auth_concurrency.py: requiere Mongo real; correr con: pytest -m requires_real_mongo
SKIPPED [1] tests\test_real_mongo_marker.py:11: requiere Mongo real; correr con: pytest -m requires_real_mongo
54 passed, 5 skipped in 7.81s
```


## salida: pytest -q -m requires_real_mongo (deben FALLAR)

```
FFFFF                                                                    [100%]
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
FAILED tests/test_real_mongo_marker.py::test_placeholder_dedup_indice_unico_parcial
5 failed, 54 deselected in 0.19s
```


## salida: ruff check .

```
All checks passed!
```

