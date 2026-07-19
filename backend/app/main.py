# backend/app/main.py
"""Punto de entrada del servicio web FastAPI (compas-api).

Regla 6 de CLAUDE.md: el servicio web NUNCA arranca el scheduler. El lifespan
falla en duro si detecta RUN_SCHEDULER=true (defensa contra un despliegue mal
configurado)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.v1 import api_router
from app.config import get_settings
from app.db import mongo


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
    try:
        yield
    finally:
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
