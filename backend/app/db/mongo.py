# backend/app/db/mongo.py
"""Conexión a MongoDB (Motor) e inicialización de Beanie.

Sprint 0b: se registran los primeros Documents de dominio (Rubro, MesControl,
Configuracion) y se cablea `init_beanie` en el lifespan. `AuditLog`, `User` y
`RefreshSession` NO son Documents de Beanie: sus escrituras van por Motor crudo
(conexión dedicada de auditoría / repositorios de auth), decisión de la Sesión 2.

Diseño consciente: el cliente Motor se crea de forma perezosa (no conecta
hasta el primer comando), por eso el servicio web arranca aunque Mongo esté
caído — la liveness (/health) no depende de la BD; la readiness sí. Como
`init_beanie` sí conecta (crea índices), en el lifespan se llama de forma NO
fatal y se reintenta desde readiness (ver app.main), preservando esa garantía.
"""

from typing import Any

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.domain import DOMAIN_DOCUMENTS

# Document models de Beanie. Fuente única: el registro explícito de app.domain
# (Kimi M-04). AuditLog/User/RefreshSession NO van aquí (Motor crudo).
DOCUMENT_MODELS: list[type] = DOMAIN_DOCUMENTS


def create_client(uri: str) -> AsyncIOMotorClient:
    """Crea el cliente Motor (perezoso: no abre conexión hasta el primer uso)."""
    return AsyncIOMotorClient(uri, tz_aware=True)


async def init_beanie_for(
    client: Any, db_name: str, document_models: list[type] | None = None
) -> None:
    """Inicializa Beanie sobre la database indicada con los Documents de dominio."""
    models = DOCUMENT_MODELS if document_models is None else document_models
    await init_beanie(database=client[db_name], document_models=models)


async def ping(client: Any) -> None:
    """Ping a Mongo. Lanza excepción si la BD no responde (lo usa readiness)."""
    await client.admin.command("ping")
