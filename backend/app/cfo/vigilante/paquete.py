# backend/app/cfo/vigilante/paquete.py
"""FABS · vigilante — genera el paquete semanal y lo entrega al revisor como borrador.
Reusa `servicio.consultar` (verifica + sustituye + audita); solo se guarda/difunde el
texto YA verificado. Fail-soft: un job proactivo no revienta el worker — el auditado
de este módulo (`vigilante.paquete.generado`) NUNCA propaga (mismo patrón que
`agente.servicio._audit_soft`; `emit_audit` puede levantar `RuntimeError` si la
conexión de auditoría no está configurada, y este es un job, no un request)."""

import logging

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cfo import config
from app.cfo.agente.cliente import crear_cliente
from app.cfo.agente.servicio import consultar
from app.cfo.telegram.cliente import crear_cliente_telegram
from app.cfo.vigilante.modelos import AvisoVigilante
from app.core.time import now_bogota

logger = logging.getLogger(__name__)

_PROMPT_PAQUETE = (
    "Compón el paquete semanal del lunes para el CEO de RODDOS: la caja disponible "
    "hoy, el rumbo de la caja hacia el umbral, el IVA del cuatrimestre que viene, y "
    "cómo viene el gasto vs el mes pasado. Cita cada cifra con su token; si un dato "
    "no está disponible, omítelo con honestidad. Sé breve y claro."
)


async def _audit_soft(evento, entidad_id: str, metadata: dict) -> None:
    try:
        await emit_audit(
            evento,
            entidad="vigilante",
            entidad_id=entidad_id,
            actor_id="vigilante",
            metadata=metadata,
        )
    except Exception:  # noqa: BLE001 — job proactivo: no bloquear por fallo de auditoría
        logger.exception("fallo al auditar %s", evento)


async def generar_y_entregar_paquete() -> AvisoVigilante | None:
    periodo = now_bogota().date().isoformat()
    if await AvisoVigilante.find_one(
        AvisoVigilante.tipo == "paquete_lunes", AvisoVigilante.periodo == periodo
    ):
        logger.info("paquete del %s ya existe; no se regenera", periodo)
        return None

    resp = await consultar(
        _PROMPT_PAQUETE, actor_id="vigilante", cliente=crear_cliente()
    )
    if resp.abstuvo and not resp.cifras:
        logger.info("consultar abstuvo sin cifras; no se guarda borrador vacío")
        return None

    pq = AvisoVigilante(
        tipo="paquete_lunes",
        periodo=periodo,
        texto=resp.texto,
        texto_crudo=resp.texto_crudo,
        estado="borrador",
        generado_at=now_bogota(),
        conceptos_usados=list(resp.conceptos_usados),
    )
    await pq.insert()

    await _audit_soft(
        AuditEvento.vigilante_paquete_generado,
        periodo,
        {
            "periodo": periodo,
            "tipo": "paquete_lunes",
            "abstuvo": resp.abstuvo,
            "conceptos_usados": list(resp.conceptos_usados),
        },
    )

    revisor = config.vigilante_revisor_telegram_id()
    if revisor is None:
        logger.warning(
            "VIGILANTE_REVISOR_TELEGRAM_ID sin configurar; borrador no enviado"
        )
        return pq

    cliente_tg = crear_cliente_telegram()
    if cliente_tg is not None:
        await cliente_tg.enviar(
            revisor,
            "📋 Borrador del paquete del lunes\n\n"
            + resp.texto
            + "\n\nRespondé 'publicar' para difundirlo al comité.",
        )
    return pq
