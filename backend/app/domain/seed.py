# backend/app/domain/seed.py
"""Semillas idempotentes de dominio (rubros y configuración).

Idempotencia por `$setOnInsert` sobre la llave de negocio: una segunda corrida NO
duplica ni sobreescribe ediciones posteriores del Admin. Devuelven cuántos docs
NUEVOS insertaron. Operan sobre una database Motor ya inicializada por Beanie.
"""

from decimal import Decimal
from typing import Any

from bson import Decimal128

from app.domain.cartera_previa import CARTERA_PREVIA_COLLECTION
from app.domain.cartera_previa_semilla import SEMILLA_CARTERA_PREVIA
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


async def seed_cartera_previa(db: Any) -> int:
    """Siembra la serie semanal de la cartera previa (97 semanas; idempotente por
    `semana_global`). CR "Fidelidad de caja" PR-1 — el motor la suma al recaudo de
    crédito y a la cartera. Segunda corrida NO pisa correcciones del CEO."""
    insertados, _ = await _upsert_muchos(
        db, CARTERA_PREVIA_COLLECTION, SEMILLA_CARTERA_PREVIA, ["semana_global"]
    )
    return insertados


async def seed_cartera_previa_reporte(db: Any) -> tuple[int, list[dict]]:
    """Como `seed_cartera_previa` pero con el reporte de colisiones (B-4)."""
    return await _upsert_muchos(
        db, CARTERA_PREVIA_COLLECTION, SEMILLA_CARTERA_PREVIA, ["semana_global"]
    )


async def seed_configuracion(db: Any) -> int:
    """Inserta las claves iniciales (idempotente por (clave, vigente_desde))."""
    insertados, _ = await _upsert_muchos(
        db, CONFIGURACION_COLLECTION, SEMILLA_CONFIGURACION, ["clave", "vigente_desde"]
    )
    return insertados


# ── C3: semilla de reglas de clasificación (GO Kimi PLAN-I 9.3) ──────────────
#
# SOLO patrones genéricos — NUNCA nombres de personas (Ley 1581, Kimi §3): las
# genéricas de ingreso 'Abono'/'Recibido de' → 'Recaudo de cartera' (PRD M7 /
# MODELO §C3), prioridad alta. Los patrones de egreso (comercios del mapeo de `Base real
# egresos`) se cargan desde la app o en una extensión de esta lista cuando el
# CEO comparta el mapeo (dato real, vive fuera del repo). origen='manual':
# curaduría, no aprendizaje.
SEMILLA_REGLAS: list[dict] = [
    {
        "patron": "Abono",
        "tipo_flujo": "ingreso",
        "rubro_nombre": "Recaudo de cartera",
        "prioridad": 1,
        "origen": "manual",
    },
    {
        "patron": "Recibido de",
        "tipo_flujo": "ingreso",
        "rubro_nombre": "Recaudo de cartera",
        "prioridad": 2,
        "origen": "manual",
    },
]


async def seed_reglas_reporte(db: Any) -> tuple[int, list[dict]]:
    """Siembra las reglas de clasificación (idempotente por
    (patron_normalizado, tipo_flujo); reporte de colisiones B-4). FAIL-LOUD
    (Kimi §3): si un rubro destino del mapeo no existe → LookupError, jamás una
    regla huérfana silenciosa."""
    from app.domain.regla_clasificacion import (
        REGLAS_COLLECTION,
        normalizar_texto,
    )
    from app.domain.rubro import RUBROS_COLLECTION

    filas: list[dict] = []
    for spec in SEMILLA_REGLAS:
        rubro = await db[RUBROS_COLLECTION].find_one({"nombre": spec["rubro_nombre"]})
        if rubro is None:
            raise LookupError(
                f"semilla de reglas: falta el rubro destino "
                f"'{spec['rubro_nombre']}' (correr seed_rubros primero)"
            )
        filas.append(
            {
                "patron": spec["patron"],
                "patron_normalizado": normalizar_texto(spec["patron"]),
                "rubro_id": rubro["_id"],
                "tipo_flujo": spec["tipo_flujo"],
                "prioridad": spec["prioridad"],
                "origen": spec["origen"],
                "activa": True,
                "creada_por": "semilla",
                "created_at": _ahora_utc(),
            }
        )
    return await _upsert_muchos(
        db, REGLAS_COLLECTION, filas, ["patron_normalizado", "tipo_flujo"]
    )


def _ahora_utc():
    from app.core.time import now_utc

    return now_utc()
