# backend/tests/test_e1_lectura.py
"""E1 · P1 — mapeo de la ejecución real a los conceptos del motor (función pura).

Cubre: B9 (Σ rubros == concepto, fixture del Plan de Cuentas real) · B12 (código del
mapeo ausente → error ruidoso) · A1 (neutros excluidos por rubro_id) · R-1 (1010 entero
a pago_inventario) · R-2 (4040 en sin_mapear)."""

from decimal import Decimal

import pytest
from app.proyeccion.ejecucion.lectura import (
    RubroInfo,
    mapear_a_conceptos,
)

# Fixture: el Plan de Cuentas real (código, grupo, nombre, es_sistema) — mismo que
# domain/rubro.py._seed(). El `id` es sintético (str del código) para el test puro.
_PLAN = [
    # ingresos
    ("0110", "ingresos_operativos", "Recaudo de cartera", True),
    ("0120", "ingresos_operativos", "Cuotas iniciales", False),
    ("0130", "ingresos_operativos", "RODANTE (crédito de repuestos)", False),
    ("0140", "ingresos_operativos", "Otros ingresos", False),
    # costo producto
    ("1010", "costo_producto", "Producto", False),
    ("1020", "costo_producto", "SOAT/Matrículas", False),
    ("1030", "costo_producto", "Seguros (Hunter)", False),
    # operación (muestra + 2130/2140 que el I-PLAN no listaba → por grupo igual entran)
    ("2010", "operacion", "Arriendos", False),
    ("2070", "operacion", "Transporte/peajes/combustible/parqueo", False),
    ("2140", "operacion", "Freelance", False),
    # nómina
    ("3010", "nomina", "Sueldos empleados", False),
    # deudas
    ("4010", "deudas_obligaciones", "Préstamos", False),
    ("4020", "deudas_obligaciones", "Deudas tarjetas de crédito", False),
    ("4030", "deudas_obligaciones", "Garantía cupo (Auteco)", False),
    ("4040", "deudas_obligaciones", "Deudas impuestos", False),
    ("4050", "deudas_obligaciones", "Deudas proveedores anteriores", False),
    ("4060", "deudas_obligaciones", "Inventario Auteco (150 días)", False),
    ("4070", "deudas_obligaciones", "Rodante – Financiación a clientes", False),
    # otros
    ("5010", "otros", "Otros gastos", False),
    ("5060", "otros", "Impuestos", False),
    ("5070", "otros", "Por clasificar", True),
    # sistema sin código (neutros)
    (None, "otros", "Ajuste de conciliación", True),
    (None, "otros", "Reversas y devoluciones", False),
    (None, "ingresos_operativos", "Tránsito Wava mes anterior", True),
]


def _rubros() -> list[RubroInfo]:
    return [
        RubroInfo(id=nombre, codigo=cod, grupo=gr, nombre=nombre, es_sistema=sis)
        for (cod, gr, nombre, sis) in _PLAN
    ]


def _valores(**por_nombre) -> dict[str, Decimal]:
    return {k: Decimal(v) for k, v in por_nombre.items()}


