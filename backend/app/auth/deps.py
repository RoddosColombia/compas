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
