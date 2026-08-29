#!/usr/bin/env python
"""Migración idempotente: siembra las reglas de clasificación APRENDIDAS de RF-F1.

CEO 2026-08-27 aprobó «todas» las 129 reglas propuestas (artefacto de revisión). Estas
reglas se **aprendieron** de la curaduría histórica del CEO (1.684 movimientos ya
clasificados; solo patrones 100% puros con evidencia >= 3) — no se inventaron.

Qué hace:
  · Lee la lista CONGELADA que el CEO aprobó: `migrations/data/20260827_semilla_rf_f1.json`
    (el mismo reporte que se revisó, para trazabilidad — no re-deriva de PROD).
  · Por cada propuesta crea la regla vía `proponer_regla_aprendida` → `origen=APRENDIDA`,
    **`activa=False`** (§1.9: NUNCA auto-activada; la activa el CEO por /aprobar), evento
    `regla.creada`, fail-closed O1.
  · Idempotente: salta si ya existe una regla (activa O inactiva) con el mismo
    (patrón_normalizado, tipo_flujo). Re-correr = 0 nuevas.
  · Robusta: si una propuesta choca (rubro incoherente/duplicado activo), se registra y
    se sigue — nunca aborta el lote.

NO activa ninguna regla, NO reclasifica movimientos, NO toca el motor ni meses cerrados.
La activación y la medición de la AC (≥90%) son pasos aparte.

Uso (Windows: PYTHONUTF8=1):
    MONGODB_URI_COMPAS="<uri>" MONGODB_URI_AUDIT="<uri>" \\
        python migrations/20260827_semilla_reglas_rf_f1.py [db=compas]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "backend")

from beanie import PydanticObjectId  # noqa: E402

from app.audit.service import configure_audit  # noqa: E402
from app.db import mongo  # noqa: E402
from app.domain.regla_clasificacion import (  # noqa: E402
    ReglaClasificacion,
    normalizar_texto,
)
from app.domain.rubro import TipoFlujo  # noqa: E402

DATA = Path("migrations/data/20260827_semilla_rf_f1.json")

mongo_db = None  # se fija en _run


async def _usuario_andres() -> str:
    doc = await mongo_db["users"].find_one({"email": "andres@roddos.com"})
    if not doc:
        sys.exit("ERROR: no existe el usuario andres@roddos.com en la base")
    return str(doc["_id"])


async def _ya_existe(patron: str, tipo: TipoFlujo) -> bool:
    """Idempotencia: ¿ya hay una regla (activa o inactiva) con ese patrón+tipo?"""
    pn = normalizar_texto(patron)
    r = await ReglaClasificacion.find_one(
        ReglaClasificacion.patron_normalizado == pn,
        ReglaClasificacion.tipo_flujo == tipo,
    )
    return r is not None


async def _run(uri: str, uri_audit: str, db_name: str) -> None:
    global mongo_db
    from app.reglas.service import ReglasError, proponer_regla_aprendida

    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db_name)
    mongo_db = client[db_name]
    audit_client = mongo.create_client(uri_audit)
    configure_audit(audit_client, db_name)

    usuario_id = await _usuario_andres()
    propuestas = json.loads(DATA.read_text(encoding="utf-8"))["propuestas"]
    print(f"[semilla] {len(propuestas)} reglas aprobadas en {DATA}")

    creadas = existentes = errores = 0
    for p in propuestas:
        tipo = TipoFlujo(p["tipo_flujo"])
        if await _ya_existe(p["patron"], tipo):
            existentes += 1
            continue
        try:
            await proponer_regla_aprendida(
                patron=p["patron"],
                rubro_id=PydanticObjectId(p["rubro_id"]),
                tipo_flujo=tipo,
                usuario_id=usuario_id,
                prioridad=int(p["prioridad"]),
            )
            creadas += 1
        except ReglasError as e:
            errores += 1
            print(f"  [skip-error] {p['patron']} ({tipo.value}) → {e.detalle}")

    inactivas = await ReglaClasificacion.find(
        ReglaClasificacion.activa == False  # noqa: E712
    ).count()
    print(
        f"[semilla] creadas={creadas} · ya_existían={existentes} · "
        f"errores={errores} · inactivas_totales_en_prod={inactivas}"
    )
    print("[semilla] TODAS quedan INACTIVAS — el CEO las activa por /aprobar.")
    client.close()
    audit_client.close()


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS") or os.environ.get("MONGODB_URI")
    uri_audit = os.environ.get("MONGODB_URI_AUDIT")
    if not uri or not uri_audit:
        sys.exit(
            "ERROR: faltan MONGODB_URI_COMPAS y/o MONGODB_URI_AUDIT en el entorno "
            "(nunca por argv)."
        )
    db_name = sys.argv[1] if len(sys.argv) > 1 else "compas"
    asyncio.run(_run(uri, uri_audit, db_name))


if __name__ == "__main__":
    main()
