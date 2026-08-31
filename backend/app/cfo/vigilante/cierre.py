# backend/app/cfo/vigilante/cierre.py
"""FABS · vigilante — comenta el cierre de un mes. Job detector: mira el ÚLTIMO mes
CERRADO y, si no tiene comentario, FABS lo narra (reusa `consultar`, mismo contrato
anti-alucinación que el paquete del lunes). Idempotente por mes; nunca hace backfill
(solo el último cerrado). Fail-soft: un job proactivo no revienta el worker."""

import logging

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cfo import config
from app.cfo.agente.cliente import crear_cliente
from app.cfo.agente.servicio import consultar
from app.cfo.telegram.cliente import crear_cliente_telegram
from app.cfo.vigilante.modelos import AvisoVigilante
from app.core.time import now_bogota
from app.domain.mes_control import EstadoMes, MesControl

logger = logging.getLogger(__name__)


def _prompt_cierre(periodo: str) -> str:
    return (
        f"Comentá el cierre del mes {periodo} de RODDOS, que acaba de cerrar. Cubrí, "
        "en orden y breve: (1) cómo cerró la caja del mes frente a cómo venía; (2) el "
        "real vs. el presupuesto — qué rubro se salió y por cuánto; (3) la composición "
        "del gasto del mes cerrado; (4) la tendencia del mes frente a los meses "
        "previos; (5) qué significa este cierre para el rumbo hacia el umbral de "
        "caja. Cita cada cifra con su token; si un dato no está disponible, omítelo "
        "con honestidad. Sé claro y conciso."
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
    except Exception:  # noqa: BLE001 — job proactivo: no bloquear por auditoría
        logger.exception("fallo al auditar %s", evento)


async def generar_y_entregar_cierre() -> AvisoVigilante | None:
    mc = await (
        MesControl.find(MesControl.estado == EstadoMes.CERRADO)
        .sort(-MesControl.mes)
        .first_or_none()
    )
    if mc is None:
        return None
    periodo = mc.mes[:7]
    if await AvisoVigilante.find_one(
        AvisoVigilante.tipo == "cierre_mensual", AvisoVigilante.periodo == periodo
    ):
        logger.info("cierre del mes %s ya comentado; no se regenera", periodo)
        return None

    resp = await consultar(
        _prompt_cierre(periodo), actor_id="vigilante", cliente=crear_cliente()
    )
    if resp.abstuvo and not resp.cifras:
        logger.info("consultar abstuvo sin cifras; no se guarda cierre vacío")
        return None

    aviso = AvisoVigilante(
        tipo="cierre_mensual",
        periodo=periodo,
        texto=resp.texto,
        texto_crudo=resp.texto_crudo,
        estado="borrador",
        generado_at=now_bogota(),
        conceptos_usados=list(resp.conceptos_usados),
    )
    await aviso.insert()

    await _audit_soft(
        AuditEvento.vigilante_cierre_generado,
        periodo,
        {
            "periodo": periodo,
            "abstuvo": resp.abstuvo,
            "conceptos_usados": list(resp.conceptos_usados),
        },
    )

    revisor = config.vigilante_revisor_telegram_id()
    if revisor is None:
        logger.warning(
            "VIGILANTE_REVISOR_TELEGRAM_ID sin configurar; cierre no enviado"
        )
        return aviso
    cliente_tg = crear_cliente_telegram()
    if cliente_tg is not None:
        await cliente_tg.enviar(
            revisor,
            f"📆 Borrador del cierre de {periodo}\n\n"
            + resp.texto
            + "\n\nRespondé 'publicar cierre' para difundirlo al comité.",
        )
    return aviso
