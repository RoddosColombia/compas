# backend/app/transacciones/router.py
"""POST /api/v1/transacciones — transacción manual con Idempotency-Key (§1.12)
+ PATCH /transacciones/{id}/clasificar — reclasificación manual (C3, CR-S5).

MARCADO PARA AUDITORÍA KIMI (flujo crítico).

Regla 1: `valor` viaja como STRING (strict=True rechaza numbers JSON). El replay
idempotente devuelve la respuesta original; misma key + payload distinto → 422.
La reclasificación NO lleva Idempotency-Key: es idempotente por naturaleza
(re-aplicar el mismo rubro no cambia nada) y no crea dinero."""

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo.errors import DuplicateKeyError

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.core.money import money_str
from app.domain.idempotency import IdempotencyKey, intentar_adquirir_huerfana
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
        if not v.is_finite():
            raise InvalidOperation
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
        # FIX-G2: vínculo del contra-asiento (None en una tx normal). La Vista Control
        # muestra el original y su reverso enlazados por este campo.
        "revierte_id": str(tx.revierte_id) if tx.revierte_id is not None else None,
        # PTS6-B: división de clasificación (None si la tx no está dividida).
        "dividida": tx.partes is not None,
        "partes": (
            [
                {"rubro_id": str(p.rubro_id), "valor": money_str(p.valor)}
                for p in tx.partes
            ]
            if tx.partes is not None
            else None
        ),
    }


_MES_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("")
async def listar(
    mes: str = Query(..., description="YYYY-MM"),
    banco: str | None = Query(default=None),
    _: User = Depends(require_permission("dashboard:leer")),
):
    """Lista las transacciones del mes (panel de manuales de /cargas, FIX-G2). Cada
    ítem trae `anulada` (ya tiene contra-asiento) y `es_reverso` (es un contra-asiento),
    para que la UI muestre original+reverso enlazados y deshabilite el botón donde toca.
    """
    if not _MES_RE.match(mes):
        raise HTTPException(422, "mes debe ser 'YYYY-MM'")
    txs, anuladas = await service.listar_transacciones(mes=mes, banco=banco)
    items = [
        {
            **_serializar(tx),
            "anulada": str(tx.id) in anuladas,
            "es_reverso": tx.revierte_id is not None,
        }
        for tx in txs
    ]
    return {"items": items}


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
    es_huerfana = False
    if previa is not None:
        if previa.request_hash != req_hash:
            raise HTTPException(422, "Idempotency-Key ya usada con un payload distinto")
        estado = previa.response_status
        if estado is not None and estado > 0:
            # Replay: la respuesta ORIGINAL, con su status original (§1.12).
            return JSONResponse(previa.response_body, status_code=estado)
        # A-4.2 (P1-10): en curso (None) o re-ejecutándose (-1). Si la marca es
        # huérfana (>5 min) se adquiere y se re-ejecuta convergente; si no, 409.
        if estado is None and await intentar_adquirir_huerfana(previa):
            marca = previa
            es_huerfana = True
        else:
            raise HTTPException(409, "petición con esta Idempotency-Key en curso")
    else:
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
            raise HTTPException(
                409, "petición con esta Idempotency-Key en curso"
            ) from None

    try:
        tx, replay = await service.crear_transaccion_manual(
            fecha=body.fecha,
            descripcion=body.descripcion,
            valor=valor,
            tipo_flujo=body.tipo_flujo,
            usuario_id=user.id,
            rubro_id=body.rubro_id,
            idempotency_key=idempotency_key,
            endpoint=_ENDPOINT,
        )
    except service.TransaccionManualError as e:
        # A-4.2: en re-ejecución de huérfana el error de negocio ES la respuesta
        # convergente (se persiste); en flujo normal, no quemar la key (se borra).
        if es_huerfana:
            marca.response_status = e.status
            marca.response_body = {"detail": e.detalle}
            await marca.save()
        else:
            await marca.delete()
        raise HTTPException(e.status, e.detalle) from e
    except Exception:
        # A-4.2 (cierre del residual): muerte durante la RE-EJECUCIÓN de una huérfana
        # (excepción NO de negocio) → devolver la marca a 'en curso' (None), no
        # dejarla clavada en el centinela -1 (la bloquearía las 24h del TTL). Su
        # created_at ya es viejo → el próximo retry la readquiere y converge. En flujo
        # normal (no huérfana) se borra como antes.
        if es_huerfana:
            marca.response_status = None
            await marca.save()
        else:
            await marca.delete()
        raise

    # A-4 (P1-9): replay convergente tras TTL → 200 + replay:true (la unicidad la
    # respaldó el índice, no la marca); creación normal → 201.
    respuesta = _serializar(tx)
    status = 200 if replay else 201
    if replay:
        respuesta = {**respuesta, "replay": True}
    marca.response_status = status
    marca.response_body = respuesta
    await marca.save()
    return JSONResponse(respuesta, status_code=status)


class ClasificarBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    rubro_id: str
    proponer_regla: bool = False  # §1.9/D5: crea propuesta APRENDIDA inactiva
    patron: str | None = Field(default=None, min_length=3, max_length=120)


class AnularBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    motivo: str = Field(min_length=1, max_length=500)

    @field_validator("motivo")
    @classmethod
    def _motivo_no_vacio(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("el motivo es obligatorio")
        return s


@router.post("/{transaccion_id}/anular")
async def anular(
    transaccion_id: str,
    body: AnularBody,
    user: User = Depends(require_permission("cargas:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        contra = await service.anular_transaccion_manual(
            tx_id=transaccion_id,
            motivo=body.motivo,
            usuario_id=user.id,
        )
    except service.TransaccionManualError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(contra)


@router.patch("/{transaccion_id}/clasificar")
async def clasificar(
    transaccion_id: str,
    body: ClasificarBody,
    user: User = Depends(require_permission("cargas:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        tx = await service.reclasificar_transaccion(
            tx_id=transaccion_id,
            rubro_id=body.rubro_id,
            usuario_id=user.id,
            proponer_regla=body.proponer_regla,
            patron=body.patron,
        )
    except service.TransaccionManualError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(tx)


class ParteBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    rubro_id: str
    valor: str  # monto COP como string (regla 1)


class DividirBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    partes: list[ParteBody] = Field(min_length=2, max_length=10)


@router.post("/{transaccion_id}/dividir")
async def dividir(
    transaccion_id: str,
    body: DividirBody,
    user: User = Depends(require_permission("cargas:gestionar")),
    _: None = Depends(verify_origin),
):
    """PTS6-B: reparte la clasificación de una transacción entre ≥2 rubros cuyas
    partes suman EXACTO su valor. Sin Idempotency-Key (mismo criterio que
    clasificar): no crea dinero, y re-aplicar sobre una tx ya dividida da 409."""
    partes = [
        {"rubro_id": p.rubro_id, "valor": _parse_valor(p.valor)} for p in body.partes
    ]
    try:
        tx = await service.dividir_transaccion(
            tx_id=transaccion_id, partes=partes, usuario_id=user.id
        )
    except service.TransaccionManualError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(tx)


@router.post("/{transaccion_id}/deshacer-division")
async def deshacer_division(
    transaccion_id: str,
    user: User = Depends(require_permission("cargas:gestionar")),
    _: None = Depends(verify_origin),
):
    """PTS6-B: revierte una división (rubro vuelve al pre-división)."""
    try:
        tx = await service.deshacer_division(
            tx_id=transaccion_id, usuario_id=user.id
        )
    except service.TransaccionManualError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(tx)
