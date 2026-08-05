#!/usr/bin/env python
"""FIX-K — cronograma real Auteco sep–dic 2026 (9 facturas del Excel del CEO).

Siembra la obligación Auteco (naturaleza=facturacion, es_sistema) + las 9
FacturaObligacion con saldo pendiente y plazo 150 días. La reconciliación D2 §4 (ya
desplegada) las netea del Auteco paramétrico → la proyección muestra esos pagos FIJOS
en sep–dic (columna `pago_inventario`); enero+ sigue el motor. Las 3 facturas ya
pagadas NO se cargan (la obligación queda con pendiente = cartera 1.016.593.087).

mes_pago lo deriva la reconciliación (fecha + plazo//30 = +5 meses): abr→sep, may→oct,
jun→nov, jul→dic. La migración VERIFICA los totales de control (regla 7): si no cuadran,
FALLA ruidoso (no inventa). Términos: plazo_base=150, tasa_excedente=0 → el pago = saldo
exacto (el saldo YA es el monto a pagar; no se inventa interés).

Idempotente por (obligacion_id, numero). DRY-RUN por defecto; URI por env (nunca argv).

Uso:
    export MONGODB_URI_COMPAS="mongodb+srv://…"
    PYTHONUTF8=1 python migrations/20260804_fixk_auteco_facturas.py    # DRY-RUN
    PYTHONUTF8=1 FIXK_APPLY=1 python migrations/20260804_fixk_auteco_facturas.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from decimal import Decimal

sys.path.insert(0, "backend")

from app.core.time import now_utc  # noqa: E402
from app.domain.obligacion import FacturaObligacion, Obligacion  # noqa: E402
from app.obligaciones.calculadora import pago_factura  # noqa: E402

ACREEDOR = "Auteco"
OBLIGACION_NOMBRE = "Inventario Auteco"
PLAZO_DIAS = 150
PLAZO_BASE_DIAS = (
    150  # = plazo → sin excedente: el pago es el saldo exacto (no inventa interés)
)
TASA_EXCEDENTE = Decimal("0")

# Las 9 facturas PENDIENTES (mueven caja futura). Las 3 saldadas NO se cargan.
FACTURAS: list[dict] = [
    {
        "numero": "E670161540",
        "fecha": "2026-04-25",
        "valor": "55650754",
        "nota": "parcial; NC $9.988.758 (prob. devol. 2 Sport 100, hip. CEO)",
    },
    {"numero": "E670162095", "fecha": "2026-04-29", "valor": "67741277", "nota": ""},
    {
        "numero": "E670165520",
        "fecha": "2026-05-29",
        "valor": "149030808",
        "nota": "22 Raider",
    },
    {
        "numero": "E670166361",
        "fecha": "2026-06-09",
        "valor": "88063659",
        "nota": "13 Raider",
    },
    {
        "numero": "E670167401",
        "fecha": "2026-06-20",
        "valor": "167604848",
        "nota": "20 Apache",
    },
    {
        "numero": "E670169372",
        "fecha": "2026-07-09",
        "valor": "124447190",
        "nota": "6 Raider + 10 Apache",
    },
    {
        "numero": "E670169887",
        "fecha": "2026-07-16",
        "valor": "167604848",
        "nota": "20 Apache",
    },
    {
        "numero": "E670170142",
        "fecha": "2026-07-21",
        "valor": "94837788",
        "nota": "14 Raider",
    },
    {
        "numero": "E670170297",
        "fecha": "2026-07-21",
        "valor": "101611915",
        "nota": "15 Raider",
    },
]

# Totales de control por mes de pago (regla 7: el script falla si no cuadran).
TOTALES_CONTROL = {
    "2026-09": Decimal("123392031"),
    "2026-10": Decimal("149030808"),
    "2026-11": Decimal("255668507"),
    "2026-12": Decimal("488501741"),
}
TOTAL_CARTERA = Decimal("1016593087")


def verificar_totales() -> dict[str, Decimal]:
    """Deriva mes_pago (fecha + plazo//30) y suma el capital por mes; falla si no cuadra
    con los totales de control (regla 7 — no se adivina)."""
    por_mes: dict[str, Decimal] = {}
    for f in FACTURAS:
        p = pago_factura(
            fecha_factura=f["fecha"],
            valor=Decimal(f["valor"]),
            plazo_elegido_dias=PLAZO_DIAS,
            plazo_base_dias=PLAZO_BASE_DIAS,
            tasa_excedente_mensual=TASA_EXCEDENTE,
        )
        por_mes[p.mes] = por_mes.get(p.mes, Decimal("0")) + p.capital
    if por_mes != TOTALES_CONTROL:
        raise SystemExit(
            f"[FALLA regla 7] los totales por mes NO cuadran:\n"
            f"  calculado = {dict(sorted(por_mes.items()))}\n"
            f"  control   = {dict(sorted(TOTALES_CONTROL.items()))}"
        )
    total = sum(por_mes.values())
    if total != TOTAL_CARTERA:
        raise SystemExit(f"[FALLA regla 7] total {total} != cartera {TOTAL_CARTERA}")
    return por_mes


async def _run(uri: str, db: str, aplica: bool) -> None:
    from app.db import mongo

    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db)
    modo = "APLICA (escribe)" if aplica else "DRY-RUN (no escribe)"
    print(f"[db] '{db}' · FIX-K facturas Auteco · {modo}\n")

    # (0) verificación de totales ANTES de tocar nada (fail-loud).
    por_mes = verificar_totales()
    print("[verif] totales por mes cuadran con el control (regla 7):")
    for mes, val in sorted(por_mes.items()):
        print(f"    {mes} = {val}")
    print(f"    TOTAL = {sum(por_mes.values())}\n")

    # (a) obligación Auteco (idempotente por acreedor+naturaleza).
    obl = await Obligacion.find_one(
        Obligacion.acreedor == ACREEDOR, Obligacion.naturaleza == "facturacion"
    )
    if obl is not None:
        print(f"[obligacion] ya existe: {obl.nombre} ({obl.id}) — no se recrea.")
    elif aplica:
        obl = Obligacion(
            nombre=OBLIGACION_NOMBRE,
            acreedor=ACREEDOR,
            naturaleza="facturacion",
            es_sistema=True,
            creado_por="migracion-fixk",
            actualizado_at=now_utc(),
            plazo_base_dias=PLAZO_BASE_DIAS,
            plazo_max_dias=PLAZO_DIAS,
            tasa_excedente_mensual=TASA_EXCEDENTE,
        )
        await obl.insert()
        print(f"[obligacion] CREADA: {OBLIGACION_NOMBRE} (facturacion, es_sistema).")
    else:
        print(f"[obligacion] [dry-run] crearía: {OBLIGACION_NOMBRE} (facturacion).")

    # (b) las 9 facturas (idempotente por numero dentro de la obligación).
    creadas = 0
    for f in FACTURAS:
        ya = None
        if obl is not None:
            ya = await FacturaObligacion.find_one(
                FacturaObligacion.obligacion_id == obl.id,
                FacturaObligacion.numero == f["numero"],
            )
        if ya is not None:
            print(f"    [factura] {f['numero']} ya existe — no se toca.")
        elif aplica and obl is not None:
            await FacturaObligacion(
                obligacion_id=obl.id,
                numero=f["numero"],
                fecha_factura=f["fecha"],
                valor=Decimal(f["valor"]),
                plazo_elegido_dias=PLAZO_DIAS,
                nota=f["nota"] or None,
                registrada_por="migracion-fixk",
                registrada_at=now_utc(),
            ).insert()
            creadas += 1
            print(f"    [factura] CREADA {f['numero']} {f['fecha']} ${f['valor']}")
        else:
            print(f"    [factura] [dry-run] crearía {f['numero']} ${f['valor']}")

    print(f"\n[resumen] facturas creadas: {creadas} (esperado 9 en un apply limpio)")
    if not aplica:
        print("[DRY-RUN] no se escribió nada. Para aplicar: FIXK_APPLY=1")
    client.close()


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS")
    if not uri:
        sys.exit("ERROR: falta la env var MONGODB_URI_COMPAS (nunca por argv).")
    db = os.environ.get("MONGODB_DB", "compas")
    aplica = os.environ.get("FIXK_APPLY") == "1"
    asyncio.run(_run(uri, db, aplica))


if __name__ == "__main__":
    main()
