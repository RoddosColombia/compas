# backend/app/main.py
"""Punto de entrada del servicio web FastAPI (compas-api).

Regla 6 de CLAUDE.md: el servicio web NUNCA arranca el scheduler. El lifespan
falla en duro si detecta RUN_SCHEDULER=true (defensa contra un despliegue mal
configurado)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.v1 import api_router
from app.audit import service as audit_service
from app.config import get_settings
from app.db import mongo

logger = logging.getLogger("compas")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Regla 6: el web jamás corre el scheduler.
    if settings.run_scheduler:
        raise RuntimeError(
            "RUN_SCHEDULER=true en el servicio web: prohibido (regla 6). "
            "Los jobs viven solo en el worker compas-jobs."
        )

    # Cliente Motor perezoso (no conecta hasta el primer comando) → el web
    # arranca aunque Mongo esté caído; la liveness no depende de la BD.
    client = mongo.create_client(settings.mongodb_uri_compas)
    app.state.mongo_client = client
    app.state.settings = settings
    # NOTA (Sprint 0b): cuando existan document models, llamar aquí
    #   await mongo.init_beanie_for(client, settings.mongodb_db)

    # Conexión DEDICADA de auditoría (DoD #6). En prod, MONGODB_URI_AUDIT usa el
    # usuario `compas_audit` (audit_writer). En dev, si no está, cae a la conexión
    # general (sin separación real de privilegios) con aviso.
    if settings.mongodb_uri_audit:
        audit_client = mongo.create_client(settings.mongodb_uri_audit)
    else:
        audit_client = client
        if settings.app_env != "development":
            logger.warning(
                "MONGODB_URI_AUDIT ausente en %s: el audit_log NO tiene conexión "
                "dedicada; la inmutabilidad por privilegios queda sin efecto.",
                settings.app_env,
            )
    app.state.audit_client = audit_client
    audit_service.configure_audit(audit_client, settings.mongodb_db)

    try:
        yield
    finally:
        audit_service.reset_audit()
        if audit_client is not client:
            audit_client.close()
        client.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="COMPAS API",
        version=__version__,
        lifespan=lifespan,
    )

    @app.get("/health", tags=["health"])
    def liveness() -> dict[str, str]:
        """Liveness — SIN tocar la BD. Es el healthCheckPath de render.yaml."""
        return {"status": "ok", "service": "compas-api", "version": __version__}

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
