# backend/app/db/mongo.py
"""Conexión a MongoDB (Motor) e inicialización de Beanie.

Sprint 0, Sesión 1: dejamos el plumbing listo y probado, pero SIN registrar
document models todavía (no existen). `init_beanie_for` se probará contra
mongomock y se cableará en el lifespan del web en el Sprint 0b, cuando lleguen
los primeros modelos (Rubro, MesControl, Configuracion, AuditLog...).

Diseño consciente: el cliente Motor se crea de forma perezosa (no conecta
hasta el primer comando), por eso el servicio web arranca aunque Mongo esté
caído — la liveness (/health) no depende de la BD; la readiness sí.
"""

from typing import Any

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

# Document models de Beanie (para lecturas), se poblará cuando existan Documents.
# AuditLog NO va aquí: es un Pydantic plano y sus escrituras van por la conexión
# dedicada `compas_audit` (app.audit.service), no por el ODM general.
DOCUMENT_MODELS: list[type] = []


def create_client(uri: str) -> AsyncIOMotorClient:
    """Crea el cliente Motor (perezoso: no abre conexión hasta el primer uso)."""
    return AsyncIOMotorClient(uri, tz_aware=True)


async def init_beanie_for(client: Any, db_name: str) -> None:
    """Inicializa Beanie sobre la database indicada.

    En la Sesión 1 `DOCUMENT_MODELS` está vacío; se irá llenando por sprint.
    """
    await init_beanie(database=client[db_name], document_models=DOCUMENT_MODELS)


async def ping(client: Any) -> None:
    """Ping a Mongo. Lanza excepción si la BD no responde (lo usa readiness)."""
    await client.admin.command("ping")
