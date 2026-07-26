#!/usr/bin/env python
"""Amplía la auto-clasificación (C3) para la carga Global66 — decisión CEO 2026-07-26.

Siembra el subconjunto de EGRESO de `SEMILLA_REGLAS` (comercios/conceptos genéricos
observados en el extracto REAL de Global66: GMF, Uber, Anthropic, Peajes, D1, Notaría…)
y re-clasifica los movimientos 'Por clasificar' de meses no cerrados vía
`aplicar_pendientes` (sella cada doc con clasificada_por/at + regla_id, regla 4/B-2).

Por qué solo el subconjunto de EGRESO: en prod el rubro de recaudo se llama 'Recaudo'
(renombrado desde 'Recaudo de cartera' por el reseed), así que `seed_reglas_reporte`
—que resuelve por nombre y hace fail-loud— abortaría con las specs de ingreso. Esas
reglas de ingreso YA existen en prod (apuntan por rubro_id) y clasifican bien; aquí solo
faltaban las de egreso, cuyos nombres de rubro SÍ coinciden con prod.

NO clasifica (se dejan a revisión manual, sin patrón genérico seguro): socios
(Andrés/Iván → CXC, nunca gasto), 'Débito' pelado, reembolsos/reversas, 'Conversión de
divisas' (transferencia FX). Idempotente: re-correr no duplica reglas ni re-sella lo ya
clasificado. Fail-loud si un rubro de egreso del mapeo no existe en prod.

GATE: muta clasificación de datos reales → GO del CEO + gate-waiver (Kimi retroactivo).

Uso (Windows: PYTHONUTF8=1). URI por env var, NUNCA argv:
    export MONGODB_URI_COMPAS="mongodb+srv://…"
    PYTHONUTF8=1 python migrations/20260726_seed_reglas_global66.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "backend")

from app.audit import service as audit_service  # noqa: E402
from app.db import mongo  # noqa: E402
from app.domain.regla_clasificacion import (  # noqa: E402
    REGLAS_COLLECTION,
    normalizar_texto,
)
from app.domain.rubro import Rubro  # noqa: E402
from app.domain.seed import SEMILLA_REGLAS, _upsert_muchos  # noqa: E402
from app.reglas.service import aplicar_pendientes  # noqa: E402


async def _contar_por_clasificar() -> int:
    from app.domain.bancos import Banco
    from app.domain.transaccion import Transaccion

    pc = await Rubro.find_one(Rubro.nombre == "Por clasificar")
    return await Transaccion.find(
        Transaccion.banco == Banco.GLOBAL66, Transaccion.rubro_id == pc.id
    ).count()


async def _sembrar_reglas_egreso(db) -> tuple[int, int]:
    from app.core.time import now_utc

    specs = [s for s in SEMILLA_REGLAS if s["tipo_flujo"] == "egreso"]
    filas: list[dict] = []
    faltan: list[str] = []
    for s in specs:
        rubro = await Rubro.find_one(Rubro.nombre == s["rubro_nombre"])
        if rubro is None:
            faltan.append(s["rubro_nombre"])
            continue
        filas.append(
            {
                "patron": s["patron"],
                "patron_normalizado": normalizar_texto(s["patron"]),
                "rubro_id": rubro.id,
                "tipo_flujo": s["tipo_flujo"],
                "prioridad": s["prioridad"],
                "origen": s["origen"],
                "activa": True,
                "creada_por": "semilla-global66",
                "created_at": now_utc(),
            }
        )
    if faltan:
        raise SystemExit(
            "FAIL-LOUD: rubros de egreso ausentes en prod: " + ", ".join(sorted(faltan))
        )
    insertadas, colisiones = await _upsert_muchos(
        db, REGLAS_COLLECTION, filas, ["patron_normalizado", "tipo_flujo"]
    )
    return insertadas, len(colisiones)


async def _run(uri: str, db_name: str) -> None:
    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db_name)
    audit_service.configure_audit(client, db_name)
    db = client[db_name]

    antes = await _contar_por_clasificar()
    print(f"[db] '{db_name}' · Global66 'Por clasificar' ANTES: {antes}")

    insertadas, colisiones = await _sembrar_reglas_egreso(db)
    print(f"[reglas] egreso: {insertadas} nuevas, {colisiones} ya existían (idempotente).")

    res = await aplicar_pendientes(usuario_id="migracion-global66")
    print(
        f"[reclasificar] clasificadas={res['clasificadas']} · "
        f"sin_match={res['sin_match']}"
    )
    if res["reglas_con_rubro_inactivo"]:
        print(f"[reclasificar] reglas con rubro inactivo: {res['reglas_con_rubro_inactivo']}")

    despues = await _contar_por_clasificar()
    cubierto = antes - despues
    pct = (cubierto / antes * 100) if antes else 0
    print(
        f"[cobertura] Global66 'Por clasificar' DESPUÉS: {despues} "
        f"(clasificados {cubierto}/{antes} = {pct:.1f}%)"
    )
    client.close()


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS")
    if not uri:
        sys.exit("ERROR: falta la env var MONGODB_URI_COMPAS (nunca por argv).")
    db_name = os.environ.get("MONGODB_DB", "compas")
    asyncio.run(_run(uri, db_name))


if __name__ == "__main__":
    main()
