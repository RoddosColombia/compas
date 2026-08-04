# backend/app/parametros_proyeccion/router.py
"""/api/v1/parametros-proyeccion — drivers del motor (CR-COCK).

GET con `dashboard:leer` (todos ven la config vigente); PUT con `proyeccion:gestionar`
+ `verify_origin`. Montos como string (regla 1). El PUT versiona por `vigente_desde`."""

import re
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.domain.parametros_proyeccion import (
    ComponenteAlistamiento,
    ParametrosProyeccion,
    costo_alistamiento_total,
)
from app.parametros_proyeccion import service

router = APIRouter(prefix="/parametros-proyeccion", tags=["parametros-proyeccion"])

_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")  # FIX-L: clave de rampa_unidades

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


class ParametrosCampos(BaseModel):
    """Los campos del set de parámetros SIN la vigencia — compartido entre el PUT
    (que versiona) y el preview de C3 (compute-only, sin persistencia)."""

    model_config = ConfigDict(strict=True, extra="forbid")

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
    # CR-002: desglose configurable del alistamiento (opcional; None = costo plano)
    componentes_alistamiento: list["ComponenteBody"] | None = None
    # FIX-L: rampa de colocación por mes (YYYY-MM → unidades enteras ≥0). Default {}.
    rampa_unidades: dict[str, int] = Field(default_factory=dict)


class ComponenteBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    nombre: str = Field(min_length=1, max_length=80)
    valor: str  # monto COP como string (regla 1)
    activo: bool = True
    orden: int = 0


class ParametrosBody(ParametrosCampos):
    vigente_desde: str
    # C3: por qué el cambio — viaja a la metadata del evento de auditoría.
    nota: str | None = Field(default=None, max_length=300)


def parsear_campos(body: ParametrosCampos) -> dict:
    """Strings regla 1 → Decimal/int, con 422 si algún decimal no parsea.
    Compartido por el PUT y el preview (C3): un solo criterio de parseo.
    CR-002: con componentes, `costo_moto_nueva` se DERIVA (Σ activos) — la
    autoridad es server-side, lo enviado en ese campo se ignora."""
    campos: dict = {}
    for c in _MONEY:
        try:
            campos[c] = Decimal(getattr(body, c))
            if not campos[c].is_finite():
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            raise HTTPException(422, f"{c} debe ser un decimal en string") from None
    for c in _INT:
        campos[c] = getattr(body, c)
    if body.componentes_alistamiento is not None:
        comps: list[ComponenteAlistamiento] = []
        for cb in body.componentes_alistamiento:
            try:
                valor = Decimal(cb.valor)
                if not valor.is_finite():
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                raise HTTPException(
                    422,
                    f"componente '{cb.nombre}': valor debe ser un decimal en string",
                ) from None
            if valor < 0:
                raise HTTPException(
                    422, f"componente '{cb.nombre}': valor no puede ser negativo"
                )
            comps.append(
                ComponenteAlistamiento(
                    nombre=cb.nombre, valor=valor, activo=cb.activo, orden=cb.orden
                )
            )
        campos["componentes_alistamiento"] = comps or None
        if comps:
            campos["costo_moto_nueva"] = costo_alistamiento_total(
                comps, campos["costo_moto_nueva"]
            )
    else:
        campos["componentes_alistamiento"] = None
    # FIX-L: rampa por mes (YYYY-MM → unidades enteras ≥0). 422 fail-loud.
    for mes, unidades in body.rampa_unidades.items():
        if not _MES.match(mes):
            raise HTTPException(422, f"rampa_unidades: mes inválido '{mes}' (YYYY-MM)")
        if unidades < 0:
            raise HTTPException(422, f"rampa_unidades: unidades negativas en {mes}")
    campos["rampa_unidades"] = dict(body.rampa_unidades)
    return campos


def _serializar(p: ParametrosProyeccion) -> dict:
    out: dict = {"id": str(p.id), "vigente_desde": p.vigente_desde}
    for c in _MONEY:
        out[c] = str(getattr(p, c))
    for c in _INT:
        out[c] = getattr(p, c)
    out["componentes_alistamiento"] = (
        [
            {
                "nombre": c.nombre,
                "valor": str(c.valor),
                "activo": c.activo,
                "orden": c.orden,
            }
            for c in p.componentes_alistamiento
        ]
        if p.componentes_alistamiento
        else None
    )
    out["rampa_unidades"] = dict(p.rampa_unidades)  # FIX-L
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
    campos = parsear_campos(body)
    try:
        p = await service.actualizar(
            vigente_desde=body.vigente_desde,
            campos=campos,
            usuario_id=user.id,
            nota=body.nota,
        )
    except service.ParametrosError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(p)
