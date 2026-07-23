#!/usr/bin/env python
"""Migración idempotente: semilla de reglas de clasificación (C3, CR-S5).

GO Kimi PLAN-I 9.3. Siembra las reglas genéricas de ingreso ('Abono',
'Recibido de' → 'Recaudo', PRD M7 / MODELO §C3). SOLO patrones genéricos — NUNCA
nombres de personas (Ley 1581). $setOnInsert por (patron_normalizado, tipo_flujo):
re-correr no duplica ni pisa. FAIL-LOUD si un rubro destino no existe (correr
seed_rubros primero). Imprime el reporte de colisiones (B-4).

B-1 I-PR1 C1 (patrón de migraciones): la URI se lee de la VARIABLE DE ENTORNO
`MONGODB_URI` — nunca por argv (visible en ps/historial).

Uso:  MONGODB_URI="<uri>" python migrations/20260722_seed_reglas_clasificacion.py [db=compas]
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "backend")

from app.db import mongo  # noqa: E402
from app.domain.seed import seed_reglas_reporte  # noqa: E402


async def _run(uri: str, db_name: str) -> None:
    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db_name)
    insertadas, colisiones = await seed_reglas_reporte(client[db_name])
    print(f"[reglas] {insertadas} nuevas insertadas (idempotente).")
    if colisiones:
        print(f"[reglas] {len(colisiones)} colisiones (doc preexistente, NO tocado):")
        for c in colisiones:
            print(f"  - ({c['patron_normalizado']}, {c['tipo_flujo']})")
    else:
        print("[reglas] sin colisiones.")
    client.close()


def main() -> None:
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        sys.exit(
            "Falta MONGODB_URI en el entorno.\n"
            'Uso: MONGODB_URI="<uri>" python '
            "migrations/20260722_seed_reglas_clasificacion.py [db=compas]"
        )
    db_name = sys.argv[1] if len(sys.argv) > 1 else "compas"
    asyncio.run(_run(uri, db_name))


if __name__ == "__main__":
    main()
