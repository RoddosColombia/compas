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
# SOLO patrones genéricos — NUNCA nombres de personas (Ley 1581, Kimi §3).
# `patron` matchea por CONTAINS normalizado (sin tildes, minúsculas) sobre la
# descripción. Ingreso: 'Abono'/'Recibido de' → 'Recaudo'. Egreso: comercios y
# conceptos genéricos observados en el extracto REAL de Global66 (carga inicial
# 2026-07-26), mapeados a la taxonomía de rubros vigente. origen='manual':
# curaduría, no aprendizaje.
#
# Se dejan DELIBERADAMENTE fuera (van a revisión manual, no hay patrón genérico
# seguro): movimientos de socios (Andrés/Iván → CXC, nunca gasto — regla de
# negocio), 'Débito' pelado (sin comercio), reembolsos/reversas y 'Conversión de
# divisas' (transferencia FX, no gasto). Los nombres de rubro deben EXISTIR y ser
# únicos (el seed hace fail-loud). El rubro de recaudo hoy se llama 'Recaudo'
# (renombrado desde 'Recaudo de cartera'); las reglas guardan rubro_id, no nombre.
SEMILLA_REGLAS: list[dict] = [
    # ── Ingreso (taxonomía canónica MODELO.md: 'Recaudo de cartera'; en prod el
    #    rubro se llama 'Recaudo' tras el reseed — las reglas apuntan por rubro_id,
    #    así que las de ingreso ya existen y clasifican allí. La migración de prod
    #    siembra solo el subconjunto de EGRESO, cuyos nombres coinciden en ambos) ──
    {"patron": "Abono", "tipo_flujo": "ingreso", "rubro_nombre": "Recaudo de cartera",
     "prioridad": 1, "origen": "manual"},
    {"patron": "Recibido de", "tipo_flujo": "ingreso",
     "rubro_nombre": "Recaudo de cartera", "prioridad": 2, "origen": "manual"},
    # ── Egreso · Gastos bancarios ──
    {"patron": "GMF", "tipo_flujo": "egreso", "rubro_nombre": "Gastos bancarios",
     "prioridad": 10, "origen": "manual"},
    {"patron": "Comisión envío", "tipo_flujo": "egreso",
     "rubro_nombre": "Gastos bancarios", "prioridad": 11, "origen": "manual"},
    {"patron": "Cargo por servicio", "tipo_flujo": "egreso",
     "rubro_nombre": "Gastos bancarios", "prioridad": 12, "origen": "manual"},
    {"patron": "Impuesto 4x1000", "tipo_flujo": "egreso",
     "rubro_nombre": "Gastos bancarios", "prioridad": 13, "origen": "manual"},
    # ── Egreso · Impuestos / financieros ──
    {"patron": "Impuesto IVA", "tipo_flujo": "egreso", "rubro_nombre": "Impuestos",
     "prioridad": 14, "origen": "manual"},
    {"patron": "Costo tipo de cambio", "tipo_flujo": "egreso",
     "rubro_nombre": "Gastos financieros", "prioridad": 15, "origen": "manual"},
    # ── Egreso · Transporte/peajes/combustible/parqueo ──
    {"patron": "Uber", "tipo_flujo": "egreso",
     "rubro_nombre": "Transporte/peajes/combustible/parqueo", "prioridad": 20,
     "origen": "manual"},
    {"patron": "Cabify", "tipo_flujo": "egreso",
     "rubro_nombre": "Transporte/peajes/combustible/parqueo", "prioridad": 21,
     "origen": "manual"},
    {"patron": "Peaje", "tipo_flujo": "egreso",
     "rubro_nombre": "Transporte/peajes/combustible/parqueo", "prioridad": 22,
     "origen": "manual"},
    {"patron": "pico y placa", "tipo_flujo": "egreso",
     "rubro_nombre": "Transporte/peajes/combustible/parqueo", "prioridad": 23,
     "origen": "manual"},
    {"patron": "Parqueader", "tipo_flujo": "egreso",
     "rubro_nombre": "Transporte/peajes/combustible/parqueo", "prioridad": 24,
     "origen": "manual"},
    {"patron": "Parking", "tipo_flujo": "egreso",
     "rubro_nombre": "Transporte/peajes/combustible/parqueo", "prioridad": 25,
     "origen": "manual"},
    {"patron": "Texaco", "tipo_flujo": "egreso",
     "rubro_nombre": "Transporte/peajes/combustible/parqueo", "prioridad": 26,
     "origen": "manual"},
    # ── Egreso · Tecnología y software ──
    {"patron": "Anthropic", "tipo_flujo": "egreso",
     "rubro_nombre": "Tecnología y software", "prioridad": 30, "origen": "manual"},
    {"patron": "Render.com", "tipo_flujo": "egreso",
     "rubro_nombre": "Tecnología y software", "prioridad": 31, "origen": "manual"},
    {"patron": "Vercel", "tipo_flujo": "egreso",
     "rubro_nombre": "Tecnología y software", "prioridad": 32, "origen": "manual"},
    {"patron": "Mongodb", "tipo_flujo": "egreso",
     "rubro_nombre": "Tecnología y software", "prioridad": 33, "origen": "manual"},
    {"patron": "Github", "tipo_flujo": "egreso",
     "rubro_nombre": "Tecnología y software", "prioridad": 34, "origen": "manual"},
    {"patron": "Openai", "tipo_flujo": "egreso",
     "rubro_nombre": "Tecnología y software", "prioridad": 35, "origen": "manual"},
    {"patron": "Microsoft", "tipo_flujo": "egreso",
     "rubro_nombre": "Tecnología y software", "prioridad": 36, "origen": "manual"},
    {"patron": "Moonshot", "tipo_flujo": "egreso",
     "rubro_nombre": "Tecnología y software", "prioridad": 37, "origen": "manual"},
    {"patron": "Higgsfield", "tipo_flujo": "egreso",
     "rubro_nombre": "Tecnología y software", "prioridad": 38, "origen": "manual"},
    {"patron": "Workspace", "tipo_flujo": "egreso",
     "rubro_nombre": "Tecnología y software", "prioridad": 39, "origen": "manual"},
    {"patron": "Apple.com", "tipo_flujo": "egreso",
     "rubro_nombre": "Tecnología y software", "prioridad": 40, "origen": "manual"},
    # ── Egreso · Cafetería ──
    {"patron": "Starbucks", "tipo_flujo": "egreso", "rubro_nombre": "Cafetería",
     "prioridad": 45, "origen": "manual"},
    {"patron": "Juan valdez", "tipo_flujo": "egreso", "rubro_nombre": "Cafetería",
     "prioridad": 46, "origen": "manual"},
    {"patron": "Dunkin", "tipo_flujo": "egreso", "rubro_nombre": "Cafetería",
     "prioridad": 47, "origen": "manual"},
    # ── Egreso · Mercado y aseo ──
    {"patron": "Tienda d1", "tipo_flujo": "egreso", "rubro_nombre": "Mercado y aseo",
     "prioridad": 50, "origen": "manual"},
    {"patron": "Carulla", "tipo_flujo": "egreso", "rubro_nombre": "Mercado y aseo",
     "prioridad": 51, "origen": "manual"},
    {"patron": "Jumbo", "tipo_flujo": "egreso", "rubro_nombre": "Mercado y aseo",
     "prioridad": 52, "origen": "manual"},
    {"patron": "Dollarcity", "tipo_flujo": "egreso", "rubro_nombre": "Mercado y aseo",
     "prioridad": 53, "origen": "manual"},
    {"patron": "Exito", "tipo_flujo": "egreso", "rubro_nombre": "Mercado y aseo",
     "prioridad": 54, "origen": "manual"},
    # ── Egreso · Marketing / notariales ──
    {"patron": "Facebk", "tipo_flujo": "egreso",
     "rubro_nombre": "Marketing y publicidad", "prioridad": 60, "origen": "manual"},
    {"patron": "Notaria", "tipo_flujo": "egreso",
     "rubro_nombre": "Gastos notariales", "prioridad": 65, "origen": "manual"},
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
