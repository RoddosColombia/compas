# backend/app/auth/router.py
"""Endpoints de auth bajo /api/v1/auth (Spec §4).

Cookie de refresh: HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth (Kimi A-01/E-2).
Verificación de Origin en las mutaciones fuera de dev (Kimi M-03/Spec §4)."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from app.auth import service
from app.auth.deps import get_current_user, require_step_up
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


class MfaSetupBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    password: str  # re-autenticación para proteger el enrolamiento


class MfaActivateBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    code: str


class MfaVerifyBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    mfa_token: str
    code: str


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
        result = await service.login(
            settings, email=body.email, password=body.password, ip=ip
        )
    except service.AuthError as e:
        raise HTTPException(e.status, e.detail) from e
    # Usuario con MFA: 1er paso OK → challenge (sin cookie ni access).
    if isinstance(result, service.MfaChallenge):
        return {"mfa_required": True, "mfa_token": result.challenge_token}
    _set_refresh_cookie(response, settings, result.refresh_token)
    return {"access_token": result.access_token, "token_type": "bearer"}


@router.post("/mfa/verify")
async def mfa_verify(
    body: MfaVerifyBody,
    request: Request,
    response: Response,
    settings: Settings = Depends(_settings),
    _: None = Depends(verify_origin),
):
    """2º paso del login: canjea challenge + código (TOTP o respaldo) por los tokens."""
    ip = client_ip(request)
    try:
        pair = await service.mfa_verify(
            settings, challenge_token=body.mfa_token, code=body.code, ip=ip
        )
    except service.AuthError as e:
        raise HTTPException(e.status, e.detail) from e
    _set_refresh_cookie(response, settings, pair.refresh_token)
    return {"access_token": pair.access_token, "token_type": "bearer"}


@router.post("/mfa/setup")
async def mfa_setup(
    body: MfaSetupBody,
    settings: Settings = Depends(_settings),
    user: User = Depends(get_current_user),
    _: None = Depends(verify_origin),
):
    """Inicia el enrolamiento: devuelve secreto + URI otpauth (para el QR) UNA vez."""
    try:
        return await service.mfa_setup(settings, user=user, password=body.password)
    except service.AuthError as e:
        raise HTTPException(e.status, e.detail) from e


@router.post("/mfa/activate")
async def mfa_activate(
    body: MfaActivateBody,
    settings: Settings = Depends(_settings),
    user: User = Depends(get_current_user),
    _: None = Depends(verify_origin),
):
    """Confirma el enrolamiento con un código válido → habilita MFA y entrega los
    códigos de respaldo (en claro, UNA vez)."""
    try:
        codes = await service.mfa_activate(settings, user=user, code=body.code)
    except service.AuthError as e:
        raise HTTPException(e.status, e.detail) from e
    return {"backup_codes": codes}


@router.post("/mfa/reset")
async def mfa_reset(
    settings: Settings = Depends(_settings),
    user: User = Depends(require_step_up()),
    _: None = Depends(verify_origin),
):
    """Reset del PROPIO MFA (exige step-up: MFA reciente). Borra secreto/códigos y
    revoca sesiones (bump token_version). El reset de OTRO usuario lo hará el Admin
    desde el módulo /users."""
    await service.mfa_reset(settings, user_id=user.id)
    return {"status": "ok"}


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
