# -*- coding: utf-8 -*-
"""E1 · Paso 0 — extracción READ-ONLY del ejecutado real de julio 2026 a un fixture congelado.

Vuelca de PROD (solo lecturas, cero escrituras) a
`backend/tests/fixtures/e1_julio_2026_ejecutado.json`:
  - egresos por rubro_id   (Σ EGRESO del mes; reusa control._egresos_por_rubro)
  - ingresos por rubro_id  (Σ INGRESO del mes; espeja la misma agregación)
  - snapshot de rubros      (id, codigo, grupo, nombre, es_sistema) para armar RubroInfo
  - ids de los rubros neutros

Controles de calidad FAIL-LOUD (regla 7), ANTES de escribir el JSON:
  - Σ egresos == 372.200.786,62   (Ejecutado real de julio — Control del CEO)
  - ingreso_real (Σ INGRESO excluyendo neutros por id) == 179.710.080,31  (FIX-B)
Si algo no cuadra: SystemExit y NO se escribe nada.

Uso (PROD, read-only):
  MONGODB_URI_COMPAS=... MONGODB_DB=compas PYTHONUTF8=1 \
      python scripts/extract_e1_julio_2026.py

El test A3 (P2) lee el JSON congelado — hermético, nunca toca PROD.
Los imports de `app`/Mongo son perezosos (dentro de la extracción) para que la lógica
pura sea testeable sin Mongo.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

MES = "2026-07"
MES_ID_STR = "2026-07-01"
# Ejecutado real del libro (Σ egresos de las 505 tx de julio en PROD), verificado por 2
# métodos. El Control del CEO traía 372.200.786,62 (de su Excel Flujo de pagos deudas.xlsx);
# la diferencia de $9,78 no cae en ningún rubro (ruido de centavos del Excel). Decisión CEO
# 2026-08-06: la verdad es Mongo — E1 ancla las transacciones reales, no el Excel. El
# ingreso_real cuadra al peso exacto, lo que confirma que la data de julio está bien.
CTRL_EGRESOS = Decimal("372200776.84")
CTRL_INGRESO_REAL = Decimal("179710080.31")
FIXTURE_PATH = Path("backend/tests/fixtures/e1_julio_2026_ejecutado.json")
COMANDO = "MONGODB_URI_COMPAS=*** MONGODB_DB=compas PYTHONUTF8=1 python scripts/extract_e1_julio_2026.py"


# ─────────────────────────── lógica pura (testeable sin Mongo) ───────────────────────────
def verificar_controles(egresos_total: Decimal, ingreso_real_val: Decimal) -> None:
    """Regla 7: los dos totales de control deben cuadrar al peso o se aborta (sin escribir)."""
    errores: list[str] = []
    if egresos_total != CTRL_EGRESOS:
        errores.append(
            f"Sigma egresos = {egresos_total} != control {CTRL_EGRESOS} "
            f"(dif {egresos_total - CTRL_EGRESOS})"
        )
    if ingreso_real_val != CTRL_INGRESO_REAL:
        errores.append(
            f"ingreso_real = {ingreso_real_val} != control {CTRL_INGRESO_REAL} "
            f"(dif {ingreso_real_val - CTRL_INGRESO_REAL})"
        )
    if errores:
        raise SystemExit(
            "[FALLA regla 7] no se escribe nada:\n  - " + "\n  - ".join(errores)
        )


def construir_fixture(
    *,
    rubros: list[dict],
    egresos: dict[str, Decimal],
    ingresos: dict[str, Decimal],
    neutros_ids: set[str],
    extraccion_iso: str,
    comando: str,
) -> dict:
    """Ensambla el fixture. Montos como string (regla 1). Puro: no toca Mongo."""
    egresos_total = sum(egresos.values(), Decimal("0"))
    ingreso_real_val = sum(
        (v for rid, v in ingresos.items() if rid not in neutros_ids), Decimal("0")
    )
    return {
        "_meta": {
            "descripcion": "E1 Paso 0 — ejecutado real de julio 2026 (fixture congelado, read-only de PROD)",
            "mes": MES,
            "extraccion": extraccion_iso,
            "comando": comando,
            "controles": {
                "egresos_total": str(egresos_total),
                "ingreso_real": str(ingreso_real_val),
                "egresos_total_esperado": str(CTRL_EGRESOS),
                "ingreso_real_esperado": str(CTRL_INGRESO_REAL),
            },
        },
        "rubros": rubros,
        "egresos_por_rubro_id": {k: str(v) for k, v in egresos.items()},
        "ingresos_por_rubro_id": {k: str(v) for k, v in ingresos.items()},
        "neutros_ids": sorted(neutros_ids),
    }


# ─────────────────────────── extracción viva (Mongo, read-only) ───────────────────────────
async def _ingresos_por_rubro(mes_id) -> dict[str, Decimal]:
    """Espejo de control._egresos_por_rubro pero para INGRESO (misma agregación $group)."""
    from bson.decimal128 import Decimal128
    from app.domain.rubro import TipoFlujo
    from app.domain.transaccion import Transaccion

    col = Transaccion.get_pymongo_collection()
    pipeline = [
        {"$match": {"mes_id": mes_id, "tipo_flujo": TipoFlujo.INGRESO.value}},
        {"$group": {"_id": "$rubro_id", "total": {"$sum": "$valor"}}},
    ]
    out: dict[str, Decimal] = {}
    async for d in col.aggregate(pipeline):
        t = d["total"]
        out[str(d["_id"])] = (
            t.to_decimal() if isinstance(t, Decimal128) else Decimal(str(t))
        )
    return out


async def _extraer(
    uri: str, db: str
) -> tuple[list[dict], dict[str, Decimal], dict[str, Decimal], set[str]]:
    """Conecta a PROD (solo lecturas) y devuelve rubros/egresos/ingresos/neutros."""
    sys.path.insert(0, "backend")
    from app.control.service import _egresos_por_rubro  # noqa: E402
    from app.db import mongo  # noqa: E402
    from app.domain.mes_control import MesControl  # noqa: E402
    from app.domain.rubro import Rubro  # noqa: E402
    from app.metas_ingreso.service import _ids_rubros_neutros  # noqa: E402

    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db)

    mc = await MesControl.find_one(MesControl.mes == MES_ID_STR)
    if mc is None:
        raise SystemExit(
            f"[FALLA] no existe MesControl {MES_ID_STR} en la base '{db}'."
        )

    egresos = await _egresos_por_rubro(mc.id)
    ingresos = await _ingresos_por_rubro(mc.id)
    rubros = [
        {
            "id": str(r.id),
            "codigo": r.codigo,
            "grupo": r.grupo.value,
            "nombre": r.nombre,
            "es_sistema": r.es_sistema,
        }
        for r in await Rubro.find_all().to_list()
    ]
    neutros = {str(i) for i in await _ids_rubros_neutros()}
    return rubros, egresos, ingresos, neutros


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS")
    if not uri:
        raise SystemExit(
            "[FALLA] falta la variable de entorno MONGODB_URI_COMPAS (read-only)."
        )
    db = os.environ.get("MONGODB_DB", "compas")

    rubros, egresos, ingresos, neutros = asyncio.run(_extraer(uri, db))

    egresos_total = sum(egresos.values(), Decimal("0"))
    ingreso_real_val = sum(
        (v for rid, v in ingresos.items() if rid not in neutros), Decimal("0")
    )
    verificar_controles(
        egresos_total, ingreso_real_val
    )  # aborta si no cuadra (regla 7)

    from datetime import datetime, timezone  # local: no lo necesita el test puro

    extraccion_iso = (
        datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    )
    fixture = construir_fixture(
        rubros=rubros,
        egresos=egresos,
        ingresos=ingresos,
        neutros_ids=neutros,
        extraccion_iso=extraccion_iso,
        comando=COMANDO,
    )
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[OK] fixture escrito: {FIXTURE_PATH}")
    print(f"     Sigma egresos     = {egresos_total}  (control {CTRL_EGRESOS})")
    print(f"     ingreso_real      = {ingreso_real_val}  (control {CTRL_INGRESO_REAL})")
    print(
        f"     rubros: {len(rubros)} · egresos: {len(egresos)} · ingresos: {len(ingresos)} · neutros: {len(neutros)}"
    )


if __name__ == "__main__":
    main()
