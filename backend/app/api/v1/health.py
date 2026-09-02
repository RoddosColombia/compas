# backend/app/api/v1/health.py
"""Readiness bajo /api/v1 (hace ping a Mongo).

La liveness (/health, sin BD) vive en app/main.py. Es el healthCheckPath
de render.yaml que Render lee para decidir si el servicio está sano.

F-03 (auditoría 2026-09-02): antes este endpoint devolvía 200 con
`beanie: "pending"` cuando Mongo respondía pero el ODM no había
inicializado — un silent-fail que engañaba a Render (200 = sano, no
reinicia). Permitió 30 días de degradación sin alarma.

FIX: el endpoint es OBSERVACIONAL — 503 explícito cuando cualquier
dependencia interna (Mongo o Beanie) no está lista. NO reintenta
`ensure_beanie` sync (eso vive en el middleware lazy de cada request
real de la API, PR #152). Así readiness responde rápido y Render
puede reiniciar con confianza si hace falta."""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from app.db import mongo
from app.deps import get_mongo_client

router = APIRouter(tags=["health"])

# Timeout del ping — más que suficiente en operación normal (~50ms) y evita
# que readiness se cuelgue si Mongo está degradado (Render tiene su propio
# límite de health check; queremos responder ANTES de que él nos declare
# muertos por lento).
_PING_TIMEOUT_S = 3.0


@router.get("/health/ready")
async def readiness(
    request: Request, response: Response, client: Any = Depends(get_mongo_client)
):
    """503 si Mongo down O si Beanie no inicializó; 200 solo si AMBOS listos.

    Los 3 escenarios:
    - Mongo ping falla o timeout → 503 {status:not_ready, mongo:down}
    - Mongo up + Beanie pending  → 503 {status:not_ready, mongo:up, beanie:pending}
    - Mongo up + Beanie ready    → 200 {status:ready, mongo:up, beanie:ready}

    Diseño: readiness es solo LECTURA de estado. El reintento pesado de
    Beanie ocurre en el middleware lazy (`_asegurar_beanie_en_request`)
    de cada request real — cuando Mongo por fin responda, el primer
    endpoint con auth despertará Beanie y readiness pasará a ready sin
    redeploy manual (patrón autocurativo)."""
    # 1. Ping a Mongo con timeout duro. Si Mongo no responde en 3s o
    #    lanza excepción, es 503 rápido — no bloqueamos el health check
    #    de Render esperando algo que ya sabemos que está mal.
    try:
        await asyncio.wait_for(mongo.ping(client), timeout=_PING_TIMEOUT_S)
    except (Exception, asyncio.TimeoutError):  # noqa: BLE001 — degradación observacional
        response.status_code = 503
        return {"status": "not_ready", "mongo": "down"}

    # 2. Mongo responde: ¿Beanie está listo? Solo LEEMOS — no reintentamos.
    app = request.app
    if not getattr(app.state, "beanie_ready", False):
        response.status_code = 503
        return {"status": "not_ready", "mongo": "up", "beanie": "pending"}

    # 3. Ambos arriba.
    return {"status": "ready", "mongo": "up", "beanie": "ready"}
