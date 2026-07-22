# backend/app/control/router.py
"""Vista Control (Sprint 4): GET /meses/{mes}/control (read-only, dashboard:leer)."""

import re

from fastapi import APIRouter, Depends, HTTPException

from app.auth.deps import require_permission
from app.auth.models import User
from app.control import service

router = APIRouter(prefix="/meses", tags=["control"])

_MES = re.compile(r"^\d{4}-\d{2}$")


def _mes_key(mes: str) -> str:
    if not _MES.match(mes):
        raise HTTPException(422, "mes debe ser 'YYYY-MM'")
    return f"{mes}-01"


@router.get("/{mes}/control")
async def vista_control(
    mes: str,
    user: User = Depends(require_permission("dashboard:leer")),
):
    try:
        return await service.control(_mes_key(mes))
    except service.ControlError as e:
        raise HTTPException(e.status, e.detalle) from e
