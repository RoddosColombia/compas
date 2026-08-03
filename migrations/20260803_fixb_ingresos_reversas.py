#!/usr/bin/env python
"""FIX-B (Ítem 1, parte ingresos): los 38 ingresos de julio en 'Por clasificar'.

Son reversas de GMF / devoluciones / reembolsos (dinero que volvió), NO recaudo. Si
julio cierra con ellos en 'Por clasificar' quedan sellados ahí; y si cayeran a un
rubro INGRESO normal inflarían el recaudo en ~$43,4M. Decisión CEO 2026-08-03:

  - Crea rubro 'Reversas y devoluciones' (INGRESO, grupo otros, administrable — NO
    es_sistema).
  - Siembra reglas INGRESO (prio 100): 'Reversa'/'Devolución'/'Reembolso' → Reversas y
    devoluciones; 'Intereses abonados' → Recaudo de cartera.
  - La exclusión de estos del ingreso_real (recaudo) es CÓDIGO (metas_ingreso), no
    esta migración.

DRY-RUN por defecto (usa las reglas INGRESO ACTIVAS reales + las nuevas en memoria,
fiel a aplicar_pendientes); aplica solo con FIXB_APPLY=1 tras el visto. El residual de
ingresos en 'Por clasificar' DEBE quedar en 0. URI por env.

Uso:
    export MONGODB_URI_COMPAS="mongodb+srv://…"
    PYTHONUTF8=1 python migrations/20260803_fixb_ingresos_reversas.py            # DRY-RUN
    PYTHONUTF8=1 FIXB_APPLY=1 python migrations/20260803_fixb_ingresos_reversas.py  # aplica
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import Counter
from decimal import Decimal

sys.path.insert(0, "backend")

from beanie import PydanticObjectId  # noqa: E402

from app.db import mongo  # noqa: E402
from app.domain.mes_control import EstadoMes, MesControl  # noqa: E402
from app.domain.regla_clasificacion import (  # noqa: E402
    OrigenRegla,
    ReglaClasificacion,
    coincide,
    normalizar_texto,
)
from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo  # noqa: E402
from app.domain.transaccion import Transaccion  # noqa: E402
from app.reglas.service import (  # noqa: E402
    RUBRO_POR_CLASIFICAR,
    reglas_activas_por_tipo,
    rubros_activos_ids,
)

MES = "2026-07-01"
PRIORIDAD = 100
ACTOR = "system:fixb-ingresos-reversas"
RUBRO_REVERSAS = "Reversas y devoluciones"
RUBRO_RECAUDO = "Recaudo"  # nombre real en prod (0110); el CEO lo llamó 'Recaudo de cartera'
_RECAUDO_ALIAS = ("Recaudo de cartera", "Recaudo")

# Reglas INGRESO (patrón contains sin-tildes/case → rubro_nombre) — decisión CEO
REGLAS_INGRESO: list[tuple[str, str]] = [
    ("Reversa", RUBRO_REVERSAS),
    ("Devolución", RUBRO_REVERSAS),
    ("Reembolso", RUBRO_REVERSAS),
    ("Intereses abonados", RUBRO_RECAUDO),
]


def _elegir(descripcion, reglas, activos):
    for regla in sorted(reglas, key=lambda r: (r.prioridad, str(r.id))):
        if regla.rubro_id not in activos:
            continue
        if coincide(regla.patron, descripcion):
            return regla
    return None


async def _run(uri: str, db: str, aplica: bool) -> None:
    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db)
    modo = "APLICA (escribe)" if aplica else "DRY-RUN (no escribe)"
    print(f"[db] '{db}' · FIX-B ingresos (reversas) julio · {modo}\n")

    pc = await Rubro.find_one(Rubro.nombre == RUBRO_POR_CLASIFICAR)
    mc = await MesControl.find_one(MesControl.mes == MES)
    if pc is None or mc is None:
        sys.exit("FAIL-LOUD: falta 'Por clasificar' o el mes julio.")
    if mc.estado is EstadoMes.CERRADO:
        sys.exit("FAIL-LOUD: julio está CERRADO.")
    recaudo = None
    for _nombre in _RECAUDO_ALIAS:
        recaudo = await Rubro.find_one(Rubro.nombre == _nombre)
        if recaudo is not None:
            break
    if recaudo is None:
        sys.exit(f"FAIL-LOUD: no existe el rubro de recaudo (probé {_RECAUDO_ALIAS}).")

    ing_pc = [
        tx
        async for tx in Transaccion.find(
            Transaccion.rubro_id == pc.id,
            Transaccion.mes_id == mc.id,
            Transaccion.tipo_flujo == TipoFlujo.INGRESO,
        )
    ]
    print(f"=== foto ANTES === ingresos en 'Por clasificar': {len(ing_pc)}\n")

    # ── rubro Reversas y devoluciones ──
    rev = await Rubro.find_one(
        Rubro.grupo == RubroGrupo.OTROS, Rubro.nombre == RUBRO_REVERSAS
    )
    if rev is not None:
        rev_id = rev.id
        print(f"    ya existe: {RUBRO_REVERSAS} (otros, INGRESO)")
    elif aplica:
        max_orden = max([r.orden async for r in Rubro.find()] + [0])
        rev = Rubro(
            grupo=RubroGrupo.OTROS,
            nombre=RUBRO_REVERSAS,
            tipo_flujo=TipoFlujo.INGRESO,
            orden=max_orden + 1,
            activo=True,
        )
        await rev.insert()
        rev_id = rev.id
        print(f"    CREADO: {RUBRO_REVERSAS} (otros, INGRESO)")
    else:
        rev_id = PydanticObjectId()
        print(f"    [dry-run] crearía: {RUBRO_REVERSAS} (otros, INGRESO)")

    nombre_a_id = {RUBRO_REVERSAS: rev_id, RUBRO_RECAUDO: recaudo.id}

    # ── DRY-RUN fiel: reglas INGRESO ACTIVAS reales + las nuevas en memoria ──
    por_tipo = await reglas_activas_por_tipo()
    activos = await rubros_activos_ids() | {rev_id}
    reglas = list(por_tipo.get(TipoFlujo.INGRESO, []))
    for patron, rnombre in REGLAS_INGRESO:
        reglas.append(
            ReglaClasificacion(
                patron=patron,
                rubro_id=nombre_a_id[rnombre],
                tipo_flujo=TipoFlujo.INGRESO,
                prioridad=PRIORIDAD,
                origen=OrigenRegla.MANUAL,
                activa=True,
                creada_por=ACTOR,
            )
        )
    id_a_nombre = {rev_id: RUBRO_REVERSAS, recaudo.id: RUBRO_RECAUDO}
    por_rubro: Counter = Counter()
    monto: dict = {}
    resid_n = 0
    resid_m = Decimal("0")
    muestras: list[str] = []
    for tx in ing_pc:
        r = _elegir(tx.descripcion, reglas, activos)
        if r is None:
            resid_n += 1
            resid_m += tx.valor
            if len(muestras) < 8:
                muestras.append(tx.descripcion[:66])
            continue
        n = id_a_nombre.get(r.rubro_id, "(otro rubro activo)")
        por_rubro[n] += 1
        monto[n] = monto.get(n, Decimal("0")) + tx.valor

    print("\n=== lote ingresos (dry-run == aplicado) ===")
    for n, k in por_rubro.most_common():
        print(f"    {k:>4}  {monto[n]:>16,.2f}  → {n}")
    print(f"\n    residual ingresos en 'Por clasificar': {resid_n} · {resid_m:,.2f}")
    if resid_n:
        print("    ⚠ residual != 0 — estos no matchean ninguna regla (revisar):")
        for m in muestras:
            print(f"        {m!r}")

    if not aplica:
        print("\n[DRY-RUN] no se escribió nada. Para aplicar: FIXB_APPLY=1")
        client.close()
        return

    # ── APLICAR: sembrar reglas (idempotente) + aplicar_pendientes ──
    from app.reglas.service import aplicar_pendientes

    sembradas = 0
    for patron, rnombre in REGLAS_INGRESO:
        pn = normalizar_texto(patron)
        ya = await ReglaClasificacion.find_one(
            ReglaClasificacion.patron_normalizado == pn,
            ReglaClasificacion.tipo_flujo == TipoFlujo.INGRESO,
            ReglaClasificacion.activa == True,  # noqa: E712
        )
        if ya is not None:
            continue
        await ReglaClasificacion(
            patron=patron,
            rubro_id=nombre_a_id[rnombre],
            tipo_flujo=TipoFlujo.INGRESO,
            prioridad=PRIORIDAD,
            origen=OrigenRegla.MANUAL,
            activa=True,
            creada_por=ACTOR,
        ).insert()
        sembradas += 1
    print(f"\n[reglas] sembradas nuevas: {sembradas}")

    res = await aplicar_pendientes(usuario_id=ACTOR)
    print(f"[aplicar_pendientes] {res}")

    rn = await Transaccion.find(
        Transaccion.rubro_id == pc.id,
        Transaccion.mes_id == mc.id,
        Transaccion.tipo_flujo == TipoFlujo.INGRESO,
    ).count()
    print(
        f"\n=== foto DESPUÉS === residual ingresos 'Por clasificar': {rn} "
        f"({'OK ✓' if rn == 0 else '⚠ != 0'})"
    )
    client.close()


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS")
    if not uri:
        sys.exit("ERROR: falta la env var MONGODB_URI_COMPAS (nunca por argv).")
    db = os.environ.get("MONGODB_DB", "compas")
    aplica = os.environ.get("FIXB_APPLY") == "1"
    asyncio.run(_run(uri, db, aplica))


if __name__ == "__main__":
    main()
