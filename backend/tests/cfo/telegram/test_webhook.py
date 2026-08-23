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
from app.cfo.telegram.modelos import HiloCFO
from app.core.time import now_utc
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
    # refuerzo explícito (nit N-2 Kimi): lo guardado nunca es lo que el usuario vio
    assert turnos_guardados["texto_crudo"] != tg.enviados[0][1]
    assert "[[" in turnos_guardados["texto_crudo"]


@pytest.mark.asyncio
async def test_vinculado_nunca_guarda_el_texto_sustituido_ni_con_texto_crudo_falsy(
    monkeypatch,
):
    """N-2 (nit Kimi, cierra el camino teórico de fuga): antes de este fix
    `webhook.py` guardaba `resp.texto_crudo or resp.texto` — si `texto_crudo`
    fuera algún día un string falsy (p. ej. ""), el `or` de Python habría caído
    al texto YA SUSTITUIDO (con valores reales), violando el invariante de que
    el hilo solo persiste `[[tokens]]`. Se fuerza aquí ese caso límite (falsy
    pero no None) para probarlo: lo registrado debe ser EXACTAMENTE
    `resp.texto_crudo` ("", en este test), nunca `resp.texto`."""

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
            texto_crudo="",  # falsy a propósito — NO None; ver docstring
            uso=UsoLLM(modelo="m", tokens_in=1, tokens_out=1, iteraciones=1),
        )

    monkeypatch.setattr("app.cfo.telegram.webhook.servicio.consultar", fake_consultar)
    turnos_guardados = {}

    async def fake_registrar(user_id, pregunta, texto_crudo, update_id, envio):
        turnos_guardados["texto_crudo"] = texto_crudo

    monkeypatch.setattr(
        "app.cfo.telegram.webhook.hilos.registrar_turno", fake_registrar
    )
    tg = ClienteTelegramFake()
    update = {
        "update_id": 9,
        "message": {"from": {"id": 111}, "chat": {"id": 111}, "text": "¿caja?"},
    }
    await webhook.procesar_update(update, cliente_telegram=tg)
    assert "$704.722.003" in tg.enviados[0][1]  # el usuario sigue viendo el valor
    # lo guardado es EXACTAMENTE texto_crudo ("") — nunca cae al texto sustituido
    assert turnos_guardados["texto_crudo"] == ""
    assert turnos_guardados["texto_crudo"] != tg.enviados[0][1]


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


@pytest.mark.asyncio
async def test_reintento_reenvia_ultimo_envio_sin_llamar_llm_ni_registrar(monkeypatch):
    """DoD #4, fijado a nivel de procesar_update (no solo del booleano
    es_reintento): un update_id que coincide con hilo.ultimo_update_id es un
    reintento de Telegram (mismo mensaje reenviado por falta de ack a tiempo) ->
    reenvía ultimo_envio SIN volver a llamar al LLM (servicio.consultar) ni
    re-registrar el turno (hilos.registrar_turno) -- si cualquiera de los dos se
    llamara, sería un bug real (gasto doble de LLM / historial duplicado), no
    solo un detalle de implementación."""

    async def fake_resolver(tid):
        return "u1"

    monkeypatch.setattr("app.cfo.telegram.webhook.vinculos.resolver", fake_resolver)

    hilo = HiloCFO(
        user_id="u1",
        turnos=[
            {"rol": "user", "contenido": "¿caja?"},
            {"rol": "assistant", "contenido": "Tu caja es [[caja_hoy]]."},
        ],
        ultimo_update_id=7,
        ultimo_envio="Tu caja es $704.722.003.",
        actualizado_at=now_utc(),
    )

    async def fake_obtener_hilo(uid):
        return hilo

    monkeypatch.setattr(
        "app.cfo.telegram.webhook.repositorio.obtener_hilo", fake_obtener_hilo
    )

    async def fake_consultar(*a, **k):
        raise AssertionError("un reintento NUNCA debe re-llamar al LLM")

    monkeypatch.setattr("app.cfo.telegram.webhook.servicio.consultar", fake_consultar)

    async def fake_registrar(*a, **k):
        raise AssertionError("un reintento NUNCA debe re-registrar el turno")

    monkeypatch.setattr(
        "app.cfo.telegram.webhook.hilos.registrar_turno", fake_registrar
    )

    tg = ClienteTelegramFake()
    update = {
        "update_id": 7,  # == hilo.ultimo_update_id -> es_reintento
        "message": {"from": {"id": 111}, "chat": {"id": 111}, "text": "¿caja?"},
    }
    await webhook.procesar_update(update, cliente_telegram=tg)

    assert tg.enviados == [(111, "Tu caja es $704.722.003.")]
