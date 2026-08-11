from app.cfo.config import cfo_enabled


def test_flag_apagado_por_defecto(monkeypatch):
    monkeypatch.delenv("CFO_ENABLED", raising=False)
    assert cfo_enabled() is False


def test_flag_encendible_por_env(monkeypatch):
    monkeypatch.setenv("CFO_ENABLED", "true")
    assert cfo_enabled() is True