def test_b9_suma_rubros_igual_concepto():
    rubros = _rubros()
    valores = _valores(
        **{
            "Recaudo de cartera": "15000",  # 0110 → neto (único ingreso real; el resto
            #                                  de rubros de ingreso no existe en PROD)
            "Producto": "70000",  # → pago_inventario (1010 entero)
            "Garantía cupo (Auteco)": "1600",  # → fondeo
            "SOAT/Matrículas": "2000",  # → costo_nueva
            "Seguros (Hunter)": "800",  # → gps
            "Arriendos": "4000",  # → gastos_fijos
            "Freelance": "500",  # → gastos_fijos (2140, por grupo)
            "Sueldos empleados": "9000",  # → gastos_fijos
            "Otros gastos": "300",  # → gastos_fijos
            "Préstamos": "1000",  # → int_deuda
            "Deudas tarjetas de crédito": "500",  # → int_deuda
            "Deudas proveedores anteriores": "700",  # → int_deuda
            "Impuestos": "6000",  # → iva
        }
    )
    r = mapear_a_conceptos(rubros=rubros, valor_por_rubro_id=valores, neutros_ids=set())
    c = r.conceptos
    assert c["neto"] == Decimal("15000")  # 0110 Recaudo
    assert c["pago_inventario"] == Decimal("70000")  # 1010 entero (4060 ya no mapea)
    assert c["fondeo"] == Decimal("1600")
    assert c["costo_nueva"] == Decimal("2000")
    assert c["gps"] == Decimal("800")
    assert c["gastos_fijos"] == Decimal("13800")  # 4000+500+9000+300
    assert c["int_deuda"] == Decimal("2200")  # 1000+500+700
    assert c["iva"] == Decimal("6000")


def test_r1_1010_entero_a_pago_inventario_no_costo_nueva():
    rubros = _rubros()
    r = mapear_a_conceptos(
        rubros=rubros,
        valor_por_rubro_id=_valores(Producto="50000"),
        neutros_ids=set(),
    )
    assert r.conceptos["pago_inventario"] == Decimal("50000")
    assert r.conceptos["costo_nueva"] == Decimal("0.00")


def test_pts6d_4040_y_4070_a_int_deuda():
    # R-2 (4040 en sin_mapear) SUPERSEDED por PTS6-D (decisión CEO 2026-08-10):
    # 4040 Deudas impuestos y 4070 Rodante–Financiación entran a int_deuda para que
    # el Gasto del mes en curso refleje TODO el presupuesto no-costo.
    rubros = _rubros()
    r = mapear_a_conceptos(
        rubros=rubros,
        valor_por_rubro_id=_valores(
            **{
                "Deudas impuestos": "8000",
                "Rodante – Financiación a clientes": "3000",
            }
        ),
        neutros_ids=set(),
    )
    assert r.conceptos["int_deuda"] == Decimal("11000")
    assert r.sin_mapear == []


def test_codigo_sin_concepto_sigue_en_sin_mapear():
    # El canal sin_mapear sigue vivo (mecanismo R-2): 4060 no tiene concepto.
    rubros = _rubros()
    r = mapear_a_conceptos(
        rubros=rubros,
        valor_por_rubro_id=_valores(**{"Inventario Auteco (150 días)": "5000"}),
        neutros_ids=set(),
    )
    assert "Inventario Auteco (150 días)" in r.sin_mapear
    # y no se sumó a ningún concepto
    assert all(v == Decimal("0.00") for v in r.conceptos.values())


def test_a1_neutros_excluidos_por_id():
    rubros = _rubros()
    # 'Reversas y devoluciones' (grupo otros, NO sistema) mapearía a gastos_fijos si no
    # se excluyera; su id en neutros_ids lo saca ANTES de la regla de grupo.
    valores = _valores(**{"Arriendos": "4000", "Reversas y devoluciones": "9999"})
    r = mapear_a_conceptos(
        rubros=rubros,
        valor_por_rubro_id=valores,
        neutros_ids={
            "Reversas y devoluciones",
            "Ajuste de conciliación",
            "Tránsito Wava mes anterior",
        },
    )
    assert r.conceptos["gastos_fijos"] == Decimal("4000")  # sin los 9999 del neutro
    assert "Reversas y devoluciones" not in r.sin_mapear


def test_b12_codigo_del_mapeo_ausente_es_ruidoso():
    # Quitar 1010 de la taxonomía → el mapeo lo referencia → error ruidoso.
    rubros = [r for r in _rubros() if r.codigo != "1010"]
    with pytest.raises(ValueError, match="B12"):
        mapear_a_conceptos(rubros=rubros, valor_por_rubro_id={}, neutros_ids=set())
