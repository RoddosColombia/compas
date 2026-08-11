"""FABS · contrato de evidencia. Toda cifra que FABS publica viaja envuelta en
ResultadoCFO con su Evidencia (fuente + fecha de corte + ref reproducible). Sin
evidencia no hay cifra; sin dato, `disponible=False` y `valor=None` (abstención)."""

from pydantic import BaseModel, ConfigDict, Field

from app.core.money import Money


class Evidencia(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    fuente: str
    fecha_corte: str | None  # 'YYYY-MM-DD' del dato más reciente (None si no aplica)
    ref: str  # identificador reproducible: mes de control, cuatrimestre, etc.


class ResultadoCFO(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    concepto: str
    valor: Money | None
    unidad: str
    disponible: bool
    evidencia: Evidencia
    detalle: dict = Field(default_factory=dict)
