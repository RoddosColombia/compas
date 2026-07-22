# backend/app/domain/presupuesto.py
"""PresupuestoLinea (Spec §1.4, F-06/F-07): la línea de presupuesto por (mes, rubro).

El sugerido lo calcula el motor §1.4.1; aquí se PERSISTE con sus componentes
(`prom_3m`, `tendencia_mes`, `crec_pct`) para verificación celda a celda. Versionado
(F-06): una sola versión `vigente` por (mes, rubro) — índice único parcial. Las
aprobadas (monto_definido != null) generan versión nueva; el recálculo solo toca las
nunca aprobadas. `ajustes` es append-only. `compromisos_programados` es una fila
INFORMATIVA (Σ DeudaCuota), NO entra en la fórmula (regla 10)."""

import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo import IndexModel

from app.core.money import Money
from app.core.time import now_utc

PRESUPUESTO_COLLECTION = "presupuesto_lineas"
_MES = re.compile(r"^\d{4}-\d{2}-01$")


class ModoCalculo(StrEnum):
    HISTORICO = "historico"
    VENTAS = "ventas"  # Fase 1.5 (N-01); en go-live TODAS en histórico (N-03)


class Ajuste(BaseModel):
    """Un acotamiento del monto (append-only, F-06)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    valor_anterior: Money | None = None
    valor_nuevo: Money
    por: str  # usuario_id
    at: datetime


class PresupuestoLinea(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    mes_id: PydanticObjectId
    rubro_id: PydanticObjectId
    version: int = 1
    monto_sugerido: Money
    prom_3m: Money
    tendencia_mes: Money  # puede ser negativa (rubro decreciente)
    crec_pct: (
        Money  # tasa; Money = Decimal que round-trip seguro (Decimal128 al releer)
    )
    compromisos_programados: Money = Decimal("0")  # informativo; NO entra en la fórmula
    monto_definido: Money | None = None  # null hasta aprobar (F-07)
    historia_incompleta: bool
    modo_calculo: ModoCalculo = ModoCalculo.HISTORICO
    ajustes: list[Ajuste] = Field(default_factory=list)
    vigente: bool = True
    creada_at: datetime = Field(default_factory=now_utc)

    class Settings:
        name = PRESUPUESTO_COLLECTION
        indexes = [
            IndexModel(
                [("mes_id", 1), ("rubro_id", 1), ("version", 1)],
                name="mes_rubro_version_unico",
                unique=True,
            ),
            # F-06: una sola versión vigente por (mes, rubro).
            IndexModel(
                [("mes_id", 1), ("rubro_id", 1)],
                name="vigente_unico",
                unique=True,
                partialFilterExpression={"vigente": True},
            ),
        ]

    @field_validator("modo_calculo", mode="before")
    @classmethod
    def _cast_modo(cls, v: object) -> object:
        return v if isinstance(v, ModoCalculo) else ModoCalculo(v)

    @field_validator("creada_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("datetime debe ser UTC-aware (regla 2)")
        return v
