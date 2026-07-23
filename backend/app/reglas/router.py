# backend/app/reglas/router.py
"""/api/v1/reglas-clasificacion — C3 auto-clasificación (CR-S5, Spec §319).

MARCADO PARA AUDITORÍA KIMI (gate I-PR1).

RBAC: GET con `dashboard:leer`; mutaciones con `reglas:gestionar` = {financiero,
admin} (CR-S5) + `verify_origin`. Sin Idempotency-Key (mismo criterio de C1: no es
movimiento de dinero; el índice único de patrón activo hace inocuo el replay).
`aplicar-pendientes` es idempotente por construcción (lo clasificado no se toca)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.domain.regla_clasificacion import ReglaClasificacion
from app.domain.rubro import TipoFlujo
from app.reglas import service

router = APIRouter(prefix="/reglas-clasificacion", tags=["reglas"])


class ReglaCrearBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    patron: str = Field(min_length=3, max_length=120)
    rubro_id: str
    tipo_flujo: TipoFlujo
    prioridad: int = 100

    @field_validator("tipo_flujo", mode="before")
    @classmethod
    def _cast_tipo(cls, v: object) -> object:
        return v if isinstance(v, TipoFlujo) else TipoFlujo(v)


class ReglaEditarBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    patron: str | None = Field(default=None, min_length=3, max_length=120)
    prioridad: int | None = None
    rubro_id: str | None = None
    activa: bool | None = None  # solo true (reactivar); false → 422


def _serializar(r: ReglaClasificacion) -> dict:
    return {
        "id": str(r.id),
        "patron": r.patron,
        "patron_normalizado": r.patron_normalizado,
        "rubro_id": str(r.rubro_id),
        "tipo_flujo": r.tipo_flujo.value,
        "prioridad": r.prioridad,
        "origen": r.origen.value,
        "activa": r.activa,
        "creada_por": r.creada_por,
    }


def _parse_tipo(tipo: str | None) -> TipoFlujo | None:
    if tipo is None:
        return None
    try:
        return TipoFlujo(tipo)
    except ValueError:
        raise HTTPException(422, f"tipo_flujo inválido: '{tipo}'") from None


@router.get("")
async def listar(
    activa: bool | None = Query(default=None),
    tipo_flujo: str | None = Query(default=None),
    _: User = Depends(require_permission("dashboard:leer")),
):
    reglas = await service.listar_reglas(
        activa=activa, tipo_flujo=_parse_tipo(tipo_flujo)
    )
    return [_serializar(r) for r in reglas]


@router.post("", status_code=201)
async def crear(
    body: ReglaCrearBody,
    user: User = Depends(require_permission("reglas:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        regla = await service.crear_regla(
            patron=body.patron,
            rubro_id=body.rubro_id,
            tipo_flujo=body.tipo_flujo,
            prioridad=body.prioridad,
            usuario_id=user.id,
        )
    except service.ReglasError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(regla)


@router.patch("/{regla_id}")
async def editar(
    regla_id: str,
    body: ReglaEditarBody,
    user: User = Depends(require_permission("reglas:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        regla = await service.editar_regla(
            regla_id=regla_id,
            usuario_id=user.id,
            patron=body.patron,
            prioridad=body.prioridad,
            rubro_id=body.rubro_id,
            activa=body.activa,
        )
    except service.ReglasError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(regla)


@router.post("/{regla_id}/desactivar")
async def desactivar(
    regla_id: str,
    user: User = Depends(require_permission("reglas:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        regla = await service.desactivar_regla(regla_id=regla_id, usuario_id=user.id)
    except service.ReglasError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(regla)


@router.post("/{regla_id}/aprobar")
async def aprobar(
    regla_id: str,
    user: User = Depends(require_permission("reglas:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        regla = await service.aprobar_regla(regla_id=regla_id, usuario_id=user.id)
    except service.ReglasError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(regla)


@router.post("/aplicar-pendientes")
async def aplicar_pendientes(
    user: User = Depends(require_permission("reglas:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        return await service.aplicar_pendientes(usuario_id=user.id)
    except service.ReglasError as e:
        raise HTTPException(e.status, e.detalle) from e
