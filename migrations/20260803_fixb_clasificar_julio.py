#!/usr/bin/env python
"""FIX-B (Ítem 1 cola Kimi): clasificación de los egresos de julio 2026.

Los ~161 egresos de julio en 'Por clasificar' traen el sufijo ' — <Categoría>' en la
descripción; la Categoría == nombre del rubro del plan de cuentas (como
resolver_rubro_id de la carga curada). Este script:

  1. RUBROS (decisiones CEO 2026-08-03): crea 'Combustible motos' (costo_producto) y
     'Comisiones externas' (operacion); REACTIVA 'Planillas anteriores' (existe,
     nómina, inactivo — usado solo en julio).
  2. SIEMBRA reglas C3 (origen manual, activas, EGRESO, prioridad 100): patrón
     '— <Categoría>' → rubro homónimo; + regla explícita 'Venture 360' → 'Préstamos'
     (pago del préstamo de Raúl, única fila sin sufijo). Idempotente.
  3. DRY-RUN del lote: simula aplicar_pendientes (elegir_regla) SIN escribir → conteo
     por rubro + residual + TECHO $1M (indicador CEO). dry-run == aplicado.
  4. APLICA (FIXB_APPLY=1): crea/reactiva rubros + siembra reglas + aplicar_pendientes
     → verifica Ejecutado ≈ $372,2M y residual < $1M.

Fuera de alcance (ítem = egresos): los 38 ingresos en 'Por clasificar' (reversas GMF /
devoluciones) NO se tocan aquí. El mes debe estar ABIERTO (aplicar_pendientes salta
cerrados). URI por env, nunca argv. DRY-RUN por defecto; aplica solo con FIXB_APPLY=1
tras el visto del CEO/Kimi.

Uso:
    export MONGODB_URI_COMPAS="mongodb+srv://…"
    PYTHONUTF8=1 python migrations/20260803_fixb_clasificar_julio.py            # DRY-RUN
    PYTHONUTF8=1 FIXB_APPLY=1 python migrations/20260803_fixb_clasificar_julio.py  # aplica
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import Counter, namedtuple
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
from app.reglas.service import RUBRO_POR_CLASIFICAR  # noqa: E402

MES = "2026-07-01"
PRIORIDAD = 100
TECHO_RESIDUAL = Decimal("1000000")  # $1M (indicador CEO)
ACTOR = "system:fixb-clasificar-julio"
CAT_NO_CLASIFICABLE = "Por clasificar"  # sufijo literal → se queda pendiente

# Regla liviana en memoria para el dry-run (evita construir el Document Beanie).
_ReglaMem = namedtuple("_ReglaMem", ["patron", "rubro_id", "prioridad"])

# ── Decisiones CEO (declaradas, no derivadas) ──
RUBROS_NUEVOS: list[tuple[str, RubroGrupo]] = [
    ("Combustible motos", RubroGrupo.COSTO_PRODUCTO),  # "debe estar en costo"
    ("Comisiones externas", RubroGrupo.OPERACION),  # "debe estar en operativo"
]
RUBRO_REACTIVAR = "Planillas anteriores"  # existe (nómina, inactivo) → reactivar
# patrón explícito (sin sufijo) → rubro homónimo:
REGLAS_EXPLICITAS: list[tuple[str, str]] = [
    ("Venture 360", "Préstamos"),  # pago del préstamo de Raúl (CEO)
]


def _categoria(desc: str) -> str | None:
    for sep in (" — ", " - ", " – "):
        if sep in desc:
            return desc.rsplit(sep, 1)[1].strip()
    return None


async def _egreso_map() -> dict[str, PydanticObjectId]:
    """nombre→id de rubros EGRESO ACTIVOS; colisión prefiere operacion."""
    m: dict[str, PydanticObjectId] = {}
    async for r in Rubro.find(Rubro.activo == True):  # noqa: E712
        if r.tipo_flujo is TipoFlujo.EGRESO and (
            r.nombre not in m or r.grupo is RubroGrupo.OPERACION
        ):
            m[r.nombre] = r.id
    return m


async def _run(uri: str, db: str, aplica: bool) -> None:
    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db)
    modo = "APLICA (escribe)" if aplica else "DRY-RUN (no escribe)"
    print(f"[db] '{db}' · FIX-B egresos julio · {modo}\n")

    pc = await Rubro.find_one(Rubro.nombre == RUBRO_POR_CLASIFICAR)
    mc = await MesControl.find_one(MesControl.mes == MES)
    if pc is None or mc is None:
        sys.exit("FAIL-LOUD: falta 'Por clasificar' o el mes julio.")
    if mc.estado is EstadoMes.CERRADO:
        sys.exit("FAIL-LOUD: julio está CERRADO; aplicar_pendientes no toca cerrados.")

    # ── Foto ANTES ──
    egr_pc = [
        tx
        async for tx in Transaccion.find(
            Transaccion.rubro_id == pc.id,
            Transaccion.mes_id == mc.id,
            Transaccion.tipo_flujo == TipoFlujo.EGRESO,
        )
    ]
    print(f"=== foto ANTES === mes.estado={mc.estado.value}")
    print(f"    egresos en 'Por clasificar': {len(egr_pc)}\n")

    # ── 1. Rubros (crear + reactivar) ──
    print("=== rubros (decisiones CEO) ===")
    ids_planeados: dict[str, PydanticObjectId] = {}
    max_orden = max([r.orden async for r in Rubro.find()] + [0])
    for i, (nombre, grupo) in enumerate(RUBROS_NUEVOS, 1):
        ex = await Rubro.find_one(Rubro.grupo == grupo, Rubro.nombre == nombre)
        if ex is not None:
            print(f"    ya existe: {nombre} ({grupo.value})")
            ids_planeados[nombre] = ex.id
        elif aplica:
            r = Rubro(
                grupo=grupo,
                nombre=nombre,
                tipo_flujo=TipoFlujo.EGRESO,
                orden=max_orden + i,
                activo=True,
            )
            await r.insert()
            ids_planeados[nombre] = r.id
            print(f"    CREADO: {nombre} ({grupo.value})")
        else:
            ids_planeados[nombre] = PydanticObjectId()  # sentinela dry-run
            print(f"    [dry-run] crearía: {nombre} ({grupo.value})")
    plan = await Rubro.find_one(Rubro.nombre == RUBRO_REACTIVAR)
    if plan is None:
        sys.exit(f"FAIL-LOUD: no existe el rubro '{RUBRO_REACTIVAR}' a reactivar.")
    ids_planeados[RUBRO_REACTIVAR] = plan.id
    if plan.activo:
        print(f"    ya activo: {RUBRO_REACTIVAR}")
    elif aplica:
        plan.activo = True
        await plan.save()
        print(f"    REACTIVADO: {RUBRO_REACTIVAR}")
    else:
        print(f"    [dry-run] reactivaría: {RUBRO_REACTIVAR}")

    # ── 2. Mapeo nombre→id (activos + planeados) ──
    nombre_a_id = await _egreso_map()
    nombre_a_id.update(ids_planeados)  # incluye nuevos/reactivado (real o sentinela)

    # ── 3. Especificar reglas (patrón → rubro_nombre), derivadas de los datos ──
    cats = {c for tx in egr_pc if (c := _categoria(tx.descripcion))}
    specs: list[tuple[str, str]] = []  # (patron, rubro_nombre)
    for cat in sorted(cats):
        if cat == CAT_NO_CLASIFICABLE:
            continue
        specs.append((f"— {cat}", cat))  # rubro homónimo (name-match)
    specs.extend(REGLAS_EXPLICITAS)

    # resolver + validar (fail-loud si algún rubro no existe)
    reglas_mem: list[
        tuple[str, PydanticObjectId, str]
    ] = []  # (patron, rubro_id, nombre)
    sin_rubro: list[str] = []
    for patron, rnombre in specs:
        rid = nombre_a_id.get(rnombre)
        if rid is None:
            sin_rubro.append(f"{patron!r} → rubro {rnombre!r} INEXISTENTE")
        else:
            reglas_mem.append((patron, rid, rnombre))
    if sin_rubro:
        print("\nFAIL-LOUD: reglas sin rubro (no se siembra ninguna):")
        for s in sin_rubro:
            print(f"    {s}")
        client.close()
        sys.exit(1)

    # ── 4. DRY-RUN del lote: simular elegir_regla sobre cada egreso pendiente ──
    reglas_obj = [_ReglaMem(p, rid, PRIORIDAD) for p, rid, _ in reglas_mem]
    activos = set(nombre_a_id.values())
    id_a_nombre = {rid: n for n, rid in nombre_a_id.items()}
    por_rubro: Counter = Counter()
    monto_rubro: dict[str, Decimal] = {}
    residual_n = 0
    residual_monto = Decimal("0")
    for tx in egr_pc:
        regla = _elegir(tx.descripcion, reglas_obj, activos)
        if regla is None:
            residual_n += 1
            residual_monto += tx.valor
            continue
        n = id_a_nombre.get(regla.rubro_id, "?")
        por_rubro[n] += 1
        monto_rubro[n] = monto_rubro.get(n, Decimal("0")) + tx.valor

    print("\n=== lote (dry-run == aplicado) ===")
    for n, k in por_rubro.most_common():
        print(f"    {k:>4}  {monto_rubro[n]:>16,.2f}  → {n}")
    print(
        f"\n    residual 'Por clasificar' egreso: {residual_n} · {residual_monto:,.2f}"
    )
    ok_techo = residual_monto <= TECHO_RESIDUAL
    print(f"    TECHO ${TECHO_RESIDUAL:,.0f}: {'OK ✓' if ok_techo else '⚠ EXCEDIDO'}")
    if not ok_techo:
        print(
            "    ⚠ INDICADOR: el residual supera el techo — revisar antes de aplicar."
        )

    if not aplica:
        print("\n[DRY-RUN] no se escribió nada. Para aplicar: FIXB_APPLY=1")
        client.close()
        return

    # ── 5. APLICAR: sembrar reglas (idempotente) + aplicar_pendientes ──
    from app.reglas.service import aplicar_pendientes

    sembradas = 0
    for patron, rid, _ in reglas_mem:
        pn = normalizar_texto(patron)
        ya = await ReglaClasificacion.find_one(
            ReglaClasificacion.patron_normalizado == pn,
            ReglaClasificacion.tipo_flujo == TipoFlujo.EGRESO,
            ReglaClasificacion.activa == True,  # noqa: E712
        )
        if ya is not None:
            continue
        await ReglaClasificacion(
            patron=patron,
            rubro_id=rid,
            tipo_flujo=TipoFlujo.EGRESO,
            prioridad=PRIORIDAD,
            origen=OrigenRegla.MANUAL,
            activa=True,
            creada_por=ACTOR,
        ).insert()
        sembradas += 1
    print(f"\n[reglas] sembradas nuevas: {sembradas}")

    res = await aplicar_pendientes(usuario_id=ACTOR)
    print(f"[aplicar_pendientes] {res}")

    # verificación
    ejec = Decimal("0")
    async for tx in Transaccion.find(
        Transaccion.mes_id == mc.id, Transaccion.tipo_flujo == TipoFlujo.EGRESO
    ):
        ejec += tx.valor
    resid = Decimal("0")
    rn = 0
    async for tx in Transaccion.find(
        Transaccion.rubro_id == pc.id,
        Transaccion.mes_id == mc.id,
        Transaccion.tipo_flujo == TipoFlujo.EGRESO,
    ):
        resid += tx.valor
        rn += 1
    print("\n=== foto DESPUÉS ===")
    print(f"    Ejecutado julio (EGRESO total): {ejec:,.2f}  (objetivo ~372.200.786)")
    print(
        f"    residual 'Por clasificar' egreso: {rn} · {resid:,.2f}  "
        f"(techo ${TECHO_RESIDUAL:,.0f}: {'OK' if resid <= TECHO_RESIDUAL else 'EXCEDIDO'})"
    )
    client.close()


def _elegir(descripcion: str, reglas, activos):
    """Espejo de reglas.service.elegir_regla (para el dry-run en memoria)."""
    for regla in sorted(reglas, key=lambda r: (r.prioridad, str(r.rubro_id))):
        if regla.rubro_id not in activos:
            continue
        if coincide(regla.patron, descripcion):
            return regla
    return None


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS")
    if not uri:
        sys.exit("ERROR: falta la env var MONGODB_URI_COMPAS (nunca por argv).")
    db = os.environ.get("MONGODB_DB", "compas")
    aplica = os.environ.get("FIXB_APPLY") == "1"
    asyncio.run(_run(uri, db, aplica))


if __name__ == "__main__":
    main()
