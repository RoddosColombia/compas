# backend/app/presupuesto/router.py
"""POST /api/v1/meses/{mes}/sugerido (generar) + GET /api/v1/meses/{mes}/presupuesto.

MARCADO PARA AUDITORÍA KIMI (motor del sugerido).

RBAC §2.4: generar = `ciclo:abrir` (fila "Abrir mes / generar sugerido"); leer =
`dashboard:leer`. `crec_pct` viaja como string (Decimal exacto). `mes` en la ruta es
YYYY-MM (se normaliza al día 1)."""

import re
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.core.money import money_str
from app.domain.mes_control import MesControl
from app.domain.presupuesto import PresupuestoLinea
from app.presupuesto import service

router = APIRouter(prefix="/meses", tags=["presupuesto"])

_MES = re.compile(r"^\d{4}-\d{2}$")


class GenerarSugeridoBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    crec_pct: str = "0"  # tasa como string (p. ej. "0.15"); Decimal exacto


def _mes_key(mes: str) -> str:
    if not _MES.match(mes):
        raise HTTPException(422, "mes debe ser 'YYYY-MM'")
    return f"{mes}-01"


def _serializar(ln: PresupuestoLinea) -> dict:
    return {
        "id": str(ln.id),
        "rubro_id": str(ln.rubro_id),
        "version": ln.version,
        "monto_sugerido": money_str(ln.monto_sugerido),
        "prom_3m": money_str(ln.prom_3m),
        "tendencia_mes": money_str(ln.tendencia_mes),
        "crec_pct": str(ln.crec_pct),
        "compromisos_programados": money_str(ln.compromisos_programados),
        "monto_definido": (
            money_str(ln.monto_definido) if ln.monto_definido is not None else None
        ),
        "historia_incompleta": ln.historia_incompleta,
        "modo_calculo": ln.modo_calculo.value,
        "vigente": ln.vigente,
    }


@router.post("/{mes}/sugerido", status_code=201)
async def generar_sugerido(
    mes: str,
    body: GenerarSugeridoBody,
    user: User = Depends(require_permission("ciclo:abrir")),
    _: None = Depends(verify_origin),
):
    try:
        crec = Decimal(body.crec_pct)
    except InvalidOperation:
        raise HTTPException(422, "crec_pct no es un decimal válido") from None
    if crec < 0:
        raise HTTPException(422, "crec_pct no puede ser negativo")
    try:
        lineas = await service.generar_sugerido(
            mes=_mes_key(mes), usuario_id=user.id, crec_pct=crec
        )
    except service.SugeridoError as e:
        raise HTTPException(e.status, e.detalle) from e
    return {"mes": mes, "lineas": [_serializar(x) for x in lineas]}


@router.get("/{mes}/presupuesto")
async def listar_presupuesto(
    mes: str,
    user: User = Depends(require_permission("dashboard:leer")),
):
    mc = await MesControl.find_one(MesControl.mes == _mes_key(mes))
    if mc is None:
        raise HTTPException(404, "mes no encontrado")
    lineas = await PresupuestoLinea.find(
        PresupuestoLinea.mes_id == mc.id,
        PresupuestoLinea.vigente == True,  # noqa: E712
    ).to_list()
    return {"mes": mes, "lineas": [_serializar(x) for x in lineas]}
