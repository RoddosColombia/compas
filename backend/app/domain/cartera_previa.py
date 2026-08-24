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
from pydantic import ConfigDict, Field, field_validator
from pymongo import IndexModel

from app.core.money import Money

CARTERA_PREVIA_COLLECTION = "cartera_previa_recaudo"
COLOCACION_MES_COLLECTION = "colocacion_mes"


class CarteraPreviaRecaudo(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    semana_global: int = Field(gt=0)  # semana global (ancla = mié 2026-03-04 = 1)
    recaudo: Money  # recaudo REAL de la cartera previa esa semana (con moras)
    n_activos: int = Field(ge=0)  # créditos previos vivos esa semana

    class Settings:
        name = CARTERA_PREVIA_COLLECTION
        # Único por semana (upsert idempotente). Unicidad real → @requires_real_mongo.
        indexes = [IndexModel([("semana_global", 1)], name="semana_unica", unique=True)]


class ColocacionMes(Document):
    """P6 del ciclo mensual — motos REALMENTE colocadas en un mes.

    Es el insumo del TERMÓMETRO (Paso 2 del contrato): "llevamos 35 de la meta de 60".
    Sale de la cuota 0 del cronograma de SISMO (el desembolso marca el mes en que se
    colocó cada moto) y se refresca en cada carga semanal.

    **No entra al motor.** La proyección del mes usa la META (dato del CEO); esto solo
    se muestra al lado para leer la desviación. Si alimentara el motor volveríamos al
    error que P4 eliminó: la realidad pisando el objetivo."""

    model_config = ConfigDict(strict=True, extra="forbid")

    mes: str  # 'YYYY-MM'
    unidades: int = Field(ge=0)
    fuente: str = "cronograma"  # de dónde salió (hoy solo el cronograma de SISMO)

    class Settings:
        name = COLOCACION_MES_COLLECTION
        indexes = [IndexModel([("mes", 1)], name="mes_unico", unique=True)]

    @field_validator("mes")
    @classmethod
    def _mes_valido(cls, v: str) -> str:
        if len(v) != 7 or v[4] != "-" or not (v[:4] + v[5:]).isdigit():
            raise ValueError(f"mes inválido '{v}' (usa YYYY-MM)")
        return v
