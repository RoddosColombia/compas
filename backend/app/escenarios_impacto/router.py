# backend/app/escenarios_impacto/router.py
"""/api/v1/escenarios-impacto — CRUD de escenarios what-if nombrados (D1 §2, CR-D1).

RBAC: GET con `dashboard:leer`; mutaciones con `proyeccion:gestionar` (= las de
preview/impactos) + `verify_origin`. Auditado (CR-D1). `valor` viaja como string y se
preserva con precisión completa (un % como 0.016 no se cuantiza)."""

import re
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.domain.escenario_impacto import AjusteEmbebido, EscenarioImpacto
from app.escenarios_impacto import service

router = APIRouter(prefix="/escenarios-impacto", tags=["escenarios-impacto"])

_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class AjusteBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    nombre: str = Field(min_length=1, max_length=80)
    naturaleza: Literal["gasto", "ingreso"]
    modo: Literal["absoluto", "porcentaje"]
    valor: str  # COP (absoluto) o fracción (porcentaje); string (regla 1)
    mes_inicio: str
    mes_fin: str | None = None
    rubro_id: str | None = None


class EscenarioCrearBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str | None = Field(default=None, max_length=500)
    ajustes: list[AjusteBody] = Field(default_factory=list)


class EscenarioEditarBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=80)
    descripcion: str | None = Field(default=None, max_length=500)
    ajustes: list[AjusteBody] | None = None
    activo: bool | None = None


def _a_embebido(a: AjusteBody) -> AjusteEmbebido:
    if not _MES.match(a.mes_inicio):
        raise HTTPException(422, "mes_inicio debe ser 'YYYY-MM'")
    if a.mes_fin is not None and not _MES.match(a.mes_fin):
        raise HTTPException(422, "mes_fin debe ser 'YYYY-MM' o null")
    try:
        valor = Decimal(a.valor)
    except (InvalidOperation, ValueError) as e:
        raise HTTPException(422, f"valor no es un decimal válido: {a.valor}") from e
    return AjusteEmbebido(
        nombre=a.nombre.strip(),
        naturaleza=a.naturaleza,
        modo=a.modo,
        valor=valor,
        mes_inicio=a.mes_inicio,
        mes_fin=a.mes_fin,
        rubro_id=a.rubro_id,
    )


def _serializar_ajuste(a: AjusteEmbebido) -> dict:
    return {
        "nombre": a.nombre,
        "naturaleza": a.naturaleza,
        "modo": a.modo,
        "valor": str(
            a.valor
        ),  # precisión completa (NO money_str: los % no se cuantizan)
        "mes_inicio": a.mes_inicio,
        "mes_fin": a.mes_fin,
        "rubro_id": a.rubro_id,
    }


def _serializar(e: EscenarioImpacto) -> dict:
    return {
        "id": str(e.id),
        "nombre": e.nombre,
        "descripcion": e.descripcion,
        "ajustes": [_serializar_ajuste(a) for a in e.ajustes],
        "creado_por": e.creado_por,
        "actualizado_at": e.actualizado_at.isoformat(),
        "activo": e.activo,
    }


@router.get("")
async def listar(
    activo: bool | None = Query(default=True),
    _: User = Depends(require_permission("dashboard:leer")),
):
    escenarios = await service.listar_escenarios(activo=activo)
    return {"items": [_serializar(e) for e in escenarios]}


@router.post("", status_code=201)
async def crear(
    body: EscenarioCrearBody,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        e = await service.crear_escenario(
            nombre=body.nombre.strip(),
            descripcion=body.descripcion,
            ajustes=[_a_embebido(a) for a in body.ajustes],
            usuario_id=user.id,
        )
    except service.EscenariosError as ex:
        raise HTTPException(ex.status, ex.detalle) from ex
    return _serializar(e)


@router.patch("/{escenario_id}")
async def editar(
    escenario_id: str,
    body: EscenarioEditarBody,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    campos = body.model_fields_set
    try:
        e = await service.editar_escenario(
            escenario_id=escenario_id,
            usuario_id=user.id,
            nombre=body.nombre.strip() if body.nombre is not None else None,
            descripcion=body.descripcion,
            descripcion_set="descripcion" in campos,
            ajustes=(
                [_a_embebido(a) for a in body.ajustes]
                if body.ajustes is not None
                else None
            ),
            activo=body.activo,
        )
    except service.EscenariosError as ex:
        raise HTTPException(ex.status, ex.detalle) from ex
    return _serializar(e)


@router.delete("/{escenario_id}", status_code=204)
async def eliminar(
    escenario_id: str,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        await service.eliminar_escenario(escenario_id=escenario_id, usuario_id=user.id)
    except service.EscenariosError as ex:
        raise HTTPException(ex.status, ex.detalle) from ex
