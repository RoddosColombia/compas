# backend/app/domain/escenario_impacto.py
"""EscenarioImpacto (D1 §2) — un conjunto de ajustes what-if guardado con nombre.

Un escenario NO es histórico financiero (regla 4 no aplica): es un borrador reutilizable
("Sede nueva", "Ventas -10%"). Se guarda EXPLÍCITAMENTE (simular no escribe), con
auditoría (CR-D1) y baja lógica (`activo=false`). Cada ajuste guarda `valor` como
Decimal con precisión completa — un % (0.016) no se cuantiza.
"""

from datetime import datetime
from typing import Literal

from beanie import Document
from pydantic import BaseModel, ConfigDict, Field

from app.core.money import Money


class AjusteEmbebido(BaseModel):
    """Un delta declarativo del §2, embebido en el escenario. `valor` es COP (absoluto)
    o fracción (porcentaje, 0.10 = 10%). Se rechaza float (regla 1, vía Money)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    nombre: str = Field(min_length=1, max_length=80)
    naturaleza: Literal["gasto", "ingreso"]
    modo: Literal["absoluto", "porcentaje"]
    valor: Money
    mes_inicio: str  # 'YYYY-MM'
    mes_fin: str | None = None
    rubro_id: str | None = None


class EscenarioImpacto(Document):
    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str | None = Field(default=None, max_length=500)
    ajustes: list[AjusteEmbebido] = Field(default_factory=list)
    creado_por: str
    actualizado_at: datetime
    activo: bool = True

    class Settings:
        name = "escenarios_impacto"
        # Unicidad de nombre entre ACTIVOS se valida en el service (colección de bajo
        # volumen, un solo escritor); la baja lógica libera el nombre para reusarlo.
