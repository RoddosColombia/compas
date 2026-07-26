# backend/tests/test_caja_diaria.py
"""Flujo de caja DIARIO — evolución día a día del dinero (para administrar la caja).

Serie determinista a partir de las transacciones: por cada día con movimiento,
ingresos/egresos/flujo del día y la caja acumulada (saldo corriendo). Todo Decimal
(regla 1). No depende del motor ni del ciclo presupuestal — lee los movimientos reales.
"""

from decimal import Decimal

from app.caja.diaria import serie_diaria


def _m(fecha, tipo, valor):
    return {"fecha": fecha, "tipo_flujo": tipo, "valor": Decimal(valor)}


def test_serie_vacia_da_lista_vacia():
    assert serie_diaria([], Decimal("0")) == []


def test_agrupa_por_dia_y_corre_el_saldo():
    movs = [
        _m("2026-03-05", "ingreso", "3800000"),
        _m("2026-03-05", "ingreso", "2000000"),
        _m("2026-03-05", "egreso", "800000"),
        _m("2026-03-06", "egreso", "1000000"),
        _m("2026-03-08", "ingreso", "500000"),
    ]
    serie = serie_diaria(movs, Decimal("1000000"))  # caja inicial 1.000.000
    # un renglón por día con movimiento, en orden
    assert [d["fecha"] for d in serie] == ["2026-03-05", "2026-03-06", "2026-03-08"]
    d0 = serie[0]
    assert d0["ingresos"] == Decimal("5800000")
    assert d0["egresos"] == Decimal("800000")
    assert d0["flujo"] == Decimal("5000000")  # 5.8M - 0.8M
    assert d0["caja"] == Decimal("6000000")  # 1M inicial + 5M
    # el saldo corre acumulando el flujo de cada día
    assert serie[1]["flujo"] == Decimal("-1000000")
    assert serie[1]["caja"] == Decimal("5000000")
    assert serie[2]["caja"] == Decimal("5500000")


def test_orden_cronologico_aunque_lleguen_desordenados():
    movs = [
        _m("2026-04-10", "ingreso", "100"),
        _m("2026-03-01", "ingreso", "200"),
    ]
    serie = serie_diaria(movs, Decimal("0"))
    assert [d["fecha"] for d in serie] == ["2026-03-01", "2026-04-10"]
    assert serie[-1]["caja"] == Decimal("300")


def test_cuenta_movimientos_por_dia():
    movs = [_m("2026-03-05", "ingreso", "1"), _m("2026-03-05", "egreso", "1")]
    serie = serie_diaria(movs, Decimal("0"))
    assert serie[0]["n"] == 2
    assert serie[0]["caja"] == Decimal("0")
