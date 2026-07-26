# backend/app/caja/diaria.py
"""Flujo de caja DIARIO — la evolución día a día del dinero, para administrar la caja.

Función PURA (sin Mongo): agrupa las transacciones por día y corre el saldo. No depende
del motor de proyección ni del ciclo presupuestal — trabaja sobre los movimientos reales
ya cargados. Todo Decimal (regla 1). El servicio la alimenta con las transacciones del
rango y el saldo inicial (configurable; 0 = saldo relativo desde el inicio del rango).
"""

from decimal import Decimal

from app.domain.rubro import TipoFlujo


def serie_diaria(movimientos: list[dict], caja_inicial: Decimal) -> list[dict]:
    """Devuelve, por cada día CON movimiento (orden cronológico), un dict con
    ingresos/egresos/flujo del día, nº de movimientos y la caja acumulada (saldo
    corriendo = caja_inicial + Σ flujo hasta ese día).

    `movimientos`: dicts con `fecha` ('YYYY-MM-DD'), `tipo_flujo` ('ingreso'/'egreso'
    o TipoFlujo) y `valor` (Decimal, magnitud positiva)."""
    por_dia: dict[str, dict] = {}
    for m in movimientos:
        f = m["fecha"]
        acc = por_dia.setdefault(
            f, {"ingresos": Decimal("0"), "egresos": Decimal("0"), "n": 0}
        )
        acc["n"] += 1
        tf = m["tipo_flujo"]
        es_ingreso = tf == TipoFlujo.INGRESO or tf == "ingreso"
        if es_ingreso:
            acc["ingresos"] += m["valor"]
        else:
            acc["egresos"] += m["valor"]

    serie: list[dict] = []
    caja = caja_inicial
    for fecha in sorted(por_dia):
        a = por_dia[fecha]
        flujo = a["ingresos"] - a["egresos"]
        caja += flujo
        serie.append(
            {
                "fecha": fecha,
                "ingresos": a["ingresos"],
                "egresos": a["egresos"],
                "flujo": flujo,
                "caja": caja,
                "n": a["n"],
            }
        )
    return serie
