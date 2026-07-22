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
) -> tuple[int, list[dict]]:
    """Upsert idempotente. Devuelve (insertados, colisiones) — B-4 (Kimi PLAN-I C1):
    cada llave donde $setOnInsert OMITIÓ por doc preexistente se reporta con el doc
    existente y lo que la semilla habría puesto, para verificación manual (un doc
    viejo con tipo_flujo/orden distintos ya no pasa en silencio)."""
    insertados = 0
    colisiones: list[dict] = []
    col = db[coleccion]
    for fila in filas:
        filtro = {k: fila[k] for k in llave}
        doc = _a_bson(fila)
        res = await col.update_one(filtro, {"$setOnInsert": doc}, upsert=True)
        if res.upserted_id is not None:
            insertados += 1
        else:
            existente = await col.find_one(filtro, {"_id": 0})
            colisiones.append({**filtro, "existente": existente, "semilla": fila})
    return insertados, colisiones


async def seed_rubros(db: Any) -> int:
    """Inserta las 34 categorías (31 reales de MODELO.md + 3 de sistema;
    idempotente). Compat: devuelve solo el conteo — el reporte B-4 está en
    `seed_rubros_reporte`."""
    insertados, _ = await _upsert_muchos(
        db, RUBROS_COLLECTION, SEMILLA_RUBROS, ["grupo", "nombre"]
    )
    return insertados


async def seed_rubros_reporte(db: Any) -> tuple[int, list[dict]]:
    """Como `seed_rubros`, pero devuelve también el reporte de colisiones (B-4).
    Lo usa la migración del re-seed C1."""
    return await _upsert_muchos(
        db, RUBROS_COLLECTION, SEMILLA_RUBROS, ["grupo", "nombre"]
    )


async def seed_configuracion(db: Any) -> int:
    """Inserta las claves iniciales (idempotente por (clave, vigente_desde))."""
    insertados, _ = await _upsert_muchos(
        db, CONFIGURACION_COLLECTION, SEMILLA_CONFIGURACION, ["clave", "vigente_desde"]
    )
    return insertados
