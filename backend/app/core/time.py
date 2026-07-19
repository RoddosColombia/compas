# backend/app/core/time.py
"""Tiempo y zona horaria — regla 2 de CLAUDE.md.

Zona horaria única: América/Bogotá. Toda marca de tiempo del dominio se
genera con `now_bogota()`. Fechas de negocio en `YYYY-MM-DD`; los meses se
normalizan al día 1 con `month_start()`.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")


def now_bogota() -> datetime:
    """Ahora, con offset -05:00 explícito (América/Bogotá)."""
    return datetime.now(BOGOTA)


def today_bogota() -> date:
    """Fecha de hoy en América/Bogotá."""
    return now_bogota().date()


def month_start(d: date) -> date:
    """Normaliza una fecha al primer día de su mes (llave de MesControl)."""
    return d.replace(day=1)
