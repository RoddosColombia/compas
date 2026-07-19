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
