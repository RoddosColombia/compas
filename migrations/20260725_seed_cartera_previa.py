#!/usr/bin/env python
"""Migración idempotente: serie semanal de la CARTERA PREVIA (CR "Fidelidad de caja", PR-1).

Siembra las 97 semanas del recaudo REAL de los 111 créditos preexistentes
(`RECAUDO_PREVIA_SEMANAL` del artefacto). El motor de proyección la suma al recaudo de
crédito y a la cartera activa — corrige la subestimación de caja de 2026-27 (período del
umbral de mayo-2027). Idempotente ($setOnInsert por `semana_global`): una segunda corrida
NO pisa correcciones del CEO. Total sembrado: $1.095.640.900.

Uso (Windows: exportar PYTHONUTF8=1):
    python migrations/20260725_seed_cartera_previa.py "<MONGODB_URI>" [db=compas]
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "backend")

from app.db import mongo  # noqa: E402
from app.domain.seed import seed_cartera_previa_reporte  # noqa: E402


async def _run(uri: str, db_name: str) -> None:
    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db_name)
    insertados, colisiones = await seed_cartera_previa_reporte(client[db_name])
    print(f"[cartera_previa] {insertados} semanas nuevas insertadas (idempotente).")
    if colisiones:
        print(f"[cartera_previa] {len(colisiones)} semanas ya existían (no se pisaron):")
        for c in colisiones:
            print(f"  - semana {c['semana_global']}: existente={c['existente']}")
    client.close()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(
            'Uso: python migrations/20260725_seed_cartera_previa.py "<MONGODB_URI>" [db]'
        )
    uri = sys.argv[1]
    db_name = sys.argv[2] if len(sys.argv) > 2 else "compas"
    asyncio.run(_run(uri, db_name))


if __name__ == "__main__":
    main()
