from app.cfo import config as cfo_config
from app.cfo.config import cfo_enabled


def test_flag_apagado_por_defecto(monkeypatch):
    monkeypatch.delenv("CFO_ENABLED", raising=False)
    assert cfo_enabled() is False


def test_flag_encendible_por_env(monkeypatch):
    monkeypatch.setenv("CFO_ENABLED", "true")
    assert cfo_enabled() is True


def test_cfo_model_default_y_override(monkeypatch):
    monkeypatch.delenv("CFO_MODEL", raising=False)
    assert cfo_config.cfo_model() == "claude-haiku-4-5-20251001"
    monkeypatch.setenv("CFO_MODEL", "claude-sonnet-5")
    assert cfo_config.cfo_model() == "claude-sonnet-5"


def test_cfo_api_key_none_si_ausente(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cfo_config.cfo_api_key() is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "  ")
    assert cfo_config.cfo_api_key() is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert cfo_config.cfo_api_key() == "sk-test"


def test_cfo_limites_default(monkeypatch):
    for k in ("CFO_MAX_ITER", "CFO_MAX_TOKENS", "CFO_TIMEOUT_S"):
        monkeypatch.delenv(k, raising=False)
    assert cfo_config.cfo_max_iter() == 3
    assert cfo_config.cfo_max_tokens() == 1024
    assert cfo_config.cfo_timeout_s() == 60.0


def test_telegram_config(monkeypatch):
    from app.cfo import config as c

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert c.telegram_bot_token() is None
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "botX")
    assert c.telegram_bot_token() == "botX"
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "sek")
    assert c.telegram_webhook_secret() == "sek"
    monkeypatch.delenv("CFO_HILO_VENTANA", raising=False)
    assert c.cfo_hilo_ventana() == 8
    monkeypatch.setenv("CFO_HILO_VENTANA", "4")
    assert c.cfo_hilo_ventana() == 4
