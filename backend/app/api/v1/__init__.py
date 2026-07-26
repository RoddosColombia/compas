# backend/app/api/v1/__init__.py
"""Router raíz de la API v1 (regla: API bajo /api/v1)."""

from fastapi import APIRouter

from app.api.v1 import health
from app.auth.router import router as auth_router
from app.caja.router import router as caja_router
from app.cargas.router import router as cargas_router
from app.ciclo.router import router as ciclo_router
from app.cierre.router import router as cierre_router
from app.control.router import router as control_router
from app.facturas.router import router as facturas_router
from app.loantape.router import router as loantape_router
from app.modelos_moto.router import router as modelos_moto_router
from app.pagos.router import router as pagos_router
from app.parametros_proyeccion.router import router as parametros_proyeccion_router
from app.presupuesto.router import router as presupuesto_router
from app.proyeccion.router import router as proyeccion_router
from app.reglas.router import router as reglas_router
from app.rubros.router import router as rubros_router
from app.transacciones.router import router as transacciones_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth_router)
api_router.include_router(caja_router)
api_router.include_router(cargas_router)
api_router.include_router(ciclo_router)
api_router.include_router(cierre_router)
api_router.include_router(control_router)
api_router.include_router(facturas_router)
api_router.include_router(loantape_router)
api_router.include_router(modelos_moto_router)
api_router.include_router(pagos_router)
api_router.include_router(parametros_proyeccion_router)
api_router.include_router(presupuesto_router)
api_router.include_router(proyeccion_router)
api_router.include_router(reglas_router)
api_router.include_router(rubros_router)
api_router.include_router(transacciones_router)
