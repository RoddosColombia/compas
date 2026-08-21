# backend/tests/cfo/telegram/test_cliente.py
from app.cfo.telegram import cliente as cli


def test_crear_cliente_none_sin_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert cli.crear_cliente_telegram() is None


def test_crear_cliente_instancia_con_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "botX")
    assert isinstance(cli.crear_cliente_telegram(), cli.ClienteTelegram)
