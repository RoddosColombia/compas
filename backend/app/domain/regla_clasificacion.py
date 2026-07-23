# backend/app/domain/regla_clasificacion.py
"""ReglaClasificacion (Spec §1.9, C3 auto-clasificación — GO Kimi PLAN-I 9.3).

Regla administrable: `patron` (contains case-insensitive y sin tildes) sobre la
descripción del movimiento → `rubro_id`. "Primera regla que matchea por prioridad
gana" (ascendente; empate → _id como desempate estable). `origen`:
manual | aprendida (propuesta desde reclasificación con `proponer_regla`; requiere
aprobación del Financiero, NUNCA auto-activada — §1.9).

NORMALIZACIÓN ÚNICA COMPARTIDA (Kimi §3 — el punto delicado): `normalizar_texto`
es LA función que normaliza tanto el patrón al escribir la regla
(`patron_normalizado`, derivado automáticamente) como la descripción al matchear
(`coincide`). Si divergieran, habría fallo silencioso — por eso viven juntas aquí.

Unicidad (regla 7): índice único PARCIAL (patron_normalizado, tipo_flujo) con
`activa=true` — dos reglas ACTIVAS idénticas son ambigüedad; duplicados
desactivados se permiten (histórico de configuración).
"""

import unicodedata
from datetime import datetime
from enum import StrEnum

from beanie import Document, PydanticObjectId
from pydantic import ConfigDict, Field, field_validator, model_validator
from pymongo import IndexModel

from app.core.time import now_utc
from app.domain.rubro import TipoFlujo

REGLAS_COLLECTION = "reglas_clasificacion"

PATRON_MIN = 3  # guarda contra match-all (Kimi §3)


def normalizar_texto(texto: str) -> str:
    """lower + sin tildes/diacríticos + trim. ÚNICA normalización del matching."""
    descompuesto = unicodedata.normalize("NFD", texto)
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_tildes.lower().strip()


def coincide(patron: str, descripcion: str) -> bool:
    """¿El patrón (contains normalizado) aparece en la descripción?"""
    return normalizar_texto(patron) in normalizar_texto(descripcion)


class OrigenRegla(StrEnum):
    MANUAL = "manual"
    APRENDIDA = "aprendida"  # propuesta; requiere aprobación (§1.9)


class ReglaClasificacion(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    patron: str = Field(min_length=PATRON_MIN, max_length=120)
    patron_normalizado: str = ""  # derivado de patron (model_validator)
    rubro_id: PydanticObjectId
    tipo_flujo: TipoFlujo
    prioridad: int
    origen: OrigenRegla = OrigenRegla.MANUAL
    activa: bool = True
    creada_por: str
    created_at: datetime = Field(default_factory=now_utc)

    class Settings:
        name = REGLAS_COLLECTION
        indexes = [
            IndexModel([("prioridad", 1)], name="por_prioridad"),
            # Regla 7: dos reglas ACTIVAS con el mismo patrón+tipo = ambigüedad.
            # Parcial: las desactivadas no cuentan (mongomock no lo exige → el
            # pre-check del service cubre el flujo normal; el índice, la carrera).
            IndexModel(
                [("patron_normalizado", 1), ("tipo_flujo", 1)],
                name="patron_tipo_activa_unico",
                unique=True,
                partialFilterExpression={"activa": True},
            ),
        ]

    @field_validator("tipo_flujo", mode="before")
    @classmethod
    def _cast_tipo(cls, v: object) -> object:
        return v if isinstance(v, TipoFlujo) else TipoFlujo(v)

    @field_validator("origen", mode="before")
    @classmethod
    def _cast_origen(cls, v: object) -> object:
        return v if isinstance(v, OrigenRegla) else OrigenRegla(v)

    @field_validator("created_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("datetime debe ser UTC-aware (regla 2)")
        return v

    @model_validator(mode="after")
    def _derivar_normalizado(self) -> "ReglaClasificacion":
        # SIEMPRE derivado del patrón vigente — nunca se acepta un valor divergente.
        object.__setattr__(self, "patron_normalizado", normalizar_texto(self.patron))
        if len(self.patron_normalizado) < PATRON_MIN:
            raise ValueError(
                f"el patrón normalizado queda menor a {PATRON_MIN} caracteres"
            )
        return self
