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
    client: Any,
    db_name: str,
    document_models: list[type] | None = None,
    *,
    skip_indexes: bool = True,
) -> None:
    """Inicializa Beanie sobre la database indicada con los Documents de dominio.

    `skip_indexes=True` por DEFECTO (fix 2026-09-03). Motivo medido: `init_beanie`
    con creación de índices recorre los 25 Documents y emite `createIndexes` por
    cada uno. Con Render en Ohio y Atlas en mexico-central-1 eso son decenas de
    round-trips cross-region EN SERIE — pasaba de los 15s del hard timeout y el
    arranque quedaba con `beanie_ready=False` para siempre. El ping a Mongo, en
    cambio, responde en ~0.1s: la BD nunca estuvo caída, era el registro de
    índices lo que no cabía en el presupuesto de arranque.

    Registrar los modelos (lo que Beanie necesita para que las queries funcionen)
    NO requiere tocar la red. Los índices se crean aparte, sin bloquear el
    arranque, con `crear_indices()`.
    """
    models = DOCUMENT_MODELS if document_models is None else document_models
    await init_beanie(
        database=client[db_name],
        document_models=models,
        skip_indexes=skip_indexes,
    )


async def crear_indices(client: Any, db_name: str) -> None:
    """Crea/actualiza los índices de todos los Documents. NO se llama en el
    arranque crítico: lo dispara una tarea en segundo plano una vez que la app
    ya está sirviendo (o un job de migración). `createIndexes` es idempotente,
    así que repetirlo es barato."""
    await init_beanie(
        database=client[db_name],
        document_models=DOCUMENT_MODELS,
        skip_indexes=False,
    )


async def ping(client: Any) -> None:
    """Ping a Mongo. Lanza excepción si la BD no responde (lo usa readiness)."""
    await client.admin.command("ping")
