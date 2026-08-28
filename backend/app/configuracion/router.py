# backend/app/configuracion/router.py
"""RF-F3 · P1 — endpoints admin del umbral de ATENCIÓN (Fundacional D-1).

Alcance: solo umbral de atención (mueve la proyección → RBAC `proyeccion:gestionar`).
El resto de `Configuracion` se administra desde sus consumidores (calendario DIAN,
tarifa IVA, etc.) — no se centraliza acá para no romper esos flujos.
"""

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.configuracion import service
from app.parametros_proyeccion.service import obtener_vigente

router = APIRouter(prefix="/configuracion", tags=["configuracion"])


class UmbralAtencionBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    valor: str = Field(min_length=1, max_length=32)


async def _caja_minima() -> Decimal:
    """La caja mínima (crítico) vive en los parámetros de proyección vigentes."""
    p = await obtener_vigente()
    if p is None:
        raise HTTPException(409, "sin parámetros de proyección vigentes")
    return Decimal(p.caja_minima)


@router.get("/umbral-atencion")
async def obtener_umbral_atencion(
    _: User = Depends(require_permission("dashboard:leer")),
):
    """Devuelve el umbral vigente (o fallback 3× crítico) + el crítico de referencia."""
    critico = await _caja_minima()
    atencion = await service.leer_umbral_atencion(critico)
    return {"critico": str(critico), "atencion": str(atencion)}


@router.put("/umbral-atencion")
async def escribir_umbral_atencion(
    body: UmbralAtencionBody,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        valor = Decimal(body.valor)
    except (InvalidOperation, ValueError):
        raise HTTPException(422, "valor inválido") from None
    critico = await _caja_minima()
    try:
        fila = await service.escribir_umbral_atencion(
            valor=valor, caja_minima=critico, usuario_id=user.id
        )
    except service.ConfiguracionError as e:
        raise HTTPException(e.status, e.detalle) from e
    return {
        "critico": str(critico),
        "atencion": str(fila.valor_decimal),
        "vigente_desde": fila.vigente_desde,
        "modificado_por": fila.modificado_por,
    }
