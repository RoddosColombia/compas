# backend/app/domain/pago_planeado.py
"""PagoPlaneado (C9/S5-01, CR-S7): una INTENCIÓN de pago programado.

MARCADO PARA AUDITORÍA KIMI (D1 coherencia de tipo + regla 1/2/4).

NO es un movimiento bancario (eso es Transaccion §1.5): es lo que el CEO planea
pagar, para responder "¿alcanza la caja para los pagos de esta semana?" (hoja
'Pagos semana' del Excel). Siempre EGRESO (un pago es salida de caja; los ingresos
esperados viven en `MesControl.ingresos_esperados_semana`). `acreedor`/`concepto`
son dato OPERATIVO que digita el usuario (persistente en Mongo, NO semilla, NO en
repo). Al `marcar-pagado` se enlaza a la Transaccion real que lo saldó
(`pagado_tx_id`)."""

import re
from datetime import datetime
from enum import StrEnum

from beanie import Document, PydanticObjectId
from pydantic import ConfigDict, Field, field_validator
from pymongo import IndexModel

from app.core.money import Money

PAGOS_PLANEADOS_COLLECTION = "pagos_planeados"

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class EstadoPago(StrEnum):
    PENDIENTE = "pendiente"
    PAGADO = "pagado"
    CANCELADO = "cancelado"


class PagoPlaneado(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    concepto: str = Field(max_length=300)
    acreedor: str = Field(max_length=200)
    monto: Money  # > 0
    fecha_programada: str  # 'YYYY-MM-DD'
    rubro_id: PydanticObjectId  # rubro EGRESO activo (D1)
    mes_id: PydanticObjectId
    estado: EstadoPago = EstadoPago.PENDIENTE
    pagado_tx_id: PydanticObjectId | None = None  # Transaccion que lo saldó (D5)
    creado_por: str | None = None
    creado_at: datetime | None = None

    class Settings:
        name = PAGOS_PLANEADOS_COLLECTION
        indexes = [
            IndexModel([("mes_id", 1), ("fecha_programada", 1)], name="por_mes_fecha"),
            IndexModel([("estado", 1)], name="por_estado"),
        ]

    @field_validator("fecha_programada")
    @classmethod
    def _fecha_str(cls, v: object) -> str:
        if not isinstance(v, str) or not _FECHA.match(v):
            raise ValueError("fecha_programada debe ser string 'YYYY-MM-DD'")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"fecha_programada inválida: {v}") from e
        return v

    @field_validator("monto")
    @classmethod
    def _monto_positivo(cls, v):
        if v <= 0:
            raise ValueError("monto debe ser > 0")
        return v

    @field_validator("estado", mode="before")
    @classmethod
    def _cast_estado(cls, v: object) -> object:
        return v if isinstance(v, EstadoPago) else EstadoPago(v)

    @field_validator("creado_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("datetime debe ser UTC-aware (regla 2)")
        return v
