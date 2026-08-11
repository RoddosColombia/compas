# backend/app/cfo/goldens/modelo.py
"""FABS · caso dorado. Un valor esperado (calculado a mano desde COMPAS) para
un concepto de cfo/calc, con su tolerancia. El runner compara el resultado
real contra esto. `valor_esperado=None` ⇒ caso de ABSTENCIÓN (el concepto
debe dar disponible=False)."""

from datetime import datetime

from beanie import Document
from pydantic import ConfigDict, Field

from app.core.money import Money

CFO_GOLDENS_COLLECTION = "cfo_goldens"


class CFOGolden(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    concepto: str
    filtros: dict = Field(default_factory=dict)
    valor_esperado: Money | None
    tolerancia: Money  # Decimal; COP para montos, 0.1 para "meses"
    unidad: str
    origen: str  # 'semilla' | 'fabian'
    nota: str | None = None
    creado_at: datetime

    class Settings:
        name = CFO_GOLDENS_COLLECTION
