# backend/app/api/v1/health.py
"""Readiness bajo /api/v1 (hace ping a Mongo).

La liveness (/health, sin BD) vive en app/main.py porque es el
healthCheckPath de render.yaml y no debe colgar de la API v1."""

from typing import Any

from fastapi import APIRouter, Depends, Response

from app.db import mongo
from app.deps import get_mongo_client

router = APIRouter(tags=["health"])


@router.get("/health/ready")
async def readiness(response: Response, client: Any = Depends(get_mongo_client)):
    """503 si Mongo no responde; 200 con {status: ready} si el ping funciona."""
    try:
        await mongo.ping(client)
    except Exception:
        response.status_code = 503
        return {"status": "not_ready", "mongo": "down"}
    return {"status": "ready", "mongo": "up"}
