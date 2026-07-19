# backend/app/audit/models.py
"""Esquema AuditLog (append-only). Spec §1.11 / §2.3.

Es un Pydantic BaseModel plano (strict): valida y serializa el registro que
`emit_audit` inserta por la conexión DEDICADA de auditoría. NO es un Beanie
Document: las escrituras no pasan por el ODM general (van por `compas_audit`), y
las lecturas (query service) llegan en un PR posterior. La inmutabilidad la impone
los PRIVILEGIOS de BD; `$jsonSchema` (Sprint 0b) es defensa en profundidad."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.audit.events import AuditEvento
from app.core.time import now_utc

AUDIT_COLLECTION = "audit_log"

# Índice forense (Spec §2.3). Lo crea la migración/init (Sprint 0b), no este módulo.
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
    # entidad_id / actor_id: str (forma canónica en texto del id referenciado) para
    # consultas forenses consistentes con el índice (entidad, entidad_id, timestamp).
    # Kimi O2: decisión explícita str (no ObjectId); el _id del audit lo pone Mongo.
    entidad_id: str | None = None
    actor_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=now_utc)  # UTC aware (regla A-04)
