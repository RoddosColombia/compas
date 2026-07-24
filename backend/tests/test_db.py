# backend/tests/test_db.py
"""Plumbing de Mongo/Beanie (Sprint 0, Sesión 1)."""

from app.db import mongo
from mongomock_motor import AsyncMongoMockClient


async def test_ping_ok_con_mongomock():
    client = AsyncMongoMockClient()
    # No debe lanzar.
    await mongo.ping(client)


async def test_init_beanie_registra_los_documents_de_dominio():
    """DOCUMENT_MODELS = los Documents de dominio (Kimi M-04): Rubro, MesControl,
    Configuracion y Transaccion (§1.5). AuditLog/User/RefreshSession NO están
    (Motor crudo)."""
    from app.audit.models import AuditLog
    from app.domain import DOMAIN_DOCUMENTS, Transaccion

    assert mongo.DOCUMENT_MODELS == DOMAIN_DOCUMENTS
    # 9 previos + ModeloMoto + ParametrosProyeccion (COCK-02, CR-COCK).
    assert len(DOMAIN_DOCUMENTS) == 11
    assert Transaccion in mongo.DOCUMENT_MODELS
    assert AuditLog not in mongo.DOCUMENT_MODELS
    client = AsyncMongoMockClient()
    await mongo.init_beanie_for(client, "compas_test")  # no debe lanzar
