# backend/app/cfo/agente/modelos.py
"""FABS · salida tipada del agente. Ninguna cifra viaja suelta: cada una lleva su
Evidencia. `strict=True, extra="forbid"` (regla 3). Montos como string (regla 1)."""

from pydantic import BaseModel, ConfigDict, Field

from app.cfo.calc.evidencia import Evidencia


class CifraPublicada(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    valor: str
    unidad: str
    evidencia: Evidencia


class UsoLLM(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    modelo: str
    tokens_in: int
    tokens_out: int
    iteraciones: int


class RespuestaCFO(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    texto: str
    abstuvo: bool
    motivo: str | None = None
    conceptos_usados: list[str] = Field(default_factory=list)
    cifras: list[CifraPublicada] = Field(default_factory=list)
    uso: UsoLLM
