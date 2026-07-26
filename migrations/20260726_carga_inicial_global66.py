#!/usr/bin/env python
"""Carga histórica INICIAL de Global66 (mar–jul 2026) — decisión CEO 2026-07-26.

De marzo a julio la ÚNICA cuenta con movimiento fue Global66 (Bancolombia/BBVA en $0),
así que este extracto es la foto COMPLETA de caja de esa ventana. Esta migración lo
ingiere a COMPAS reusando el flujo de carga ya auditado por Kimi (`procesar_carga`):
parse → clasificación por reglas → Transaccion, con dedup por el ID nativo de Global66
(`id_banco = ID transaccion`, único por movimiento → idempotencia perfecta).

Idempotente por diseño:
  - Rubro de sistema 'Por clasificar' y los 5 MesControl (mar..jul 2026) se siembran
    solo si faltan ($setOnInsert de facto: find_one → insert si None).
  - `procesar_carga` deduplica por (banco, id_banco): una segunda corrida NO duplica
    (todas 'duplicadas'). Si el archivo ya se cargó completo, F-02 la rechaza por hash.

NO es contabilidad: es el flujo de caja real que alimenta la predicción (norte COMPAS).

GATE (regla crítica CLAUDE.md): esto es migración de datos reales → requiere GO del CEO
+ gate-waiver trazable en el tracker (Kimi ausente) + auditoría Kimi retroactiva. Correr
esto contra prod es el acto gated; escribirlo/leerlo no lo es.

Uso (Windows: PYTHONUTF8=1). La URI NUNCA va por argv (no filtrarla al historial ni a la
lista de procesos) — se lee de la env var, igual que la app:
    export MONGODB_URI_COMPAS="mongodb+srv://..."   # o setéala en el entorno
    PYTHONUTF8=1 python migrations/20260726_carga_inicial_global66.py \
        "docs/modelo/Global66_COP_ene-jul2026.xlsx"
El path del extracto (no es secreto) sí puede ir por argv; por defecto usa el del repo.
"""

from __future__ import annotations

import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, "backend")

from app.audit import service as audit_service  # noqa: E402
from app.cargas.service import (  # noqa: E402
    CargaDuplicadaError,
    procesar_carga,
)
from app.db import mongo  # noqa: E402
from app.domain.bancos import Banco  # noqa: E402
from app.domain.mes_control import MesControl  # noqa: E402
from app.domain.rubro import Rubro, TipoFlujo  # noqa: E402
from app.domain.transaccion import Transaccion  # noqa: E402
from beanie import PydanticObjectId  # noqa: E402

RUBRO_POR_CLASIFICAR = "Por clasificar"
# Ventana real del extracto Global66 (mar–jul 2026). Meses normalizados al día 1
# (regla 2). Si el extracto trae un mes fuera de esta lista, `procesar_carga` lo
# reporta como error de fila (mes sin MesControl) — no lo adivina (regla 7).
MESES = ("2026-03-01", "2026-04-01", "2026-05-01", "2026-06-01", "2026-07-01")

DEFAULT_EXTRACTO = "docs/modelo/Global66_COP_ene-jul2026.xlsx"


async def _sembrar_prerrequisitos() -> None:
    """Idempotente: rubro 'Por clasificar' + los 5 MesControl de la ventana."""
    rubro = await Rubro.find_one(Rubro.nombre == RUBRO_POR_CLASIFICAR)
    if rubro is None:
        await Rubro(
            grupo="otros", nombre=RUBRO_POR_CLASIFICAR, orden=99, es_sistema=True
        ).insert()
        print(f"[seed] rubro de sistema '{RUBRO_POR_CLASIFICAR}' creado.")
    else:
        print(f"[seed] rubro '{RUBRO_POR_CLASIFICAR}' ya existía.")
    for mes in MESES:
        mc = await MesControl.find_one(MesControl.mes == mes)
        if mc is None:
            # saldo_inicial_caja=0: reportamos el FLUJO (neto) del mes, que es lo
            # verificable con el extracto. El saldo absoluto de caja exige el saldo
            # de apertura real de Global66 (dato que el CEO puede fijar aparte).
            await MesControl(mes=mes, saldo_inicial_caja=Decimal("0")).insert()
            print(f"[seed] MesControl {mes[:7]} abierto.")
        else:
            print(f"[seed] MesControl {mes[:7]} ya existía ({mc.estado}).")


