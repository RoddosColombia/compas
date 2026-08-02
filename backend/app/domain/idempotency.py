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


# A-4.2 (P1-10): recuperación de marca huérfana. Un proceso que muere ENTRE el commit
# de la mutación y `marca.save()` deja la marca en curso (response_status=None) y
# bloquea la key durante las 24 h del TTL: la mutación se aplicó pero el cliente
# nunca obtuvo el resultado y el retry choca con 409. Pasados _HUERFANA_MIN se
# considera huérfana y un retry puede ADQUIRIRLA atómicamente (centinela -1) y
# re-ejecutar de forma convergente.
_HUERFANA_MIN = 5
_CENTINELA_REEJECUCION = -1


async def intentar_adquirir_huerfana(previa: IdempotencyKey) -> bool:
    """Adquiere atómicamente una marca en curso si lleva >_HUERFANA_MIN sin
    completarse. El update exige `response_status=None`, así que en una carrera solo
    UN request lo cambia a -1 y gana. Devuelve True si la adquirió (el caller
    re-ejecuta y persiste el resultado en `previa`); False si sigue fresca o ya la
    tomó otro (el caller responde 409). El centinela -1 se lee como 'en curso'."""
    umbral = now_utc() - timedelta(minutes=_HUERFANA_MIN)
    res = await IdempotencyKey.get_motor_collection().update_one(
        {
            "_id": previa.id,
            "response_status": None,
            "created_at": {"$lt": umbral},
        },
        {"$set": {"response_status": _CENTINELA_REEJECUCION}},
    )
    return res.modified_count == 1
