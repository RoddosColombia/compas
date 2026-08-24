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
from app.core.money import money_str
from app.domain.parametros_proyeccion import (
    ComponenteAlistamiento,
    ParametrosProyeccion,
    costo_alistamiento_total,
)
from app.parametros_proyeccion import service
from app.parametros_proyeccion.sugerencias import sugerencias

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
    # SUP-1: segundo tramo de crecimiento (van JUNTOS; None/None = sin tramo 2).
    crec_pct_mensual_2: str | None = None
    crec_mes_corte: int | None = Field(default=None, gt=0, le=180)
    # SUP-2: mora/recuperación de los escenarios extremos + rezago + prefondeo + aval.
    # Los cuatro primeros en None = se conserva el delta de SUP-1 (compatibilidad).
    pct_mora_pesimista: str | None = None
    pct_recuperacion_pesimista: str | None = None
    pct_mora_optimista: str | None = None
    pct_recuperacion_optimista: str | None = None
    meses_rezago_recuperacion: int = Field(default=1, ge=0, le=12)
    pct_prefondeo_iva: str = "1"
    pct_aval_recaudo: str = "0"


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
    # SUP-2: los porcentajes editables (escenarios extremos, prefondeo, aval). Los de
    # escenario admiten None = "sin editar" (cae al delta de SUP-1); los otros dos
    # siempre traen valor. El rango [0,1] lo valida el dominio (fail-closed).
    for c in (
        "pct_mora_pesimista",
        "pct_recuperacion_pesimista",
        "pct_mora_optimista",
        "pct_recuperacion_optimista",
        "pct_prefondeo_iva",
        "pct_aval_recaudo",
    ):
        crudo = getattr(body, c)
        if crudo is None:
            campos[c] = None
            continue
        try:
            v = Decimal(crudo)
            if not v.is_finite():
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            raise HTTPException(422, f"{c} debe ser un decimal en string") from None
        if not (Decimal("0") <= v <= Decimal("1")):
            raise HTTPException(422, f"{c} debe ser una fracción entre 0 y 1")
        campos[c] = v
    campos["meses_rezago_recuperacion"] = body.meses_rezago_recuperacion
    # SUP-1: segundo tramo de crecimiento. Los dos campos van JUNTOS (422 fail-loud);
    # el Decimal se parsea aquí (regla 1: el monto/pct viaja como string).
    if (body.crec_pct_mensual_2 is None) != (body.crec_mes_corte is None):
        raise HTTPException(
            422,
            "segundo tramo de crecimiento incompleto: crec_pct_mensual_2 y "
            "crec_mes_corte van juntos (o ninguno)",
        )
    if body.crec_pct_mensual_2 is not None:
        try:
            tasa2 = Decimal(body.crec_pct_mensual_2)
            if not tasa2.is_finite():
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            raise HTTPException(
                422, "crec_pct_mensual_2 debe ser un decimal en string"
            ) from None
        if tasa2 < 0:
            raise HTTPException(422, "crec_pct_mensual_2 no puede ser negativo")
        campos["crec_pct_mensual_2"] = tasa2
        campos["crec_mes_corte"] = body.crec_mes_corte
    else:
        campos["crec_pct_mensual_2"] = None
        campos["crec_mes_corte"] = None
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
    # SUP-1: segundo tramo (pct como string, regla 1; None cuando no hay tramo 2)
    out["crec_pct_mensual_2"] = (
        str(p.crec_pct_mensual_2) if p.crec_pct_mensual_2 is not None else None
    )
    out["crec_mes_corte"] = p.crec_mes_corte
    # SUP-2: porcentajes editables (None cuando el escenario no está editado)
    for c in (
        "pct_mora_pesimista",
        "pct_recuperacion_pesimista",
        "pct_mora_optimista",
        "pct_recuperacion_optimista",
    ):
        v = getattr(p, c)
        out[c] = str(v) if v is not None else None
    out["meses_rezago_recuperacion"] = p.meses_rezago_recuperacion
    out["pct_prefondeo_iva"] = str(p.pct_prefondeo_iva)
    out["pct_aval_recaudo"] = str(p.pct_aval_recaudo)
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


@router.get("/sugerencias")
async def obtener_sugerencias(
    _u: User = Depends(require_permission("proyeccion:gestionar")),
):
    """P7 del ciclo mensual — supuestos SUGERIDOS por el gasto real de los meses
    cerrados. Compute-only: no escribe nada, el CEO decide si los adopta.

    RBAC: el permiso que EDITA los supuestos (es un insumo para editarlos, igual que el
    preview de C3). Montos como string (regla 1)."""
    s = await sugerencias()
    g = s["gastos_fijos"]
    return {
        "gastos_fijos": (
            None
            if g is None
            else {
                "valor": money_str(g["valor"]),
                "meses": g["meses"],
                "n": g["n"],
                "detalle": [
                    {"mes": d["mes"], "valor": money_str(d["valor"])}
                    for d in g["detalle"]
                ],
            }
        )
    }
