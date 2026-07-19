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
