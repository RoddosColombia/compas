# backend/app/cfo/telegram/hilos.py
"""FABS · lógica de hilos. El historial que se re-alimenta al modelo son los turnos
CRUDOS (con [[tokens]]), NUNCA valores — así la garantía de Pieza A se mantiene entre
turnos. Ventana acotada (costo); el hilo persiste (sin TTL naïve).

Los turnos se guardan en pares [user, assistant] (uno por cada registrar_turno). La
API de Anthropic exige que la lista de mensajes empiece en 'user' y alterne; una
ventana desalineada con esos pares (p. ej. impar) puede cortar a la mitad y dejar un
'assistant' al frente — historial_para_loop lo descarta para no violar ese contrato
(CARRY de la revisión de Task 1 / B1)."""

from app.cfo.telegram import repositorio
from app.cfo.telegram.modelos import HiloCFO
from app.core.time import now_utc

_MAX_TURNOS = 200  # se persiste hasta esto; se re-alimenta solo la ventana


def historial_para_loop(hilo: HiloCFO | None, ventana: int) -> list[dict]:
    if hilo is None or not hilo.turnos:
        return []
    ult = hilo.turnos[-ventana:] if ventana > 0 else []
    if ult and ult[0]["rol"] == "assistant":
        ult = ult[1:]  # ventana desalineada: no empezar el mensaje en 'assistant'
    return [{"role": t["rol"], "content": t["contenido"]} for t in ult]


def es_reintento(hilo: HiloCFO | None, update_id: int) -> bool:
    return hilo is not None and hilo.ultimo_update_id == update_id


async def _append_turnos(
    user_id: str,
    pregunta: str,
    crudo: str,
    mostrado: str,
    canal: str,
    *,
    update_id: int | None = None,
    set_dedup: bool = False,
) -> None:
    """Arma los dos turnos (user + assistant) con display (`mostrado`/`canal`/`ts`) y
    persiste, recortando a _MAX_TURNOS. `set_dedup=True` (Telegram) actualiza el
    estado de dedup (`ultimo_update_id`/`ultimo_envio`); `set_dedup=False` (web) lo
    PRESERVA."""
    hilo = await repositorio.obtener_hilo(user_id)
    ts = now_utc().isoformat()
    turnos = (hilo.turnos if hilo else []) + [
        {
            "rol": "user",
            "contenido": pregunta,
            "mostrado": pregunta,
            "canal": canal,
            "ts": ts,
        },
        {
            "rol": "assistant",
            "contenido": crudo,
            "mostrado": mostrado,
            "canal": canal,
            "ts": ts,
        },
    ]
    turnos = turnos[-_MAX_TURNOS:]
    nuevo = HiloCFO(
        user_id=user_id,
        turnos=turnos,
        ultimo_update_id=update_id
        if set_dedup
        else (hilo.ultimo_update_id if hilo else None),
        ultimo_envio=mostrado if set_dedup else (hilo.ultimo_envio if hilo else None),
        actualizado_at=now_utc(),
    )
    await repositorio.guardar_hilo(nuevo)


async def registrar_turno(
    user_id: str, pregunta: str, texto_crudo: str, update_id: int, envio: str
) -> None:
    await _append_turnos(
        user_id,
        pregunta,
        texto_crudo,
        envio,
        "telegram",
        update_id=update_id,
        set_dedup=True,
    )


async def registrar_turno_web(
    user_id: str, pregunta: str, texto_crudo: str, mostrado: str
) -> None:
    await _append_turnos(
        user_id, pregunta, texto_crudo, mostrado, "web", set_dedup=False
    )


_LEGACY_ASSISTANT = "(respuesta anterior)"


def historial_para_display(hilo: HiloCFO | None) -> list[dict]:
    """Scrollback renderizado: user → su texto; assistant → `mostrado` (ya sustituido).
    Un assistant legacy sin `mostrado` se enmascara — NUNCA se expone el crudo con
    tokens."""
    if hilo is None or not hilo.turnos:
        return []
    out: list[dict] = []
    for t in hilo.turnos:
        rol = t.get("rol", "assistant")
        if rol == "user":
            texto = t.get("mostrado") or t.get("contenido") or ""
        else:
            texto = t.get("mostrado") or _LEGACY_ASSISTANT
        out.append(
            {
                "rol": rol,
                "texto": texto,
                "canal": t.get("canal", "desconocido"),
                "ts": t.get("ts"),
            }
        )
    return out


async def registrar_dedup(user_id: str, update_id: int, envio: str) -> None:
    """Persiste SOLO los campos de dedup (último update_id + último envío) sin tocar
    los turnos conversacionales. Para comandos que NO pasan por el LLM (p. ej.
    'publicar'): así un reintento de Telegram reenvía la confirmación previa en vez
    de re-ejecutar el efecto (re-difundir), y sin inyectar el comando en el historial
    que se re-alimenta al modelo (que mantiene solo pares user/assistant CRUDOS)."""
    hilo = await repositorio.obtener_hilo(user_id)
    nuevo = HiloCFO(
        user_id=user_id,
        turnos=hilo.turnos if hilo else [],
        ultimo_update_id=update_id,
        ultimo_envio=envio,
        actualizado_at=now_utc(),
    )
    await repositorio.guardar_hilo(nuevo)
