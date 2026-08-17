# backend/tests/cfo/agente/test_loop.py
from decimal import Decimal

import pytest
from app.cfo.agente import loop as loop_mod
from app.cfo.agente.cliente import BloqueTexto, BloqueToolUse, RespuestaLLM
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from tests.cfo.agente.fakes import ClienteFake


def _res():
    return ResultadoCFO(
        concepto="caja_hoy",
        valor=Decimal("704722003"),
        unidad="COP",
        disponible=True,
        evidencia=Evidencia(fuente="f", fecha_corte="2026-08-11", ref="2026-08"),
    )


@pytest.mark.asyncio
async def test_conversar_tool_luego_texto(monkeypatch):
    async def fake_tool(nombre):
        return _res()

    monkeypatch.setattr(loop_mod, "ejecutar_tool", fake_tool)
    guiones = [
        RespuestaLLM(
            "tool_use",
            [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})],
            5,
            3,
        ),
        RespuestaLLM("end_turn", [BloqueTexto(texto="La caja es $704.722.003.")], 4, 8),
    ]
    r = await loop_mod.conversar(
        ClienteFake(guiones), [{"role": "user", "content": "¿caja?"}], max_iter=3
    )
    assert r.texto == "La caja es $704.722.003."
    assert len(r.resultados) == 1 and r.resultados[0].valor == Decimal("704722003")
    assert r.tokens_in == 9 and r.tokens_out == 11 and r.iteraciones == 2


@pytest.mark.asyncio
async def test_conversar_agota_iteraciones(monkeypatch):
    async def fake_tool(nombre):
        return _res()

    monkeypatch.setattr(loop_mod, "ejecutar_tool", fake_tool)
    # siempre pide tool → nunca da texto
    guiones = [
        RespuestaLLM(
            "tool_use",
            [BloqueToolUse(id=f"t{i}", nombre="caja_disponible_hoy", input={})],
            1,
            1,
        )
        for i in range(5)
    ]
    r = await loop_mod.conversar(
        ClienteFake(guiones), [{"role": "user", "content": "x"}], max_iter=3
    )
    assert r.texto is None
    assert r.iteraciones == 3
