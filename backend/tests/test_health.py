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
