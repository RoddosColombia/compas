# backend/app/api/v1/__init__.py
"""Router raíz de la API v1 (regla: API bajo /api/v1)."""

from fastapi import APIRouter

from app.api.v1 import health
from app.auth.router import router as auth_router
from app.cargas.router import router as cargas_router
from app.ciclo.router import router as ciclo_router
from app.cierre.router import router as cierre_router
from app.presupuesto.router import router as presupuesto_router
from app.transacciones.router import router as transacciones_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth_router)
api_router.include_router(cargas_router)
api_router.include_router(ciclo_router)
api_router.include_router(cierre_router)
api_router.include_router(presupuesto_router)
api_router.include_router(transacciones_router)
