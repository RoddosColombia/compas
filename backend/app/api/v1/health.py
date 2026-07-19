# backend/app/api/v1/health.py
"""Readiness bajo /api/v1 (hace ping a Mongo).

La liveness (/health, sin BD) vive en app/main.py porque es el
healthCheckPath de render.yaml y no debe colgar de la API v1."""

from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from app.db import mongo
from app.deps import get_mongo_client

router = APIRouter(tags=["health"])


@router.get("/health/ready")
async def readiness(
    request: Request, response: Response, client: Any = Depends(get_mongo_client)
):
    """503 si Mongo no responde; 200 con {status: ready} si el ping funciona.

    Aprovecha el ping (Mongo arriba) para reintentar `init_beanie` si el arranque
    ocurrió con la BD caída (init no fatal en el lifespan)."""
    try:
        await mongo.ping(client)
    except Exception:
        response.status_code = 503
        return {"status": "not_ready", "mongo": "down"}

    # Mongo respondió: si Beanie no quedó inicializado en el arranque, reintentar.
    from app.main import ensure_beanie

    app = request.app
    if not getattr(app.state, "beanie_ready", False):
        await ensure_beanie(app, app.state.mongo_client, app.state.settings.mongodb_db)
    return {
        "status": "ready",
        "mongo": "up",
        "beanie": "ready" if app.state.beanie_ready else "pending",
    }
