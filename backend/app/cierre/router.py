# backend/app/cierre/router.py
"""Cierre de mes + conciliación (Sprint 4).

MARCADO PARA AUDITORÍA KIMI (regla 8 + §2.4).

- POST /meses/{mes}/cierre/conciliacion — cierre operativo (ciclo:cierre_operativo).
- POST /meses/{mes}/cierre/confirmar — confirmar cierre (solo Admin, Idempotency-Key).
- POST /meses/{mes}/reabrir — reapertura (Admin + step-up MFA).
"""

import hashlib
import json
import re

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError

from app.auth.deps import require_permission, require_step_up
from app.auth.models import User
from app.auth.router import verify_origin
from app.cierre import service
from app.domain.idempotency import IdempotencyKey

router = APIRouter(prefix="/meses", tags=["cierre"])

_MES = re.compile(r"^\d{4}-\d{2}$")
_ENDPOINT_CONFIRMAR = "POST /meses/{mes}/cierre/confirmar"


def _mes_key(mes: str) -> str:
    if not _MES.match(mes):
        raise HTTPException(422, "mes debe ser 'YYYY-MM'")
    return f"{mes}-01"


@router.post("/{mes}/cierre/conciliacion")
async def cierre_operativo(
    mes: str,
    user: User = Depends(require_permission("ciclo:cierre_operativo")),
    _: None = Depends(verify_origin),
):
    try:
        return await service.conciliacion(_mes_key(mes))
    except service.CierreError as e:
        raise HTTPException(e.status, e.detalle) from e


@router.post("/{mes}/cierre/confirmar")
async def confirmar_cierre(
    mes: str,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    user: User = Depends(require_permission("ciclo:confirmar_cierre")),
    _: None = Depends(verify_origin),
):
    req_hash = hashlib.sha256(
        json.dumps({"mes": mes}, sort_keys=True).encode()
    ).hexdigest()
    previa = await IdempotencyKey.find_one(
        IdempotencyKey.usuario_id == user.id,
        IdempotencyKey.endpoint == _ENDPOINT_CONFIRMAR,
        IdempotencyKey.key == idempotency_key,
    )
    if previa is not None:
        if previa.request_hash != req_hash:
            raise HTTPException(422, "Idempotency-Key ya usada con un payload distinto")
        if previa.response_status is None:
            raise HTTPException(409, "petición con esta Idempotency-Key en curso")
        return JSONResponse(previa.response_body, status_code=previa.response_status)

    marca = IdempotencyKey(
        usuario_id=user.id,
        endpoint=_ENDPOINT_CONFIRMAR,
        key=idempotency_key,
        request_hash=req_hash,
    )
    try:
        await marca.insert()
    except DuplicateKeyError:
        raise HTTPException(409, "petición con esta Idempotency-Key en curso") from None

    try:
        resultado = await service.confirmar_cierre(
            mes=_mes_key(mes), usuario_id=user.id
        )
    except service.CierreError as e:
        await marca.delete()
        raise HTTPException(e.status, e.detalle) from e
    except Exception:
        await marca.delete()
        raise

    marca.response_status = 200
    marca.response_body = resultado
    await marca.save()
    return resultado


@router.post("/{mes}/reabrir")
async def reabrir(
    mes: str,
    user: User = Depends(require_permission("ciclo:reabrir")),
    _step_up: User = Depends(require_step_up()),  # Admin + MFA reciente (§2.4)
    _: None = Depends(verify_origin),
):
    try:
        return await service.reabrir_mes(mes=_mes_key(mes), usuario_id=user.id)
    except service.CierreError as e:
        raise HTTPException(e.status, e.detalle) from e
