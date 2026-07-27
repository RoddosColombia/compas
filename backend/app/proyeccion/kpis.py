"""KPIs de proyección — función COMPARTIDA (D1).

El motor (`motor.proyectar`) calcula estos mismos KPIs en línea (motor.py:721-732) sobre
la serie base. D1 necesita recalcularlos sobre series AJUSTADAS (capa de impactos) sin
tocar el motor. Esta función reproduce ese bloque EXACTAMENTE — un test de paridad
(`test_kpis.py`) verifica que sobre la serie base da bit a bit lo mismo que el motor, de
modo que nunca diverjan.

Decisión de gobierno (spec §2 vs regla §2.1): la spec pedía "extraer, no duplicar" la
lógica de KPIs; pero la regla dura es `motor.py` con CERO diffs. Se reconcilia dejando
el bloque original intacto en el motor y espejándolo aquí para la capa nueva, con el
test de paridad como candado anti-deriva.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.proyeccion.motor import _cop


@dataclass(frozen=True)
class KpisResultado:
    piso_caja: Decimal
    mes_mas_ajustado: str
    meses_bajo_minimo: int
    caja_final: Decimal
    capital_requerido: Decimal
    runway_meses: Decimal | None


def calcular_kpis(
    cajas: list[Decimal],
    flujos: list[Decimal],
    meses: list[str],
    caja_minima: Decimal,
) -> KpisResultado:
    """Reproduce motor.py:721-732 sobre cualquier serie (base o ajustada)."""
    piso = min(cajas)
    idx_piso = cajas.index(piso)
    bajo_min = sum(1 for c in cajas if c < caja_minima)
    caja_final = cajas[-1]
    capital_req = _cop(max(Decimal("0"), caja_minima - piso))
    prom_flujo = sum(flujos, Decimal("0")) / Decimal(len(flujos))
    runway = (
        _cop(caja_final / -prom_flujo) if prom_flujo < 0 and caja_final > 0 else None
    )
    return KpisResultado(
        piso_caja=piso,
        mes_mas_ajustado=meses[idx_piso],
        meses_bajo_minimo=bajo_min,
        caja_final=caja_final,
        capital_requerido=capital_req,
        runway_meses=runway,
    )
