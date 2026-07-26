# backend/app/cartera_previa/service.py
"""Cartera previa (PR-1 "Fidelidad de caja") — carga idempotente de la serie semanal +
lectura como dicts para el motor.

`obtener_series()` devuelve dos mapas (semana → recaudo / semana → nº activos) que el
servicio de proyección pasa al motor (`recaudo_previo_por_semana` / `activos_previos_
por_semana`). `cargar_serie()` hace upsert por semana (idempotente: pisa, no duplica) y
emite `cartera_previa.cargada` (fail-closed). No toca el histórico: es dato de entrada
persistente, no un movimiento."""

from decimal import Decimal

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.domain.cartera_previa import CarteraPreviaRecaudo


async def obtener_series() -> tuple[dict[int, Decimal], dict[int, int]]:
    """(recaudo_por_semana, activos_por_semana) de toda la cartera previa cargada."""
    recaudo: dict[int, Decimal] = {}
    activos: dict[int, int] = {}
    async for fila in CarteraPreviaRecaudo.find_all():
        recaudo[fila.semana_global] = fila.recaudo
        activos[fila.semana_global] = fila.n_activos
    return recaudo, activos


async def cargar_serie(filas: list[dict], usuario_id: str) -> int:
    """Upsert idempotente de la serie (cada fila: semana_global · recaudo · n_activos).
    Devuelve el nº de semanas cargadas. Emite `cartera_previa.cargada`."""
    for f in filas:
        existente = await CarteraPreviaRecaudo.find_one(
            CarteraPreviaRecaudo.semana_global == f["semana_global"]
        )
        if existente is None:
            await CarteraPreviaRecaudo(**f).insert()
        else:
            existente.recaudo = f["recaudo"]
            existente.n_activos = f["n_activos"]
            await existente.save()
    await emit_audit(
        AuditEvento.cartera_previa_cargada,
        entidad="cartera_previa",
        entidad_id="serie",
        actor_id=usuario_id,
        metadata={"semanas": len(filas)},
    )
    return len(filas)
