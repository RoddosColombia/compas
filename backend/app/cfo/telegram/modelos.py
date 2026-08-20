# backend/app/cfo/telegram/modelos.py
"""FABS · Documents del canal Telegram. Colecciones cfo_* (S1). Vínculo uno-a-uno
(único en telegram_id y user_id, B-3). El hilo guarda el texto CRUDO del modelo
(con [[tokens]], NUNCA valores) para preservar la garantía de Pieza A entre turnos."""

from datetime import datetime

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import IndexModel

CFO_VINCULOS_COLLECTION = "cfo_vinculos_telegram"
CFO_HILOS_COLLECTION = "cfo_hilos"


class VinculoTelegram(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    telegram_id: int
    user_id: str
    creado_por: str
    creado_at: datetime

    class Settings:
        name = CFO_VINCULOS_COLLECTION
        indexes = [
            IndexModel([("telegram_id", 1)], unique=True, name="telegram_id_unico"),
            IndexModel([("user_id", 1)], unique=True, name="user_id_unico"),
        ]


class HiloCFO(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    user_id: str
    turnos: list[dict] = Field(default_factory=list)
    ultimo_update_id: int | None = None
    ultimo_envio: str | None = None
    actualizado_at: datetime

    class Settings:
        name = CFO_HILOS_COLLECTION
        indexes = [
            IndexModel([("user_id", 1)], unique=True, name="user_id_unico"),
        ]
