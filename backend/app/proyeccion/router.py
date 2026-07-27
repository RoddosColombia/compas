# backend/app/proyeccion/router.py
"""/api/v1/proyeccion — el motor de proyección expuesto (COCK-01).

Compute-only, sin estado → `dashboard:leer` (todos los roles la ven; gestionar los
drivers es `proyeccion:gestionar`). Query: escenario (default 'base'), horizonte_meses
(default = el de los parámetros, tope 180), mes_inicio 'YYYY-MM' (default: mes vigente
en América/Bogotá, día 1 — regla 2)."""

import re
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.core.time import today_bogota
from app.parametros_proyeccion.router import ParametrosCampos, parsear_campos
from app.proyeccion import service
from app.proyeccion.impactos import Ajuste

router = APIRouter(prefix="/proyeccion", tags=["proyeccion"])

_MES = re.compile(r"^\d{4}-\d{2}$")


def _parse_mes_inicio(mes_inicio: str | None) -> tuple[int, int]:
    if mes_inicio is None:
        hoy = today_bogota()
        return (hoy.year, hoy.month)
    if not _MES.match(mes_inicio):
        raise HTTPException(422, "mes_inicio debe ser 'YYYY-MM'")
    y, m = mes_inicio.split("-")
    mes = int(m)
    if not 1 <= mes <= 12:
        raise HTTPException(422, "mes_inicio: mes fuera de rango")
    return (int(y), mes)


@router.get("")
async def proyectar(
    escenario: str = Query(default="base"),
    horizonte_meses: int | None = Query(default=None),
    mes_inicio: str | None = Query(default=None),
    _: User = Depends(require_permission("dashboard:leer")),
):
    try:
        return await service.proyectar_vigente(
            escenario=escenario,
            mes_inicio=_parse_mes_inicio(mes_inicio),
            horizonte_meses=horizonte_meses,
        )
    except service.ProyeccionError as e:
        raise HTTPException(e.status, e.detalle) from e


class PreviewBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    parametros: ParametrosCampos


