#!/usr/bin/env python
"""Bootstrap del saldo inicial de julio 2026 (op de datos, patrón migración).

La migración inicial sembró `MesControl(2026-07-01).saldo_inicial_caja = 0`, pero la
apertura REAL de caja de julio es el saldo de Global66 al 30-jun = **814.796.138,93**
(confirmado por el CEO del extracto). Con saldo 0 la conciliación no cuadra (C_M queda
~149M por debajo); con el saldo real, C_M ≈ 665.715.591 vs reportado ≈ 665.715.578 →
diferencia ≈ −13 COP, dentro del umbral. Este script fija ese saldo inicial y emite
`saldo_inicial.editado` (catálogo cerrado, verificado presente).

Guardas (fail-loud, NO pisa un valor real):
  - el mes debe existir y estar `en_ejecucion`;
  - si el saldo ya es el objetivo → no-op idempotente (re-ejecución segura);
  - si el saldo es 0 → aplica;
  - si el saldo es cualquier otro valor → ABORTA (no sobrescribe un dato real).

Reusa `cierre.service.conciliacion` (compute-only) para imprimir el cuadre; el emit va
con saga O1 (si falla, revierte el saldo). URI por env var, nunca por argv.

Uso (DRY-RUN por defecto; aplica SOLO con BOOTSTRAP_APPLY=1, tras el visto del CEO):
    export MONGODB_URI_COMPAS="mongodb+srv://…"
    PYTHONUTF8=1 python migrations/20260802_bootstrap_saldo_inicial_julio.py        # DRY-RUN
    PYTHONUTF8=1 BOOTSTRAP_APPLY=1 python migrations/20260802_bootstrap_saldo_inicial_julio.py  # aplica
"""

from __future__ import annotations

import asyncio
import os
import sys
from decimal import Decimal

sys.path.insert(0, "backend")

from app.audit import service as audit_service  # noqa: E402
from app.audit.events import AuditEvento  # noqa: E402
from app.cierre import service as cierre_service  # noqa: E402
from app.core.money import money_str  # noqa: E402
from app.db import mongo  # noqa: E402
from app.domain.mes_control import EstadoMes, MesControl  # noqa: E402
from app.domain.transaccion import Transaccion  # noqa: E402

MES = "2026-07-01"
OBJETIVO = Decimal("814796138.93")  # apertura real Global66 al 30-jun (CEO)
ACTOR = "system:bootstrap-saldo-inicial-julio"
MOTIVO = "bootstrap: apertura real Global66 al 30-jun, la migración inicial sembró 0"


async def _cuadre(mes: str) -> tuple[dict | None, str | None]:
    """Conciliación compute-only (no escribe). Devuelve (dict, None) o (None, error)."""
    try:
        return await cierre_service.conciliacion(mes), None
    except cierre_service.CierreError as e:
        return None, e.detalle


def _linea_cuadre(r: dict) -> None:
    print(f"    consolidado_reportado (R_M) : {r['consolidado_reportado']}")
    print(f"    caja_libro            (C_M) : {r['caja_libro']}")
    print(f"    diferencia (R_M - C_M)      : {r['diferencia']}")
    print(f"    umbral                      : {r['umbral']}")
    print(f"    dentro_de_umbral            : {r['dentro_de_umbral']}")
    print(f"    sin_dato                    : {r['sin_dato']}")
    print(f"    aviso_manual                : {r['aviso_manual']}")


