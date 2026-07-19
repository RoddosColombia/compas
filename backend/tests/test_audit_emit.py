# backend/tests/test_audit_emit.py
"""emit_audit — inserción append-only por la conexión dedicada (PR-1)."""

from datetime import UTC

import pytest
from app.audit import service
from app.audit.events import AuditEvento
from mongomock_motor import AsyncMongoMockClient


@pytest.fixture
def audit_col():
    """Configura emit_audit contra una colección mongomock y la devuelve."""
    client = AsyncMongoMockClient()
    service.configure_audit(client, "compas_test")
    yield client["compas_test"]["audit_log"]
    service.reset_audit()


async def test_emit_audit_inserta_doc_bien_formado(audit_col):
    await service.emit_audit(
        AuditEvento.user_login,
        entidad="user",
        entidad_id="507f1f77bcf86cd799439011",
        actor_id="507f1f77bcf86cd799439011",
        metadata={"ip": "1.2.3.4"},
    )
    doc = await audit_col.find_one({"evento": "user.login"})
    assert doc is not None
    assert doc["entidad"] == "user"
    assert doc["metadata"] == {"ip": "1.2.3.4"}


async def test_emit_audit_timestamp_es_utc_aware(audit_col):
    # Regla A-04: persistencia en UTC aware, nunca naive.
    d = await service.emit_audit(
        AuditEvento.mes_creado, entidad="mes", entidad_id="2026-07"
    )
    assert d.timestamp.tzinfo is not None
    assert d.timestamp.utcoffset() == UTC.utcoffset(None)


async def test_emit_audit_rechaza_evento_invalido(audit_col):
    with pytest.raises((ValueError, KeyError)):
        await service.emit_audit("evento.inventado", entidad="x")  # type: ignore[arg-type]


async def test_emit_audit_sin_configurar_falla():
    service.reset_audit()
    with pytest.raises(RuntimeError, match="configur"):
        await service.emit_audit(AuditEvento.user_login, entidad="user")
