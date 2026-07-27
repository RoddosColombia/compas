"""Valles de caja (D1 §3) — los HITOS de solvencia (decisión CEO #3).

Un valle es un mínimo local de la caja mensual cuya distancia al umbral lo hace
relevante: `caja < umbral × factor_atencion` (factor configurable, default 3×). Cada
valle se explica con los egresos del mes que más se apartan (hacia arriba) de su
promedio móvil de meses vecinos — "en feb-2027 la caja cae porque coinciden el pago del
lote Auteco y el IVA".

Post-proceso PURO sobre cualquier serie de `MesProyeccion` (base o ajustada); el motor
no se toca. Los conceptos de egreso son las columnas que el motor YA entrega.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.proyeccion.motor import MesProyeccion, _cop

# Conceptos de egreso que el motor entrega por mes (spec §3), con etiqueta llana.
CONCEPTO_ETIQUETA: dict[str, str] = {
    "pago_inventario": "Pago de lote (Auteco)",
    "iva": "IVA",
    "int_deuda": "Intereses de deuda",
    "gastos_fijos": "Gastos fijos",
    "adelanto": "Adelanto Auteco",
    "fondeo": "Costo de fondeo",
}
_CONCEPTOS = tuple(CONCEPTO_ETIQUETA)
_REL = Decimal("0.0001")


@dataclass(frozen=True)
class Causa:
    concepto: str
    etiqueta: str
    monto: Decimal  # magnitud del egreso ese mes (positiva)
    promedio: Decimal  # promedio de los meses vecinos (positivo)
    # desvío relativo (0.40 = 40% sobre lo normal); None si el promedio es 0
    vs_promedio: Decimal | None


@dataclass(frozen=True)
class Valle:
    mes: str
    caja: Decimal
    distancia_al_umbral: Decimal  # caja - umbral (negativo = perfora)
    meses_para_prepararse: int  # desde hoy (índice del mes; 0 = mes en curso)
    causas: list[Causa]


def _es_minimo_local(cajas: list[Decimal], i: int) -> bool:
    izq_ok = i == 0 or cajas[i] <= cajas[i - 1]
    der_ok = i == len(cajas) - 1 or cajas[i] <= cajas[i + 1]
    estricto = (i > 0 and cajas[i] < cajas[i - 1]) or (
        i < len(cajas) - 1 and cajas[i] < cajas[i + 1]
    )
    return izq_ok and der_ok and estricto


def _causas_del_mes(
    meses: list[MesProyeccion], i: int, ventana: int, max_causas: int
) -> list[Causa]:
    lado = ventana // 2
    lo = max(0, i - lado)
    hi = min(len(meses), i + lado + 1)
    vecinos = [j for j in range(lo, hi) if j != i]
    # (concepto, monto, promedio, desvio)
    candidatas: list[tuple[str, Decimal, Decimal, Decimal]] = []
    for c in _CONCEPTOS:
        monto = abs(getattr(meses[i], c))
        vals = [abs(getattr(meses[j], c)) for j in vecinos]
        prom = sum(vals, Decimal("0")) / Decimal(len(vals)) if vals else Decimal("0")
        desvio = monto - prom  # solo lo que subió sobre lo normal explica el hueco
        if desvio > 0:
            candidatas.append((c, monto, prom, desvio))
    candidatas.sort(key=lambda x: x[3], reverse=True)
    causas: list[Causa] = []
    for c, monto, prom, _desvio in candidatas[:max_causas]:
        rel = (
            ((monto - prom) / prom).quantize(_REL) if prom > 0 else None
        )
        causas.append(
            Causa(
                concepto=c,
                etiqueta=CONCEPTO_ETIQUETA[c],
                monto=_cop(monto),
                promedio=_cop(prom),
                vs_promedio=rel,
            )
        )
    return causas


def detectar_valles(
    meses: list[MesProyeccion],
    caja_minima: Decimal,
    *,
    factor_atencion: Decimal = Decimal("3"),
    max_causas: int = 3,
    ventana_causas: int = 6,
) -> list[Valle]:
    """Mínimos locales de la caja relevantes por cercanía al umbral, cada uno con sus
    causas. Devuelve la lista en orden cronológico."""
    cajas = [f.caja for f in meses]
    limite = caja_minima * factor_atencion
    valles: list[Valle] = []
    for i in range(len(meses)):
        if not _es_minimo_local(cajas, i):
            continue
        if cajas[i] >= limite:
            continue  # holgado: no relevante
        valles.append(
            Valle(
                mes=meses[i].mes,
                caja=cajas[i],
                distancia_al_umbral=_cop(cajas[i] - caja_minima),
                meses_para_prepararse=i,
                causas=_causas_del_mes(meses, i, ventana_causas, max_causas),
            )
        )
    return valles
