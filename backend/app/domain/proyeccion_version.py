# backend/app/domain/proyeccion_version.py
"""RF-F2 (COMPAS 2.0) — versión INMUTABLE de la serie de proyección.

Fundacional §3: «La proyección se vuelve versionada: cada aprobación de mes produce una
versión inmutable de la serie; la anterior no se sobrescribe.» Esta es la ÚNICA entidad
cuyo ciclo de vida cambia en 2.0 — ningún otro objeto lo hace.

Patrón (igual que `PresupuestoLinea`): historia append-only con un puntero `vigente`.
Al aprobar, la versión anterior solo cambia `vigente→False` (su `serie` jamás se
sobrescribe); la nueva entra con `version = máx+1` y `vigente=True`. Un índice parcial
único sobre `vigente=True` garantiza una sola versión vigente.

`serie` guarda el JSON COMPLETO de `_serializar` (los ~23 campos + los meses del
horizonte), con los montos como string (regla 1). Es un snapshot fiel, no un resumen.
"""

from datetime import datetime

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import IndexModel

from app.core.time import now_utc

PROYECCION_VERSION_COLLECTION = "proyeccion_versiones"


class ProyeccionVersion(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    version: int  # secuencia global monótona (1, 2, 3…)
    vigente: bool = True  # exactamente una True = la última aprobada
    mes_aprobado: str  # 'YYYY-MM-01' — qué aprobación la creó (trazabilidad)
    escenario: str = "base"
    horizonte_meses: int
    serie: dict  # JSON completo de _serializar (montos como string, regla 1)
    piso_caja: str  # atajo para el diff (Decimal→string)
    mes_mas_ajustado: str  # mes del piso
    valles: list[dict] = Field(default_factory=list)  # snapshot de detectar_valles
    caja_minima: str  # umbral con el que se calculó
    creado_por: str
    creado_at: datetime = Field(default_factory=now_utc)

    class Settings:
        name = PROYECCION_VERSION_COLLECTION
        indexes = [
            IndexModel([("version", 1)], name="version_unica", unique=True),
            # Una sola versión vigente en todo el sistema (parcial sobre vigente=True).
            IndexModel(
                [("vigente", 1)],
                name="una_vigente",
                unique=True,
                partialFilterExpression={"vigente": True},
            ),
        ]
