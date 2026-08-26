# backend/app/cfo/agente/loop.py
"""FABS · loop acotado modelo↔tool (D1). Corre ≤ max_iter rondas: si el modelo pide
tools, se ejecutan (solo lectura) y se realimentan; si da texto final, termina. No
verifica (eso lo hace el servicio). Determinista: temp 0.1 la fija el cliente."""

import json
from dataclasses import dataclass

from app.cfo.agente.cliente import (
    BloqueTexto,
    BloqueToolUse,
    ClienteLLM,
    contenido_asistente,
)
from app.cfo.agente.prompt import SYSTEM_PROMPT
from app.cfo.agente.tools import TOOLS_SCHEMA, ejecutar_tool, resultado_a_dict
from app.cfo.calc.evidencia import ResultadoCFO


@dataclass
class ResultadoLoop:
    texto: str | None
    resultados: list[ResultadoCFO]
    tokens_in: int
    tokens_out: int
    iteraciones: int


def _texto_de(bloques: list) -> str | None:
    partes = [b.texto for b in bloques if isinstance(b, BloqueTexto)]
    return "\n".join(partes).strip() if partes else None


async def conversar(
    cliente: ClienteLLM,
    mensajes: list[dict],
    *,
    max_iter: int,
    system: str = SYSTEM_PROMPT,
) -> ResultadoLoop:
    mensajes = list(mensajes)
    resultados: list[ResultadoCFO] = []
    tin = tout = 0
    for i in range(1, max_iter + 1):
        resp = await cliente.crear(system=system, messages=mensajes, tools=TOOLS_SCHEMA)
        tin += resp.tokens_in
        tout += resp.tokens_out
        usos = [b for b in resp.bloques if isinstance(b, BloqueToolUse)]
        if not usos:
            return ResultadoLoop(_texto_de(resp.bloques), resultados, tin, tout, i)
        # ejecutar tools y realimentar
        mensajes.append(
            {"role": "assistant", "content": contenido_asistente(resp.bloques)}
        )
        contenido_tool: list[dict] = []
        for u in usos:
            rs = await ejecutar_tool(u.nombre, u.input)
            resultados.extend(rs)
            contenido_tool.append(
                {
                    "type": "tool_result",
                    "tool_use_id": u.id,
                    "content": json.dumps(
                        [resultado_a_dict(x) for x in rs], ensure_ascii=False
                    ),
                }
            )
        mensajes.append({"role": "user", "content": contenido_tool})
    return ResultadoLoop(None, resultados, tin, tout, max_iter)
