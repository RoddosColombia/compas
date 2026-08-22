# backend/tests/cfo/telegram/test_webhook.py
"""T6 (inc3 Pieza B) · lógica pura del webhook (fakes, sin red/DB real).

No-vinculado -> rehúsa sin llamar al servicio (nunca gasta un turno de LLM en
alguien no autorizado) y le dice su telegram_id (para que se lo pase al admin).
Vinculado -> el usuario VE el valor sustituido pero el hilo guarda el texto CRUDO
(con [[tokens]]) — es la garantía anti-alucinación de Pieza A sobreviviendo entre
turnos (inc3 Pieza B). Además: el webhook es un endpoint PÚBLICO -> updates con
forma inesperada (sin 'message', sin texto, sin update_id/from/chat) se ignoran
en silencio, nunca revientan (Telegram no debe ver un 500 por un update raro)."""

import pytest
from app.cfo.telegram import webhook
from tests.cfo.telegram.fakes import ClienteTelegramFake


@pytest.mark.asyncio
async def test_no_vinculado_rehusa_sin_llamar_servicio(monkeypatch):
    async def fake_resolver(tid):
        return None

    monkeypatch.setattr("app.cfo.telegram.webhook.vinculos.resolver", fake_resolver)
    llamado = False

    async def fake_consultar(*a, **k):
        nonlocal llamado
        llamado = True

    monkeypatch.setattr("app.cfo.telegram.webhook.servicio.consultar", fake_consultar)
    tg = ClienteTelegramFake()
    update = {
        "update_id": 1,
        "message": {"from": {"id": 111}, "chat": {"id": 111}, "text": "hola"},
    }
    await webhook.procesar_update(update, cliente_telegram=tg)
    assert llamado is False
    assert "111" in tg.enviados[0][1]  # le dice su telegram_id


@pytest.mark.asyncio
async def test_vinculado_responde_y_guarda_hilo_crudo(monkeypatch):
    async def fake_resolver(tid):
        return "u1"

    monkeypatch.setattr("app.cfo.telegram.webhook.vinculos.resolver", fake_resolver)

    async def fake_obtener_hilo(uid):
        return None

    monkeypatch.setattr(
        "app.cfo.telegram.webhook.repositorio.obtener_hilo", fake_obtener_hilo
    )
    from app.cfo.agente.modelos import RespuestaCFO, UsoLLM

    async def fake_consultar(pregunta, *, actor_id, cliente=None, historial=None):
        return RespuestaCFO(
            texto="Tu caja es $704.722.003.",
            abstuvo=False,
            texto_crudo="Tu caja es [[caja_hoy]].",
            uso=UsoLLM(modelo="m", tokens_in=1, tokens_out=1, iteraciones=1),
        )

    monkeypatch.setattr("app.cfo.telegram.webhook.servicio.consultar", fake_consultar)
    turnos_guardados = {}

    async def fake_registrar(user_id, pregunta, texto_crudo, update_id, envio):
        turnos_guardados.update(texto_crudo=texto_crudo, envio=envio)

    monkeypatch.setattr(
        "app.cfo.telegram.webhook.hilos.registrar_turno", fake_registrar
    )
    tg = ClienteTelegramFake()
    update = {
        "update_id": 7,
        "message": {"from": {"id": 111}, "chat": {"id": 111}, "text": "¿caja?"},
    }
    await webhook.procesar_update(update, cliente_telegram=tg)
    assert "$704.722.003" in tg.enviados[0][1]  # el usuario ve el valor
    # el hilo guarda el token, NUNCA el valor sustituido (invariante anti-alucinación)
    assert turnos_guardados["texto_crudo"] == "Tu caja es [[caja_hoy]]."


@pytest.mark.asyncio
async def test_update_sin_mensaje_se_ignora():
    # updates sin 'message' (edited_message, channel_post, etc.) no son preguntas
    tg = ClienteTelegramFake()
    await webhook.procesar_update({"update_id": 2}, cliente_telegram=tg)
    assert tg.enviados == []


@pytest.mark.asyncio
async def test_update_sin_texto_se_ignora():
    # mensaje sin 'text' (sticker, foto, voz...) — se ignora, no revienta
    tg = ClienteTelegramFake()
    update = {
        "update_id": 3,
        "message": {"from": {"id": 1}, "chat": {"id": 1}, "sticker": {}},
    }
    await webhook.procesar_update(update, cliente_telegram=tg)
    assert tg.enviados == []


@pytest.mark.asyncio
async def test_update_con_forma_inesperada_no_revienta():
    # 'message' con texto pero sin 'from'/'chat'/'update_id' -> nunca debe lanzar
    tg = ClienteTelegramFake()
    update = {"message": {"text": "hola"}}
    await webhook.procesar_update(update, cliente_telegram=tg)
    assert tg.enviados == []
