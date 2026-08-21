# backend/tests/cfo/telegram/test_cliente.py
import pytest
from app.cfo.telegram import cliente as cli


def test_crear_cliente_none_sin_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert cli.crear_cliente_telegram() is None


def test_crear_cliente_instancia_con_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "botX")
    assert isinstance(cli.crear_cliente_telegram(), cli.ClienteTelegram)


@pytest.mark.asyncio
async def test_enviar_postea_url_y_payload(monkeypatch):
    llamada = {}

    class _FakeResp:
        def raise_for_status(self):
            pass

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            llamada["url"] = url
            llamada["json"] = json
            return _FakeResp()

    monkeypatch.setattr("httpx.AsyncClient", _FakeClient)
    c = cli.ClienteTelegram("botX")
    await c.enviar(123, "hola")
    assert llamada["url"] == "https://api.telegram.org/botbotX/sendMessage"
    assert llamada["json"] == {"chat_id": 123, "text": "hola"}


@pytest.mark.asyncio
async def test_enviar_traga_errores_no_revienta(monkeypatch):
    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            raise RuntimeError("red caída")

    monkeypatch.setattr("httpx.AsyncClient", _FakeClient)
    c = cli.ClienteTelegram("botX")
    # NO debe levantar — el fallo de red se traga y se loguea
    await c.enviar(123, "hola")
