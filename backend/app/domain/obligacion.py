# backend/app/domain/obligacion.py
"""Obligaciones genéricas (D2 §2) — deudas / cuentas por pagar administrables.

Dos naturalezas: `cuotas` (calendario fijo: acreedor, monto, cuotas, periodicidad, tasa,
inicio, gracia) y `facturacion` (términos como ATRIBUTOS: plazo base sin interés, plazo
máximo, tasa del excedente — registro factura a factura). Ningún caso especial: Auteco
es una obligación `facturacion` más. Montos y tasas como Decimal (regla 1)."""

import re
from datetime import datetime
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.money import Money

NaturalezaObligacion = Literal["cuotas", "facturacion"]

_FECHA = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _valida_fecha(v: str) -> str:
    if not _FECHA.match(v):
        raise ValueError("fecha debe ser 'YYYY-MM-DD'")
    return v


class Obligacion(Document):
    nombre: str = Field(min_length=1, max_length=120)
    acreedor: str = Field(min_length=1, max_length=120)
    naturaleza: NaturalezaObligacion
    activo: bool = True
    es_sistema: bool = False  # semilla Auteco (protegida de baja/borrado)
    creado_por: str
    actualizado_at: datetime

    # naturaleza = cuotas
    monto_total: Money | None = None
    n_cuotas: int | None = Field(default=None, ge=1)
    periodicidad_meses: int | None = Field(default=None, ge=1)  # 1=mes, 3=trimestre
    tasa_mensual: Money | None = None  # fracción (0.011 = 1,1%)
    fecha_inicio: str | None = None  # 'YYYY-MM-DD'
    meses_gracia: int | None = Field(default=None, ge=0)

    # naturaleza = facturacion (términos, no constantes)
    plazo_base_dias: int | None = Field(default=None, ge=0)
    plazo_max_dias: int | None = Field(default=None, ge=0)
    tasa_excedente_mensual: Money | None = None  # fracción (0.016 = 1,6%)

    class Settings:
        name = "obligaciones"

    @field_validator("fecha_inicio")
    @classmethod
    def _fecha(cls, v: str | None) -> str | None:
        return _valida_fecha(v) if v is not None else None

    @model_validator(mode="after")
    def _coherencia(self) -> "Obligacion":
        if self.naturaleza == "cuotas":
            faltan = [
                c
                for c in (
                    "monto_total",
                    "n_cuotas",
                    "periodicidad_meses",
                    "tasa_mensual",
                    "fecha_inicio",
                    "meses_gracia",
                )
                if getattr(self, c) is None
            ]
            if faltan:
                raise ValueError(f"naturaleza 'cuotas' requiere: {', '.join(faltan)}")
        else:  # facturacion
            faltan = [
                c
                for c in ("plazo_base_dias", "plazo_max_dias", "tasa_excedente_mensual")
                if getattr(self, c) is None
            ]
            if faltan:
                raise ValueError(
                    f"naturaleza 'facturacion' requiere: {', '.join(faltan)}"
                )
            base, maximo = self.plazo_base_dias, self.plazo_max_dias
            if base is not None and maximo is not None and maximo < base:
                raise ValueError("plazo_max_dias no puede ser < plazo_base_dias")
        return self


class FacturaObligacion(Document):
    obligacion_id: PydanticObjectId
    fecha_factura: str  # 'YYYY-MM-DD'
    valor: Money
    plazo_elegido_dias: int = Field(ge=0)
    nota: str | None = Field(default=None, max_length=500)
    activo: bool = True
    registrada_por: str
    registrada_at: datetime

    class Settings:
        name = "facturas_obligacion"

    @field_validator("fecha_factura")
    @classmethod
    def _fecha(cls, v: str) -> str:
        return _valida_fecha(v)


class LineaMeta(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    nombre: str = Field(min_length=1, max_length=120)
    valor: Money


class MetaIngreso(Document):
    mes: str  # 'YYYY-MM'
    valor: Money
    lineas: list[LineaMeta] = Field(default_factory=list)
    activo: bool = True
    creado_por: str
    actualizado_at: datetime

    class Settings:
        name = "metas_ingreso"

    @field_validator("mes")
    @classmethod
    def _mes(cls, v: str) -> str:
        if not _MES.match(v):
            raise ValueError("mes debe ser 'YYYY-MM'")
        return v
