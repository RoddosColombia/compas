# backend/tests/cfo/telegram/test_hilos.py
"""FABS · lógica de hilos: ventana del historial (re-alimentado CRUDO al modelo),
dedup por update_id y append/trim al persistir un turno."""

from datetime import UTC, datetime

import pytest
from app.cfo.telegram import hilos
from app.cfo.telegram.modelos import HiloCFO


def _hilo(turnos, uid=None):
    return HiloCFO(
        user_id="u1",
        turnos=turnos,
        ultimo_update_id=uid,
        ultimo_envio="prev",
        actualizado_at=datetime.now(UTC),
    )


def test_historial_toma_ultimos_n():
    turnos = [{"rol": "user", "contenido": f"q{i}"} for i in range(20)]
    msgs = hilos.historial_para_loop(_hilo(turnos), ventana=4)
    assert len(msgs) == 4
    assert msgs[-1] == {"role": "user", "content": "q19"}
    # 'rol' -> 'role', 'contenido' -> 'content'
    assert set(msgs[0].keys()) == {"role", "content"}


def test_historial_none_es_vacio():
    assert hilos.historial_para_loop(None, ventana=8) == []


def test_historial_ventana_cero_es_vacia():
    """ventana=0 debe devolver [] explícitamente. Bug: `lista[-0:]` en Python es
    `lista[0:]` (la lista COMPLETA, porque -0 == 0) — sin guarda, ventana=0
    devolvía todo el hilo en vez de una ventana acotada (vacía)."""
    turnos = [{"rol": "user", "contenido": f"q{i}"} for i in range(5)]
    assert hilos.historial_para_loop(_hilo(turnos), ventana=0) == []


def test_historial_ventana_negativa_es_vacia():
    turnos = [{"rol": "user", "contenido": f"q{i}"} for i in range(5)]
    assert hilos.historial_para_loop(_hilo(turnos), ventana=-1) == []


def test_historial_ventana_desalineada_no_empieza_en_assistant():
    """CARRY de la revisión B1 (Task 1): los turnos se guardan en pares
    [user, assistant]. La API de Anthropic exige que la lista de mensajes
    EMPIECE en 'user' y alterne — si la ventana corta a mitad de un par
    (ventana impar / desalineada), el primer elemento del slice cae en
    'assistant' y hay que descartarlo, en vez de mandarlo así al loop."""
    turnos = []
    for i in range(5):
        turnos.append({"rol": "user", "contenido": f"u{i}"})
        turnos.append({"rol": "assistant", "contenido": f"a{i}"})
    # 10 turnos totales; ventana=3 -> slice crudo = [a3, u4, a4] (empieza en assistant)
    msgs = hilos.historial_para_loop(_hilo(turnos), ventana=3)
    assert msgs[0]["role"] == "user"
    assert msgs == [
        {"role": "user", "content": "u4"},
        {"role": "assistant", "content": "a4"},
    ]


def test_historial_ventana_alineada_no_se_toca():
    """Ventana PAR (alineada con los pares) no debe perder turnos: es el caso
    normal (ventana par por defecto, CFO_HILO_VENTANA=8)."""
    turnos = []
    for i in range(5):
        turnos.append({"rol": "user", "contenido": f"u{i}"})
        turnos.append({"rol": "assistant", "contenido": f"a{i}"})
    msgs = hilos.historial_para_loop(_hilo(turnos), ventana=4)
    assert len(msgs) == 4
    assert msgs[0] == {"role": "user", "content": "u3"}
    assert msgs[-1] == {"role": "assistant", "content": "a4"}


def test_es_reintento_por_update_id():
    assert hilos.es_reintento(_hilo([], uid=42), 42) is True
    assert hilos.es_reintento(_hilo([], uid=42), 43) is False
    assert hilos.es_reintento(None, 42) is False


@pytest.mark.asyncio
async def test_registrar_turno_sin_hilo_previo(monkeypatch):
    guardados = []

    async def fake_obtener(user_id):
        return None

    async def fake_guardar(h):
        guardados.append(h)

    monkeypatch.setattr("app.cfo.telegram.hilos.repositorio.obtener_hilo", fake_obtener)
    monkeypatch.setattr("app.cfo.telegram.hilos.repositorio.guardar_hilo", fake_guardar)

    await hilos.registrar_turno(
        user_id="u1",
        pregunta="cuanto vendimos",
        texto_crudo="vendimos [[V1]]",
        update_id=7,
        envio="vendimos $10.000.000",
    )

    assert len(guardados) == 1
    h = guardados[0]
    assert h.user_id == "u1"
    assert h.turnos == [
        {"rol": "user", "contenido": "cuanto vendimos"},
        {"rol": "assistant", "contenido": "vendimos [[V1]]"},
    ]
    assert h.ultimo_update_id == 7
    assert h.ultimo_envio == "vendimos $10.000.000"


@pytest.mark.asyncio
async def test_registrar_turno_recorta_al_maximo(monkeypatch):
    # hilo previo ya en el tope (_MAX_TURNOS=40 -> 20 pares)
    previos = []
    for i in range(20):
        previos.append({"rol": "user", "contenido": f"u{i}"})
        previos.append({"rol": "assistant", "contenido": f"a{i}"})
    hilo_previo = _hilo(list(previos), uid=98)

    async def fake_obtener(user_id):
        return hilo_previo

    guardados = []

    async def fake_guardar(h):
        guardados.append(h)

    monkeypatch.setattr("app.cfo.telegram.hilos.repositorio.obtener_hilo", fake_obtener)
    monkeypatch.setattr("app.cfo.telegram.hilos.repositorio.guardar_hilo", fake_guardar)

    await hilos.registrar_turno(
        user_id="u1",
        pregunta="nueva pregunta",
        texto_crudo="nueva respuesta",
        update_id=99,
        envio="env99",
    )

    h = guardados[0]
    assert len(h.turnos) == 40  # se mantiene en el tope, no crece sin límite
    assert h.turnos[0] == {
        "rol": "user",
        "contenido": "u1",
    }  # se botó el par mas viejo (u0,a0)
    assert h.turnos[-2:] == [
        {"rol": "user", "contenido": "nueva pregunta"},
        {"rol": "assistant", "contenido": "nueva respuesta"},
    ]
    assert h.ultimo_update_id == 99
