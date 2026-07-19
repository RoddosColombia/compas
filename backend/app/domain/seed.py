# backend/app/domain/seed.py
"""Semillas idempotentes de dominio (rubros y configuración).

Idempotencia por `$setOnInsert` sobre la llave de negocio: una segunda corrida NO
duplica ni sobreescribe ediciones posteriores del Admin. Devuelven cuántos docs
NUEVOS insertaron. Operan sobre una database Motor ya inicializada por Beanie.
"""

from decimal import Decimal
from typing import Any

from bson import Decimal128

from app.domain.configuracion import (
    CONFIGURACION_COLLECTION,
    SEMILLA_CONFIGURACION,
)
from app.domain.rubro import RUBROS_COLLECTION, SEMILLA_RUBROS


def _a_bson(v: Any) -> Any:
    """Escribimos por Motor crudo (no por el ODM), así que pymongo NO encodea
    `Decimal` — hay que pasarlo como `Decimal128` (regla 1; al leer, el tipo Money
    lo devuelve a Decimal)."""
    if isinstance(v, Decimal):
        return Decimal128(v)
    if isinstance(v, dict):
        return {k: _a_bson(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_a_bson(x) for x in v]
    return v


async def _upsert_muchos(
    db: Any, coleccion: str, filas: list[dict], llave: list[str]
) -> int:
    insertados = 0
    col = db[coleccion]
    for fila in filas:
        filtro = {k: fila[k] for k in llave}
        doc = _a_bson(fila)
        res = await col.update_one(filtro, {"$setOnInsert": doc}, upsert=True)
        if res.upserted_id is not None:
            insertados += 1
    return insertados


async def seed_rubros(db: Any) -> int:
    """Inserta las 32 categorías reales (idempotente por (grupo, nombre))."""
    return await _upsert_muchos(
        db, RUBROS_COLLECTION, SEMILLA_RUBROS, ["grupo", "nombre"]
    )


async def seed_configuracion(db: Any) -> int:
    """Inserta las claves iniciales (idempotente por (clave, vigente_desde))."""
    return await _upsert_muchos(
        db, CONFIGURACION_COLLECTION, SEMILLA_CONFIGURACION, ["clave", "vigente_desde"]
    )
