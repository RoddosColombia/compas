# backend/tests/test_audit_failfast.py
"""Kimi C-01: fuera de dev, el arranque FALLA si falta MONGODB_URI_AUDIT.

Un warning no es un control; el canal de auditoría no puede degradarse en silencio."""

import pytest
from app.config import get_settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_arranque_falla_sin_uri_audit_fuera_de_dev(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv(
        "JWT_SECRET", "x" * 40
    )  # pasa el fail-fast de JWT (L3) para llegar al de audit
    monkeypatch.delenv("MONGODB_URI_AUDIT", raising=False)
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()
    app = create_app()
    with pytest.raises(RuntimeError, match="MONGODB_URI_AUDIT"):
        with TestClient(app):
            pass
    get_settings.cache_clear()


def test_arranque_falla_sin_jwt_secret_fuera_de_dev(monkeypatch):
    # L3 (Kimi): mismo principio que C-01, aplicado a JWT_SECRET.
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()
    app = create_app()
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        with TestClient(app):
            pass
    get_settings.cache_clear()


def test_arranque_ok_en_dev_sin_uri_audit(monkeypatch):
    """En dev SÍ cae a la conexión general (con warning), sin fallar."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("MONGODB_URI_AUDIT", raising=False)
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
    get_settings.cache_clear()
