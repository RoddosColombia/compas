# backend/tests/cfo/agente/test_loop.py
import json
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


def _res_named(concepto: str, valor: Decimal) -> ResultadoCFO:
    return ResultadoCFO(
        concepto=concepto,
        valor=valor,
        unidad="COP",
        disponible=True,
        evidencia=Evidencia(fuente="f", fecha_corte="2026-08-11", ref="2026-08"),
    )


@pytest.mark.asyncio
async def test_conversar_tool_luego_texto(monkeypatch):
    async def fake_tool(nombre, entrada=None):
        return [_res()]

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
    async def fake_tool(nombre, entrada=None):
        return [_res()]

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


@pytest.mark.asyncio
async def test_conversar_pasa_input_y_extiende_multiples_resultados(monkeypatch):
    # inc4 T4: una sola tool puede devolver VARIOS ResultadoCFO nombrados (p. ej. un
    # escenario que produce piso_con + piso_sin). El loop debe (a) reenviar u.input
    # como `entrada`, (b) extender TODOS a res.resultados (no solo el primero), y
    # (c) realimentar al modelo un ARRAY json de resultado_a_dict, uno por concepto.
    llamadas: list[tuple[str, dict | None]] = []

    async def fake_tool(nombre, entrada=None):
        llamadas.append((nombre, entrada))
        return [
            _res_named("piso_con", Decimal("100")),
            _res_named("piso_sin", Decimal("200")),
        ]

    monkeypatch.setattr(loop_mod, "ejecutar_tool", fake_tool)
    entrada_escenario = {
        "naturaleza": "gasto",
        "monto": "20000000",
        "mes_inicio": "2026-09",
    }
    guiones = [
        RespuestaLLM(
            "tool_use",
            [
                BloqueToolUse(
                    id="t1", nombre="impacto_escenario", input=entrada_escenario
                )
            ],
            5,
            3,
        ),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Listo.")], 4, 8),
    ]
    cliente = ClienteFake(guiones)
    r = await loop_mod.conversar(
        cliente, [{"role": "user", "content": "¿bodega?"}], max_iter=3
    )

    # (a) el loop pasó u.input tal cual como `entrada`
    assert llamadas == [("impacto_escenario", entrada_escenario)]
    # (b) resultados.extend: AMBOS conceptos quedan citables, no solo uno
    assert [x.concepto for x in r.resultados] == ["piso_con", "piso_sin"]

    # (c) el tool_result realimentado es un array JSON de resultado_a_dict (uno por
    # ResultadoCFO), sin `valor` ni `detalle` (el modelo nunca ve la cifra cruda)
    mensaje_tool = cliente.llamadas[1]["messages"][-1]
    bloque = mensaje_tool["content"][0]
    assert bloque["type"] == "tool_result" and bloque["tool_use_id"] == "t1"
    payload = json.loads(bloque["content"])
    assert isinstance(payload, list)
    assert [d["concepto"] for d in payload] == ["piso_con", "piso_sin"]
    assert all("valor" not in d and "detalle" not in d for d in payload)
