# backend/app/cfo/vigilante/alerta.py
"""FABS · vigilante — genera la alerta de caja diaria y la entrega al revisor como
borrador. Espeja `paquete.py`: soft-audit, solo texto verificado. Garantiza ≤1 borrador
de alerta pendiente: supersede los de días previos y retira el de hoy si no dispara."""

import logging

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cfo import config
from app.cfo.telegram.cliente import crear_cliente_telegram
from app.cfo.vigilante.alerta_texto import construir_texto
from app.cfo.vigilante.disparadores import evaluar_disparadores
from app.cfo.vigilante.modelos import AvisoVigilante
from app.core.time import now_bogota

logger = logging.getLogger(__name__)


async def _audit_soft(evento, entidad_id: str, metadata: dict) -> None:
    try:
        await emit_audit(
            evento,
            entidad="vigilante",
            entidad_id=entidad_id,
            actor_id="vigilante",
            metadata=metadata,
        )
    except Exception:  # noqa: BLE001 — job proactivo: no reventar por auditoría
        logger.exception("fallo al auditar %s", evento)


async def _superar_borradores_alerta(excepto: str | None) -> None:
    """Marca 'superado' todo borrador de alerta pendiente cuyo periodo != `excepto`."""
    pendientes = await AvisoVigilante.find(
        AvisoVigilante.tipo == "alerta_caja", AvisoVigilante.estado == "borrador"
    ).to_list()
    for a in pendientes:
        if excepto is None or a.periodo != excepto:
            a.estado = "superado"
            await a.save()


async def generar_y_entregar_alerta() -> AvisoVigilante | None:
    hoy = now_bogota().date().isoformat()
    res = await evaluar_disparadores()
    if res is None:
        await _superar_borradores_alerta(excepto=None)  # retira todo pendiente
        logger.info("alerta de caja: ningún disparador; nada que enviar")
        return None

    await _superar_borradores_alerta(excepto=hoy)  # deja solo el de hoy
    crudo, texto = construir_texto(res)
    conceptos = [r.concepto for r in res.resultados]

    aviso = await AvisoVigilante.find_one(
        AvisoVigilante.tipo == "alerta_caja", AvisoVigilante.periodo == hoy
    )
    if aviso is None:
        aviso = AvisoVigilante(
            tipo="alerta_caja",
            periodo=hoy,
            texto=texto,
            texto_crudo=crudo,
            estado="borrador",
            generado_at=now_bogota(),
            conceptos_usados=conceptos,
        )
        await aviso.insert()
    else:  # refresca el de hoy (idempotencia diaria)
        aviso.texto, aviso.texto_crudo = texto, crudo
        aviso.estado, aviso.generado_at = "borrador", now_bogota()
        aviso.conceptos_usados = conceptos
        await aviso.save()

    await _audit_soft(
        AuditEvento.vigilante_alerta_generada,
        hoy,
        {
            "periodo": hoy,
            "disparadores": [d.tipo for d in res.disparos],
            "severidad": res.severidad,
            "conceptos_usados": conceptos,
        },
    )

    revisor = config.vigilante_revisor_telegram_id()
    if revisor is None:
        logger.warning(
            "VIGILANTE_REVISOR_TELEGRAM_ID sin configurar; alerta no enviada"
        )
        return aviso
    cliente_tg = crear_cliente_telegram()
    if cliente_tg is not None:
        await cliente_tg.enviar(
            revisor,
            aviso.texto + "\n\nRespondé 'publicar alerta' para difundirla al comité.",
        )
    return aviso
