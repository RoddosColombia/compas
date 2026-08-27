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

# Router aparte con prefijo /caja para la evolución diaria (lectura).
diaria_router = APIRouter(prefix="/caja", tags=["caja"])

_MES = re.compile(r"^\d{4}-\d{2}$")
_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@diaria_router.get("/diaria")
async def caja_diaria(
    desde: str,
    hasta: str,
    caja_inicial: str = "0",
    _: User = Depends(require_permission("dashboard:leer")),
):
    """Evolución diaria de la caja en [desde, hasta] (YYYY-MM-DD). `caja_inicial`
    string (regla 1); 0 = saldo relativo desde el inicio del rango."""
    for etiqueta, v in (("desde", desde), ("hasta", hasta)):
        if not _FECHA.match(v):
            raise HTTPException(422, f"{etiqueta} debe ser 'YYYY-MM-DD'")
    if hasta < desde:
        raise HTTPException(422, "hasta no puede ser anterior a desde")
    try:
        inicial = Decimal(caja_inicial)
        if not inicial.is_finite():
            raise InvalidOperation
    except InvalidOperation:
        raise HTTPException(422, "caja_inicial no es un decimal válido") from None
    return await service.caja_diaria(desde=desde, hasta=hasta, caja_inicial=inicial)


@diaria_router.get("/disponible")
async def saldo_disponible(
    _: User = Depends(require_permission("dashboard:leer")),
):
    """Saldo disponible EN VIVO (CEO 2026-08-24): el número fijo que se actualiza al
    cargar movimientos — saldo en banco por banco + tránsito Wava + frescura. Lectura
    pura (no toca el motor). Reusa la conciliación del cierre (misma verdad)."""
    return await service.saldo_disponible()


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
            if not saldo.is_finite():
                raise InvalidOperation
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
