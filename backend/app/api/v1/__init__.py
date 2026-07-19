# backend/app/api/v1/__init__.py
"""Router raíz de la API v1 (regla: API bajo /api/v1)."""

from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)
