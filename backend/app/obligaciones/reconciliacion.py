"""Reconciliación anti-doble-conteo (D2 §4) — la pieza delicada.

El motor YA proyecta el pago Auteco paramétricamente (`pago_inventario`, `fondeo`).
Meter las facturas reales encima sin reconciliar duplicaría el egreso. Esta capa es
post-motor (mecánica de `impactos.reacumular`, motor intacto).

Decisión documentada del ⚠ (§4): no hay correspondencia limpia mes-a-mes entre el lote
paramétrico y las facturas reales, así que la **ventana cubierta se define por los meses
de PAGO reales** (fecha de factura + plazo). Dentro de esa ventana se NETEA el
`pago_inventario`+`fondeo` paramétrico y se aplica el calendario real (capital + interés
en sus meses de pago verdaderos). Fuera de la ventana, la proyección paramétrica sigue
tal cual. El interés real viaja SEPARADO para la serialización. Sin facturas activas ⇒
la serie es la base, bit a bit.

§0 (Sprint V1): además de ajustar flujo/caja, dentro de la ventana se reescriben los
campos POR CONCEPTO del mes (`pago_inventario` = capital real, `fondeo` = interés real;
0 en meses sin pago) para que `neto + Σ egresos == flujo` al peso en toda la serie. Esto
vive aquí (capa D2 §4), NO en `reacumular` — que D1 comparte y donde reescribir
conceptos sería incorrecto.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from app.obligaciones.calculadora import pago_factura
from app.proyeccion.impactos import ResultadoAjustado, reacumular
from app.proyeccion.motor import ResultadoProyeccion, _cop

_CERO = Decimal("0.00")


@dataclass(frozen=True)
class FacturaReconciliar:
    """Una factura activa + los términos de su obligación (aplanados)."""

    fecha_factura: str
    valor: Decimal
    plazo_elegido_dias: int
    plazo_base_dias: int
    tasa_excedente_mensual: Decimal


@dataclass(frozen=True)
class ResultadoReconciliado:
    ajustado: ResultadoAjustado
    ventana: tuple[str, str] | None  # (mes_desde, mes_hasta) de pagos reales
    interes_por_mes: dict[str, str]  # interés real de obligaciones por mes (separado)
    capital_por_mes: dict[str, str]  # capital real de obligaciones por mes


def reconciliar(
    resultado: ResultadoProyeccion,
    facturas: list[FacturaReconciliar],
    caja_minima: Decimal,
    *,
    meses_anclados: frozenset[str] = frozenset(),
) -> ResultadoReconciliado:
    """`meses_anclados` (E1·P3): los meses que la capa de anclaje ya fijó a la ejecución
    real quedan FUERA de esta reconciliación — ni se netea su Auteco paramétrico ni se
    aplican sus pagos reales aquí (esa realidad ya la puso E1; tocarla sería doble
    conteo). Precedencia `motor → EJECUCIÓN (E1) → OBLIGACIONES (D2) → IMPACTOS (D1)`.
    Composición con COCK-09: COCK-09 ancla la caja inicial; E1 ancla las líneas de los
    meses cerrados/en ejecución y re-acumula desde ahí — no hay doble anclaje. Con
    `meses_anclados` vacío la serie es idéntica a hoy (candado de no-regresión)."""
    base = resultado.meses
    n = len(base)
    idx = {fila.mes: i for i, fila in enumerate(base)}

    # 1) pagos reales agregados por mes de pago
    cap: dict[str, Decimal] = {}
    interes: dict[str, Decimal] = {}
    for f in facturas:
        p = pago_factura(
            fecha_factura=f.fecha_factura,
            valor=f.valor,
            plazo_elegido_dias=f.plazo_elegido_dias,
            plazo_base_dias=f.plazo_base_dias,
            tasa_excedente_mensual=f.tasa_excedente_mensual,
        )
        cap[p.mes] = _cop(cap.get(p.mes, _CERO) + p.capital)
        interes[p.mes] = _cop(interes.get(p.mes, _CERO) + p.interes)

    # solo los pagos DENTRO del horizonte y NO anclados por E1 cuentan para la ventana
    meses_pago = sorted(m for m in cap if m in idx and m not in meses_anclados)
    if not meses_pago:
        return ResultadoReconciliado(
            ajustado=reacumular(resultado, [_CERO] * n, caja_minima),
            ventana=None,
            interes_por_mes={},
            capital_por_mes={},
        )

    desde, hasta = meses_pago[0], meses_pago[-1]
    i_desde, i_hasta = idx[desde], idx[hasta]

    # 2) deltas de flujo: netear el paramétrico en la ventana + sumar el pago real
    deltas = [_CERO] * n
    for m in range(i_desde, i_hasta + 1):
        fila = base[m]
        if fila.mes in meses_anclados:
            continue  # anclado por E1 → D2 no lo toca (evita doble conteo)
        # pago_inventario y fondeo son NEGATIVOS (egresos); netearlos = sumar su opuesto
        deltas[m] = _cop(deltas[m] - fila.pago_inventario - fila.fondeo)
    for mes in meses_pago:
        m = idx[mes]
        # el pago real es egreso: resta capital + interés del flujo
        deltas[m] = _cop(deltas[m] - cap[mes] - interes[mes])

    ajustado = reacumular(resultado, deltas, caja_minima)

    # 3) coherencia concepto-a-concepto (§0 Sprint V1): `reacumular` ajustó flujo+caja
    # pero dejó `pago_inventario`/`fondeo` con el valor PARAMÉTRICO. Dentro de la
    # ventana los reemplazamos por el pago REAL — capital → pago_inventario, interés →
    # fondeo (mapeo CEO 2026-07-27: el fondeo Auteco es costo de inventario), 0 en los
    # meses sin pago. Así `neto + Σ egresos == flujo` al peso en toda la serie y V1
    # muestra el Auteco real, no el proyectado. No se toca `reacumular` (D1 lo comparte:
    # allí un ajuste genérico no es de ningún concepto y reescribirlo sería error).
    filas = list(ajustado.meses)
    for m in range(i_desde, i_hasta + 1):
        mes = base[m].mes
        if mes in meses_anclados:
            continue  # anclado por E1 → conserva lo que E1 escribió, D2 no reescribe
        filas[m] = replace(
            filas[m],
            pago_inventario=_cop(-cap.get(mes, _CERO)),
            fondeo=_cop(-interes.get(mes, _CERO)),
        )
    ajustado = replace(ajustado, meses=filas)

    return ResultadoReconciliado(
        ajustado=ajustado,
        ventana=(desde, hasta),
        interes_por_mes={m: str(interes[m]) for m in meses_pago},
        capital_por_mes={m: str(cap[m]) for m in meses_pago},
    )
