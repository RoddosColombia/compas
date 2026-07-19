# backend/app/audit/models.py
"""Esquema AuditLog (append-only). Spec §1.11 / §2.3.

Es un Pydantic BaseModel plano (strict): valida y serializa el registro que
`emit_audit` inserta por la conexión DEDICADA de auditoría. NO es un Beanie
Document: las escrituras no pasan por el ODM general (van por `compas_audit`), y
las lecturas (query service) llegan en un PR posterior — reusarán ESTE mismo
schema. La inmutabilidad la imponen los PRIVILEGIOS de BD; `$jsonSchema` (Sprint
0b) es defensa en profundidad."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.audit.events import AuditEvento
from app.core.time import now_utc

AUDIT_COLLECTION = "audit_log"

# Índice forense (Spec §2.3). Lo crea el script de setup (create_audit_role.py) con
# privilegios de admin — NO el rol audit_writer (solo insert+find).
AUDIT_INDEXES = [
    {
        "keys": [("entidad", 1), ("entidad_id", 1), ("timestamp", 1)],
        "name": "forense_entidad_ts",
    },
]


class AuditLog(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")  # regla 3

    evento: AuditEvento
    entidad: str
    # entidad_id / actor_id: str (forma canónica del id referenciado) para consultas
    # forenses consistentes con el índice (entidad, entidad_id, timestamp).
    # Kimi O2: decisión explícita str (no ObjectId); el _id del audit lo pone Mongo.
    entidad_id: str | None = None
    actor_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # H-07: debe ser BSON-able
    timestamp: datetime = Field(default_factory=now_utc)  # UTC aware (regla A-04)

    @field_validator("evento", mode="before")
    @classmethod
    def _cast_evento(cls, v: Any) -> AuditEvento:
        # H-04: strict rechazaría un str; casteamos str→enum al leer desde Mongo
        # (query service futuro). AuditEvento(v) lanza ValueError si no está en el
        # catálogo cerrado (regla 11).
        return v if isinstance(v, AuditEvento) else AuditEvento(v)

    @field_validator("timestamp")
    @classmethod
    def _timestamp_aware(cls, v: datetime) -> datetime:
        # H-05: nunca naive. BSON no guarda tz; el cliente usa tz_aware=True y aquí
        # rechazamos cualquier naive que se cuele (regla A-04).
        if v.tzinfo is None:
            raise ValueError("timestamp debe ser UTC-aware (regla A-04), no naive")
        return v
