#!/usr/bin/env python
"""Migración idempotente: semilla del catálogo de rubros (Spec §1.2, PRD M1).

Inserta las 32 categorías reales del Excel congelado + el rubro de sistema
'Ajuste de conciliación'. Idempotente ($setOnInsert por (grupo, nombre)): re-correr
no duplica ni pisa ediciones del Admin.

Uso:  MONGODB_URI_COMPAS="<uri>" python migrations/20260901_seed_rubros.py [db=compas]
Lo corre el operador (RUNBOOK) y el CI de la Sesión 3.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "backend")

from app.db import mongo  # noqa: E402
from app.domain.seed import seed_rubros  # noqa: E402


async def _run(uri: str, db_name: str) -> None:
    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db_name)
    n = await seed_rubros(client[db_name])
    print(f"[rubros] {n} nuevos insertados (idempotente).")
    client.close()


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS") or os.environ.get("MONGODB_URI")
    if not uri:
        sys.exit(
            "ERROR: falta MONGODB_URI_COMPAS (o MONGODB_URI) en el entorno; nunca por "
            'argv (visible en ps/historial). Uso: MONGODB_URI_COMPAS="<uri>" '
            "python migrations/20260901_seed_rubros.py [db=compas]"
        )
    db_name = sys.argv[1] if len(sys.argv) > 1 else "compas"
    asyncio.run(_run(uri, db_name))


if __name__ == "__main__":
    main()
