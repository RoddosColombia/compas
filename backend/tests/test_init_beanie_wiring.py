# backend/tests/test_init_beanie_wiring.py
"""init_beanie cableado en el lifespan SIN romper 'liveness sin BD'.

`init_beanie` conecta (crea índices). Si Mongo está caído al arrancar, el startup
NO debe caerse: /health sigue en 200 y Beanie se reintenta en el primer request
real de la API (middleware lazy). Readiness solo observa."""

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


def test_readiness_NO_reintenta_beanie_solo_observa(app, monkeypatch):
    """Readiness es OBSERVACIONAL (F-03, PR #154): reporta el estado, no lo cambia.

    Este test decía lo contrario y llevaba fallando en `main` desde que F-03
    cambió el diseño — un rojo permanente que nadie miró. Se corrige para
    afirmar el contrato real: quien recupera Beanie es el middleware lazy de un
    request de la API (test siguiente), no el health check.
    """
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
        estado["falla"] = False  # Mongo se recupera...
        r = client.get("/api/v1/health/ready")

    # ...pero readiness solo MIRA: sigue 503 y no tocó el estado.
    assert r.status_code == 503
    assert r.json()["beanie"] == "pending"
    assert app.state.beanie_ready is False


def test_un_request_real_recupera_beanie_via_middleware_lazy(app, monkeypatch):
    """El patrón autocurativo (PR #152): el primer request de la API tras la
    recuperación de Mongo reinicializa Beanie, sin redeploy manual."""
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
        # Un request cualquiera de la API (su status da igual: puede ser 401 por
        # RBAC). Lo que importa es que el middleware lazy corrió ensure_beanie.
        client.get("/api/v1/modelos-moto")
        assert app.state.beanie_ready is True
        r = client.get("/api/v1/health/ready")
        assert r.status_code == 200
        assert r.json()["beanie"] == "ready"
