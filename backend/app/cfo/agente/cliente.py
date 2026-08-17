# backend/app/cfo/agente/cliente.py
"""FABS · wrapper del SDK Anthropic. Import PEREZOSO (la dep solo se toca al invocar de
verdad; los tests usan un cliente falso). Normaliza la respuesta del SDK a RespuestaLLM
para desacoplar el loop del formato del SDK. Sin API key ⇒ crear_cliente() = None."""

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol

from app.cfo import config


@dataclass(frozen=True)
class BloqueTexto:
    texto: str


@dataclass(frozen=True)
class BloqueToolUse:
    id: str
    nombre: str
    input: dict


@dataclass(frozen=True)
class RespuestaLLM:
    stop_reason: str
    bloques: list  # list[BloqueTexto | BloqueToolUse]
    tokens_in: int
    tokens_out: int


class ClienteLLM(Protocol):
    def crear(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> Awaitable[RespuestaLLM]: ...


def contenido_asistente(bloques: list) -> list[dict]:
    out: list[dict] = []
    for b in bloques:
        if isinstance(b, BloqueTexto):
            out.append({"type": "text", "text": b.texto})
        elif isinstance(b, BloqueToolUse):
            out.append(
                {"type": "tool_use", "id": b.id, "name": b.nombre, "input": b.input}
            )
    return out


class ClienteAnthropic:
    def __init__(self, api_key: str, modelo: str, max_tokens: int, timeout_s: float):
        from anthropic import AsyncAnthropic  # import perezoso

        self._client = AsyncAnthropic(api_key=api_key, timeout=timeout_s)
        self._modelo = modelo
        self._max_tokens = max_tokens

    async def crear(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> RespuestaLLM:
        resp = await self._client.messages.create(
            model=self._modelo,
            max_tokens=self._max_tokens,
            temperature=0.1,
            system=system,
            messages=messages,
            tools=tools,
        )
        bloques: list = []
        for b in resp.content:
            if b.type == "text":
                bloques.append(BloqueTexto(texto=b.text))
            elif b.type == "tool_use":
                bloques.append(
                    BloqueToolUse(id=b.id, nombre=b.name, input=dict(b.input))
                )
        return RespuestaLLM(
            stop_reason=resp.stop_reason,
            bloques=bloques,
            tokens_in=resp.usage.input_tokens,
            tokens_out=resp.usage.output_tokens,
        )


def crear_cliente() -> ClienteLLM | None:
    key = config.cfo_api_key()
    if key is None:
        return None
    return ClienteAnthropic(
        api_key=key,
        modelo=config.cfo_model(),
        max_tokens=config.cfo_max_tokens(),
        timeout_s=config.cfo_timeout_s(),
    )
