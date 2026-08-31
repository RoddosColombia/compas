# backend/tests/cfo/telegram/test_hilos.py
"""FABS · lógica de hilos: ventana del historial (re-alimentado CRUDO al modelo),
dedup por update_id y append/trim al persistir un turno."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.cfo.telegram import hilos, repositorio
from app.cfo.telegram.modelos import HiloCFO
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


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
    assert len(h.turnos) == 2
    assert h.turnos[0]["rol"] == "user"
    assert h.turnos[0]["contenido"] == "cuanto vendimos"
    assert h.turnos[0]["mostrado"] == "cuanto vendimos"
    assert h.turnos[0]["canal"] == "telegram"
    assert h.turnos[1]["rol"] == "assistant"
    assert h.turnos[1]["contenido"] == "vendimos [[V1]]"
    assert h.turnos[1]["mostrado"] == "vendimos $10.000.000"
    assert h.turnos[1]["canal"] == "telegram"
    assert h.ultimo_update_id == 7
    assert h.ultimo_envio == "vendimos $10.000.000"


@pytest.mark.asyncio
async def test_registrar_turno_recorta_al_maximo(monkeypatch):
    # hilo previo ya en el tope (_MAX_TURNOS=200 -> 100 pares)
    previos = []
    for i in range(100):
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
    assert len(h.turnos) == 200  # se mantiene en el tope, no crece sin límite
    assert h.turnos[0]["rol"] == "user"
    assert h.turnos[0]["contenido"] == "u1"  # se botó el par mas viejo (u0,a0)
    assert h.turnos[-2]["rol"] == "user"
    assert h.turnos[-2]["contenido"] == "nueva pregunta"
    assert h.turnos[-1]["rol"] == "assistant"
    assert h.turnos[-1]["contenido"] == "nueva respuesta"
    assert h.turnos[-1]["mostrado"] == "env99"
    assert h.turnos[-1]["canal"] == "telegram"
    assert h.ultimo_update_id == 99


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=client["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield client


@pytest.mark.asyncio
async def test_registrar_turno_web_guarda_mostrado_y_no_toca_dedup(db):
    # un turno de Telegram deja estado de dedup
    await hilos.registrar_turno("u1", "hola tg", "[[x]]", 55, "MOSTRADO TG")
    # un turno web NO debe pisar ultimo_update_id/ultimo_envio
    await hilos.registrar_turno_web("u1", "hola web", "[[y]]", "MOSTRADO WEB")
    hilo = await repositorio.obtener_hilo("u1")
    assert hilo.ultimo_update_id == 55  # intacto
    assert hilo.ultimo_envio == "MOSTRADO TG"  # intacto
    # 4 turnos, el último assistant es el web con su mostrado + canal
    ult = hilo.turnos[-1]
    assert ult["rol"] == "assistant" and ult["mostrado"] == "MOSTRADO WEB"
    assert ult["canal"] == "web" and ult["contenido"] == "[[y]]"
    tg_asst = hilo.turnos[1]
    assert tg_asst["canal"] == "telegram" and tg_asst["mostrado"] == "MOSTRADO TG"


@pytest.mark.asyncio
async def test_historial_para_display_enmascara_legacy(db):
    # sembrar un hilo con un turno assistant LEGACY (sin mostrado) + uno nuevo
    from app.core.time import now_utc

    await repositorio.guardar_hilo(
        HiloCFO(
            user_id="u2",
            turnos=[
                {"rol": "user", "contenido": "q vieja"},  # legacy user (sin mostrado)
                {
                    "rol": "assistant",
                    "contenido": "[[caja_hoy]]",
                },  # legacy assistant sin mostrado
                {
                    "rol": "user",
                    "contenido": "q nueva",
                    "mostrado": "q nueva",
                    "canal": "web",
                    "ts": "2026-08-30T00:00:00+00:00",
                },
                {
                    "rol": "assistant",
                    "contenido": "[[x]]",
                    "mostrado": "$5.000.000 (al 2026-08-30)",
                    "canal": "web",
                    "ts": "2026-08-30T00:00:00+00:00",
                },
            ],
            actualizado_at=now_utc(),
        )
    )
    disp = hilos.historial_para_display(await repositorio.obtener_hilo("u2"))
    assert disp[0] == {
        "rol": "user",
        "texto": "q vieja",
        "canal": "desconocido",
        "ts": None,
    }
    assert (
        disp[1]["texto"] == "(respuesta anterior)"
    )  # legacy assistant NO expone crudo
    assert "[[" not in disp[1]["texto"]
    assert (
        disp[3]["texto"] == "$5.000.000 (al 2026-08-30)" and disp[3]["canal"] == "web"
    )


@pytest.mark.asyncio
async def test_retencion_200(db):
    for i in range(150):  # 150 pares = 300 turnos → recorta a 200
        await hilos.registrar_turno_web("u3", f"q{i}", f"[[{i}]]", f"m{i}")
    hilo = await repositorio.obtener_hilo("u3")
    assert len(hilo.turnos) == 200
