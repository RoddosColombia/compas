# backend/tests/test_init_beanie_wiring.py
"""init_beanie cableado en el lifespan SIN romper 'liveness sin BD'.

`init_beanie` conecta (crea índices). Si Mongo está caído al arrancar, el startup
NO debe caerse: /health sigue en 200 y Beanie se reintenta desde readiness."""

from fastapi.testclient import TestClient


def test_beanie_listo_tras_arranque_normal(app):
    with TestClient(app) as client:
        assert app.state.beanie_ready is True
        r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json()["beanie"] == "ready"


def test_liveness_sobrevive_si_init_beanie_falla(app, monkeypatch):
    """Mongo caído al arrancar → init_beanie revienta, pero /health responde 200."""
    from app.db import mongo

    async def _revienta(*_a, **_k):
        raise RuntimeError("Mongo caído")

    monkeypatch.setattr(mongo, "init_beanie_for", _revienta)

    with TestClient(app) as client:
        assert app.state.beanie_ready is False  # no se cayó el startup
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readiness_reintenta_beanie(app, monkeypatch):
    """Arranca con init fallando; cuando Mongo 'vuelve', readiness reinicializa."""
    from app.db import mongo

    real_init = mongo.init_beanie_for
    estado = {"falla": True}

    async def _condicional(*a, **k):
        if estado["falla"]:
            raise RuntimeError("Mongo caído")
        await real_init(*a, **k)

    monkeypatch.setattr(mongo, "init_beanie_for", _condicional)

    with TestClient(app) as client:
        assert app.state.beanie_ready is False
        estado["falla"] = False  # Mongo se recupera
        r = client.get("/api/v1/health/ready")
        assert r.status_code == 200
        assert r.json()["beanie"] == "ready"
        assert app.state.beanie_ready is True
