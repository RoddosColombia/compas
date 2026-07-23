# backend/app/caja/router.py
"""PATCH /api/v1/meses/{mes}/saldos — C4 reporte diario de saldos por banco (CR-S6).

MARCADO PARA AUDITORÍA KIMI (gate I-PR1).

RBAC: `caja:reportar` = {financiero, admin} (CR-S6) + `verify_origin`. Sin
Idempotency-Key (D6: el upsert es idempotente por naturaleza; la convención de keys
se reserva a POST sensibles de dinero/decisión). `mes` en la ruta es YYYY-MM. Regla
1: el saldo viaja como STRING (strict rechaza el number del JSON)."""

import re
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.caja import service
from app.domain.bancos import Banco

router = APIRouter(prefix="/meses", tags=["caja"])

_MES = re.compile(r"^\d{4}-\d{2}$")


def _mes_key(mes: str) -> str:
    if not _MES.match(mes):
        raise HTTPException(422, "mes debe ser 'YYYY-MM'")
    return f"{mes}-01"


class SaldoReporteBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    banco: str
    saldo: str  # string (regla 1)
    fecha_reporte: str


class ReportarSaldosBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    saldos: list[SaldoReporteBody] = Field(min_length=1)


@router.patch("/{mes}/saldos")
async def reportar_saldos(
    mes: str,
    body: ReportarSaldosBody,
    user: User = Depends(require_permission("caja:reportar")),
    _: None = Depends(verify_origin),
):
    reportes: list[service.ReporteBanco] = []
    vistos: set[Banco] = set()
    for s in body.saldos:
        try:
            banco = Banco(s.banco)
        except ValueError:
            raise HTTPException(422, f"banco desconocido: {s.banco}") from None
        if banco is Banco.MANUAL:
            raise HTTPException(422, "'manual' no es un banco de saldos (§1.3)")
        if banco in vistos:
            raise HTTPException(
                422, f"banco repetido en la misma llamada: {banco.value}"
            )
        vistos.add(banco)
        try:
            saldo = Decimal(s.saldo)
        except InvalidOperation:
            raise HTTPException(
                422, f"saldo no es un decimal válido: {s.saldo}"
            ) from None
        reportes.append(
            service.ReporteBanco(
                banco=banco, saldo=saldo, fecha_reporte=s.fecha_reporte
            )
        )

    try:
        return await service.reportar_saldos(
            mes=_mes_key(mes), reportes=reportes, usuario_id=user.id
        )
    except service.CajaError as e:
        raise HTTPException(e.status, e.detalle) from e