@router.post("/preview")
async def preview(
    body: PreviewBody,
    escenario: str = Query(default="base"),
    horizonte_meses: int | None = Query(default=None),
    mes_inicio: str | None = Query(default=None),
    _u: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    """C3 §5.1 — impacto de un set de parámetros PROPUESTO, compute-only: mismo shape
    que GET /proyeccion, sin persistir nada. RBAC = el permiso que edita parámetros.

    Nota QA C3 (documentada, sin acción): cada preview es una proyección completa
    (cartera previa + IVA + motor). Con el debounce de 600 ms del editor y dos
    usuarios gestores es irrelevante; si el nº de usuarios o el horizonte crecen,
    añadir rate-limit con el patrón existente de auth (client_ip + ventana)."""
    try:
        return await service.proyectar_preview(
            campos=parsear_campos(body.parametros),
            escenario=escenario,
            mes_inicio=_parse_mes_inicio(mes_inicio),
            horizonte_meses=horizonte_meses,
        )
    except service.ProyeccionError as e:
        raise HTTPException(e.status, e.detalle) from e


class AjusteBody(BaseModel):
    """Un ajuste declarativo del §2. `valor` viaja como string (regla 1): monto COP para
    `absoluto`, fracción (0.10 = 10%) para `porcentaje`."""

    model_config = ConfigDict(strict=True, extra="forbid")

    nombre: str
    naturaleza: Literal["gasto", "ingreso"]
    modo: Literal["absoluto", "porcentaje"]
    valor: str
    mes_inicio: str
    mes_fin: str | None = None
    rubro_id: str | None = None


class ImpactosBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    ajustes: list[AjusteBody]


def _a_ajuste(a: AjusteBody) -> Ajuste:
    nombre = a.nombre.strip()
    if not 1 <= len(nombre) <= 80:
        raise HTTPException(422, "nombre del ajuste debe tener 1..80 caracteres")
    if not _MES.match(a.mes_inicio):
        raise HTTPException(422, "mes_inicio debe ser 'YYYY-MM'")
    if a.mes_fin is not None and not _MES.match(a.mes_fin):
        raise HTTPException(422, "mes_fin debe ser 'YYYY-MM' o null")
    try:
        valor = Decimal(a.valor)
    except (InvalidOperation, ValueError) as e:
        raise HTTPException(422, f"valor no es un decimal válido: {a.valor}") from e
    return Ajuste(
        nombre=nombre,
        naturaleza=a.naturaleza,
        modo=a.modo,
        valor=valor,
        mes_inicio=a.mes_inicio,
        mes_fin=a.mes_fin,
        rubro_id=a.rubro_id,
    )


@router.post("/impactos")
async def impactos(
    body: ImpactosBody,
    escenario: str = Query(default="base"),
    horizonte_meses: int | None = Query(default=None),
    mes_inicio: str | None = Query(default=None),
    _u: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    """D1 §2 — proyección BASE vs. CON AJUSTES, compute-only (SIMULAR NUNCA ESCRIBE).

    RBAC = `proyeccion:gestionar` (⚠ VERIFICAR del §2 resuelto): aunque es lectura con
    matemática encima, comparte el permiso del preview de C3 por consistencia — es la
    misma clase de operación (proponer un cambio y ver su impacto sin persistir)."""
    try:
        return await service.proyectar_impactos(
            ajustes=[_a_ajuste(a) for a in body.ajustes],
            escenario=escenario,
            mes_inicio=_parse_mes_inicio(mes_inicio),
            horizonte_meses=horizonte_meses,
        )
    except service.ProyeccionError as e:
        raise HTTPException(e.status, e.detalle) from e


@router.get("/valles")
async def valles(
    escenario: str = Query(default="base"),
    horizonte_meses: int | None = Query(default=None),
    mes_inicio: str | None = Query(default=None),
    _: User = Depends(require_permission("dashboard:leer")),
):
    """D1 §3 — los valles (hitos) de la proyección vigente. Lectura pura."""
    try:
        return await service.valles_vigente(
            escenario=escenario,
            mes_inicio=_parse_mes_inicio(mes_inicio),
            horizonte_meses=horizonte_meses,
        )
    except service.ProyeccionError as e:
        raise HTTPException(e.status, e.detalle) from e


@router.get("/operacion")
async def operacion(
    escenario: str = Query(default="base"),
    horizonte_meses: int | None = Query(default=None),
    mes_inicio: str | None = Query(default=None),
    _: User = Depends(require_permission("dashboard:leer")),
):
    """DASH-01 — agregación operativa (Dashboards): colocación mensual + cartera activa
    desglosada por añada (cohorte)."""
    try:
        return await service.operacion_vigente(
            escenario=escenario,
            mes_inicio=_parse_mes_inicio(mes_inicio),
            horizonte_meses=horizonte_meses,
        )
    except service.ProyeccionError as e:
        raise HTTPException(e.status, e.detalle) from e


@router.get("/sensibilidad")
async def sensibilidad(
    escenario: str = Query(default="base"),
    mes_inicio: str | None = Query(default=None),
    _: User = Depends(require_permission("dashboard:leer")),
):
    """C3 §5.2 — el tornado '¿qué mueve mi umbral?': variación del piso de caja
    ante cambios naturales de las 7 variables. Compute-only, cache por vigencia."""
    try:
        return await service.sensibilidad_vigente(
            escenario=escenario, mes_inicio=_parse_mes_inicio(mes_inicio)
        )
    except service.ProyeccionError as e:
        raise HTTPException(e.status, e.detalle) from e


@router.get("/comparar")
async def comparar(
    escenario: str = Query(default="base"),
    ancla: str = Query(default="cerrado"),  # 'cerrado' | 'movimientos'
    horizonte_meses: int | None = Query(default=None),
    mes_inicio: str | None = Query(default=None),
    _: User = Depends(require_permission("dashboard:leer")),
):
    """COCK-09 — actuals (caja real de bancos) vs proyección + rolling forecast (la
    proyección se re-ancla a la caja real del último mes cerrado o con movimientos)."""
    try:
        return await service.comparar_vigente(
            escenario=escenario,
            ancla_modo=ancla,
            horizonte_meses=horizonte_meses,
            mes_inicio_defecto=_parse_mes_inicio(mes_inicio),
        )
    except service.ProyeccionError as e:
        raise HTTPException(e.status, e.detalle) from e
