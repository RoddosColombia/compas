#!/usr/bin/env python
"""FIX-H (higiene): sanea la divergencia semilla↔PROD del rubro de recaudo.

PROD tiene el rubro de sistema **'Recaudo'** (0110, ingresos_operativos), pero el
guard `es_sistema` (FIX-A/P0-1) y toda la base de código (semilla, reglas C3 'Abono'/
'Recibido de', tests) usan **'Recaudo de cartera'**. Consecuencia real: la whitelist
`RUBROS_SISTEMA_CLASIFICABLES` NO contiene 'Recaudo' → `es_rubro_clasificable('Recaudo')
= False` → clasificar/reclasificar un abono hacia el recaudo queda BLOQUEADO. Además
`seed_reglas_reporte` es fail-loud contra 'Recaudo de cartera' (re-seed rompería).

El nombre NO afecta `rubro_id` (las reglas y transacciones referencian por id), así que
renombrar es no-destructivo y restaura la consistencia. Decisión CEO 2026-08-03:

  - PROD tiene 'Recaudo' y NO existe 'Recaudo de cartera' → renombrar a
    'Recaudo de cartera' (emite rubro.editado, saga O1).
  - Si AMBOS existen → COLISIÓN: reporta y NO toca nada.
  - Si ya está 'Recaudo de cartera' y no existe 'Recaudo' → no-op idempotente.
  - Si no existe ninguno → fail-loud.

DRY-RUN por defecto; aplica con FIXH_APPLY=1. URI por env, nunca por argv. Verifica
tras el rename: es_rubro_clasificable=True y las reglas que apuntan al rubro resuelven.

Uso:
    export MONGODB_URI_COMPAS="mongodb+srv://…"
    PYTHONUTF8=1 python migrations/20260803_fixh_rename_recaudo.py            # DRY-RUN
    PYTHONUTF8=1 FIXH_APPLY=1 python migrations/20260803_fixh_rename_recaudo.py  # aplica
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "backend")

from app.audit import service as audit_service  # noqa: E402
from app.audit.events import AuditEvento  # noqa: E402
from app.db import mongo  # noqa: E402
from app.domain.regla_clasificacion import ReglaClasificacion  # noqa: E402
from app.domain.rubro import (  # noqa: E402
    RUBROS_SISTEMA_CLASIFICABLES,
    Rubro,
    RubroGrupo,
    es_rubro_clasificable,
)

VIEJO = "Recaudo"
NUEVO = "Recaudo de cartera"
ACTOR = "system:fixh-rename-recaudo"

CLAVE = [
    VIEJO,
    NUEVO,
    "Por clasificar",
    "Ajuste de conciliación",
    "Reversas y devoluciones",
    "Tránsito Wava mes anterior",
]


async def _foto(titulo: str) -> None:
    print(f"=== {titulo} ===")
    print(f"whitelist guard: {sorted(RUBROS_SISTEMA_CLASIFICABLES)}")
    for n in CLAVE:
        rs = await Rubro.find(Rubro.nombre == n).to_list()
        if not rs:
            print(f"    {n:<32} (NO EXISTE)")
            continue
        for r in rs:
            print(
                f"    {r.nombre:<32} grupo={r.grupo.value:<20} cod={r.codigo or '-':<5}"
                f" sist={r.es_sistema!s:<5} act={r.activo!s:<5}"
                f" clasificable={es_rubro_clasificable(r)}"
            )
    print()


async def _run(uri: str, db: str, aplica: bool) -> None:
    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db)
    audit_service.configure_audit(client, db)
    modo = "APLICA (escribe)" if aplica else "DRY-RUN (no escribe)"
    print(f"[db] '{db}' · FIX-H rename recaudo · {modo}\n")

    await _foto("foto ANTES")

    viejo = await Rubro.find_one(
        Rubro.nombre == VIEJO, Rubro.grupo == RubroGrupo.INGRESOS_OPERATIVOS
    )
    nuevo = await Rubro.find_one(Rubro.nombre == NUEVO)

    # ── casos ──
    if viejo is not None and nuevo is not None:
        print(
            f"COLISIÓN: existen AMBOS '{VIEJO}' (id {viejo.id}) y '{NUEVO}' "
            f"(id {nuevo.id}). Decisión CEO: reportar y NO tocar. Sin cambios."
        )
        client.close()
        return
    if viejo is None and nuevo is not None:
        print(
            f"[no-op idempotente] ya existe '{NUEVO}' (id {nuevo.id}) y no hay '{VIEJO}'."
        )
        client.close()
        return
    if viejo is None and nuevo is None:
        sys.exit(
            f"FAIL-LOUD: no existe ni '{VIEJO}' ni '{NUEVO}' en ingresos_operativos."
        )

    # viejo existe, nuevo no → renombrar
    if not viejo.es_sistema:
        print(
            f"AVISO: '{VIEJO}' no es es_sistema (esperado True); continúo el rename igual."
        )
    refs = await ReglaClasificacion.find(
        ReglaClasificacion.rubro_id == viejo.id
    ).count()
    print(
        f"→ renombrar '{VIEJO}' (id {viejo.id}, cod {viejo.codigo}, "
        f"sist={viejo.es_sistema}) a '{NUEVO}'. Reglas que lo referencian: {refs} "
        "(por rubro_id → intactas)."
    )

    if not aplica:
        print("\n[DRY-RUN] no se escribió nada. Para aplicar: FIXH_APPLY=1")
        client.close()
        return

    # ── APLICA (con saga O1 en el emit) ──
    prev = viejo.nombre
    viejo.nombre = NUEVO
    await viejo.save()
    try:
        await audit_service.emit_audit(
            AuditEvento.rubro_editado,
            entidad="rubro",
            entidad_id=str(viejo.id),
            actor_id=ACTOR,
            metadata={"cambios": {"nombre": {"anterior": prev, "nuevo": NUEVO}}},
        )
    except Exception:
        # Saga O1: sin auditoría no hay operación → revertir y propagar.
        viejo.nombre = prev
        await viejo.save()
        client.close()
        raise

    print(f"\n[OK] renombrado '{prev}' → '{NUEVO}' + evento rubro.editado emitido.\n")

    # ── verificación post-rename ──
    r2 = await Rubro.get(viejo.id)
    clasif = es_rubro_clasificable(r2)
    print("=== verificación ===")
    print(f"    nombre actual:            {r2.nombre}")
    print(f"    en whitelist:             {r2.nombre in RUBROS_SISTEMA_CLASIFICABLES}")
    print(
        f"    es_rubro_clasificable:    {clasif}  ({'OK ✓' if clasif else '⚠ sigue bloqueado'})"
    )
    print(f"    reglas referencian id:    {refs} (intactas, por rubro_id)")
    client.close()


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS")
    if not uri:
        sys.exit("ERROR: falta la env var MONGODB_URI_COMPAS (nunca por argv).")
    db = os.environ.get("MONGODB_DB", "compas")
    aplica = os.environ.get("FIXH_APPLY") == "1"
    asyncio.run(_run(uri, db, aplica))


if __name__ == "__main__":
    main()
