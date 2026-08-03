# backend/app/ciclo/router.py
"""POST /api/v1/meses (abrir mes, US-01) + GET /api/v1/meses.

MARCADO PARA AUDITORÍA KIMI (flujo del ciclo mensual).

RBAC §2.4: `ciclo:abrir` (financiero/directivo/admin). Regla 1: montos como
STRING. El saldo inicial NO se edita por aquí después (eso es `ciclo:config`
+ step-up MFA, incremento futuro)."""

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.ciclo import service
from app.cierre.transito import transito_heredado
from app.core.money import money_str
from app.domain.bancos import Banco
from app.domain.mes_control import MesControl, SaldoBanco

router = APIRouter(prefix="/meses", tags=["ciclo"])


class SaldoBancoBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    banco: str
    saldo: str  # string (regla 1)
    fecha_reporte: str


class AbrirMesBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    mes: str  # YYYY-MM-01 (valida el Document)
    # M-1 (F-14): SOLO para el primer mes de la historia; con predecesor se
    # deriva del consolidado bancario anterior y traerlo es 422.
    saldo_inicial_caja: str | None = None
    saldos_banco: list[SaldoBancoBody] = Field(default_factory=list)
    ingresos_esperados_semana: str | None = None


def _decimal(s: str, campo: str) -> Decimal:
    try:
        v = Decimal(s)
        if not v.is_finite():
            raise InvalidOperation
        return v
    except InvalidOperation:
        raise HTTPException(422, f"{campo} no es un decimal válido") from None


def _serializar(mc: MesControl) -> dict:
    return {
        "id": str(mc.id),
        "mes": mc.mes,
        "estado": mc.estado.value,
        "saldo_inicial_caja": money_str(mc.saldo_inicial_caja),
        "saldos_banco": [
            {
                "banco": s.banco.value,
                "saldo": money_str(s.saldo),
                "fecha_reporte": s.fecha_reporte,
            }
            for s in mc.saldos_banco
        ],
        "ingresos_esperados_semana": (
            money_str(mc.ingresos_esperados_semana)
            if mc.ingresos_esperados_semana is not None
            else None
        ),
    }


@router.post("", status_code=201)
async def abrir_mes(
    body: AbrirMesBody,
    user: User = Depends(require_permission("ciclo:abrir")),
    _: None = Depends(verify_origin),
):
    saldos: list[SaldoBanco] = []
    vistos: set[Banco] = set()  # A-6 (parte 4): dedup, espejo de reportar_saldos
    for s in body.saldos_banco:
        try:
            banco = Banco(s.banco)
        except ValueError:
            raise HTTPException(422, f"banco desconocido: {s.banco}") from None
        if banco is Banco.MANUAL:
            raise HTTPException(422, "'manual' no es un banco de saldos (§1.3)")
        if banco in vistos:
            # Un saldos_banco con banco duplicado rompe el dict de conciliación
            # ({sb.banco: sb}) y los updates posicionales por banco. Fail-loud.
            raise HTTPException(
                422, f"banco repetido en la misma llamada: {banco.value}"
            )
        vistos.add(banco)
        try:
            saldos.append(
                SaldoBanco(
                    banco=banco,
                    saldo=_decimal(s.saldo, "saldo"),
                    fecha_reporte=s.fecha_reporte,
                )
            )
        except ValueError as e:
            raise HTTPException(422, str(e)) from None

    try:
        mc = await service.abrir_mes(
            mes=body.mes,
            saldo_inicial_caja=(
                _decimal(body.saldo_inicial_caja, "saldo_inicial_caja")
                if body.saldo_inicial_caja is not None
                else None
            ),
            saldos_banco=saldos,
            ingresos_esperados_semana=(
                _decimal(body.ingresos_esperados_semana, "ingresos_esperados_semana")
                if body.ingresos_esperados_semana is not None
                else None
            ),
            usuario_id=user.id,
        )
    except service.MesYaAbiertoError as e:
        raise HTTPException(409, f"el mes {e.mes[:7]} ya está abierto") from e
    except service.AperturaInvalidaError as e:
        raise HTTPException(422, e.detalle) from e
    except ValueError as e:  # validación del Document (mes no normalizado, etc.)
        raise HTTPException(422, str(e)) from e
    return _serializar(mc)


@router.get("")
async def listar_meses(
    user: User = Depends(require_permission("dashboard:leer")),
):
    filas = await MesControl.find_all().sort(-MesControl.mes).to_list()
    items = []
    for m in filas:
        d = _serializar(m)
        # CR-WAVA: tránsito de apertura (heredado del mes anterior) + caja inicial.
        # Aditivo: 0 sin declaración → respuesta idéntica a pre-módulo.
        heredado = await transito_heredado(m.mes)
        d["transito_heredado"] = money_str(heredado)
        d["caja_inicial_total"] = money_str(m.saldo_inicial_caja + heredado)
        items.append(d)
    return {"items": items}
