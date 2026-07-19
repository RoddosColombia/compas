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
from app.auth import mfa, passwords, repository, tokens
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


@dataclass
class MfaChallenge:
    """1er paso del login para usuarios con MFA: no da acceso; se canjea en
    /auth/mfa/verify con un código TOTP o de respaldo."""

    challenge_token: str


async def _safe_emit(evento: AuditEvento, **kw) -> None:
    try:
        await emit_audit(evento, **kw)
    except Exception:  # noqa: BLE001 — auth no debe fallar por el canal de audit (O1)
        # H3: registrar Y alertar (Sentry si está), no tragar en silencio.
        logger.error("no se pudo emitir %s", evento, exc_info=True)
        try:
            import sentry_sdk

            sentry_sdk.capture_exception()
        except ImportError:
            pass


def _issue_pair(
    settings: Settings,
    user: User,
    family_id: str,
    family_created_at: datetime,
    *,
    mfa_at: int | None = None,
) -> tuple[TokenPair, RefreshSession]:
    secret = settings.jwt_secret
    access = tokens.create_access_token(
        secret,
        sub=user.id,
        tv=user.token_version,
        ttl=timedelta(minutes=settings.access_ttl_min),
        mfa_at=mfa_at,
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


async def login(
    settings: Settings, *, email: str, password: str, ip: str
) -> TokenPair | MfaChallenge:
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

    # Anti-enumeración: si no existe, gastamos el mismo tiempo con el hash dummy (L1).
    if user is None:
        passwords.verify_password(password, passwords.DUMMY_HASH)
        await _safe_emit(
            AuditEvento.user_login_fallido,
            entidad="user",
            metadata={"email": email, "ip": ip},
        )
        raise AuthError(_INVALID)

    now = now_utc()
    # L6: si el bloqueo ya expiró, la condena se cumplió → ventana nueva (reset ANTES
    # de evaluar; si no, un fallo tras la expiración re-bloquea con 6≥5).
    if user.locked_until is not None and user.locked_until <= now:
        await repository.reset_failed_login(user.id)
        user.failed_attempts = 0
        user.locked_until = None

    bloqueado = user.locked_until is not None and user.locked_until > now
    # L1: verificar SIEMPRE (una vez), incluso si está bloqueado/inactivo → sin oráculo
    # de timing (el cortocircuito del `or` delataba la cuenta con un 401 inmediato).
    password_ok = passwords.verify_password(password, user.password_hash)

    if bloqueado or not user.activo or not password_ok:
        if user.activo and not bloqueado:
            await repository.register_failed_login(
                user.id,
                max_intentos=settings.login_max_intentos,
                lock_min=settings.login_lock_min,
            )
            refreshed = await repository.get_user_by_email(email)
            # H5: emitir bloqueado SOLO en la transición exacta (== max).
            if refreshed and refreshed.failed_attempts == settings.login_max_intentos:
                await _safe_emit(
                    AuditEvento.user_bloqueado,
                    entidad="user",
                    entidad_id=user.id,
                    metadata={"ip": ip},
                )
        await _safe_emit(
            AuditEvento.user_login_fallido,
            entidad="user",
            entidad_id=user.id,
            metadata={"ip": ip},
        )
        raise AuthError(_INVALID)

    # Contraseña correcta (1er factor).
    await repository.reset_failed_login(user.id)
    await repository.reset_ip_attempts(ip)  # H1: liberar el cupo IP en éxito

    # 2º factor: si el usuario tiene MFA, NO emitimos login ni creamos sesión aún;
    # devolvemos un challenge que se canjea en /auth/mfa/verify.
    if user.mfa_habilitado:
        return MfaChallenge(
            tokens.create_challenge_token(
                settings.jwt_secret, sub=user.id, tv=user.token_version
            )
        )

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


async def _flag_reuse(family_id: str, sub: str) -> None:
    """Revoca la familia y emite user.bloqueado SOLO si hubo transición (H5:
    evita el doble evento por carrera o por replays sucesivos)."""
    revocadas = await repository.revoke_family(family_id)
    if revocadas > 0:
        await _safe_emit(
            AuditEvento.user_bloqueado,
            entidad="user",
            entidad_id=sub,
            metadata={"motivo": "reuso_refresh"},
        )


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
        await _flag_reuse(family_id, sub)
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
        await _flag_reuse(family_id, sub)
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


# ── MFA: verificación (2º paso), enrolamiento y reset ───────────────────
async def mfa_verify(
    settings: Settings, *, challenge_token: str, code: str, ip: str
) -> TokenPair:
    """2º paso del login: canjea el challenge + un código TOTP (o de respaldo) por el
    par de tokens, con claim `mfa_at`. Throttle por cuenta+IP (fuerza bruta de 6
    dígitos)."""
    if not settings.jwt_secret or not settings.mfa_enc_key:
        raise AuthError("servicio de auth no configurado", status=500)
    try:
        claims = tokens.decode_token(
            settings.jwt_secret, challenge_token, expected_type="mfa_challenge"
        )
    except tokens.TokenError as e:
        raise AuthError(_INVALID) from e
    sub, tv, jti = claims["sub"], claims["tv"], claims["jti"]

    # M1 (Kimi): el challenge es de UN SOLO USO. Si ya se canjeó (está en la denylist)
    # → replay → 401. Sin esto acuñaría familias ilimitadas en sus 5 min de vida.
    if await repository.denylist_contains(jti):
        raise AuthError(_INVALID)

    count = await repository.register_mfa_attempt(
        sub, ip, window_min=settings.mfa_verify_window_min
    )
    if count > settings.mfa_verify_max:
        raise AuthError("Demasiados intentos. Intente más tarde.", status=429)

    user = await repository.get_user_by_id(sub)
    if (
        user is None
        or not user.activo
        or user.token_version != tv
        or not user.mfa_habilitado
        or not user.mfa_secret
    ):
        raise AuthError(_INVALID)

    try:
        secret_plano = mfa.decrypt_secret(user.mfa_secret, settings.mfa_enc_key)
    except Exception as e:  # noqa: BLE001 — clave de cifrado mala = error de config
        logger.error("no se pudo descifrar mfa_secret", exc_info=True)
        raise AuthError("servicio de auth no configurado", status=500) from e

    ok = mfa.verify_totp(secret_plano, code)
    if not ok:
        consumido, restantes = mfa.consume_backup_code(code, user.mfa_backup_codes)
        if consumido:
            ok = True
            await repository.replace_backup_codes(user.id, restantes)

    if not ok:
        await _safe_emit(
            AuditEvento.user_login_fallido,
            entidad="user",
            entidad_id=user.id,
            metadata={"ip": ip, "factor": "mfa"},
        )
        raise AuthError(_INVALID)

    # Éxito del 2º factor. Quemamos el challenge (M1): denylist hasta su exp natural.
    await repository.denylist_add(jti, _exp_dt(claims))
    await repository.reset_mfa_attempts(sub, ip)
    now = now_utc()
    family_id = uuid4().hex
    pair, session = _issue_pair(
        settings, user, family_id, now, mfa_at=int(now.timestamp())
    )
    await repository.create_refresh_session(session)
    await _safe_emit(
        AuditEvento.user_login,
        entidad="user",
        entidad_id=user.id,
        actor_id=user.id,
        metadata={"ip": ip, "mfa": True},
    )
    return pair


async def mfa_setup(settings: Settings, *, user: User, password: str) -> dict:
    """Enrolamiento: re-verifica la contraseña (paso protegido), genera el secreto,
    lo guarda CIFRADO (mfa_habilitado sigue False) y devuelve el secreto + URI para el
    QR UNA sola vez. No se activa hasta /mfa/activate con un código válido."""
    if not settings.mfa_enc_key:
        raise AuthError("MFA no configurado", status=500)
    if not passwords.verify_password(password, user.password_hash):
        raise AuthError(_INVALID)
    secret = mfa.new_totp_secret()
    await repository.set_mfa_secret(
        user.id, mfa.encrypt_secret(secret, settings.mfa_enc_key)
    )
    return {"secret": secret, "otpauth_uri": mfa.totp_uri(secret, user.email)}


async def mfa_activate(settings: Settings, *, user: User, code: str) -> list[str]:
    """Confirma el enrolamiento con un código TOTP válido → habilita MFA y devuelve
    los códigos de respaldo (en claro, UNA vez)."""
    if not settings.mfa_enc_key:
        raise AuthError("MFA no configurado", status=500)
    if not user.mfa_secret:
        raise AuthError("Primero /auth/mfa/setup.", status=400)
    secret = mfa.decrypt_secret(user.mfa_secret, settings.mfa_enc_key)
    if not mfa.verify_totp(secret, code):
        raise AuthError("Código inválido.", status=400)
    plain, hashed = mfa.generate_backup_codes(settings.mfa_backup_codes)
    await repository.enable_mfa(user.id, hashed)
    return plain


async def mfa_reset(settings: Settings, *, user_id: str) -> None:
    """Reset de MFA (self con step-up, o Admin sobre otro): borra secreto/códigos y
    hace BUMP de token_version → revoca todas las sesiones."""
    user = await repository.get_user_by_id(user_id)
    if user is None:
        raise AuthError("Usuario no encontrado.", status=404)
    await repository.clear_mfa(user_id, user.token_version + 1)


async def authenticate_with_claims(
    settings: Settings, *, access_token: str
) -> tuple[User, dict]:
    """Valida el access por request: firma, tipo, denylist, activo y token_version.
    Devuelve también los claims (para el step-up, que lee `mfa_at`)."""
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
    return user, claims


async def authenticate(settings: Settings, *, access_token: str) -> User:
    user, _ = await authenticate_with_claims(settings, access_token=access_token)
    return user


def _exp_dt(claims: dict) -> datetime:
    from datetime import UTC

    return datetime.fromtimestamp(claims["exp"], tz=UTC)
