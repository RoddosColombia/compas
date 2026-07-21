# backend/app/presupuesto/motor.py
"""Fórmula oficial del sugerido — Spec §1.4.1 (F-07). Función PURA (sin I/O),
auditada por Kimi celda a celda contra el Excel congelado.

    prom_3m       = (E(M-1) + E(M-2) + E(M-3)) / 3
    tendencia_mes = (E(M-1) − E(M-3)) / 2
    sugerido      = prom_3m + tendencia_mes + prom_3m × crec_pct

E(i) = ejecutado del rubro en el mes i, usando EXCLUSIVAMENTE meses 'cerrado'.
`historia_incompleta` = true si hay menos de 3 meses cerrados (el sugerido se
calcula con los que haya). Todo en Decimal (regla 1); cuantización COP 2 decimales
HALF_EVEN (misma política que `money_str`).

**Decisión declarada (Kimi):** el Spec define la fórmula para n=3. Para n<3 se
generaliza sin adivinar: `prom_3m` = promedio de los meses disponibles;
`tendencia_mes` = (más_reciente − más_antiguo)/(n−1) —para n=3 da /2, exactamente la
fórmula oficial— y 0 si n<2 (un punto no define pendiente); n=0 → todo 0. En todos
esos casos `historia_incompleta=true`. En el go-live todas las líneas se generan con
n=3 (may–jul cerrados y migrados), que es el caso certificado."""

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

_CENTAVO = Decimal("0.01")


def _cop(v: Decimal) -> Decimal:
    return v.quantize(_CENTAVO, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class ComponentesSugerido:
    prom_3m: Decimal
    tendencia_mes: Decimal
    monto_sugerido: Decimal
    historia_incompleta: bool


def calcular_sugerido_historico(
    ejecutados: list[Decimal], crec_pct: Decimal
) -> ComponentesSugerido:
    """`ejecutados` = ejecutado de meses CERRADOS, ordenados de MÁS RECIENTE a más
    antiguo: [E(M-1), E(M-2), E(M-3), …]. Solo se usan los 3 más recientes."""
    usados = ejecutados[:3]  # E(M-1..M-3); ignora historia más vieja
    n = len(usados)
    historia_incompleta = n < 3

    if n == 0:
        cero = _cop(Decimal("0"))
        return ComponentesSugerido(cero, cero, cero, True)

    prom_3m = sum(usados, Decimal("0")) / Decimal(n)
    # tendencia: pendiente media entre el más reciente y el más antiguo disponible.
    # n=3 → (E(M-1) − E(M-3))/2 (fórmula oficial); n=2 → /1; n=1 → 0.
    tendencia = (usados[0] - usados[-1]) / Decimal(n - 1) if n >= 2 else Decimal("0")
    sugerido = prom_3m + tendencia + prom_3m * crec_pct
    return ComponentesSugerido(
        prom_3m=_cop(prom_3m),
        tendencia_mes=_cop(tendencia),
        monto_sugerido=_cop(sugerido),
        historia_incompleta=historia_incompleta,
    )
