# backend/app/rubros/router.py
"""/api/v1/rubros — C1 categorías administrables (CR-S4, GO Kimi PLAN-I 9.2).

MARCADO PARA AUDITORÍA KIMI (gate I-PR1).

RBAC: GET con `dashboard:leer` (los 4 roles); mutaciones con `rubros:gestionar`
(= {financiero, admin}, CR-S4) + `verify_origin` (anti-CSRF). Sin Idempotency-Key:
no es movimiento de dinero (§1.12 aplica a POST de dinero); el índice único
(grupo,nombre) hace inocuo el replay del POST de creación (→ 409)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo, TipoRubro
from app.rubros import service

router = APIRouter(prefix="/rubros", tags=["rubros"])


class RubroCrearBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    grupo: RubroGrupo
    nombre: str = Field(min_length=1, max_length=80)
    tipo_flujo: TipoFlujo = TipoFlujo.EGRESO
    # RF-F9 · Fundacional §2 — «Plan de cuentas completo». `codigo` (contable) y
    # `tipo` (clase Fijo/Variable) son obligatorios al CREAR. Rubros existentes
    # sin código no se tocan (regla es «al CREAR», no reescritura del histórico).
    codigo: str = Field(min_length=1, max_length=8)
    tipo: TipoRubro

    @field_validator("grupo", mode="before")
    @classmethod
    def _cast_grupo(cls, v: object) -> object:
        # strict=True no coerciona str→StrEnum; valor inválido → ValueError → 422.
        return v if isinstance(v, RubroGrupo) else RubroGrupo(v)

    @field_validator("tipo_flujo", mode="before")
    @classmethod
    def _cast_tipo(cls, v: object) -> object:
        return v if isinstance(v, TipoFlujo) else TipoFlujo(v)

    @field_validator("tipo", mode="before")
    @classmethod
    def _cast_tipo_rubro(cls, v: object) -> object:
        return v if isinstance(v, TipoRubro) else TipoRubro(v)


class RubroEditarBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=80)
    orden: int | None = None
    tipo_flujo: TipoFlujo | None = None
    activo: bool | None = None  # solo true (reactivar, B-3); false → 422
    codigo: str | None = Field(default=None, max_length=8)
    tipo: TipoRubro | None = None

    @field_validator("tipo_flujo", mode="before")
    @classmethod
    def _cast_tipo(cls, v: object) -> object:
        if v is None or isinstance(v, TipoFlujo):
            return v
        return TipoFlujo(v)

    @field_validator("tipo", mode="before")
    @classmethod
    def _cast_tipo_rubro(cls, v: object) -> object:
        return v if v is None or isinstance(v, TipoRubro) else TipoRubro(v)


def _serializar(r: Rubro) -> dict:
    return {
        "id": str(r.id),
        "grupo": r.grupo.value,
        "nombre": r.nombre,
        "tipo_flujo": r.tipo_flujo.value,
        "codigo": r.codigo,
        "tipo": r.tipo.value if r.tipo is not None else None,
        "orden": r.orden,
        "activo": r.activo,
        "es_sistema": r.es_sistema,
    }


def _parse_grupo(grupo: str | None) -> RubroGrupo | None:
    if grupo is None:
        return None
    try:
        return RubroGrupo(grupo)
    except ValueError:
        raise HTTPException(422, f"grupo inválido: '{grupo}'") from None


@router.get("")
async def listar(
    activo: bool | None = Query(default=None),
    grupo: str | None = Query(default=None),
    _: User = Depends(require_permission("dashboard:leer")),
):
    rubros = await service.listar_rubros(activo=activo, grupo=_parse_grupo(grupo))
    return [_serializar(r) for r in rubros]


@router.post("", status_code=201)
async def crear(
    body: RubroCrearBody,
    user: User = Depends(require_permission("rubros:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        rubro = await service.crear_rubro(
            grupo=body.grupo,
            nombre=body.nombre,
            tipo_flujo=body.tipo_flujo,
            codigo=body.codigo,
            tipo=body.tipo,
            usuario_id=user.id,
        )
    except service.RubrosError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(rubro)


@router.patch("/{rubro_id}")
async def editar(
    rubro_id: str,
    body: RubroEditarBody,
    user: User = Depends(require_permission("rubros:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        rubro = await service.editar_rubro(
            rubro_id=rubro_id,
            usuario_id=user.id,
            nombre=body.nombre,
            orden=body.orden,
            tipo_flujo=body.tipo_flujo,
            activo=body.activo,
            codigo=body.codigo,
            tipo=body.tipo,
        )
    except service.RubrosError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(rubro)


@router.post("/{rubro_id}/desactivar")
async def desactivar(
    rubro_id: str,
    user: User = Depends(require_permission("rubros:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        rubro = await service.desactivar_rubro(rubro_id=rubro_id, usuario_id=user.id)
    except service.RubrosError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(rubro)
