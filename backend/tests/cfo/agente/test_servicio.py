# backend/tests/cfo/agente/test_servicio.py
from decimal import Decimal

import pytest
from app.cfo.agente import servicio as srv
from app.cfo.agente.cliente import BloqueTexto, BloqueToolUse, RespuestaLLM
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from tests.cfo.agente.fakes import ClienteFake


@pytest.fixture(autouse=True)
def _audit(monkeypatch):
    eventos = []

    async def fake_emit(evento, entidad, entidad_id=None, actor_id=None, metadata=None):
        eventos.append((str(evento), metadata))

    monkeypatch.setattr(srv, "emit_audit", fake_emit)
    return eventos


def _res():
    return ResultadoCFO(
        concepto="caja_hoy",
        valor=Decimal("704722003"),
        unidad="COP",
        disponible=True,
        evidencia=Evidencia(fuente="f", fecha_corte="2026-08-11", ref="2026-08"),
    )


@pytest.mark.asyncio
async def test_sin_key_abstiene(monkeypatch, _audit):
    monkeypatch.setattr(srv, "crear_cliente", lambda: None)
    r = await srv.consultar("¿caja?", actor_id="u1")
    assert r.abstuvo is True and r.motivo == "sin_api_key"
    assert [e[0] for e in _audit] == ["cfo.consulta", "cfo.respuesta"]


@pytest.mark.asyncio
async def test_camino_feliz(monkeypatch, _audit):
    async def fake_tool(nombre):
        return _res()

    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", fake_tool)
    # inc3 Pieza A: el modelo cita el TOKEN del concepto, nunca escribe la cifra cruda.
    guiones = [
        RespuestaLLM(
            "tool_use",
            [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})],
            5,
            3,
        ),
        RespuestaLLM(
            "end_turn", [BloqueTexto(texto="Tu caja hoy es [[caja_hoy]].")], 4, 8
        ),
    ]
    r = await srv.consultar("¿caja?", actor_id="u1", cliente=ClienteFake(guiones))
    assert r.abstuvo is False
    assert "[[caja_hoy]]" not in r.texto
    assert "$704.722.003 (al 2026-08-11)" in r.texto
    assert r.cifras[0].valor == "704722003"
    assert "caja_hoy" in r.conceptos_usados
    resp_meta = [m for e, m in _audit if e == "cfo.respuesta"][0]
    assert resp_meta["abstuvo"] is False


@pytest.mark.asyncio
async def test_alucinacion_reintento_falla_abstiene(monkeypatch, _audit):
    async def fake_tool(nombre):
        return _res()

    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", fake_tool)
    # 1ra conversación: tool + texto con cifra inventada. Reintento: sigue inventando.
    guiones = [
        RespuestaLLM(
            "tool_use",
            [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})],
            1,
            1,
        ),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Tienes $999.999.999.")], 1, 1),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Bueno, $888.888.888.")], 1, 1),
    ]
    fake = ClienteFake(guiones)
    r = await srv.consultar("¿caja?", actor_id="u1", cliente=fake)
    assert r.abstuvo is True and r.motivo == "verificacion"
    assert fake._guiones == []  # tope D-3: exactamente 1 reintento, jamás loop


@pytest.mark.asyncio
async def test_publica_con_tokens_sustituidos(monkeypatch, _audit):
    async def fake_tool(nombre):
        return _res()

    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", fake_tool)
    guiones = [
        RespuestaLLM(
            "tool_use",
            [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})],
            1,
            1,
        ),
        RespuestaLLM(
            "end_turn", [BloqueTexto(texto="Tu caja hoy es [[caja_hoy]].")], 1, 1
        ),
    ]
    r = await srv.consultar("¿caja?", actor_id="u1", cliente=ClienteFake(guiones))
    assert r.abstuvo is False
    assert "[[caja_hoy]]" not in r.texto
    assert "$704.722.003 (al 2026-08-11)" in r.texto


@pytest.mark.asyncio
async def test_reincidencia_en_cifra_cruda_abstiene_un_solo_reintento(
    monkeypatch, _audit
):
    async def fake_tool(nombre):
        return _res()

    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", fake_tool)
    # 1ª: tool + cifra cruda (aunque numéricamente correcta); reintento: vuelve a
    # escribir cruda en vez de citar el token → abstención, jamás loop (D-3).
    guiones = [
        RespuestaLLM(
            "tool_use",
            [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})],
            1,
            1,
        ),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Tu caja es $704.722.003.")], 1, 1),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Perdón: $704.722.003.")], 1, 1),
    ]
    fake = ClienteFake(guiones)
    r = await srv.consultar("¿caja?", actor_id="u1", cliente=fake)
    assert r.abstuvo is True and r.motivo == "verificacion"
    # consumió exactamente 3 respuestas (1ª: tool+texto; reintento: 1 texto), no más
    assert fake._guiones == []


@pytest.mark.asyncio
async def test_error_interno_no_revienta_y_audita(monkeypatch, _audit):
    # crear_cliente revienta (fallo no-LLM) -> abstención graciosa, no excepción
    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(srv, "crear_cliente", boom)
    r = await srv.consultar("¿caja?", actor_id="u1")  # NO debe levantar
    assert r.abstuvo is True and r.motivo == "error"
    assert [e[0] for e in _audit] == ["cfo.consulta", "cfo.respuesta"]
