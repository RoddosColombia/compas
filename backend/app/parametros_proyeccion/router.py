# backend/app/parametros_proyeccion/router.py
"""/api/v1/parametros-proyeccion — drivers del motor (CR-COCK).

GET con `dashboard:leer` (todos ven la config vigente); PUT con `proyeccion:gestionar`
+ `verify_origin`. Montos como string (regla 1). El PUT versiona por `vigente_desde`."""

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.domain.parametros_proyeccion import ParametrosProyeccion
from app.parametros_proyeccion import service

router = APIRouter(prefix="/parametros-proyeccion", tags=["parametros-proyeccion"])

_MONEY = (
    "caja_inicial",
    "caja_minima",
    "crec_pct_mensual",
    "adelanto_auteco",
    "tasa_auteco",
    "gastos_fijos",
    "gps_moto",
    "costo_moto_nueva",
    "deuda",
    "tasa_deuda",
    "pct_mora",
    "pct_recuperacion",
    "pct_default",
    "pct_provision",
)
_INT = (
    "motos_base",
    "horizonte_meses",
    "plazo_auteco_dias",
    "base_auteco_dias",
    "mes_inicio_deuda",
    "meses_deuda",
)


class ParametrosBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    vigente_desde: str
    caja_inicial: str
    caja_minima: str
    motos_base: int = Field(ge=0)
    crec_pct_mensual: str
    horizonte_meses: int = Field(gt=0, le=180)
    adelanto_auteco: str
    plazo_auteco_dias: int = Field(ge=0)
    base_auteco_dias: int = Field(ge=0)
    tasa_auteco: str
    gastos_fijos: str
    gps_moto: str
    costo_moto_nueva: str
    deuda: str
    tasa_deuda: str
    mes_inicio_deuda: int = Field(ge=0)
    meses_deuda: int = Field(ge=0)
    pct_mora: str
    pct_recuperacion: str
    pct_default: str
    pct_provision: str


def _serializar(p: ParametrosProyeccion) -> dict:
    out: dict = {"id": str(p.id), "vigente_desde": p.vigente_desde}
    for c in _MONEY:
        out[c] = str(getattr(p, c))
    for c in _INT:
        out[c] = getattr(p, c)
    out["modificado_por"] = p.modificado_por
    return out


@router.get("")
async def obtener(_: User = Depends(require_permission("dashboard:leer"))):
    p = await service.obtener_vigente()
    if p is None:
        raise HTTPException(404, "no hay parámetros de proyección configurados")
    return _serializar(p)


@router.put("")
async def actualizar(
    body: ParametrosBody,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    campos: dict = {}
    for c in _MONEY:
        try:
            campos[c] = Decimal(getattr(body, c))
        except (InvalidOperation, ValueError):
            raise HTTPException(422, f"{c} debe ser un decimal en string") from None
    for c in _INT:
        campos[c] = getattr(body, c)
    try:
        p = await service.actualizar(
            vigente_desde=body.vigente_desde, campos=campos, usuario_id=user.id
        )
    except service.ParametrosError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(p)
