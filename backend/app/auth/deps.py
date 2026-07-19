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
from app.core.time import now_utc


def _settings() -> Settings:
    return get_settings()


def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "No autenticado.")
    return auth[7:]


async def get_current_user(
    request: Request, settings: Settings = Depends(_settings)
) -> User:
    try:
        return await service.authenticate(settings, access_token=_bearer(request))
    except service.AuthError as e:
        raise HTTPException(e.status, e.detail) from e


def require_step_up() -> Callable[..., Awaitable[User]]:
    """Exige MFA RECIENTE (claim `mfa_at` dentro de la ventana) — para acciones
    sensibles: ciclo:reabrir, ciclo:config, editar saldo inicial (Spec §2.4). No basta
    estar autenticado: hay que haber pasado el 2º factor hace poco."""

    async def dep(
        request: Request, settings: Settings = Depends(_settings)
    ) -> User:
        try:
            user, claims = await service.authenticate_with_claims(
                settings, access_token=_bearer(request)
            )
        except service.AuthError as e:
            raise HTTPException(e.status, e.detail) from e
        mfa_at = claims.get("mfa_at")
        ventana = settings.mfa_stepup_window_min * 60
        if mfa_at is None or (now_utc().timestamp() - mfa_at) > ventana:
            raise HTTPException(403, "Step-up MFA requerido.")
        return user

    return dep


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
