#!/usr/bin/env python
"""CR-WAVA §6 — siembra el rubro de sistema 'Tránsito Wava mes anterior' + verifica.

Idempotente, DRY-RUN por defecto, URI por env (nunca por argv). Se corre en PROD tras
el merge del PR de CR-WAVA. NO escribe ningún MesControl: el campo `transito_wava`
default 0 es un no-op de datos (los docs existentes lo leen como 0 por construcción);
esta migración solo lo VERIFICA y siembra el rubro.

  (a) siembra el rubro (`$setOnInsert` por (grupo, nombre); reporte de colisión).
  (b) verifica que todos los MesControl leen con el campo nuevo (foto: estado,
      transito_wava).
  (c) reporta.

Uso:
    export MONGODB_URI_COMPAS="mongodb+srv://…"
    PYTHONUTF8=1 python migrations/20260803_wava_transito.py            # DRY-RUN
    PYTHONUTF8=1 WAVA_APPLY=1 python migrations/20260803_wava_transito.py  # aplica
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "backend")

from app.db import mongo  # noqa: E402
from app.domain.mes_control import MesControl  # noqa: E402
from app.domain.rubro import (  # noqa: E402
    RUBROS_SISTEMA_CLASIFICABLES,
    Rubro,
    RubroGrupo,
    TipoFlujo,
    es_rubro_clasificable,
)

RUBRO = "Tránsito Wava mes anterior"


async def _run(uri: str, db: str, aplica: bool) -> None:
    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db)
    modo = "APLICA (escribe)" if aplica else "DRY-RUN (no escribe)"
    print(f"[db] '{db}' · CR-WAVA siembra rubro tránsito · {modo}\n")

    # ── (a) rubro de sistema ──
    existente = await Rubro.find(
        Rubro.grupo == RubroGrupo.OTROS, Rubro.nombre == RUBRO
    ).to_list()
    if existente:
        r = existente[0]
        print(
            f"[rubro] ya existe: {RUBRO} (otros, INGRESO, sist={r.es_sistema}, "
            f"activo={r.activo}) — no se toca (colisión reportada, idempotente)."
        )
    elif aplica:
        max_orden = max([x.orden async for x in Rubro.find()] + [0])
        r = Rubro(
            grupo=RubroGrupo.OTROS,
            nombre=RUBRO,
            tipo_flujo=TipoFlujo.INGRESO,
            orden=max_orden + 1,
            activo=True,
            es_sistema=True,
        )
        await r.insert()
        print(f"[rubro] CREADO: {RUBRO} (otros, INGRESO, es_sistema=True)")
    else:
        print(f"[rubro] [dry-run] crearía: {RUBRO} (otros, INGRESO, es_sistema=True)")

    print(
        f"[guard] '{RUBRO}' en whitelist es_sistema: "
        f"{RUBRO in RUBROS_SISTEMA_CLASIFICABLES} "
        "(la clasificación manual hacia él está permitida)"
    )

    # ── (b) verificación del campo nuevo en todos los MesControl (no escribe) ──
    print("\n=== foto MesControl (campo transito_wava) ===")
    n = 0
    async for mc in MesControl.find().sort(+MesControl.mes):
        n += 1
        print(
            f"    {mc.mes}  estado={mc.estado.value:<12} transito_wava={mc.transito_wava}"
        )
    print(f"\n[verif] {n} MesControl leídos OK con el campo nuevo (todos default 0).")

    # ── (c) verificación del guard tras la siembra (solo si el rubro ya existe/creó) ──
    r2 = await Rubro.find_one(Rubro.grupo == RubroGrupo.OTROS, Rubro.nombre == RUBRO)
    if r2 is not None:
        print(f"[verif] es_rubro_clasificable('{RUBRO}') = {es_rubro_clasificable(r2)}")

    if not aplica:
        print("\n[DRY-RUN] no se escribió nada. Para aplicar: WAVA_APPLY=1")
    client.close()


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS")
    if not uri:
        sys.exit("ERROR: falta la env var MONGODB_URI_COMPAS (nunca por argv).")
    db = os.environ.get("MONGODB_DB", "compas")
    aplica = os.environ.get("WAVA_APPLY") == "1"
    asyncio.run(_run(uri, db, aplica))


if __name__ == "__main__":
    main()
