# backend/app/domain/gasto_recurrente.py
"""GastoRecurrente — plantilla administrable de gastos fijos (decisión CEO 2026-07-26).

Es la versión persistente de la 'hoja de gastos' del simulador (42 líneas reales):
cada gasto recurrente apunta a un RUBRO existente (hereda grupo/código del Plan de
Cuentas — el cruce con la arquitectura presupuestal) y trae su monto, frecuencia,
día de pago y notas de cómo administrarlo. Es INFORMATIVO: no alimenta el motor de
proyección (decisión CEO Q3), así que no hay riesgo de doble conteo con `gastos_fijos`.

Dinero=Decimal (regla 1). `monto` es el valor POR PERÍODO según `frecuencia`; el
equivalente mensual (para sumar la plantilla) lo deriva `monto_mensual`.
"""

import re
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum

from beanie import Document, PydanticObjectId
from pydantic import ConfigDict, Field, field_validator
from pymongo import IndexModel

from app.core.money import Money

GASTOS_RECURRENTES_COLLECTION = "gastos_recurrentes"

_CENTAVO = Decimal("0.01")
_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")  # YYYY-MM, mes válido


class Frecuencia(StrEnum):
    MENSUAL = "mensual"
    BIMESTRAL = "bimestral"
    TRIMESTRAL = "trimestral"
    CUATRIMESTRAL = "cuatrimestral"
    SEMESTRAL = "semestral"
    ANUAL = "anual"


# Meses que abarca cada período — para normalizar a equivalente mensual.
MESES_POR_FRECUENCIA: dict[Frecuencia, int] = {
    Frecuencia.MENSUAL: 1,
    Frecuencia.BIMESTRAL: 2,
    Frecuencia.TRIMESTRAL: 3,
    Frecuencia.CUATRIMESTRAL: 4,
    Frecuencia.SEMESTRAL: 6,
    Frecuencia.ANUAL: 12,
}


class GastoRecurrente(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    rubro_id: PydanticObjectId  # apunta al Rubro (trae grupo/código del plan)
    descripcion: str = Field(min_length=1, max_length=120)
    monto: Money  # por período (según frecuencia)
    frecuencia: Frecuencia = Frecuencia.MENSUAL
    dia_pago: int | None = Field(default=None, ge=1, le=31)
    hasta: str | None = None  # mes final YYYY-MM (gasto temporal); None = permanente
    notas: str | None = Field(default=None, max_length=500)
    activo: bool = True
    orden: int

    class Settings:
        name = GASTOS_RECURRENTES_COLLECTION
        indexes = [IndexModel([("orden", 1)], name="por_orden")]

    @field_validator("frecuencia", mode="before")
    @classmethod
    def _cast_frecuencia(cls, v: object) -> object:
        # strict=True no coerciona str→StrEnum; valor inválido → ValueError → 422.
        return v if isinstance(v, Frecuencia) else Frecuencia(v)

    @field_validator("hasta")
    @classmethod
    def _valida_hasta(cls, v: str | None) -> str | None:
        if v is not None and not _MES.match(v):
            raise ValueError("hasta debe ser 'YYYY-MM'")
        return v

    @property
    def monto_mensual(self) -> Decimal:
        """Equivalente mensual = monto / meses del período (COP, HALF_EVEN)."""
        meses = MESES_POR_FRECUENCIA[self.frecuencia]
        mensual = self.monto / Decimal(meses)
        return mensual.quantize(_CENTAVO, rounding=ROUND_HALF_EVEN)
