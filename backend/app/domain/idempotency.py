# backend/app/domain/idempotency.py
"""IdempotencyKeys (Spec §1.12, F-13): replay seguro de POST sensibles.

Scope = índice ÚNICO COMPUESTO (usuario_id, endpoint, key). Se guarda el hash
del request y la respuesta original: misma clave + mismo payload → replay de la
respuesta; misma clave + payload distinto → 422. TTL 24 h (expires_at + índice
expireAfterSeconds=0, patrón E-6)."""

from datetime import datetime, timedelta

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import IndexModel

from app.core.time import now_utc

IDEMPOTENCY_COLLECTION = "idempotency_keys"
_TTL_HORAS = 24


def _expira() -> datetime:
    return now_utc() + timedelta(hours=_TTL_HORAS)


class IdempotencyKey(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    usuario_id: str
    endpoint: str
    key: str
    request_hash: str  # sha256 del payload canónico
    response_status: int | None = None  # None = petición aún en curso
    response_body: dict | None = None
    created_at: datetime = Field(default_factory=now_utc)
    expires_at: datetime = Field(default_factory=_expira)

    class Settings:
        name = IDEMPOTENCY_COLLECTION
        indexes = [
            IndexModel(
                [("usuario_id", 1), ("endpoint", 1), ("key", 1)],
                name="scope_unico",
                unique=True,
            ),
            IndexModel([("expires_at", 1)], name="ttl", expireAfterSeconds=0),
        ]
