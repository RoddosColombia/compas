"""Calculadora de obligaciones (D2 §3) — pura, Decimal, motor intocable.

Reutiliza la SEMÁNTICA del motor por convención (no lo importa aquí; el candado de
paridad en `test_calculadora.py` sí importa `inventario_auteco_mensual` y verifica al
peso). Decisión de fuente única (spec §3): se adopta el redondeo del motor
(`delay = plazo // 30` meses; `meses_interes = (plazo − base) // 30`) en vez de días
exactos — para los plazos reales (90/120/150, múltiplos de 30) coinciden; en el resto
manda el motor. Capital e interés van SEPARADOS, en el mes de pago.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

_Q = Decimal("0.01")


def _cop(v: Decimal) -> Decimal:
    return v.quantize(_Q, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class PagoObligacion:
    mes: str  # 'YYYY-MM'
    capital: Decimal
    interes: Decimal


def _mes_de(fecha: str) -> str:
    """'YYYY-MM-DD' → 'YYYY-MM'."""
    return fecha[:7]


def _add_meses(mes: str, n: int) -> str:
    """'YYYY-MM' + n meses → 'YYYY-MM'."""
    idx = int(mes[:4]) * 12 + (int(mes[5:7]) - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def pago_factura(
    *,
    fecha_factura: str,
    valor: Decimal,
    plazo_elegido_dias: int,
    plazo_base_dias: int,
    tasa_excedente_mensual: Decimal,
) -> PagoObligacion:
    """El pago de UNA factura: capital = valor en el mes de pago; interés = valor × tasa
    × meses excedentes (0 si el plazo ≤ la base). Convención del motor (//30)."""
    delay = plazo_elegido_dias // 30
    meses_interes = max(0, (plazo_elegido_dias - plazo_base_dias) // 30)
    mes_pago = _add_meses(_mes_de(fecha_factura), delay)
    interes = _cop(valor * tasa_excedente_mensual * Decimal(meses_interes))
    return PagoObligacion(mes=mes_pago, capital=_cop(valor), interes=interes)


def calendario_cuotas(
    *,
    monto_total: Decimal,
    n_cuotas: int,
    periodicidad_meses: int,
    tasa_mensual: Decimal,
    fecha_inicio: str,
    meses_gracia: int,
) -> list[PagoObligacion]:
    """Calendario de una obligación a cuotas: capital de igual amortización + interés
    sobre el saldo del período. La última cuota ajusta el capital para cerrar el saldo
    exacto (sin residuos por redondeo)."""
    pagos: list[PagoObligacion] = []
    saldo = monto_total
    capital_cuota = _cop(monto_total / Decimal(n_cuotas))
    mes0 = _add_meses(_mes_de(fecha_inicio), meses_gracia)
    for i in range(n_cuotas):
        mes = _add_meses(mes0, i * periodicidad_meses)
        interes = _cop(saldo * tasa_mensual * Decimal(periodicidad_meses))
        cap = capital_cuota if i < n_cuotas - 1 else _cop(saldo)
        pagos.append(PagoObligacion(mes=mes, capital=cap, interes=interes))
        saldo = _cop(saldo - cap)
    return pagos
