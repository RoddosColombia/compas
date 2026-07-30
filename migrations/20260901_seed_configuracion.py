#!/usr/bin/env python
"""Migración idempotente: claves iniciales de Configuracion (Spec §1.10).

UMBRAL_DIF_BANCO_CIERRE ($50.000), CALENDARIO_DIAN (vencimientos IVA reales de
RODDOS) y DIAS_CREDITO_POR_PROVEEDOR (dict vacío, lo puebla Financiero).
Idempotente ($setOnInsert por (clave, vigente_desde)).

Uso:  MONGODB_URI_COMPAS="<uri>" python migrations/20260901_seed_configuracion.py [db=compas]
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "backend")

from app.db import mongo  # noqa: E402
from app.domain.seed import seed_configuracion  # noqa: E402


async def _run(uri: str, db_name: str) -> None:
    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db_name)
    n = await seed_configuracion(client[db_name])
    print(f"[configuracion] {n} nuevas insertadas (idempotente).")
    client.close()


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS") or os.environ.get("MONGODB_URI")
    if not uri:
        sys.exit(
            "ERROR: falta MONGODB_URI_COMPAS (o MONGODB_URI) en el entorno; nunca por "
            'argv (visible en ps/historial). Uso: MONGODB_URI_COMPAS="<uri>" '
            "python migrations/20260901_seed_configuracion.py [db=compas]"
        )
    db_name = sys.argv[1] if len(sys.argv) > 1 else "compas"
    asyncio.run(_run(uri, db_name))


if __name__ == "__main__":
    main()
