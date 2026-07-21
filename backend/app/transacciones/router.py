# backend/app/transacciones/router.py
"""POST /api/v1/transacciones — transacción manual con Idempotency-Key (§1.12).

MARCADO PARA AUDITORÍA KIMI (flujo crítico).

Regla 1: `valor` viaja como STRING (strict=True rechaza numbers JSON). El replay
idempotente devuelve la respuesta original; misma key + payload distinto → 422."""

import hashlib
import json
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo.errors import DuplicateKeyError

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.core.money import money_str
from app.domain.idempotency import IdempotencyKey
from app.domain.rubro import TipoFlujo
from app.domain.transaccion import Transaccion
from app.transacciones import service

router = APIRouter(prefix="/transacciones", tags=["transacciones"])

_ENDPOINT = "POST /transacciones"


class TransaccionManualBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    fecha: str  # YYYY-MM-DD (valida el Document)
    descripcion: str = Field(min_length=1, max_length=300)
    valor: str  # monto COP como string (regla 1)
    tipo_flujo: TipoFlujo
    rubro_id: str | None = None

    @field_validator("tipo_flujo", mode="before")
    @classmethod
    def _cast_tipo(cls, v: object) -> object:
        # strict=True no coerciona str→StrEnum; el cast explícito es el patrón
        # del dominio. Un valor inválido lanza ValueError → 422.
        return v if isinstance(v, TipoFlujo) else TipoFlujo(v)


def _parse_valor(s: str) -> Decimal:
    try:
        v = Decimal(s)
    except InvalidOperation:
        raise HTTPException(422, "valor no es un decimal válido") from None
    if v <= 0:
        raise HTTPException(422, "valor debe ser > 0")
    return v


def _serializar(tx: Transaccion) -> dict:
    return {
        "id": str(tx.id),
        "fecha": tx.fecha,
        "descripcion": tx.descripcion,
        "valor": money_str(tx.valor),
        "tipo_flujo": tx.tipo_flujo.value,
        "rubro_id": str(tx.rubro_id),
        "mes_id": str(tx.mes_id),
        "banco": tx.banco.value,
        "id_banco": tx.id_banco,
        "tardia": tx.tardia,
    }


@router.post("", status_code=201)
async def crear_manual(
    body: TransaccionManualBody,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    user: User = Depends(require_permission("cargas:gestionar")),
    _: None = Depends(verify_origin),
):
    valor = _parse_valor(body.valor)
    req_hash = hashlib.sha256(
        json.dumps(body.model_dump(), sort_keys=True).encode()
    ).hexdigest()

    # §1.12: scope (usuario, endpoint, key). El índice único respalda la carrera;
    # mongomock no lo exige, pero el find_one previo cubre el flujo normal.
    previa = await IdempotencyKey.find_one(
        IdempotencyKey.usuario_id == user.id,
        IdempotencyKey.endpoint == _ENDPOINT,
        IdempotencyKey.key == idempotency_key,
    )
    if previa is not None:
        if previa.request_hash != req_hash:
            raise HTTPException(422, "Idempotency-Key ya usada con un payload distinto")
        if previa.response_status is None:
            raise HTTPException(409, "petición con esta Idempotency-Key en curso")
        # Replay: la respuesta ORIGINAL, con su status original (§1.12).
        return JSONResponse(previa.response_body, status_code=previa.response_status)

    marca = IdempotencyKey(
        usuario_id=user.id,
        endpoint=_ENDPOINT,
        key=idempotency_key,
        request_hash=req_hash,
    )
    try:
        await marca.insert()
    except DuplicateKeyError:
        # Kimi B-1: doble-clic real (2 requests concurrentes) — el índice único
        # `scope_unico` atrapa al 2º → 409, no 500.
        raise HTTPException(409, "petición con esta Idempotency-Key en curso") from None

    try:
        tx = await service.crear_transaccion_manual(
            fecha=body.fecha,
            descripcion=body.descripcion,
            valor=valor,
            tipo_flujo=body.tipo_flujo,
            usuario_id=user.id,
            rubro_id=body.rubro_id,
        )
    except service.TransaccionManualError as e:
        await marca.delete()  # una petición fallida no quema la key
        raise HTTPException(e.status, e.detalle) from e
    except Exception:
        await marca.delete()
        raise

    respuesta = _serializar(tx)
    marca.response_status = 201
    marca.response_body = respuesta
    await marca.save()
    return respuesta
