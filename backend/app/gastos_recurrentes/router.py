# backend/app/gastos_recurrentes/router.py
"""/api/v1/gastos-recurrentes — plantilla de gastos recurrentes (CEO 2026-07-26).

RBAC: GET con `dashboard:leer`; mutaciones con `rubros:gestionar` (= {financiero,
admin}) + `verify_origin` (anti-CSRF), igual que rubros — es configuración
presupuestal, no movimiento de dinero. Sin Idempotency-Key ni auditoría (módulo
informativo; catálogo de eventos cerrado, regla 11). Montos como STRING (regla 1).
"""

import re
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.core.money import money_str
from app.domain.gasto_recurrente import Frecuencia, GastoRecurrente
from app.domain.rubro import Rubro
from app.gastos_recurrentes import service

router = APIRouter(prefix="/gastos-recurrentes", tags=["gastos-recurrentes"])


def _parse_monto(s: str) -> Decimal:
    try:
        v = Decimal(s)
        if not v.is_finite():
            raise InvalidOperation
    except InvalidOperation:
        raise HTTPException(422, "monto no es un decimal válido") from None
    if v < 0:
        raise HTTPException(422, "monto no puede ser negativo")
    return v


_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _valida_hasta(v: str | None) -> str | None:
    if v is not None and not _MES.match(v):
        raise ValueError("hasta debe ser 'YYYY-MM'")
    return v


class GastoCrearBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    rubro_id: str
    descripcion: str = Field(min_length=1, max_length=120)
    monto: str  # COP como string (regla 1)
    frecuencia: Frecuencia = Frecuencia.MENSUAL
    dia_pago: int | None = Field(default=None, ge=1, le=31)
    hasta: str | None = None  # mes final YYYY-MM (gasto temporal)
    notas: str | None = Field(default=None, max_length=500)

    @field_validator("frecuencia", mode="before")
    @classmethod
    def _cast_frecuencia(cls, v: object) -> object:
        return v if isinstance(v, Frecuencia) else Frecuencia(v)

    @field_validator("hasta")
    @classmethod
    def _hasta(cls, v: str | None) -> str | None:
        return _valida_hasta(v)


class GastoEditarBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    rubro_id: str | None = None
    descripcion: str | None = Field(default=None, min_length=1, max_length=120)
    monto: str | None = None
    frecuencia: Frecuencia | None = None
    dia_pago: int | None = Field(default=None, ge=1, le=31)
    hasta: str | None = None
    notas: str | None = Field(default=None, max_length=500)
    activo: bool | None = None

    @field_validator("frecuencia", mode="before")
    @classmethod
    def _cast_frecuencia(cls, v: object) -> object:
        return v if v is None or isinstance(v, Frecuencia) else Frecuencia(v)

    @field_validator("hasta")
    @classmethod
    def _hasta(cls, v: str | None) -> str | None:
        return _valida_hasta(v)


def _serializar(g: GastoRecurrente, rubros: dict) -> dict:
    r = rubros.get(g.rubro_id)
    return {
        "id": str(g.id),
        "rubro_id": str(g.rubro_id),
        "rubro_nombre": r.nombre if r is not None else None,
        "rubro_grupo": r.grupo.value if r is not None else None,
        "rubro_codigo": r.codigo if r is not None else None,
        "descripcion": g.descripcion,
        "monto": money_str(g.monto),
        "frecuencia": g.frecuencia.value,
        "monto_mensual": money_str(g.monto_mensual),
        "dia_pago": g.dia_pago,
        "hasta": g.hasta,
        "notas": g.notas,
        "activo": g.activo,
        "orden": g.orden,
    }


async def _rubros_de(gastos: list[GastoRecurrente]) -> dict:
    ids = list({g.rubro_id for g in gastos})
    if not ids:
        return {}
    return {r.id: r for r in await Rubro.find({"_id": {"$in": ids}}).to_list()}


@router.get("")
async def listar(
    activo: bool | None = Query(default=None),
    _: User = Depends(require_permission("dashboard:leer")),
):
    gastos = await service.listar_gastos(activo=activo)
    rubros = await _rubros_de(gastos)
    resumen = await service.resumen_mensual(gastos)
    return {
        "items": [_serializar(g, rubros) for g in gastos],
        "resumen": {
            "total": money_str(resumen["total"]),
            "por_grupo": {k: money_str(v) for k, v in resumen["por_grupo"].items()},
        },
    }


@router.post("", status_code=201)
async def crear(
    body: GastoCrearBody,
    user: User = Depends(require_permission("rubros:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        g = await service.crear_gasto(
            rubro_id=body.rubro_id,
            descripcion=body.descripcion,
            monto=_parse_monto(body.monto),
            frecuencia=body.frecuencia,
            dia_pago=body.dia_pago,
            notas=body.notas,
            hasta=body.hasta,
            usuario_id=user.id,
        )
    except service.GastosError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(g, await _rubros_de([g]))


@router.patch("/{gasto_id}")
async def editar(
    gasto_id: str,
    body: GastoEditarBody,
    user: User = Depends(require_permission("rubros:gestionar")),
    _: None = Depends(verify_origin),
):
    campos = body.model_fields_set
    try:
        g = await service.editar_gasto(
            gasto_id=gasto_id,
            rubro_id=body.rubro_id,
            descripcion=body.descripcion,
            monto=_parse_monto(body.monto) if body.monto is not None else None,
            frecuencia=body.frecuencia,
            dia_pago=body.dia_pago,
            dia_pago_set="dia_pago" in campos,
            hasta=body.hasta,
            hasta_set="hasta" in campos,
            notas=body.notas,
            notas_set="notas" in campos,
            activo=body.activo,
        )
    except service.GastosError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(g, await _rubros_de([g]))


@router.delete("/{gasto_id}", status_code=204)
async def eliminar(
    gasto_id: str,
    _u: User = Depends(require_permission("rubros:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        await service.eliminar_gasto(gasto_id=gasto_id)
    except service.GastosError as e:
        raise HTTPException(e.status, e.detalle) from e
