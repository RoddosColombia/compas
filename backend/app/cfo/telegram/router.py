# backend/app/cfo/telegram/router.py
"""FABS · rutas del canal Telegram (inc3 Pieza B). Doble barrera: (1) solo se monta
en main si CFO_ENABLED; (2) guard 404 defensivo en cada handler (cfo_enabled() relee
el entorno en cada llamada, sin cache — igual que app/cfo/router.py). El webhook
verifica el secret token de Telegram (X-Telegram-Bot-Api-Secret-Token).

RBAC de /vinculos: `require_permission('cfo:telegram_administrar')` — capacidad
restringida a Role.admin en app/auth/permissions.py — y NO `require_role(Role.admin)`.
`require_role` está documentado en app/auth/deps.py como "SOLO para administración de
identidad (/users); prohibido en negocio (H-1)"; administrar la allowlist del canal
Telegram es un endpoint de NEGOCIO (no /users), así que usar require_role aquí
violaría esa regla y la Regla 9 de CLAUDE.md (RBAC vía la matriz de permisos única).
Money/cifras no viajan por aquí (los cuerpos son telegram_id/user_id, no dinero)."""

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.auth.deps import require_permission
from app.auth.models import User
from app.cfo.config import cfo_enabled, telegram_webhook_secret
from app.cfo.telegram import repositorio, vinculos, webhook
from app.cfo.telegram.cliente import crear_cliente_telegram

router = APIRouter(prefix="/api/v1/cfo/telegram", tags=["cfo-telegram"])


class VinculoBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    telegram_id: int
    user_id: str


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if not cfo_enabled():  # guard defensivo (barrera 2)
        raise HTTPException(404, "No encontrado.")
    secret = telegram_webhook_secret()
    # compare_digest: comparación en tiempo constante (evita side-channel de
    # timing en un endpoint público)
    if (
        not secret
        or not x_telegram_bot_api_secret_token
        or not secrets.compare_digest(x_telegram_bot_api_secret_token, secret)
    ):
        raise HTTPException(403, "Prohibido.")
    cli = crear_cliente_telegram()
    if cli is None:
        raise HTTPException(503, "Canal no configurado.")
    update = await request.json()
    await webhook.procesar_update(update, cliente_telegram=cli)
    return {"ok": True}


@router.post("/vinculos")
async def crear(
    body: VinculoBody,
    admin: User = Depends(require_permission("cfo:telegram_administrar")),
):
    if not cfo_enabled():
        raise HTTPException(404, "No encontrado.")
    try:
        await vinculos.vincular(body.telegram_id, body.user_id, admin_id=str(admin.id))
    except repositorio.VinculoDuplicado as e:  # uno-a-uno (B-3); narrow catch
        # a propósito: un fallo real (p. ej. de auditoría) debe propagar (500),
        # nunca disfrazarse de 409 — ver Fix 1, auditoría Kimi de este gate.
        raise HTTPException(409, "telegram_id o user_id ya vinculado.") from e
    return {"ok": True}


@router.get("/vinculos")
async def listar(
    admin: User = Depends(require_permission("cfo:telegram_administrar")),
):
    if not cfo_enabled():
        raise HTTPException(404, "No encontrado.")
    vs = await repositorio.listar_vinculos()
    return [{"telegram_id": v.telegram_id, "user_id": v.user_id} for v in vs]


@router.delete("/vinculos/{telegram_id}")
async def borrar(
    telegram_id: int,
    admin: User = Depends(require_permission("cfo:telegram_administrar")),
):
    if not cfo_enabled():
        raise HTTPException(404, "No encontrado.")
    ok = await vinculos.desvincular(telegram_id, admin_id=str(admin.id))
    if not ok:
        raise HTTPException(404, "Vínculo no encontrado.")
    return {"ok": True}
