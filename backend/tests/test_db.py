# backend/tests/test_db.py
"""Plumbing de Mongo/Beanie (Sprint 0, Sesión 1)."""

from app.db import mongo
from mongomock_motor import AsyncMongoMockClient


async def test_ping_ok_con_mongomock():
    client = AsyncMongoMockClient()
    # No debe lanzar.
    await mongo.ping(client)


async def test_init_beanie_sin_modelos_no_falla():
    """DOCUMENT_MODELS aún vacío (AuditLog es Pydantic plano, no Beanie Document);
    init_beanie debe ser un no-op seguro."""
    client = AsyncMongoMockClient()
    assert mongo.DOCUMENT_MODELS == []
    await mongo.init_beanie_for(client, "compas_test")
