# backend/app/domain/mes_control.py
"""MesControl (Spec §1.3): el mes de trabajo del ciclo presupuestal.

Decisión (regla 2 de CLAUDE.md): las fechas se guardan como string 'YYYY-MM-DD'
(mes normalizado al día 1), NO como Date. BSON no tiene fecha-sin-hora: un `date`
se persiste como datetime a medianoche y al releer vuelve datetime → romperia el
schema strict y arrastraría zona horaria. El string es inequívoco y estable.
"""

import re
from datetime import datetime
from enum import StrEnum

from beanie import Document
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo import IndexModel

from app.core.money import Money
from app.domain.bancos import Banco

MESES_CONTROL_COLLECTION = "meses_control"

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valida_fecha(v: object, *, dia1: bool = False) -> str:
    if not isinstance(v, str) or not _FECHA.match(v):
        raise ValueError("fecha debe ser string 'YYYY-MM-DD'")
    try:
        d = datetime.strptime(v, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"fecha inválida: {v}") from e
    if dia1 and d.day != 1:
        raise ValueError("el mes debe estar normalizado al día 1 (YYYY-MM-01)")
    return v


class EstadoMes(StrEnum):
    SUGERIDO = "sugerido"
    PROPUESTO = "propuesto"
    DEFINIDO = "definido"
    EN_EJECUCION = "en_ejecucion"
    CERRADO = "cerrado"


class MesCerradoError(Exception):
    """Se intentó editar un mes cerrado (histórico inmutable, regla 4)."""


class SaldoBanco(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    banco: Banco  # enum, no texto libre (Kimi B-2)
    saldo: Money
    fecha_reporte: str

    @field_validator("banco", mode="before")
    @classmethod
    def _cast_banco(cls, v: object) -> object:
        return v if isinstance(v, Banco) else Banco(v)

    @field_validator("fecha_reporte")
    @classmethod
    def _fecha(cls, v: object) -> str:
        return _valida_fecha(v)


class MesControl(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    mes: str  # 'YYYY-MM-01', llave de negocio (única)
    estado: EstadoMes = EstadoMes.SUGERIDO
    saldo_inicial_caja: Money
    saldos_banco: list[SaldoBanco] = Field(default_factory=list)
    ingresos_esperados_semana: Money | None = None
    definido_por: str | None = None
    definido_at: datetime | None = None
    cerrado_por: str | None = None
    cerrado_at: datetime | None = None

    class Settings:
        name = MESES_CONTROL_COLLECTION
        indexes = [IndexModel([("mes", 1)], name="mes_unico", unique=True)]

    @field_validator("mes")
    @classmethod
    def _mes_dia1(cls, v: object) -> str:
        return _valida_fecha(v, dia1=True)

    @field_validator("estado", mode="before")
    @classmethod
    def _cast_estado(cls, v: object) -> object:
        return v if isinstance(v, EstadoMes) else EstadoMes(v)

    @field_validator("definido_at", "cerrado_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("datetime debe ser UTC-aware (regla 2)")
        return v

    def assert_editable(self) -> None:
        """Los meses cerrados son inmutables (regla 4). Las tardías (tardia=true)
        son la única excepción y se manejan en el flujo de cierre (Sprint 4)."""
        if self.estado is EstadoMes.CERRADO:
            raise MesCerradoError(f"el mes {self.mes} está cerrado y es inmutable")
