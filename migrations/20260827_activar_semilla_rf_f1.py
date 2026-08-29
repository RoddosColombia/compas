#!/usr/bin/env python
"""Migración idempotente: ACTIVA las 129 reglas semilla RF-F1 (CEO 2026-08-27 «ambas»).

Complemento de `20260827_semilla_reglas_rf_f1.py` (que las sembró INACTIVAS). El CEO ya
revisó y aprobó las 129, así que se activan en lote vía `aprobar_regla` (revalida el
destino, evento `regla.editada` con via=aprobacion, fail-closed). Desde este momento las
cargas futuras auto-clasifican los movimientos que casen esos patrones.

Idempotente: salta las que ya están activas. Robusta: un 409 (p.ej. otra activa ya usa el
patrón) se registra y no aborta el lote. Lee la lista CONGELADA que el CEO aprobó.

Reversible: `desactivar_regla` deja cualquier regla inactiva de nuevo.
NO toca el motor, ni reclasifica el histórico (solo cambia el estado de las reglas).

Uso (Windows: PYTHONUTF8=1):
    MONGODB_URI_COMPAS="<uri>" MONGODB_URI_AUDIT="<uri>" \\
        python migrations/20260827_activar_semilla_rf_f1.py [db=compas]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "backend")

from app.audit.service import configure_audit  # noqa: E402
from app.db import mongo  # noqa: E402
from app.domain.regla_clasificacion import (  # noqa: E402
    OrigenRegla,
    ReglaClasificacion,
    normalizar_texto,
)
from app.domain.rubro import TipoFlujo  # noqa: E402

DATA = Path("migrations/data/20260827_semilla_rf_f1.json")


async def _run(uri: str, uri_audit: str, db_name: str) -> None:
    from app.reglas.service import ReglasError, aprobar_regla

    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db_name)
    audit_client = mongo.create_client(uri_audit)
    configure_audit(audit_client, db_name)

    doc = await client[db_name]["users"].find_one({"email": "andres@roddos.com"})
    if not doc:
        sys.exit("ERROR: no existe andres@roddos.com")
    usuario_id = str(doc["_id"])

    propuestas = json.loads(DATA.read_text(encoding="utf-8"))["propuestas"]
    print(f"[activar] {len(propuestas)} reglas aprobadas por el CEO")

    activadas = ya_activas = no_encontradas = errores = 0
    for p in propuestas:
        tipo = TipoFlujo(p["tipo_flujo"])
        pn = normalizar_texto(p["patron"])
        inactiva = await ReglaClasificacion.find_one(
            ReglaClasificacion.patron_normalizado == pn,
            ReglaClasificacion.tipo_flujo == tipo,
            ReglaClasificacion.origen == OrigenRegla.APRENDIDA,
            ReglaClasificacion.activa == False,  # noqa: E712
        )
        if inactiva is None:
            ya = await ReglaClasificacion.find_one(
                ReglaClasificacion.patron_normalizado == pn,
                ReglaClasificacion.tipo_flujo == tipo,
                ReglaClasificacion.activa == True,  # noqa: E712
            )
            if ya is not None:
                ya_activas += 1
            else:
                no_encontradas += 1
                print(f"  [no-encontrada] {p['patron']} ({tipo.value})")
            continue
        try:
            await aprobar_regla(regla_id=str(inactiva.id), usuario_id=usuario_id)
            activadas += 1
        except ReglasError as e:
            errores += 1
            print(f"  [skip] {p['patron']} ({tipo.value}) → {e.detalle}")

    activas_apr = await ReglaClasificacion.find(
        ReglaClasificacion.origen == OrigenRegla.APRENDIDA,
        ReglaClasificacion.activa == True,  # noqa: E712
    ).count()
    print(
        f"[activar] activadas={activadas} · ya_activas={ya_activas} · "
        f"no_encontradas={no_encontradas} · errores={errores}"
    )
    print(f"[activar] reglas APRENDIDAS activas en prod: {activas_apr}")
    client.close()
    audit_client.close()


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS") or os.environ.get("MONGODB_URI")
    uri_audit = os.environ.get("MONGODB_URI_AUDIT")
    if not uri or not uri_audit:
        sys.exit("ERROR: faltan MONGODB_URI_COMPAS y/o MONGODB_URI_AUDIT en el entorno")
    db_name = sys.argv[1] if len(sys.argv) > 1 else "compas"
    asyncio.run(_run(uri, uri_audit, db_name))


if __name__ == "__main__":
    main()
