# backend/app/cfo/vigilante/modelos.py
"""FABS · vigilante (watchdog) — el "paquete del lunes". `PaqueteVigilante` guarda
el borrador semanal que el job arma (texto narrado + texto_crudo con [[tokens]],
mismo patrón que el hilo de Telegram) hasta que el revisor lo publica al comité."""

from datetime import datetime

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import IndexModel

CFO_PAQUETES_COLLECTION = "cfo_paquetes_vigilante"


class PaqueteVigilante(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    semana: str  # 'YYYY-MM-DD' del lunes (idempotencia)
    texto: str
    texto_crudo: str
    estado: str  # 'borrador' | 'publicado'
    generado_at: datetime
    publicado_at: datetime | None = None
    conceptos_usados: list[str] = Field(default_factory=list)

    class Settings:
        name = CFO_PAQUETES_COLLECTION
        indexes = [
            IndexModel([("semana", 1)], unique=True, name="semana_unica"),
        ]
