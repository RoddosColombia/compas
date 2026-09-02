# backend/tests/test_health.py
"""Tests del split de health (Sprint 0, Sesión 1).

- /health           → liveness, SIN tocar la BD (es el healthCheckPath de
  render.yaml; debe responder 200 aunque Mongo esté caído).
- /api/v1/health/ready → readiness, hace ping a Mongo.
"""

from fastapi.testclient import TestClient


def test_liveness_ok_sin_bd(app):
    """/health responde 200 sin depender de Mongo."""
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_readiness_ok_con_mongo_arriba(app):
    """/api/v1/health/ready responde 200 cuando el ping a Mongo funciona."""
    with TestClient(app) as client:
        resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["mongo"] == "up"


def test_readiness_503_cuando_mongo_cae(app, monkeypatch):
    """Si el ping a Mongo falla, readiness responde 503 (no 200)."""
    from app.db import mongo

    async def ping_falla(_client):
        raise RuntimeError("mongo caído")

    monkeypatch.setattr(mongo, "ping", ping_falla)

    with TestClient(app) as client:
        resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["mongo"] == "down"


# ─── F-03 · readiness honesto (auditoría 2026-09-02) ───────────────────────
# Antes: si Mongo respondía el ping pero Beanie no había inicializado, el
# endpoint devolvía 200 con `beanie: "pending"`. Render lee 200 = sano y no
# reinicia — permitió 30 días de degradación silenciosa. FIX: 503 explícito
# cuando cualquier dependencia interna (Mongo o Beanie) no está lista.


def test_readiness_503_cuando_mongo_up_pero_beanie_pending(app):
    """F-03 · Con Mongo respondiendo pero Beanie sin inicializar, readiness
    devuelve 503 (no 200 mentiroso). Render debe reiniciar cuando esto pasa."""
    with TestClient(app) as client:
        # El lifespan puso beanie_ready=True; forzamos a False para simular
        # el escenario post-timeout donde init_beanie no completó.
        app.state.beanie_ready = False
        resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["mongo"] == "up"
    assert body["beanie"] == "pending"


def test_readiness_200_solo_cuando_mongo_y_beanie_listos(app):
    """El único caso 200 es cuando AMBAS dependencias están arriba."""
    with TestClient(app) as client:
        app.state.beanie_ready = True  # explícito para el test
        resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["mongo"] == "up"
    assert body["beanie"] == "ready"


def test_readiness_no_llama_ensure_beanie(app, monkeypatch):
    """El endpoint es OBSERVACIONAL — no ejecuta reintento pesado de Beanie
    (eso vive en el middleware lazy de cada request real, PR #152). Así el
    health check responde rápido y no cuelga aunque init_beanie tomara 15s."""
    from app import main

    with TestClient(app) as client:
        # El lifespan ya corrió su ensure_beanie (arranque OK). Ahora espiamos
        # SOLO lo que pase durante el request al readiness.
        llamados = []

        async def ensure_beanie_espia(app_arg, client_arg, db_arg):
            llamados.append((app_arg, db_arg))
            return True

        monkeypatch.setattr(main, "ensure_beanie", ensure_beanie_espia)
        app.state.beanie_ready = False
        # Con beanie=False, ANTES readiness llamaba ensure_beanie (lento).
        # AHORA solo lee el flag y devuelve 503 rápido.
        client.get("/api/v1/health/ready")

    assert llamados == [], (
        "readiness NO debe llamar ensure_beanie — es observacional. "
        f"Se llamó {len(llamados)} veces."
    )
