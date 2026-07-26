# backend/app/loantape/aging.py
"""Aging (mora por tramo) — derivación PURA, compute-only, sin I/O.

Réplica del contrato docs/CONTRATO-SISMO-V3-LOANTAPE.md: el aging se DERIVA de
`dias_mora` (tramo) + `saldo_en_mora` (monto). No se inventa: si SISMO-V3 no manda mora,
no hay aging. Todo monto es Decimal (regla 1). Tramos fijos: al día / 1-30 / 31-60 /
61-90 / 90+.
"""

from decimal import Decimal

# Orden fijo de presentación (del menos al más moroso).
TRAMOS: tuple[str, ...] = ("al_dia", "1_30", "31_60", "61_90", "90_mas")

TRAMO_LABEL: dict[str, str] = {
    "al_dia": "Al día",
    "1_30": "1-30 días",
    "31_60": "31-60 días",
    "61_90": "61-90 días",
    "90_mas": "90+ días",
}


def tramo_de(dias_mora: int) -> str:
    """Tramo de aging de un crédito según sus días de atraso."""
    if dias_mora <= 0:
        return "al_dia"
    if dias_mora <= 30:
        return "1_30"
    if dias_mora <= 60:
        return "31_60"
    if dias_mora <= 90:
        return "61_90"
    return "90_mas"


def aging_por_tramo(items: list[dict]) -> list[dict]:
    """Agrupa créditos por tramo. `items`: iterable de dicts con `dias_mora` (int) y
    `saldo_en_mora` (Decimal). Devuelve SIEMPRE los 5 tramos en orden, cada uno con
    `n_creditos` y `saldo_en_mora` (suma). Determinista."""
    n: dict[str, int] = dict.fromkeys(TRAMOS, 0)
    saldo: dict[str, Decimal] = {t: Decimal("0") for t in TRAMOS}
    for it in items:
        t = tramo_de(int(it["dias_mora"]))
        n[t] += 1
        saldo[t] += it["saldo_en_mora"]
    return [
        {
            "tramo": t,
            "etiqueta": TRAMO_LABEL[t],
            "n_creditos": n[t],
            "saldo_en_mora": saldo[t],
        }
        for t in TRAMOS
    ]
