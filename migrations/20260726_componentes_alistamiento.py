#!/usr/bin/env python
"""CR-002 — siembra el desglose de 'Costos de alistamiento por moto vendida' en
todas las vigencias de parametros_proyeccion que no lo tengan.

Desglose aprobado (Σ = 692.005 EXACTO, el costo vigente):
  Matrícula (trámite) $ 227.800 · Instalación GPS $ 83.000 · SOAT $ 363.300 ·
  Colchón/otros $ 17.905  (decisión pendiente del CEO sobre el colchón: se siembra
  tal cual; eliminarlo queda a un clic del editor, ya con impacto visible).

REGLA DEL CR: la migración NO puede mover la caja. Verificación automática por
fila: Σ(componentes) == costo_moto_nueva previo, o la migración FALLA (exit 1)
sin escribir esa fila. Idempotente: filas con componentes se saltan.

    export MONGODB_URI_COMPAS="mongodb+srv://…"
    PYTHONUTF8=1 python migrations/20260726_componentes_alistamiento.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from decimal import Decimal

from bson.decimal128 import Decimal128
from motor.motor_asyncio import AsyncIOMotorClient

COMPONENTES = [
    {
        "nombre": "Matrícula (trámite)",
        "valor": Decimal("227800"),
        "activo": True,
        "orden": 1,
    },
    {
        "nombre": "Instalación GPS",
        "valor": Decimal("83000"),
        "activo": True,
        "orden": 2,
    },
    {"nombre": "SOAT", "valor": Decimal("363300"), "activo": True, "orden": 3},
    {
        "nombre": "Colchón/otros",
        "valor": Decimal("17905"),
        "activo": True,
        "orden": 4,
    },
]

SUMA = sum(c["valor"] for c in COMPONENTES)  # 692005


def _dec(v: object) -> Decimal:
    if isinstance(v, Decimal128):
        return v.to_decimal()
    return Decimal(str(v))


async def _run(uri: str, db_name: str) -> None:
    client = AsyncIOMotorClient(uri)
    col = client[db_name]["parametros_proyeccion"]
    fallo = False

    async for doc in col.find({}):
        vig = doc.get("vigente_desde", "?")
        if doc.get("componentes_alistamiento"):
            print(f"[skip] {vig}: ya tiene componentes")
            continue
        previo = _dec(doc["costo_moto_nueva"])
        if previo != SUMA:
            print(
                f"[FALLA] {vig}: costo_moto_nueva={previo} != Σ componentes={SUMA} "
                "— el desglose del CR-002 no aplica a esta vigencia; resolver a mano."
            )
            fallo = True
            continue
        await col.update_one(
            {"_id": doc["_id"]},
            {
                "$set": {
                    "componentes_alistamiento": [
                        {**c, "valor": Decimal128(c["valor"])} for c in COMPONENTES
                    ]
                }
            },
        )
        print(f"[ok]   {vig}: desglose sembrado (Σ = {SUMA} == costo previo)")

    client.close()
    if fallo:
        sys.exit(1)


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS")
    if not uri:
        sys.exit("ERROR: falta la env var MONGODB_URI_COMPAS (nunca por argv).")
    db_name = os.environ.get("MONGODB_DB", "compas")
    asyncio.run(_run(uri, db_name))


if __name__ == "__main__":
    main()
