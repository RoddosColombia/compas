# backend/app/configuracion/service.py
"""RF-F3 · P1 — resolvedores y mutación de claves de `Configuracion` administrables.

Patrón del proyecto (idéntico a `cierre/service.py::_umbral_dif_banco`): leer la fila
más reciente por `vigente_desde`; si no hay, aplicar un fallback explícito. La
escritura crea una NUEVA fila (historial temporal por (clave, vigente_desde)), nunca
edita las anteriores.

Hoy vive `UMBRAL_ATENCION`. A medida que RF-F3 crezca (P3a), otros consumidores del
motor leerán este mismo resolvedor.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.time import today_bogota
from app.domain.configuracion import ClaveConfig, Configuracion

# Espeja el default de `valles.py::factor_atencion` (3× el crítico).
_FACTOR_ATENCION_FALLBACK = Decimal("3")


class ConfiguracionError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


async def leer_umbral_atencion(caja_minima: Decimal) -> Decimal:
    """Devuelve la última vigencia de `UMBRAL_ATENCION`. Descarta valores incoherentes
    (≤ crítico) y en su ausencia aplica `caja_minima × factor_atencion` (default 3×) —
    el mismo umbral con el que `valles.py` filtra hoy sus mínimos relevantes. Así, sin
    fila configurada, el comportamiento del sistema NO cambia."""
    fila = (
        await Configuracion.find(Configuracion.clave == ClaveConfig.UMBRAL_ATENCION)
        .sort(-Configuracion.vigente_desde)
        .first_or_none()
    )
    if fila is not None and fila.valor_decimal is not None:
        val = Decimal(fila.valor_decimal)
        if val > caja_minima:
            return val
        # dato incoherente (≤ crítico): se ignora y se usa el fallback.
    return caja_minima * _FACTOR_ATENCION_FALLBACK


async def escribir_umbral_atencion(
    *,
    valor: Decimal,
    caja_minima: Decimal,
    usuario_id: str,
    vigente_desde: date | None = None,
) -> Configuracion:
    """Escribe una nueva vigencia del umbral de atención. Validación estricta: DEBE
    ser mayor al crítico (D-1: la atención vive por encima del mínimo). Idempotente:
    dos escrituras en el mismo `vigente_desde` colisionan por el índice único
    (clave, vigente_desde) — el cliente debe cambiar el día o los valores."""
    if valor <= caja_minima:
        raise ConfiguracionError(
            "el umbral de atención debe ser mayor al mínimo (crítico)", 422
        )
    fila = Configuracion(
        clave=ClaveConfig.UMBRAL_ATENCION,
        valor_decimal=valor,
        vigente_desde=(vigente_desde or today_bogota()).isoformat(),
        modificado_por=usuario_id,
    )
    await fila.insert()
    return fila
