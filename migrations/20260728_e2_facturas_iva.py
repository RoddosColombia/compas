#!/usr/bin/env python
"""Migración idempotente E2 — captura de facturas / módulo de IVA.

Dos cosas, ambas idempotentes (segunda corrida sin cambios, criterio A13):
  1. Crea el índice único SPARSE sobre `cufe` (y el resto de índices de `Factura`)
     vía `init_beanie` — crear un índice ya existente con la misma definición es no-op.
  2. Siembra las claves de Configuracion de E2 (NIT_RODDOS, NIT_AUTECO,
     IVA_ALIMENTA_PROYECCION apagada) con `seed_configuracion` ($setOnInsert por
     (clave, vigente_desde)).

La colección `facturas` está VACÍA antes de E2 (verificado en producción), así que la
creación del índice no tiene riesgo de datos.

Plan de reversa (NO ejecutar sin aprobación): borrar el índice `cufe_unico`
(`db.facturas.drop_index("cufe_unico")`), quitar los campos nuevos de las facturas
creadas (`$unset cufe, tipo_documento, signo, inc, bolsas, otros_impuestos, rete_fuente,
rete_iva, rete_ica, archivo_ref`) y las 3 claves de config sembradas. La colección
estaba vacía → la reversa es limpia.

Uso:  python migrations/20260728_e2_facturas_iva.py "<MONGODB_URI>" [db=compas]
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "backend")

from app.db import mongo  # noqa: E402
from app.domain.factura import FACTURAS_COLLECTION  # noqa: E402
from app.domain.seed import seed_configuracion  # noqa: E402


async def _run(uri: str, db_name: str) -> None:
    client = mongo.create_client(uri)
    db = client[db_name]

    antes = await db[FACTURAS_COLLECTION].count_documents({})
    print(f"[e2] facturas antes: {antes}")

    # init_beanie asegura los índices declarados en Settings (nit_numero, por_fecha).
    await mongo.init_beanie_for(client, db_name)

    # Índice único SPARSE de CUFE (A2). Va aquí y no en Settings: mongomock no honra
    # partialFilterExpression y rompería la suite rápida (ver factura.py). En Mongo real
    # el partial excluye las capturas manuales sin CUFE. create_index es idempotente:
    # re-crear con la misma definición y nombre es no-op.
    await db[FACTURAS_COLLECTION].create_index(
        [("cufe", 1)],
        name="cufe_unico",
        unique=True,
        partialFilterExpression={"cufe": {"$type": "string"}},
    )
    indices = await db[FACTURAS_COLLECTION].index_information()
    print(f"[e2] índices de facturas: {sorted(indices)}")

    n = await seed_configuracion(db)
    print(f"[e2] configuracion: {n} claves nuevas insertadas (idempotente).")

    despues = await db[FACTURAS_COLLECTION].count_documents({})
    print(f"[e2] facturas después: {despues} (sin cambios de datos)")
    client.close()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(
            'Uso: python migrations/20260728_e2_facturas_iva.py "<MONGODB_URI>" [db]'
        )
    uri = sys.argv[1]
    db_name = sys.argv[2] if len(sys.argv) > 2 else "compas"
    asyncio.run(_run(uri, db_name))


if __name__ == "__main__":
    main()
