"""RF-F7 · Fundacional §2 — Recomendaciones por impacto: reparto del recorte por rubro.
Motor corrido al revés.

Función PURA: recibe un objetivo de recorte (COP/mes) y un `gasto_por_rubro` (calculado
aguas arriba con `_ejecutados_por_rubro_mes` de presupuesto/service.py sobre los últimos
3 meses cerrados) y devuelve una lista ordenada por impacto.

Reglas de dominio:
  · **Ordenamiento por impacto DESC**: el rubro que más gasta aparece primero. La
    Fundacional habla de "reparto por impacto"; ese es el orden natural — "empieza
    por el que más pesa".
  · **Regla del 50%**: ningún rubro aporta más del 50% de su propio gasto promedio.
    Sin esto un objetivo grande "vaciaría" el rubro-líder; con esto se fuerza
    diversificación, alineado con la lectura de "reparto" y no "recorte-guillotina".
  · **Rubros de cero gasto se ignoran**: no pueden aportar recorte (0 × 50% = 0).
  · **Objetivo ≥ suma de topes**: devuelve todos los topes al 50% — el caller ve un
    `restante` en el resumen y sabe que hace falta otra palanca (subir ingreso, más
    unidades, revisar el umbral).

Motor sin tocar; `Ajuste.rubro_id` sigue siendo trazabilidad — el reparto se propaga
como MÚLTIPLES `Ajuste` con distinto `rubro_id` para que la UI los muestre por rubro,
pero la aritmética del motor los suma como un único recorte global equivalente.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

_TOPE_POR_RUBRO = Decimal("0.5")  # 50% del gasto propio (regla de dominio RF-F7)
_PESO = Decimal("0.01")
_PCT = Decimal("0.0001")


def reparto_por_rubro(
    objetivo_recorte: Decimal,
    gasto_por_rubro: dict[str, Decimal],
    *,
    tope_por_rubro: Decimal = _TOPE_POR_RUBRO,
) -> list[dict]:
    """Devuelve una lista de líneas `{rubro_id, monto_recortar, gasto_actual,
    pct_de_su_gasto}` ordenada por gasto DESC.

    Con objetivo=0 o gasto vacío devuelve `[]`. Cuando el objetivo excede la suma
    de topes, cada rubro queda al 50% y el resumen (calcularlo en el caller como
    `sum(monto_recortar)`) permite mostrar el faltante en la UI.
    """
    if objetivo_recorte <= 0:
        return []
    # Ordenamos por gasto DESC (rubros de 0 gasto quedan al final; los descartamos
    # después porque su tope es 0 y no pueden aportar).
    ordenados = sorted(
        gasto_por_rubro.items(),
        key=lambda kv: (kv[1], kv[0]),  # gasto DESC, rubro_id ASC para determinismo
        reverse=True,
    )
    restante = objetivo_recorte
    lineas: list[dict] = []
    for rubro_id, gasto in ordenados:
        if gasto <= 0:
            continue  # rubros de 0 gasto no aportan
        tope_rubro = (gasto * tope_por_rubro).quantize(_PESO, rounding=ROUND_DOWN)
        aporte = min(restante, tope_rubro) if restante > 0 else tope_rubro
        if restante <= 0:
            # Ya cerró el objetivo — no incluimos rubros adicionales para no
            # ensuciar la lectura (la UI muestra "de aquí sale el recorte").
            break
        pct = (aporte / gasto).quantize(_PCT, rounding=ROUND_DOWN)
        lineas.append(
            {
                "rubro_id": rubro_id,
                "monto_recortar": aporte,
                "gasto_actual": gasto,
                "pct_de_su_gasto": pct,
            }
        )
        restante -= aporte
    return lineas