async def _run(uri: str, db_name: str, aplica: bool) -> None:
    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db_name)
    audit_service.configure_audit(client, db_name)
    modo = "APLICA (escribe)" if aplica else "DRY-RUN (no escribe)"
    print(f"[db] '{db_name}' · mes {MES[:7]} · {modo}\n")

    mc = await MesControl.find_one(MesControl.mes == MES)
    if mc is None:
        sys.exit(f"FAIL-LOUD: no existe MesControl({MES}). Aborta.")
    n_txs = await Transaccion.find(Transaccion.mes_id == mc.id).count()

    # ── Foto ANTES ──
    print("=== foto ANTES ===")
    print(f"    estado             : {mc.estado.value}")
    print(f"    saldo_inicial_caja : {money_str(mc.saldo_inicial_caja)}")
    print(f"    #transacciones     : {n_txs}\n")

    # ── Guardas (fail-loud) ──
    if mc.estado is not EstadoMes.EN_EJECUCION:
        sys.exit(
            f"FAIL-LOUD: el mes está en '{mc.estado.value}', no en_ejecucion. "
            "El bootstrap solo corre sobre el mes operando. Aborta."
        )
    if mc.saldo_inicial_caja == OBJETIVO:
        print(
            f"[idempotente] el saldo inicial YA es {money_str(OBJETIVO)} → no-op. "
            "Nada que hacer."
        )
        client.close()
        return
    if mc.saldo_inicial_caja != Decimal("0"):
        sys.exit(
            "FAIL-LOUD: el saldo inicial actual es "
            f"{money_str(mc.saldo_inicial_caja)} (ni 0 ni el objetivo). NO se "
            "sobrescribe un valor real sin revisión. Aborta."
        )

    # ── Preview del cuadre con el saldo NUEVO (sin escribir) ──
    # La conciliación actual usa saldo=0 → su caja_libro == Σ signo(tx). Con el saldo
    # nuevo: C_M(nuevo) = OBJETIVO + Σ signo(tx); diferencia = R_M − C_M(nuevo).
    r0, err = await _cuadre(MES)
    print("=== foto DESPUÉS (proyectada) ===")
    print(
        f"    saldo_inicial_caja : {money_str(mc.saldo_inicial_caja)} → {money_str(OBJETIVO)}"
    )
    if err:
        print(f"    (no se pudo calcular el cuadre ahora: {err})")
        print("    reporta el saldo Global66 al 31-jul para ver el cuadre final.")
    else:
        sigma = Decimal(r0["caja_libro"])  # con saldo=0, caja_libro == Σ signo(tx)
        c_m_nuevo = OBJETIVO + sigma
        r_m = Decimal(r0["consolidado_reportado"])
        print(f"    consolidado_reportado (R_M) : {money_str(r_m)}")
        print(f"    caja_libro proyectado (C_M) : {money_str(c_m_nuevo)}")
        print(f"    diferencia proyectada       : {money_str(r_m - c_m_nuevo)}")
        print(f"    umbral                      : {r0['umbral']}")
        if r0["sin_dato"]:
            print(
                f"    (bancos sin saldo reportado : {r0['sin_dato']} — reporta el "
                "saldo Global66 al 31-jul para el cuadre real)"
            )
    print()

    if not aplica:
        print("[DRY-RUN] no se escribió nada. Para aplicar: BOOTSTRAP_APPLY=1")
        client.close()
        return

    # ── APLICA (con saga O1 en el emit) ──
    prev = mc.saldo_inicial_caja
    mc.saldo_inicial_caja = OBJETIVO
    await mc.save()
    try:
        await audit_service.emit_audit(
            AuditEvento.saldo_inicial_editado,
            entidad="mes",
            entidad_id=str(mc.id),
            actor_id=ACTOR,
            metadata={
                "mes": MES[:7],
                "anterior": money_str(prev),
                "nuevo": money_str(OBJETIVO),
                "motivo": MOTIVO,
            },
        )
    except Exception:
        # Saga O1: sin auditoría no hay operación → revertir y propagar.
        mc.saldo_inicial_caja = prev
        await mc.save()
        client.close()
        raise

    print(
        f"[OK] saldo_inicial_caja fijado a {money_str(OBJETIVO)} + evento "
        "saldo_inicial.editado emitido.\n"
    )

    # ── Conciliación resultante REAL (post-escritura) ──
    r2, err2 = await _cuadre(MES)
    print("=== conciliación resultante ===")
    if err2:
        print(f"    (no disponible: {err2})")
    else:
        _linea_cuadre(r2)
    client.close()


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS")
    if not uri:
        sys.exit("ERROR: falta la env var MONGODB_URI_COMPAS (nunca por argv).")
    db_name = os.environ.get("MONGODB_DB", "compas")
    aplica = os.environ.get("BOOTSTRAP_APPLY") == "1"
    asyncio.run(_run(uri, db_name, aplica))


if __name__ == "__main__":
    main()
