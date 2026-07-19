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


# ── MFA ────────────────────────────────────────────────────────────────
async def _set_user(user_id: str, campos: dict) -> None:
    from bson import ObjectId

    campos["updated_at"] = now_utc()
    await _col(USERS_COLLECTION).update_one(
        {"_id": ObjectId(user_id)}, {"$set": campos}
    )


async def set_mfa_secret(user_id: str, enc_secret: str) -> None:
    """Enrolamiento (setup): guarda el secreto CIFRADO; mfa_habilitado sigue False
    hasta que /activate confirme un código válido."""
    await _set_user(user_id, {"mfa_secret": enc_secret, "mfa_habilitado": False})


async def enable_mfa(user_id: str, hashed_backup_codes: list[str]) -> None:
    """Activación: habilita MFA y fija los códigos de respaldo (hashes)."""
    await _set_user(
        user_id,
        {"mfa_habilitado": True, "mfa_backup_codes": hashed_backup_codes},
    )


async def replace_backup_codes(user_id: str, hashed_backup_codes: list[str]) -> None:
    await _set_user(user_id, {"mfa_backup_codes": hashed_backup_codes})


async def clear_mfa(user_id: str, new_token_version: int) -> None:
    """Reset de MFA: borra secreto y códigos, deshabilita y BUMP token_version
    (revoca todas las sesiones activas — el access viejo deja de validar)."""
    await _set_user(
        user_id,
        {
            "mfa_secret": None,
            "mfa_habilitado": False,
            "mfa_backup_codes": [],
            "token_version": new_token_version,
        },
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


async def revoke_family(family_id: str) -> int:
    """Revoca la familia y devuelve cuántas sesiones NO-revocadas pasó a revocadas
    (para emitir el evento solo en la transición — Kimi H5)."""
    res = await _col(REFRESH_SESSIONS_COLLECTION).update_many(
        {"family_id": family_id, "revocado": False}, {"$set": {"revocado": True}}
    )
    return getattr(res, "modified_count", 0)


# ── Denylist ───────────────────────────────────────────────────────────
async def denylist_add(jti: str, expires_at: datetime) -> None:
    await _col(JWT_DENYLIST_COLLECTION).update_one(
        {"jti": jti}, {"$set": {"jti": jti, "expires_at": expires_at}}, upsert=True
    )


async def denylist_contains(jti: str) -> bool:
    return await _col(JWT_DENYLIST_COLLECTION).find_one({"jti": jti}) is not None


# ── Rate limit por IP ──────────────────────────────────────────────────
async def register_ip_attempt(ip: str, *, window_min: int) -> int:
    """Incrementa el contador de intentos de la IP en la ventana y devuelve el total.
    El TTL (expires_at + índice expireAfterSeconds:0) reinicia la ventana; sin ese
    índice el contador sería monótono para siempre (Kimi L4)."""
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


async def reset_ip_attempts(ip: str) -> None:
    """Libera el cupo de la IP tras un login exitoso (Kimi H1): así una ráfaga
    legítima desde una NAT de oficina no se auto-bloquea con 429."""
    await _col(LOGIN_THROTTLE_COLLECTION).delete_one({"_id": f"ip:{ip}"})


async def _bump_throttle(key: str, window_min: int) -> int:
    doc = await _col(LOGIN_THROTTLE_COLLECTION).find_one_and_update(
        {"_id": key},
        {
            "$inc": {"count": 1},
            "$setOnInsert": {"expires_at": now_utc() + timedelta(minutes=window_min)},
        },
        upsert=True,
        return_document=True,
    )
    return doc.get("count", 1) if doc else 1


async def register_mfa_attempt(user_id: str, ip: str, *, window_min: int) -> int:
    """Throttle de /auth/mfa/verify por CUENTA e IP (6 dígitos = fuerza bruta viable).
    Devuelve el mayor de los dos contadores. Mismo TTL que el rate limit de login."""
    a = await _bump_throttle(f"mfa:acct:{user_id}", window_min)
    b = await _bump_throttle(f"mfa:ip:{ip}", window_min)
    return max(a, b)


async def reset_mfa_attempts(user_id: str, ip: str) -> None:
    await _col(LOGIN_THROTTLE_COLLECTION).delete_one({"_id": f"mfa:acct:{user_id}"})
    await _col(LOGIN_THROTTLE_COLLECTION).delete_one({"_id": f"mfa:ip:{ip}"})
