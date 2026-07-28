# backend/app/domain/cartera_previa.py
"""CarteraPreviaRecaudo (PR-1 "Fidelidad de caja") — serie semanal REAL del recaudo de
los 111 créditos preexistentes (LoanTape / 'Modelo Pagos'), incluidas moras y semanas
sin pago. Es un TERCER sumando del recaudo de crédito del motor (no una tercera vía):
réplica de `RECAUDO_PREVIA_SEMANAL` del `Dashboard_Artefacto.jsx`.

Dato PERSISTENTE (regla NORTE) y ADMINISTRABLE (regla 9): se siembra una vez desde la
serie del artefacto (migración idempotente) y el CEO puede corregirlo. Serie FINITA:
w1 = mié 2026-03-04 … ~w97 (ene-2028), cuando la cartera previa se agota. Todo monto es
Money/Decimal (regla 1)."""

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import IndexModel

from app.core.money import Money

CARTERA_PREVIA_COLLECTION = "cartera_previa_recaudo"


class CarteraPreviaRecaudo(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    semana_global: int = Field(gt=0)  # semana global (ancla = mié 2026-03-04 = 1)
    recaudo: Money  # recaudo REAL de la cartera previa esa semana (con moras)
    n_activos: int = Field(ge=0)  # créditos previos vivos esa semana

    class Settings:
        name = CARTERA_PREVIA_COLLECTION
        # Único por semana (upsert idempotente). Unicidad real → @requires_real_mongo.
        indexes = [IndexModel([("semana_global", 1)], name="semana_unica", unique=True)]
