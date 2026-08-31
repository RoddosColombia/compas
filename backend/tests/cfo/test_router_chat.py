# backend/tests/cfo/test_router_chat.py
"""FABS · chat embebido (Task 2): POST /api/v1/cfo conversacional sobre el hilo
compartido con Telegram + GET /api/v1/cfo/historial (scrollback)."""

import pytest
import pytest_asyncio
from app.cfo import router as cfo_router
from app.cfo.agente.modelos import RespuestaCFO, UsoLLM
from app.cfo.telegram import hilos, repositorio
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=client["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield client


@pytest.mark.asyncio
async def test_consultar_es_conversacional_y_persiste(db, monkeypatch):
    monkeypatch.setattr(cfo_router, "cfo_enabled", lambda: True)
    capturado = {}

    async def fake_consultar(pregunta, *, actor_id, cliente=None, historial=None):
        capturado["historial"] = historial
        capturado["actor_id"] = actor_id
        return RespuestaCFO(
            texto="$5.000 (al hoy)",
            abstuvo=False,
            texto_crudo="[[caja_hoy]]",
            uso=UsoLLM(modelo="test", tokens_in=1, tokens_out=1, iteraciones=1),
        )

    monkeypatch.setattr(cfo_router.servicio, "consultar", fake_consultar)

    class _U:
        id = "u1"

    body = cfo_router.ConsultaBody(pregunta="cuánta caja?")
    resp = await cfo_router.consultar(body, user=_U())
    assert resp.texto == "$5.000 (al hoy)"
    assert capturado["actor_id"] == "u1"
    # persistió el turno con mostrado en el hilo del user
    hilo = await repositorio.obtener_hilo("u1")
    assert hilo.turnos[-1]["mostrado"] == "$5.000 (al hoy)"
    assert hilo.turnos[-1]["canal"] == "web"

    # segunda pregunta: ahora consultar recibe el historial del turno previo
    await cfo_router.consultar(cfo_router.ConsultaBody(pregunta="y ayer?"), user=_U())
    assert capturado["historial"]  # no vacío en el 2º turno


@pytest.mark.asyncio
async def test_historial_devuelve_scrollback(db, monkeypatch):
    monkeypatch.setattr(cfo_router, "cfo_enabled", lambda: True)
    await hilos.registrar_turno_web("u2", "hola", "[[x]]", "respuesta mostrada")

    class _U:
        id = "u2"

    out = await cfo_router.historial(user=_U())
    textos = [t["texto"] for t in out]
    assert "hola" in textos and "respuesta mostrada" in textos


@pytest.mark.asyncio
async def test_flag_off_da_404(db, monkeypatch):
    monkeypatch.setattr(cfo_router, "cfo_enabled", lambda: False)
    from fastapi import HTTPException

    class _U:
        id = "u3"

    with pytest.raises(HTTPException) as e:
        await cfo_router.consultar(cfo_router.ConsultaBody(pregunta="x"), user=_U())
    assert e.value.status_code == 404
