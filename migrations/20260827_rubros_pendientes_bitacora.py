#!/usr/bin/env python
"""Migración idempotente: incorpora a COMPAS las cuentas que la «Bitácora de cuentas»
del Excel del CEO (`Flujo de pagos deudas.xlsx`) marca para replicar y que aún faltaban.

Contrato (Bitácora, decisión CEO 2026-08-19/20):
  · Sección 1 «Cuentas nuevas»: Devoluciones a clientes, Vigilancia y seguridad,
    Anticipo de nómina empleados.
  · Sección 4 «Cuentas sin uso → se replican en Compás»: Provisión parafiscales
    (las otras — Seguro créditos activos, Planillas nuevas, Deudas impuestos — ya
    existen activas en PROD).
  · Nota fila 75: se replican las 44 cuentas de egreso de la sección 2; «Por
    clasificar» es bandeja interna, NO se lleva a Compás.

Diff verificado al peso contra PROD (lectura read-only, 2026-08-27). De las 44 del
catálogo, PROD ya tenía 41 activas. Faltaban exactamente 3 + 1 reconciliación:

1. CREA (vía `crear_rubro` → evento `rubro.creado`, fail-closed O1; idempotente por
   índice único (grupo, nombre)):
     · Vigilancia y seguridad        (operacion, egreso, cod 2170)
     · Anticipo de nómina empleados  (nomina,    egreso, cod 3090)
     · Devoluciones a clientes       (otros,     egreso, cod 5090)
2. RECONCILIA (vía `editar_rubro` → evento `rubro.editado`; idempotente por skip-si-
   ya-está): PROD tiene «Parafiscales» (nomina, INACTIVO, cod 3080, 0 referencias).
   La Bitácora la nombra «Provisión parafiscales» y pide replicarla → se REACTIVA y se
   RENOMBRA al nombre canónico. NO se crea un duplicado.

NO toca: el motor, la proyección, ningún mes de control, transacciones, ni ningún otro
rubro. Crear un rubro es solo ampliar el catálogo de categorías del ciclo presupuestal
(no alimenta el motor; el costo de moto lo sigue calculando pago_inventario/fondeo).
«Producto» ya existe en PROD (cod 1010) — no se toca.

Idempotente: re-correr = 0 cambios (creates → skip por 409/pre-check; rename → skip si
ya está «Provisión parafiscales» y activo).

Uso (Windows: PYTHONUTF8=1):
    MONGODB_URI_COMPAS="<uri>" MONGODB_URI_AUDIT="<uri>" \\
        python migrations/20260827_rubros_pendientes_bitacora.py [db=compas]
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "backend")

from app.audit.service import configure_audit  # noqa: E402
from app.db import mongo  # noqa: E402
from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo  # noqa: E402
from app.rubros.service import (  # noqa: E402
    RubrosError,
    crear_rubro,
    editar_rubro,
)

# (grupo, nombre, tipo_flujo, codigo)
RUBROS_NUEVOS = [
    (RubroGrupo.OPERACION, "Vigilancia y seguridad", TipoFlujo.EGRESO, "2170"),
    (RubroGrupo.NOMINA, "Anticipo de nómina empleados", TipoFlujo.EGRESO, "3090"),
    (RubroGrupo.OTROS, "Devoluciones a clientes", TipoFlujo.EGRESO, "5090"),
]

# Reconciliación de nombre+estado: (grupo, nombre_actual, nombre_canonico)
RENOMBRA_REACTIVA = [
    (RubroGrupo.NOMINA, "Parafiscales", "Provisión parafiscales"),
]

mongo_db = None  # se fija en _run (para _usuario_andres)


async def _usuario_andres() -> str:
    doc = await mongo_db["users"].find_one({"email": "andres@roddos.com"})
    if not doc:
        sys.exit("ERROR: no existe el usuario andres@roddos.com en la base")
    return str(doc["_id"])


async def _run(uri: str, uri_audit: str, db_name: str) -> None:
    global mongo_db
    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db_name)
    mongo_db = client[db_name]

    audit_client = mongo.create_client(uri_audit)
    configure_audit(audit_client, db_name)

    usuario_id = await _usuario_andres()

    antes = await Rubro.find_all().to_list()
    print(f"[estado] rubros en PROD antes: {len(antes)}")

    # ── 1. Rubros nuevos ──
    for grupo, nombre, flujo, codigo in RUBROS_NUEVOS:
        try:
            r = await crear_rubro(
                grupo=grupo,
                nombre=nombre,
                tipo_flujo=flujo,
                usuario_id=usuario_id,
                codigo=codigo,
            )
            print(f"[rubro] CREADO {codigo} {grupo.value}/{nombre} (id={r.id})")
        except RubrosError as e:
            if e.status == 409:
                print(f"[rubro] ya existe: {grupo.value}/{nombre} (skip)")
            else:
                raise

    # ── 2. Reconciliar Parafiscales → Provisión parafiscales (reactivar+renombrar) ──
    for grupo, actual, canonico in RENOMBRA_REACTIVA:
        ya = await Rubro.find_one(Rubro.grupo == grupo, Rubro.nombre == canonico)
        if ya is not None:
            estado = "activo" if ya.activo else "INACTIVO"
            if ya.activo:
                print(f"[recon] ya existe y activo: {grupo.value}/{canonico} (skip)")
            else:
                await editar_rubro(
                    rubro_id=str(ya.id), usuario_id=usuario_id, activo=True
                )
                print(f"[recon] REACTIVADO {grupo.value}/{canonico} (estaba {estado})")
            continue
        viejo = await Rubro.find_one(Rubro.grupo == grupo, Rubro.nombre == actual)
        if viejo is None:
            print(f"[recon] no encuentro {grupo.value}/{actual} ni {canonico} (skip)")
            continue
        # reactivar + renombrar en una sola edición (evento rubro.editado)
        await editar_rubro(
            rubro_id=str(viejo.id),
            usuario_id=usuario_id,
            nombre=canonico,
            activo=True if not viejo.activo else None,
        )
        print(
            f"[recon] {grupo.value}/{actual} → «{canonico}» "
            f"(cod={viejo.codigo}, reactivado={not viejo.activo})"
        )

    despues = await Rubro.find_all().to_list()
    activos = sum(1 for r in despues if r.activo)
    print(f"[estado] rubros en PROD después: {len(despues)} ({activos} activos)")
    client.close()
    audit_client.close()


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS") or os.environ.get("MONGODB_URI")
    uri_audit = os.environ.get("MONGODB_URI_AUDIT")
    if not uri or not uri_audit:
        sys.exit(
            "ERROR: faltan MONGODB_URI_COMPAS y/o MONGODB_URI_AUDIT en el entorno "
            "(nunca por argv). Uso: MONGODB_URI_COMPAS=... MONGODB_URI_AUDIT=... "
            "python migrations/20260827_rubros_pendientes_bitacora.py [db=compas]"
        )
    db_name = sys.argv[1] if len(sys.argv) > 1 else "compas"
    asyncio.run(_run(uri, uri_audit, db_name))


if __name__ == "__main__":
    main()
