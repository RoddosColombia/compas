# backend/app/ciclo/service.py
"""Apertura del mes (US-01).

MARCADO PARA AUDITORÍA KIMI (flujo del ciclo mensual).

Crea el MesControl (estado inicial `sugerido`) y emite `mes.creado` (regla 11).
Política O1 (audit fail-closed en operaciones de estado del ciclo): si el emit
falla, la apertura se COMPENSA (delete del mes) y el error se propaga — no queda
un mes operable sin rastro de auditoría. La unicidad la garantiza el índice
`mes_unico` (real) + verificación previa (mongomock/UX)."""

from decimal import Decimal

from pymongo.errors import DuplicateKeyError

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.domain.mes_control import MesControl, SaldoBanco


class MesYaAbiertoError(Exception):
    def __init__(self, mes: str) -> None:
        super().__init__(mes)
        self.mes = mes


async def abrir_mes(
    *,
    mes: str,
    saldo_inicial_caja: Decimal,
    saldos_banco: list[SaldoBanco],
    ingresos_esperados_semana: Decimal | None,
    usuario_id: str,
) -> MesControl:
    existente = await MesControl.find_one(MesControl.mes == mes)
    if existente is not None:
        raise MesYaAbiertoError(mes)

    mc = MesControl(
        mes=mes,
        saldo_inicial_caja=saldo_inicial_caja,
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
                "saldo_inicial_caja": f"{saldo_inicial_caja:.2f}",
                "bancos": [s.banco.value for s in saldos_banco],
            },
        )
    except Exception:
        # O1: sin auditoría no hay operación de ciclo → compensar y propagar.
        await mc.delete()
        raise
    return mc
