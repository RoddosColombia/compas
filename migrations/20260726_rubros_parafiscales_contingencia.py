#!/usr/bin/env python
"""Crea 2 rubros que faltaban (decisión CEO 2026-07-26) para la plantilla de gastos.

  - 'Parafiscales'  → Nómina    (3080, fijo)     — seguridad social / parafiscales.
  - 'Contingencia'  → Operación (2150, variable) — reserva operativa.

Idempotente: si el rubro (grupo, nombre) ya existe, no lo toca. `orden` = máx global
+ 1 (no colisiona). Sin PII → migración commiteada. URI por env (nunca argv):

    export MONGODB_URI_COMPAS="mongodb+srv://…"
    PYTHONUTF8=1 python migrations/20260726_rubros_parafiscales_contingencia.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient

NUEVOS = [
    {
        "grupo": "nomina",
        "nombre": "Parafiscales",
        "tipo_flujo": "egreso",
        "codigo": "3080",
        "tipo": "fijo",
        "activo": True,
        "es_sistema": False,
    },
    {
        "grupo": "operacion",
        "nombre": "Contingencia",
        "tipo_flujo": "egreso",
        "codigo": "2150",
        "tipo": "variable",
        "activo": True,
        "es_sistema": False,
    },
]


async def _run(uri: str, db_name: str) -> None:
    client = AsyncIOMotorClient(uri)
    col = client[db_name]["rubros"]

    ultimo = await col.find_one(sort=[("orden", -1)])
    orden = (ultimo["orden"] if ultimo else 0) + 1

    for r in NUEVOS:
        existe = await col.find_one({"grupo": r["grupo"], "nombre": r["nombre"]})
        if existe is not None:
            print(f"[skip] ya existe: {r['grupo']} / {r['nombre']}")
            continue
        doc = {**r, "orden": orden}
        await col.insert_one(doc)
        print(f"[ok]   creado: {r['codigo']} {r['nombre']} ({r['grupo']})")
        orden += 1

    client.close()


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS")
    if not uri:
        sys.exit("ERROR: falta la env var MONGODB_URI_COMPAS (nunca por argv).")
    db_name = os.environ.get("MONGODB_DB", "compas")
    asyncio.run(_run(uri, db_name))


if __name__ == "__main__":
    main()
