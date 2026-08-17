# backend/tests/cfo/agente/fakes.py
"""Cliente LLM falso para tests del loop/servicio (sin API real)."""

from app.cfo.agente.cliente import RespuestaLLM


class ClienteFake:
    def __init__(self, guiones: list[RespuestaLLM]):
        self._guiones = list(guiones)
        self.llamadas: list[dict] = []

    async def crear(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> RespuestaLLM:
        self.llamadas.append({"system": system, "messages": messages, "tools": tools})
        if not self._guiones:
            raise AssertionError("ClienteFake sin más guiones")
        return self._guiones.pop(0)
