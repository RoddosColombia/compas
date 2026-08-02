# backend/app/modelos_moto/router.py
"""/api/v1/modelos-moto — catálogo administrable de modelos de moto (CR-COCK).

RBAC: GET con `dashboard:leer`; mutaciones con `proyeccion:gestionar` = {financiero,
admin} + `verify_origin` (anti-CSRF). Montos como string (regla 1): el body los parsea
a Decimal antes de construir el modelo. Sin Idempotency-Key: no es movimiento de
dinero; el índice único (nombre) hace inocuo el replay (→ 409)."""

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.domain.modelo_moto import ModeloMoto
from app.modelos_moto import service

router = APIRouter(prefix="/modelos-moto", tags=["modelos-moto"])


def _dec(valor: str, campo: str) -> Decimal:
    try:
        v = Decimal(valor)
        if not v.is_finite():
            raise InvalidOperation
        return v
    except (InvalidOperation, ValueError):
        raise HTTPException(422, f"{campo} debe ser un decimal en string") from None


class ModeloCrearBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    nombre: str = Field(min_length=1, max_length=60)
    costo_auteco: str
    precio_venta_con_iva: str
    cuota_inicial: str
    cuota_semanal: str
    plazo_semanas: int = Field(gt=0)
    matricula: str
    participacion_mix: str


class ModeloEditarBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=60)
    orden: int | None = None
    plazo_semanas: int | None = Field(default=None, gt=0)
    activo: bool | None = None  # solo true (reactivar, B-3); false → 422
    costo_auteco: str | None = None
    precio_venta_con_iva: str | None = None
    cuota_inicial: str | None = None
    cuota_semanal: str | None = None
    matricula: str | None = None
    participacion_mix: str | None = None


def _serializar(m: ModeloMoto) -> dict:
    return {
        "id": str(m.id),
        "nombre": m.nombre,
        "costo_auteco": str(m.costo_auteco),
        "precio_venta_con_iva": str(m.precio_venta_con_iva),
        "cuota_inicial": str(m.cuota_inicial),
        "cuota_semanal": str(m.cuota_semanal),
        "plazo_semanas": m.plazo_semanas,
        "matricula": str(m.matricula),
        "participacion_mix": str(m.participacion_mix),
        "orden": m.orden,
        "activo": m.activo,
        "es_sistema": m.es_sistema,
    }


@router.get("")
async def listar(
    activo: bool | None = Query(default=None),
    _: User = Depends(require_permission("dashboard:leer")),
):
    modelos = await service.listar_modelos(activo=activo)
    return [_serializar(m) for m in modelos]


@router.post("", status_code=201)
async def crear(
    body: ModeloCrearBody,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        modelo = await service.crear_modelo(
            nombre=body.nombre,
            costo_auteco=_dec(body.costo_auteco, "costo_auteco"),
            precio_venta_con_iva=_dec(
                body.precio_venta_con_iva, "precio_venta_con_iva"
            ),
            cuota_inicial=_dec(body.cuota_inicial, "cuota_inicial"),
            cuota_semanal=_dec(body.cuota_semanal, "cuota_semanal"),
            plazo_semanas=body.plazo_semanas,
            matricula=_dec(body.matricula, "matricula"),
            participacion_mix=_dec(body.participacion_mix, "participacion_mix"),
            usuario_id=user.id,
        )
    except service.ModelosMotoError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(modelo)


@router.patch("/{modelo_id}")
async def editar(
    modelo_id: str,
    body: ModeloEditarBody,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    campos_money = {
        c: _dec(getattr(body, c), c)
        for c in service._EDITABLES_MONEY
        if getattr(body, c) is not None
    }
    try:
        modelo = await service.editar_modelo(
            modelo_id=modelo_id,
            usuario_id=user.id,
            nombre=body.nombre,
            orden=body.orden,
            plazo_semanas=body.plazo_semanas,
            activo=body.activo,
            campos_money=campos_money or None,
        )
    except service.ModelosMotoError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(modelo)


@router.post("/{modelo_id}/desactivar")
async def desactivar(
    modelo_id: str,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        modelo = await service.desactivar_modelo(
            modelo_id=modelo_id, usuario_id=user.id
        )
    except service.ModelosMotoError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(modelo)
