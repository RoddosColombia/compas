# backend/app/domain/loantape.py
"""LoanTapeCredito (SISMO-V3 aging) — snapshot semanal de UN crédito a la fecha de
corte, tal como lo entrega SISMO-V3 (la fuente de verdad de los pagos).

Contrato completo en docs/CONTRATO-SISMO-V3-LOANTAPE.md. Grano: 1 fila por crédito vivo
por `fecha_corte`. COMPAS deriva de aquí: mora por tramo (aging), cartera por añada y la
proyección de recaudo crédito a crédito. Dedup (regla 5): índice único parcial
(credito_id, fecha_corte) — recargar un corte NO duplica. Todo monto es Money/Decimal
(regla 1); fechas 'YYYY-MM-DD' (regla 2). Sin datos personales (Ley 1581): `cliente_id`
opaco. Baja lógica no aplica: el snapshot se pisa por corte.
"""

import re
from datetime import datetime
from enum import StrEnum

from beanie import Document
from pydantic import ConfigDict, Field, field_validator
from pymongo import IndexModel

from app.core.money import Money

LOANTAPE_COLLECTION = "loantape_creditos"

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class EstadoCredito(StrEnum):
    vigente = "vigente"
    en_mora = "en_mora"
    castigado = "castigado"  # default / write-off


class LoanTapeCredito(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    credito_id: str = Field(min_length=1, max_length=60)
    fecha_corte: str  # 'YYYY-MM-DD' (miércoles del corte)
    modelo: str = Field(min_length=1, max_length=60)
    fecha_desembolso: str  # 'YYYY-MM-DD' (añada / inicio del cronograma)
    monto_financiado: Money
    plazo_semanas: int = Field(gt=0)
    cuota_semanal: Money
    cuotas_pagadas: int = Field(ge=0)
    cuotas_vencidas: int = Field(ge=0)
    dias_mora: int = Field(ge=0)  # atraso de la cuota más antigua sin pagar
    saldo_en_mora: Money  # aging por monto
    saldo_pendiente: Money  # cartera total por cobrar del crédito
    estado: EstadoCredito
    # Opcionales del contrato (mejoran precisión / trazabilidad).
    cliente_id: str | None = Field(default=None, max_length=60)  # opaco, sin PII
    fecha_ultimo_pago: str | None = None

    class Settings:
        name = LOANTAPE_COLLECTION
        indexes = [
            # Regla 5: dedup por (credito_id, fecha_corte). Único donde credito_id es
            # string (siempre). Unicidad real → @requires_real_mongo.
            IndexModel(
                [("credito_id", 1), ("fecha_corte", 1)],
                name="credito_corte_unico",
                unique=True,
                partialFilterExpression={"credito_id": {"$type": "string"}},
            ),
            IndexModel([("fecha_corte", 1)], name="por_corte"),
        ]

    @field_validator("fecha_corte", "fecha_desembolso")
    @classmethod
    def _fecha(cls, v: object) -> str:
        if not isinstance(v, str) or not _FECHA.match(v):
            raise ValueError("fecha debe ser string 'YYYY-MM-DD'")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"fecha inválida: {v}") from e
        return v

    @field_validator("fecha_ultimo_pago")
    @classmethod
    def _fecha_opc(cls, v: object) -> object:
        if v is None:
            return v
        return cls._fecha(v)

    @field_validator("estado", mode="before")
    @classmethod
    def _cast_estado(cls, v: object) -> object:
        return v if isinstance(v, EstadoCredito) else EstadoCredito(v)
