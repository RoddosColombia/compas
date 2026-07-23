#!/usr/bin/env python
"""Migración idempotente: re-seed de la taxonomía REAL de categorías (C1, CR-S4).

GO Kimi PLAN-I 9.2 (sprint4-categorias). Alinea la semilla de rubros a las 31
categorías reales de `docs/modelo/MODELO.md` ('Base real egresos') + 3 de sistema.
$setOnInsert por (grupo, nombre): re-correr no duplica ni pisa ediciones.

B-4 (Kimi): imprime el REPORTE DE COLISIONES — las llaves donde el seed omitió por
doc preexistente, con el doc existente vs lo que la semilla habría puesto. El
operador verifica los coincidentes (D3: las categorías viejas que no estén en la
taxonomía real quedan activas; el CEO las depura desde la app).

B-1 I-PR1 (eco H-03 Sprint 0): la URI se lee de la VARIABLE DE ENTORNO
`MONGODB_URI` — nunca por argv (quedaría visible en `ps` y en el historial del
shell). PATRÓN para toda migración futura.

Uso:  MONGODB_URI="<uri>" python migrations/20260722_reseed_rubros_reales.py [db=compas]
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "backend")

from app.db import mongo  # noqa: E402
from app.domain.seed import seed_rubros_reporte  # noqa: E402


async def _run(uri: str, db_name: str) -> None:
    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db_name)
    insertados, colisiones = await seed_rubros_reporte(client[db_name])
    print(f"[rubros] {insertados} nuevos insertados (idempotente).")
    if colisiones:
        print(f"[rubros] {len(colisiones)} colisiones (doc preexistente, NO tocado):")
        for c in colisiones:
            ex, se = c["existente"], c["semilla"]
            difs = [
                f"{campo}: existente={ex.get(campo)!r} vs semilla={se[campo]!r}"
                for campo in ("tipo_flujo", "orden", "activo", "es_sistema")
                if ex is not None and ex.get(campo) != se[campo]
            ]
            marca = " ⚠ DIFIERE → verificar" if difs else " (igual a la semilla)"
            print(f"  - ({c['grupo']}, {c['nombre']}){marca}")
            for d in difs:
                print(f"      {d}")
    else:
        print("[rubros] sin colisiones.")
    client.close()


def main() -> None:
    # B-1 I-PR1: URI SOLO por entorno (eco H-03 — argv queda en ps/historial).
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        sys.exit(
            "Falta MONGODB_URI en el entorno.\n"
            'Uso: MONGODB_URI="<uri>" python '
            "migrations/20260722_reseed_rubros_reales.py [db=compas]"
        )
    db_name = sys.argv[1] if len(sys.argv) > 1 else "compas"
    asyncio.run(_run(uri, db_name))


if __name__ == "__main__":
    main()
