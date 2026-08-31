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
from app.cierre.service import CierreError, conciliacion, mes_en_ejecucion
from app.core.money import money_str
from app.core.time import now_bogota
from app.domain.bancos import Banco
from app.proyeccion.service import ProyeccionError, proyectar_vigente

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


class DisponibleTesoreria(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    bruto: str
    reserva_iva: str
    neto: str
    fecha_corte: str | None
    sin_dato: list[str]


@diaria_router.get("/disponible", response_model=DisponibleTesoreria)
async def caja_disponible(
    _: User = Depends(require_permission("dashboard:leer")),
) -> DisponibleTesoreria:
    """RF-IVA-TES · Task 4 — 'la cerca' (backend): descompone la caja disponible EN
    VIVO en bruto/reserva-IVA/neto, para que la barra de saldo muestre el dinero del
    IVA como apartado (no como caja libre). `bruto` = `consolidado_reportado` de la
    conciliación (misma verdad que D4) del mes EN_EJECUCION; `reserva_iva` = saldo
    acumulado del fondo de provisión de IVA (P1.4) del mes calendario de HOY (América/
    Bogotá), leído de la proyección vigente -- mismo patrón que
    `cfo/agente/tools.py:_iva_tesoreria` (Task 3, `mes_inicio=(hoy.year, hoy.month)`,
    `horizonte_meses=None`): el fondo acumula su saldo DESDE `mes_inicio`, así que hay
    que anclar ahí, no en el mes EN_EJECUCION del ciclo (que puede no coincidir con
    hoy) para no truncar los aportes ya acumulados del período. `neto = bruto -
    reserva_iva` (puede ser negativo). Todo money como STRING (regla 1). Sin mes en
    ejecución o sin fondo/proyección configurada → respuesta en cero / `reserva_iva='0'`
    (fail-closed a 'no hay reserva', nunca se inventa una cifra — regla 7)."""
    mes = await mes_en_ejecucion()
    if mes is None:
        return DisponibleTesoreria(
            bruto="0", reserva_iva="0", neto="0", fecha_corte=None, sin_dato=[]
        )

    try:
        con = await conciliacion(mes)
    except CierreError as e:
        raise HTTPException(e.status, e.detalle) from e

    bruto = con["consolidado_reportado"]
    sin_dato = con["sin_dato"]

    hoy = now_bogota()
    mes_actual = f"{hoy.year:04d}-{hoy.month:02d}"
    reserva_iva = "0"
    try:
        proy = await proyectar_vigente(
            escenario="base",
            mes_inicio=(hoy.year, hoy.month),
            horizonte_meses=None,
        )
    except ProyeccionError:
        proy = None
    if proy is not None:
        for f in proy.get("fondo_provision", []):
            if f["mes"] == mes_actual:
                reserva_iva = f["saldo"]
                break

    neto = money_str(Decimal(bruto) - Decimal(reserva_iva))
    return DisponibleTesoreria(
        bruto=bruto,
        reserva_iva=reserva_iva,
        neto=neto,
        fecha_corte=None,
        sin_dato=sin_dato,
    )


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