async def _cuadre_por_mes() -> None:
    """Imprime ingreso/egreso/neto por mes desde las Transaccion cargadas (el
    cuadre que pide G2). Signo por tipo_flujo; sin rubro de ajuste aquí (carga
    inicial, no conciliación)."""
    por_mes: dict[str, dict[str, Decimal]] = {}
    id_a_mes = {}
    for mes in MESES:
        mc = await MesControl.find_one(MesControl.mes == mes)
        if mc is not None:
            id_a_mes[mc.id] = mes
            por_mes[mes] = {"ingreso": Decimal("0"), "egreso": Decimal("0"), "n": 0}

    async for t in Transaccion.find(Transaccion.banco == Banco.GLOBAL66):
        mes = id_a_mes.get(t.mes_id)
        if mes is None:
            continue
        acc = por_mes[mes]
        acc["n"] += 1
        if t.tipo_flujo is TipoFlujo.INGRESO:
            acc["ingreso"] += t.valor
        else:
            acc["egreso"] += t.valor

    print("\n=== CUADRE Global66 por mes (flujo real) ===")
    print(f"{'mes':>9} | {'movs':>5} | {'ingresos':>16} | {'egresos':>16} | {'neto':>16}")
    tot_i = tot_e = Decimal("0")
    tot_n = 0
    for mes in MESES:
        a = por_mes[mes]
        neto = a["ingreso"] - a["egreso"]
        tot_i += a["ingreso"]
        tot_e += a["egreso"]
        tot_n += a["n"]
        print(
            f"{mes[:7]:>9} | {a['n']:>5} | {a['ingreso']:>16,.2f} | "
            f"{a['egreso']:>16,.2f} | {neto:>16,.2f}"
        )
    print(
        f"{'TOTAL':>9} | {tot_n:>5} | {tot_i:>16,.2f} | {tot_e:>16,.2f} | "
        f"{tot_i - tot_e:>16,.2f}"
    )


async def _run(uri: str, db_name: str, extracto: str) -> None:
    ruta = Path(extracto)
    if not ruta.is_file():
        sys.exit(f"ERROR: no existe el extracto: {ruta.resolve()}")

    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db_name)
    audit_service.configure_audit(client, db_name)

    print(f"[db] conectado a '{db_name}'. Extracto: {ruta.name}")
    await _sembrar_prerrequisitos()

    # Preservar el original (regla dura M-04). S3 diferido (DISP-02) → dir local.
    originales = os.environ.get("ORIGINALES_DIR", "data/originales")
    Path(originales).mkdir(parents=True, exist_ok=True)

    print("\n[carga] procesando extracto Global66…")
    try:
        carga = await procesar_carga(
            banco=Banco.GLOBAL66,
            archivo_path=str(ruta),
            archivo_nombre=ruta.name,
            usuario_id=PydanticObjectId(),  # migración: actor de sistema
            dir_originales=originales,
        )
    except CargaDuplicadaError as e:
        print(f"[carga] YA CARGADO (idempotente): {e}")
        await _cuadre_por_mes()
        client.close()
        return

    print(
        f"[carga] estado={carga.estado.value} · filas={carga.total_filas} · "
        f"nuevas={carga.nuevas} · duplicadas={carga.duplicadas} · "
        f"errores={carga.errores}"
    )
    print(
        f"[clasificación] clasificadas={carga.clasificadas} · "
        f"por_clasificar={carga.por_clasificar}"
    )
    if carga.errores_detalle:
        print(f"[carga] primeros errores ({min(5, len(carga.errores_detalle))}):")
        for e in carga.errores_detalle[:5]:
            print(f"   fila {e.fila}: {e.motivo}")

    await _cuadre_por_mes()
    client.close()


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS")
    if not uri:
        sys.exit(
            "ERROR: falta la env var MONGODB_URI_COMPAS (la URI NUNCA va por argv). "
            'Ej: export MONGODB_URI_COMPAS="mongodb+srv://…" y reintenta.'
        )
    db_name = os.environ.get("MONGODB_DB", "compas")
    extracto = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EXTRACTO
    asyncio.run(_run(uri, db_name, extracto))


if __name__ == "__main__":
    main()
