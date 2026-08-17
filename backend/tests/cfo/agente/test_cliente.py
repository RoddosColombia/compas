# backend/tests/cfo/agente/test_cliente.py
from types import SimpleNamespace

import pytest
from app.cfo.agente import cliente as cli


def test_crear_cliente_none_sin_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cli.crear_cliente() is None


def test_crear_cliente_instancia_con_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    c = cli.crear_cliente()
    assert isinstance(c, cli.ClienteAnthropic)


def test_contenido_asistente_reconstruye_wire():
    bloques = [
        cli.BloqueTexto(texto="hola"),
        cli.BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={}),
    ]
    wire = cli.contenido_asistente(bloques)
    assert wire[0] == {"type": "text", "text": "hola"}
    assert wire[1] == {
        "type": "tool_use",
        "id": "t1",
        "name": "caja_disponible_hoy",
        "input": {},
    }


@pytest.mark.asyncio
async def test_crear_mapea_respuesta_del_sdk(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    c = cli.crear_cliente()

    async def fake_create(**kwargs):
        return SimpleNamespace(
            stop_reason="tool_use",
            content=[
                SimpleNamespace(type="text", text="hola"),
                SimpleNamespace(
                    type="tool_use", id="t1", name="caja_disponible_hoy", input={"x": 1}
                ),
            ],
            usage=SimpleNamespace(input_tokens=11, output_tokens=22),
        )

    c._client = SimpleNamespace(messages=SimpleNamespace(create=fake_create))
    r = await c.crear(system="s", messages=[{"role": "user", "content": "q"}], tools=[])
    assert r.stop_reason == "tool_use"
    assert r.tokens_in == 11 and r.tokens_out == 22
    assert isinstance(r.bloques[0], cli.BloqueTexto) and r.bloques[0].texto == "hola"
    assert isinstance(r.bloques[1], cli.BloqueToolUse)
    assert r.bloques[1].nombre == "caja_disponible_hoy"
    assert r.bloques[1].input == {"x": 1}
