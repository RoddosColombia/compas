# backend/app/cfo/vigilante/modelos.py
"""FABS · vigilante — avisos salientes (borrador→publicar). Un `AvisoVigilante` guarda
el borrador que un job proactivo arma (texto sustituido + texto_crudo con [[tokens]])
hasta que el revisor lo publica al comité. `tipo` distingue el paquete del lunes de la
alerta de caja; `(tipo, periodo)` es la clave de idempotencia (lunes / día)."""

from datetime import datetime

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import IndexModel

CFO_AVISOS_COLLECTION = "cfo_avisos_vigilante"


class AvisoVigilante(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    tipo: str  # 'paquete_lunes' | 'alerta_caja'
    periodo: str  # 'YYYY-MM-DD' (lunes para el paquete, día para la alerta)
    texto: str
    texto_crudo: str
    estado: str  # 'borrador' | 'publicado' | 'superado'
    generado_at: datetime
    publicado_at: datetime | None = None
    conceptos_usados: list[str] = Field(default_factory=list)

    class Settings:
        name = CFO_AVISOS_COLLECTION
        indexes = [
            IndexModel(
                [("tipo", 1), ("periodo", 1)], unique=True, name="tipo_periodo_unico"
            ),
        ]
