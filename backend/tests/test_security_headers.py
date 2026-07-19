# backend/tests/test_security_headers.py
"""Cabeceras de seguridad (Spec §8.3 / DoD #12): presentes en TODA respuesta.

Este test ES el control de CI del DoD #12."""

from fastapi.testclient import TestClient


def test_cabeceras_presentes_en_liveness(app):
    with TestClient(app) as client:
        r = client.get("/health")
    h = r.headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["Referrer-Policy"] == "no-referrer"
    assert h["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert "default-src 'none'" in h["Content-Security-Policy"]


def test_csp_estricta_sin_unsafe_inline(app):
    with TestClient(app) as client:
        r = client.get("/health")
    assert "unsafe-inline" not in r.headers["Content-Security-Policy"]
    assert "unsafe-eval" not in r.headers["Content-Security-Policy"]


def test_hsts_ausente_en_dev(app):
    # En dev (http local) NO fijamos HSTS: evita pinnear localhost.
    with TestClient(app) as client:
        r = client.get("/health")
    assert "Strict-Transport-Security" not in r.headers


def test_hsts_presente_fuera_de_dev(app, monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("MFA_ENC_KEY", "k" * 44)
    # Fuera de dev el lifespan exige MONGODB_URI_AUDIT (C-01); create_client está
    # parcheado a mongomock por el fixture, así que el valor da igual.
    monkeypatch.setenv("MONGODB_URI_AUDIT", "mongodb://localhost:27017")
    from app.config import get_settings

    get_settings.cache_clear()
    with TestClient(app) as client:
        r = client.get("/health")
    hsts = r.headers.get("Strict-Transport-Security", "")
    assert "max-age=" in hsts and "includeSubDomains" in hsts
    get_settings.cache_clear()


def test_cabeceras_tambien_en_404(app):
    # Las cabeceras van en TODA respuesta, no solo en 200.
    with TestClient(app) as client:
        r = client.get("/no-existe")
    assert r.status_code == 404
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_cabeceras_en_preflight_cors(app):
    """B-1 (Kimi): Security es la capa MÁS EXTERNA → cubre las respuestas que genera
    CORS (preflight OPTIONS), no solo las de la app."""
    with TestClient(app) as client:
        r = client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://compas.roddos.com",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
