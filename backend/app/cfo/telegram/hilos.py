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

_MAX_TURNOS = 40  # se persiste hasta esto; se re-alimenta solo la ventana


def historial_para_loop(hilo: HiloCFO | None, ventana: int) -> list[dict]:
    if hilo is None or not hilo.turnos:
        return []
    ult = hilo.turnos[-ventana:]
    if ult and ult[0]["rol"] == "assistant":
        ult = ult[1:]  # ventana desalineada: no empezar el mensaje en 'assistant'
    return [{"role": t["rol"], "content": t["contenido"]} for t in ult]


def es_reintento(hilo: HiloCFO | None, update_id: int) -> bool:
    return hilo is not None and hilo.ultimo_update_id == update_id


async def registrar_turno(
    user_id: str, pregunta: str, texto_crudo: str, update_id: int, envio: str
) -> None:
    hilo = await repositorio.obtener_hilo(user_id)
    turnos = (hilo.turnos if hilo else []) + [
        {"rol": "user", "contenido": pregunta},
        {"rol": "assistant", "contenido": texto_crudo},
    ]
    turnos = turnos[-_MAX_TURNOS:]
    nuevo = HiloCFO(
        user_id=user_id,
        turnos=turnos,
        ultimo_update_id=update_id,
        ultimo_envio=envio,
        actualizado_at=now_utc(),
    )
    await repositorio.guardar_hilo(nuevo)
