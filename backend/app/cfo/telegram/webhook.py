# backend/app/cfo/telegram/webhook.py
"""FABS · lógica del webhook (pura, testeable con fakes). Reactivo: responde a quien
escribe. No-vinculado ⇒ rehúsa sin llamar al servicio. Dedup por update_id (reenvía la
respuesta previa). El hilo guarda el texto CRUDO (tokens), lo que ve el usuario es el
sustituido.

Endpoint PÚBLICO (Telegram lo golpea sin que controlemos la forma del payload):
`_extraer` parsea con `.get(...)` y devuelve None ante CUALQUIER forma inesperada
(sin 'message', sin texto, sin 'update_id'/'from'/'chat') — `procesar_update` ignora
esos updates en silencio. A propósito NO hay un try/except envolvente en el resto de
la función: eso ocultaría bugs reales de este módulo y le quitaría a Telegram la señal
de reintento (un webhook que revienta con 500 hace que Telegram reintente; uno que
traga el error y devuelve 200 vacío, no). Lo que sí es seguro sin envoltura adicional:
`servicio.consultar` nunca lanza (tiene su propio backstop) y `cliente_telegram.enviar`
ya se traga sus propios errores de red."""

import logging

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cfo import config
from app.cfo.agente import servicio
from app.cfo.agente.cliente import crear_cliente as crear_cliente_llm
from app.cfo.telegram import hilos, repositorio, vinculos
from app.cfo.telegram.cliente import ClienteTelegramProto
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
    except Exception:  # noqa: BLE001 — no bloquear la difusión por fallo de auditoría
        logger.exception("fallo al auditar %s", evento)


async def _publicar_paquete(
    chat_id: int, cliente_telegram: ClienteTelegramProto
) -> str:
    """Difunde el último borrador a todo el comité (todos los vínculos) y lo marca
    `publicado` DESPUÉS de difundir. `cliente_telegram.enviar` traga sus propios
    errores de red, así que el loop de difusión no revienta a medio camino.
    Devuelve el texto de confirmación enviado al revisor (para dedup del comando)."""
    borradores = await (
        AvisoVigilante.find(
            AvisoVigilante.tipo == "paquete_lunes",
            AvisoVigilante.estado == "borrador",
        )
        .sort(-AvisoVigilante.generado_at)
        .limit(1)
        .to_list()
    )
    pq = borradores[0] if borradores else None
    if pq is None:
        msg = "No hay un paquete pendiente para publicar."
        await cliente_telegram.enviar(chat_id, msg)
        return msg

    vinculos_all = await repositorio.listar_vinculos()
    for v in vinculos_all:
        await cliente_telegram.enviar(v.telegram_id, pq.texto)

    pq.estado = "publicado"
    pq.publicado_at = now_bogota()
    await pq.save()

    await _audit_soft(
        AuditEvento.vigilante_paquete_publicado,
        pq.periodo,
        {"periodo": pq.periodo, "n_destinatarios": len(vinculos_all)},
    )

    msg = f"✅ Paquete publicado al comité ({len(vinculos_all)} destinatarios)."
    await cliente_telegram.enviar(chat_id, msg)
    return msg


def _formatear(resp) -> str:
    if resp.abstuvo or not resp.cifras:
        return resp.texto
    lineas = "\n".join(
        f"• {c.valor} {c.unidad} — {c.evidencia.fuente} ({c.evidencia.ref})"
        for c in resp.cifras
    )
    return f"{resp.texto}\n\nCifras (con su fuente):\n{lineas}"


def _extraer(update: dict) -> tuple[int, int, int, str] | None:
    """(update_id, telegram_id, chat_id, texto) o None si el update no es un
    mensaje de texto de un usuario, o le falta algún campo requerido. Nunca lanza:
    cualquier forma inesperada del payload público se traduce en None."""
    msg = update.get("message")
    if not msg or not msg.get("text"):
        return None
    update_id = update.get("update_id")
    telegram_id = (msg.get("from") or {}).get("id")
    chat_id = (msg.get("chat") or {}).get("id")
    if update_id is None or telegram_id is None or chat_id is None:
        return None
    return update_id, telegram_id, chat_id, msg["text"]


async def procesar_update(
    update: dict, *, cliente_telegram: ClienteTelegramProto, cliente_llm=None
) -> None:
    extraido = _extraer(update)
    if extraido is None:
        logger.debug("update de Telegram ignorado (no es mensaje de texto válido)")
        return
    update_id, telegram_id, chat_id, texto = extraido

    user_id = await vinculos.resolver(telegram_id)
    if user_id is None:
        await cliente_telegram.enviar(
            chat_id,
            f"No estás autorizado para usar FABS. Tu ID de Telegram es "
            f"{telegram_id} — pídele al administrador que te vincule.",
        )
        return

    hilo = await repositorio.obtener_hilo(user_id)
    # Dedup por update_id ANTES de bifurcar — cubre por igual el Q&A y el comando
    # 'publicar' (que también difunde un efecto de una sola vez a todo el comité).
    # LIMITACIÓN ACEPTADA (piloto, flag off): es check-then-set (no hay claim atómico).
    # Si Telegram RE-entrega el mismo update_id mientras la 1ª petición sigue en vuelo
    # (LLM/difusión más lentos que el timeout de entrega de Telegram), ambas pasan
    # es_reintento==False → doble efecto. NO afecta la garantía anti-alucinación.
    # Endurecimiento futuro: reclamar el update_id de forma atómica (update condicional)
    # ANTES de ejecutar el efecto.
    if hilos.es_reintento(hilo, update_id):
        # reintento de Telegram: reenvía la respuesta previa (B-1/B-2, no silencioso)
        if hilo.ultimo_envio:
            await cliente_telegram.enviar(chat_id, hilo.ultimo_envio)
        return

    es_comando_publicar = (
        texto.strip().lower() == "publicar"
        and telegram_id == config.vigilante_revisor_telegram_id()
    )
    if es_comando_publicar:
        # 'publicar' NO llama al LLM: registrar SOLO el dedup (sin tocar los turnos que
        # se re-alimentan al modelo) para que un reintento reenvíe la confirmación en
        # vez de re-difundir.
        envio = await _publicar_paquete(chat_id, cliente_telegram)
        await hilos.registrar_dedup(user_id, update_id, envio)
        return

    historial = hilos.historial_para_loop(hilo, config.cfo_hilo_ventana())
    resp = await servicio.consultar(
        texto,
        actor_id=user_id,
        cliente=cliente_llm or crear_cliente_llm(),
        historial=historial,
    )
    envio = _formatear(resp)
    await hilos.registrar_turno(user_id, texto, resp.texto_crudo, update_id, envio)
    await cliente_telegram.enviar(chat_id, envio)
