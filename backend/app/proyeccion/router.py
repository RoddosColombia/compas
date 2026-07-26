# backend/app/proyeccion/router.py
"""/api/v1/proyeccion — el motor de proyección expuesto (COCK-01).

Compute-only, sin estado → `dashboard:leer` (todos los roles la ven; gestionar los
drivers es `proyeccion:gestionar`). Query: escenario (default 'base'), horizonte_meses
(default = el de los parámetros, tope 180), mes_inicio 'YYYY-MM' (default: mes vigente
en América/Bogotá, día 1 — regla 2)."""

import re

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import require_permission
from app.auth.models import User
from app.core.time import today_bogota
from app.proyeccion import service

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
