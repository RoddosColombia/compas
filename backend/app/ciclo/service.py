# backend/app/ciclo/service.py
"""Apertura del mes (US-01).

MARCADO PARA AUDITORÍA KIMI (flujo del ciclo mensual).

Crea el MesControl (estado inicial `sugerido`) y emite `mes.creado` (regla 11).
Política O1 (audit fail-closed en operaciones de estado del ciclo): si el emit
falla, la apertura se COMPENSA (delete del mes) y el error se propaga — no queda
un mes operable sin rastro de auditoría. La unicidad la garantiza el índice
`mes_unico` (real) + verificación previa (mongomock/UX).

**Arrastre del saldo (Kimi M-1, F-14/US-01):** `saldo_inicial_caja` NO es input
libre. Con mes anterior existente se DERIVA del consolidado bancario del
predecesor (Σ saldos_banco reportados; cuando exista el flujo de cierre, Sprint 4,
será el consolidado fijado al cerrar); digitar el saldo con predecesor → error
(el override es `ciclo:config` + step-up, futuro). Input obligatorio SOLO para el
primer mes de la historia. El ciclo es secuencial: no se saltan meses (el
arrastre solo tiene sentido contiguo)."""

from datetime import datetime
from decimal import Decimal

from pymongo.errors import DuplicateKeyError

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.core.money import money_str
from app.domain.mes_control import EstadoMes, MesControl, SaldoBanco


class MesYaAbiertoError(Exception):
    def __init__(self, mes: str) -> None:
        super().__init__(mes)
        self.mes = mes


class AperturaInvalidaError(Exception):
    """Apertura que viola el contrato de arrastre (M-1). Mensaje accionable."""

    def __init__(self, detalle: str) -> None:
        super().__init__(detalle)
        self.detalle = detalle


class SaldoInicialError(Exception):
    """FIX-F: error al editar el saldo inicial (mes 404 / no editable 409)."""

    def __init__(self, detalle: str, status: int) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


def _mes_siguiente(mes: str) -> str:
    d = datetime.strptime(mes, "%Y-%m-%d")
    return f"{d.year + 1}-01-01" if d.month == 12 else f"{d.year}-{d.month + 1:02d}-01"


async def _resolver_saldo_inicial(mes: str, saldo_input: Decimal | None) -> Decimal:
    """M-1: deriva el saldo del consolidado del predecesor; input solo sin historia."""
    ultimo = await MesControl.find_all().sort(-MesControl.mes).limit(1).to_list()
    if not ultimo:  # primer mes de la historia
        if saldo_input is None:
            raise AperturaInvalidaError(
                "saldo_inicial_caja es obligatorio para el primer mes de la historia"
            )
        return saldo_input

    anterior = ultimo[0]
    esperado = _mes_siguiente(anterior.mes)
    if mes != esperado:
        raise AperturaInvalidaError(
            f"el ciclo es secuencial: el siguiente mes a abrir es {esperado[:7]}"
        )
    if saldo_input is not None:
        raise AperturaInvalidaError(
            "saldo_inicial_caja se deriva del mes anterior (F-14); el override "
            "manual es ciclo:config + step-up MFA"
        )
    if not anterior.saldos_banco:
        raise AperturaInvalidaError(
            f"el mes {anterior.mes[:7]} no tiene consolidado bancario (saldos_banco "
            "vacío); no hay de dónde arrastrar el saldo (regla 7: no se adivina)"
        )
    return sum((s.saldo for s in anterior.saldos_banco), Decimal("0"))


async def abrir_mes(
    *,
    mes: str,
    saldo_inicial_caja: Decimal | None,
    saldos_banco: list[SaldoBanco],
    ingresos_esperados_semana: Decimal | None,
    usuario_id: str,
) -> MesControl:
    existente = await MesControl.find_one(MesControl.mes == mes)
    if existente is not None:
        raise MesYaAbiertoError(mes)

    saldo = await _resolver_saldo_inicial(mes, saldo_inicial_caja)

    mc = MesControl(
        mes=mes,
        saldo_inicial_caja=saldo,
        saldos_banco=saldos_banco,
        ingresos_esperados_semana=ingresos_esperados_semana,
    )
    try:
        await mc.insert()
    except DuplicateKeyError:  # carrera real: el índice único decide
        raise MesYaAbiertoError(mes) from None

    try:
        await emit_audit(
            AuditEvento.mes_creado,
            entidad="mes",
            entidad_id=str(mc.id),
            actor_id=usuario_id,
            metadata={
                "mes": mes,
                "saldo_inicial_caja": f"{saldo:.2f}",
                "saldo_derivado": saldo_inicial_caja is None,  # M-1: arrastre
                "bancos": [s.banco.value for s in saldos_banco],
            },
        )
    except Exception:
        # O1: sin auditoría no hay operación de ciclo → compensar y propagar.
        await mc.delete()
        raise
    return mc


async def editar_saldo_inicial(
    *, mes: str, saldo_inicial_caja: Decimal, motivo: str, usuario_id: str
) -> MesControl:
    """FIX-F: edita el saldo inicial de un mes EN EJECUCIÓN (ciclo:config + step-up en
    el router). Emite `saldo_inicial.editado` (anterior→nuevo + motivo); saga O1: si el
    emit falla, revierte el saldo. El histórico (mes cerrado) es inmutable (regla 4) →
    409. `saldo`/`motivo` llegan ya validados por el router (finito, no vacío)."""
    mc = await MesControl.find_one(MesControl.mes == mes)
    if mc is None:
        raise SaldoInicialError(f"el mes {mes[:7]} no existe", 404)
    if mc.estado is not EstadoMes.EN_EJECUCION:
        raise SaldoInicialError(
            f"solo se edita el saldo de un mes en ejecución (está en "
            f"'{mc.estado.value}'); el histórico es inmutable (regla 4)",
            409,
        )
    anterior = mc.saldo_inicial_caja
    mc.saldo_inicial_caja = saldo_inicial_caja
    await mc.save()
    try:
        await emit_audit(
            AuditEvento.saldo_inicial_editado,
            entidad="mes",
            entidad_id=str(mc.id),
            actor_id=usuario_id,
            metadata={
                "mes": mes[:7],
                "anterior": money_str(anterior),
                "nuevo": money_str(saldo_inicial_caja),
                "motivo": motivo,
            },
        )
    except Exception:
        # O1 (mismo criterio que la apertura): sin rastro no hay edición → revertir.
        mc.saldo_inicial_caja = anterior
        await mc.save()
        raise
    return mc
