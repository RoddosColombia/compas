# backend/tests/cfo/agente/test_cliente.py
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
