# backend/app/pagos/router.py
"""C9/S5-01 — Pagos de la semana (CR-S7). API de pagos planeados + veredicto.

MARCADO PARA AUDITORÍA KIMI (gate).

RBAC: mutaciones con `pagos:gestionar` = {financiero, admin} (CR-S7) + verify_origin;
lecturas (listar + veredicto) con `dashboard:leer`. `mes` en la ruta es YYYY-MM.
Regla 1: monto como STRING (strict rechaza el number del JSON). Sin Idempotency-Key
(no hay convergencia de dinero movido: el pago es una intención; marcar-pagado enlaza
una tx ya existente y es idempotente por el guard de estado)."""

import re
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.domain.pago_planeado import EstadoPago
from app.pagos import service

router = APIRouter(tags=["pagos"])

_MES = re.compile(r"^\d{4}-\d{2}$")


def _mes_key(mes: str) -> str:
    if not _MES.match(mes):
        raise HTTPException(422, "mes debe ser 'YYYY-MM'")
    return f"{mes}-01"


def _monto(s: str) -> Decimal:
    try:
        v = Decimal(s)
    except InvalidOperation:
        raise HTTPException(422, f"monto no es un decimal válido: {s}") from None
    if v <= 0:
        raise HTTPException(422, "monto debe ser > 0")
    return v


class CrearPagoBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    concepto: str = Field(min_length=1, max_length=300)
    acreedor: str = Field(min_length=1, max_length=200)
    monto: str  # string (regla 1)
    fecha_programada: str
    rubro_id: str


class EditarPagoBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    concepto: str | None = Field(default=None, min_length=1, max_length=300)
    acreedor: str | None = Field(default=None, min_length=1, max_length=200)
    monto: str | None = None
    fecha_programada: str | None = None
    rubro_id: str | None = None


class MarcarPagadoBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    transaccion_id: str


@router.post("/meses/{mes}/pagos-planeados", status_code=201)
async def crear_pago(
    mes: str,
    body: CrearPagoBody,
    user: User = Depends(require_permission("pagos:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        pago = await service.crear_pago(
            mes=_mes_key(mes),
            concepto=body.concepto,
            acreedor=body.acreedor,
            monto=_monto(body.monto),
            fecha_programada=body.fecha_programada,
            rubro_id=body.rubro_id,
            usuario_id=user.id,
        )
    except service.PagosError as e:
        raise HTTPException(e.status, e.detalle) from e
    except ValueError as e:  # validación del Document (fecha mal formada, etc.)
        raise HTTPException(422, str(e)) from e
    return service._serializar(pago)


@router.get("/meses/{mes}/pagos-planeados")
async def listar_pagos(
    mes: str,
    estado: str | None = Query(default=None),
    _: User = Depends(require_permission("dashboard:leer")),
):
    est: EstadoPago | None = None
    if estado is not None:
        try:
            est = EstadoPago(estado)
        except ValueError:
            raise HTTPException(422, f"estado inválido: {estado}") from None
    try:
        filas = await service.listar_pagos(mes=_mes_key(mes), estado=est)
    except service.PagosError as e:
        raise HTTPException(e.status, e.detalle) from e
    return [service._serializar(p) for p in filas]


@router.get("/meses/{mes}/pagos-semana")
async def pagos_semana(
    mes: str,
    _: User = Depends(require_permission("dashboard:leer")),
):
    try:
        return await service.pagos_semana(_mes_key(mes))
    except service.PagosError as e:
        raise HTTPException(e.status, e.detalle) from e


@router.patch("/pagos-planeados/{pago_id}")
async def editar_pago(
    pago_id: str,
    body: EditarPagoBody,
    user: User = Depends(require_permission("pagos:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        pago = await service.editar_pago(
            pago_id=pago_id,
            usuario_id=user.id,
            concepto=body.concepto,
            acreedor=body.acreedor,
            monto=_monto(body.monto) if body.monto is not None else None,
            fecha_programada=body.fecha_programada,
            rubro_id=body.rubro_id,
        )
    except service.PagosError as e:
        raise HTTPException(e.status, e.detalle) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return service._serializar(pago)


@router.post("/pagos-planeados/{pago_id}/cancelar")
async def cancelar_pago(
    pago_id: str,
    user: User = Depends(require_permission("pagos:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        pago = await service.cancelar_pago(pago_id=pago_id, usuario_id=user.id)
    except service.PagosError as e:
        raise HTTPException(e.status, e.detalle) from e
    return service._serializar(pago)


@router.post("/pagos-planeados/{pago_id}/marcar-pagado")
async def marcar_pagado(
    pago_id: str,
    body: MarcarPagadoBody,
    user: User = Depends(require_permission("pagos:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        pago = await service.marcar_pagado(
            pago_id=pago_id,
            transaccion_id=body.transaccion_id,
            usuario_id=user.id,
        )
    except service.PagosError as e:
        raise HTTPException(e.status, e.detalle) from e
    return service._serializar(pago)
