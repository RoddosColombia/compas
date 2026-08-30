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


async def _umbral_atencion_configurado(caja_minima: Decimal) -> Decimal | None:
    """La vigencia CONFIGURADA (o None si no hay o es incoherente)."""
    fila = (
        await Configuracion.find(Configuracion.clave == ClaveConfig.UMBRAL_ATENCION)
        .sort(-Configuracion.vigente_desde)
        .first_or_none()
    )
    if fila is None or fila.valor_decimal is None:
        return None
    val = Decimal(fila.valor_decimal)
    if val <= caja_minima:
        return None  # dato incoherente
    return val


async def leer_umbral_atencion(caja_minima: Decimal) -> Decimal:
    """Para la UI (Supuestos): devuelve la vigencia o, en su ausencia, la SUGERENCIA
    de `caja_minima × factor_atencion` (default 3×) — sirve como pre-carga del editor
    para que el CEO tenga un valor plausible con qué empezar."""
    val = await _umbral_atencion_configurado(caja_minima)
    if val is not None:
        return val
    return caja_minima * _FACTOR_ATENCION_FALLBACK


async def leer_umbral_atencion_activo(caja_minima: Decimal) -> Decimal | None:
    """Para el pipeline de proyección: la vigencia CONFIGURADA solamente. Sin
    configurar → None → la banda ámbar NO se activa (comportamiento actual). Así el
    CEO controla cuándo empieza a colorearse el ámbar (Fundacional D-1)."""
    return await _umbral_atencion_configurado(caja_minima)


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


_ALERTA_HORIZONTE_FALLBACK = 6


async def leer_alerta_caja_activa() -> bool:
    """On/off del vigilante de caja. Ausente/incoherente → False (apagada)."""
    fila = (
        await Configuracion.find(Configuracion.clave == ClaveConfig.ALERTA_CAJA_ACTIVA)
        .sort(-Configuracion.vigente_desde)
        .first_or_none()
    )
    if fila is None or fila.valor_json is None:
        return False
    return bool(fila.valor_json.get("activa", False))


async def leer_alerta_horizonte_meses() -> int:
    """Meses hacia adelante del disparador proyectado. Ausente/incoherente → 6."""
    fila = (
        await Configuracion.find(
            Configuracion.clave == ClaveConfig.ALERTA_CAJA_HORIZONTE_MESES
        )
        .sort(-Configuracion.vigente_desde)
        .first_or_none()
    )
    if fila is None or fila.valor_json is None:
        return _ALERTA_HORIZONTE_FALLBACK
    m = fila.valor_json.get("meses")
    return m if isinstance(m, int) and m > 0 else _ALERTA_HORIZONTE_FALLBACK


async def escribir_alerta_caja_activa(
    *, activa: bool, usuario_id: str, vigente_desde: date | None = None
) -> Configuracion:
    fila = Configuracion(
        clave=ClaveConfig.ALERTA_CAJA_ACTIVA,
        valor_json={"activa": bool(activa)},
        vigente_desde=(vigente_desde or today_bogota()).isoformat(),
        modificado_por=usuario_id,
    )
    await fila.insert()
    return fila


async def escribir_alerta_horizonte_meses(
    *, meses: int, usuario_id: str, vigente_desde: date | None = None
) -> Configuracion:
    if not isinstance(meses, int) or meses <= 0:
        raise ConfiguracionError("el horizonte debe ser un entero de meses > 0", 422)
    fila = Configuracion(
        clave=ClaveConfig.ALERTA_CAJA_HORIZONTE_MESES,
        valor_json={"meses": meses},
        vigente_desde=(vigente_desde or today_bogota()).isoformat(),
        modificado_por=usuario_id,
    )
    await fila.insert()
    return fila
