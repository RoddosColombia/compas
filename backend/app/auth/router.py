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
