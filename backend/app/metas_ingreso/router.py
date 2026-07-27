# backend/app/metas_ingreso/router.py
"""/api/v1/metas-ingreso — metas de ingreso por mes (D2 §6, CR-D2).

INFORMATIVA: no toca el motor ni la caja proyectada. RBAC: GET `dashboard:leer`;
mutaciones `proyeccion:gestionar` + `verify_origin`. Montos string (regla 1)."""

import re
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.core.money import money_str
from app.domain.obligacion import LineaMeta, MetaIngreso
from app.metas_ingreso import service

router = APIRouter(prefix="/metas-ingreso", tags=["metas-ingreso"])

_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _dec(s: str, campo: str) -> Decimal:
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError) as e:
        raise HTTPException(422, f"{campo} no es un decimal válido: {s}") from e


class LineaBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    nombre: str = Field(min_length=1, max_length=120)
    valor: str


class MetaCrearBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    mes: str
    valor: str
    lineas: list[LineaBody] = Field(default_factory=list)


class MetaEditarBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    valor: str | None = None
    lineas: list[LineaBody] | None = None


def _lineas(bodies: list[LineaBody]) -> list[LineaMeta]:
    return [
        LineaMeta(nombre=b.nombre, valor=_dec(b.valor, "linea.valor")) for b in bodies
    ]


async def _serializar(m: MetaIngreso) -> dict:
    real = await service.ingreso_real(m.mes)
    pct = None
    if real is not None and m.valor > 0:
        pct = str((real / m.valor * 100).quantize(Decimal("0.1"), ROUND_HALF_EVEN))
    return {
        "id": str(m.id),
        "mes": m.mes,
        "valor": money_str(m.valor),
        "lineas": [
            {"nombre": ln.nombre, "valor": money_str(ln.valor)} for ln in m.lineas
        ],
        "real_ejecutado": money_str(real) if real is not None else None,
        "pct_cumplimiento": pct,
        "activo": m.activo,
    }


@router.get("")
async def listar(_: User = Depends(require_permission("dashboard:leer"))):
    metas = await service.listar_metas()
    return {"items": [await _serializar(m) for m in metas]}


@router.post("", status_code=201)
async def crear(
    body: MetaCrearBody,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    if not _MES.match(body.mes):
        raise HTTPException(422, "mes debe ser 'YYYY-MM'")
    try:
        m = await service.crear_meta(
            mes=body.mes,
            valor=_dec(body.valor, "valor"),
            lineas=_lineas(body.lineas),
            usuario_id=user.id,
        )
    except service.MetasError as e:
        raise HTTPException(e.status, e.detalle) from e
    return await _serializar(m)


@router.patch("/{meta_id}")
async def editar(
    meta_id: str,
    body: MetaEditarBody,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        m = await service.editar_meta(
            meta_id=meta_id,
            usuario_id=user.id,
            valor=_dec(body.valor, "valor") if body.valor is not None else None,
            lineas=_lineas(body.lineas) if body.lineas is not None else None,
        )
    except service.MetasError as e:
        raise HTTPException(e.status, e.detalle) from e
    return await _serializar(m)


@router.delete("/{meta_id}", status_code=204)
async def eliminar(
    meta_id: str,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        await service.eliminar_meta(meta_id=meta_id, usuario_id=user.id)
    except service.MetasError as e:
        raise HTTPException(e.status, e.detalle) from e
