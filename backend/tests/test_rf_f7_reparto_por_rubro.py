# backend/tests/test_rf_f7_reparto_por_rubro.py
"""RF-F7 · Fundacional §2 — Recomendaciones por impacto: reparto del recorte
por rubro. Motor corrido al revés.

Insight del mapa (spec-miner):
  · El motor NO conoce rubros; solo conceptos agregados (`gastos_fijos`, etc.).
  · YA existe `_ejecutados_por_rubro_mes` (presupuesto/service.py:78) que da
    gasto real por rubro sobre los últimos 3 meses cerrados (usa el sugerido §7).
  · YA existe mapeo `codigo → concepto` en ejecucion/lectura.py.
  · `Ajuste.rubro_id` es solo trazabilidad (impactos.py:52); el motor lo ignora.
    Perfecto: podemos devolver una LISTA de ajustes con rubro_id para que la UI
    los muestre discriminados, y el motor los suma como el recorte global equivalente.

RF-F7 introduce `reparto_por_rubro`: dado un objetivo de recorte total (COP/mes)
y el gasto por rubro (que ya sabemos calcular), devuelve la lista ORDENADA POR
IMPACTO — el rubro que más gasta aporta primero, hasta cumplir el objetivo.

Regla de dominio (para no ser un solver naïve): **ningún rubro aporta más del 50%
de su propio gasto** — la Fundacional habla de "reparto", no de "vaciar". Fuerza
diversificación cuando el objetivo es alto.
"""

from decimal import Decimal

import pytest
from app.proyeccion.reparto import reparto_por_rubro

# Rubros simulados: 4 rubros con montos distintos, para probar ordenamiento.
RUBROS = {
    "arriendo": Decimal("10000000"),
    "sueldos": Decimal("30000000"),
    "papeleria": Decimal("500000"),
    "servicios": Decimal("2000000"),
}


def test_rff7_objetivo_cero_devuelve_lista_vacia():
    """Objetivo 0 — nada que recortar → lista vacía. Sin dividir por cero."""
    r = reparto_por_rubro(Decimal("0"), RUBROS)
    assert r == []


def test_rff7_sin_rubros_no_puede_repartir():
    """Sin rubros hay `alcanzable=False` para el caller — devuelve lista vacía."""
    r = reparto_por_rubro(Decimal("1000000"), {})
    assert r == []


def test_rff7_reparto_por_impacto_prioriza_el_mas_gastón():
    """Objetivo 5M sobre RUBROS. El rubro que MÁS gasta (sueldos=30M) debe aparecer
    primero y aportar hasta cerrar el objetivo (o hasta su tope 50% = 15M)."""
    r = reparto_por_rubro(Decimal("5000000"), RUBROS)
    # Con 5M pedidos y regla del 50%, sueldos puede aportar los 5M solo (< 50%).
    assert r[0]["rubro_id"] == "sueldos"
    assert r[0]["monto_recortar"] == Decimal("5000000")
    assert r[0]["gasto_actual"] == Decimal("30000000")
    # 5M/30M ≈ 16.66%; quantize ROUND_DOWN → 0.1666 (nunca sobre-estima el %)
    assert r[0]["pct_de_su_gasto"] == Decimal("0.1666")


def test_rff7_regla_del_50_pct_fuerza_diversificar():
    """Objetivo 20M — sueldos (30M) no puede aportar 20M (excede su 50% de 15M) →
    el resto debe salir de arriendo/servicios en orden de impacto."""
    r = reparto_por_rubro(Decimal("20000000"), RUBROS)
    montos = {x["rubro_id"]: x["monto_recortar"] for x in r}
    # sueldos aporta su tope (50% = 15M)
    assert montos["sueldos"] == Decimal("15000000")
    # arriendo aporta lo que queda (5M) — está bajo su tope (5M < 5M no, 5M < 5M
    # es igual: entra completo porque es el siguiente por impacto)
    assert montos["arriendo"] == Decimal("5000000")
    # papeleria y servicios no aportan porque ya se cerró el objetivo
    assert "servicios" not in montos
    assert "papeleria" not in montos
    # Verifica que la suma == objetivo
    assert sum(montos.values()) == Decimal("20000000")


def test_rff7_objetivo_mayor_que_todos_los_topes_reporta_faltante():
    """Objetivo tan alto que ni recortando el 50% de todos alcanza. El caller
    necesita saberlo — cada línea trae `alcanzable_total: bool` en el shape del
    reparto, y el resumen indica `restante` COP/mes que no se pudo cubrir."""
    r = reparto_por_rubro(Decimal("50000000"), RUBROS)
    # Suma máxima posible = 50% × (30 + 10 + 2 + 0.5) M = 21.25M
    total_max = sum(x["monto_recortar"] for x in r)
    assert total_max == Decimal("21250000")
    # Con objetivo 50M: cada rubro aporta hasta su tope (50%) y no hay más de dónde
    for x in r:
        assert x["pct_de_su_gasto"] == Decimal("0.5000")


def test_rff7_orden_estable_por_impacto_desc():
    """El shape del resultado siempre viene ordenado por gasto_actual DESC — es lo
    que hace la lectura útil ('empieza por el que más gastas')."""
    r = reparto_por_rubro(Decimal("20000000"), RUBROS)
    gastos_orden = [x["gasto_actual"] for x in r]
    assert gastos_orden == sorted(gastos_orden, reverse=True)


def test_rff7_rubros_de_cero_gasto_se_ignoran():
    """Un rubro que no gasta no puede aportar recorte (0 × 50% = 0). No aparece."""
    with_zero = {**RUBROS, "categoria_inactiva": Decimal("0")}
    r = reparto_por_rubro(Decimal("5000000"), with_zero)
    ids = {x["rubro_id"] for x in r}
    assert "categoria_inactiva" not in ids


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
