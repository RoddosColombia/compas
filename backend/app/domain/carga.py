# backend/app/domain/carga.py
"""CargaBancaria (Spec §1.6): ciclo de vida de una carga de extracto (F-02).

Inserción idempotente por lotes (§1.6): `insertMany ordered=False`, duplicados
contados por DuplicateKeyError contra el índice único parcial (banco, id_banco) de
Transaccion. El rechazo por `archivo_hash` aplica SOLO si existe una carga previa
'completada' con ese hash; si la previa está 'fallida', la re-carga se permite (la
dedup por (banco, id_banco) hace el reintento seguro).

`archivo_s3_key` es opcional: el almacenamiento del original en S3 está diferido
(RUNBOOK §6, S3 pendiente). Desviación documentada del §1.6 (Req) → gate Kimi.
"""

import re
from datetime import datetime
from enum import StrEnum

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo import IndexModel

from app.core.time import now_utc
from app.domain.bancos import Banco

CARGAS_COLLECTION = "cargas"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EstadoCarga(StrEnum):
    PROCESANDO = "procesando"
    COMPLETADA = "completada"
    FALLIDA = "fallida"


class ErrorCarga(BaseModel):
    """Fila del extracto que no se pudo transformar/ubicar (regla 7)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    fila: int  # número de fila del extracto; -1 = error no ligado a una fila
    motivo: str
    valor_crudo: str | None = None  # texto crudo para el Financiero (regla 7)


class CargaBancaria(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    banco: Banco  # solo bancos reales (no 'manual')
    archivo_nombre: str
    archivo_hash: str  # SHA-256 hex del archivo (dedup de archivo, F-02)
    archivo_s3_key: str | None = None  # S3 diferido (RUNBOOK §6)
    total_filas: int = 0
    nuevas: int = 0
    duplicadas: int = 0
    errores: int = 0
    # C3 (GO Kimi 9.3): contadores de auto-clasificación sobre las NUEVAS
    # insertadas (D3: el rastro por doc es regla_id; el agregado vive aquí y en
    # la metadata de carga.completada).
    clasificadas: int = 0
    por_clasificar: int = 0
    # D2 (fail-loud informativo, patrón B-4): patrones de reglas ACTIVAS cuyo
    # rubro está inactivo — se saltaron al clasificar esta carga.
    reglas_con_rubro_inactivo: list[str] = Field(default_factory=list)
    errores_detalle: list[ErrorCarga] = Field(default_factory=list)
    estado: EstadoCarga = EstadoCarga.PROCESANDO
    motivo_fallo: str | None = None
    usuario_id: PydanticObjectId
    created_at: datetime = Field(default_factory=now_utc)

    class Settings:
        name = CARGAS_COLLECTION
        indexes = [
            IndexModel([("archivo_hash", 1), ("estado", 1)], name="hash_estado"),
            # RF-F6 · Fundacional §2 — Cargas idempotentes por huella. Índice único
            # parcial: para el mismo (banco, hash), solo UNA carga puede quedar como
            # COMPLETADA. Es el candado de BD contra el race entre dos cargas
            # concurrentes del mismo archivo (Bancolombia septiembre) — la consulta
            # de dedup en `service.procesar_carga` sigue atrapando el caso normal y
            # este índice cierra la carrera. La escritura fatal ocurre en
            # `service._finalizar` al pasar el estado a COMPLETADA; ahí se traduce el
            # DuplicateKeyError a `CargaDuplicadaError` (mismo 409 idempotente que la
            # ruta por consulta).
            IndexModel(
                [("banco", 1), ("archivo_hash", 1)],
                name="banco_hash_completada_unico",
                unique=True,
                partialFilterExpression={"estado": "completada"},
            ),
        ]

    @field_validator("banco", mode="before")
    @classmethod
    def _cast_banco(cls, v: object) -> object:
        b = v if isinstance(v, Banco) else Banco(v)
        if b is Banco.MANUAL:
            raise ValueError("una carga proviene de un banco real, no 'manual'")
        return b

    @field_validator("archivo_hash")
    @classmethod
    def _hash_sha256(cls, v: object) -> str:
        if not isinstance(v, str) or not _SHA256.match(v):
            raise ValueError("archivo_hash debe ser SHA-256 hex (64 chars)")
        return v

    @field_validator("estado", mode="before")
    @classmethod
    def _cast_estado(cls, v: object) -> object:
        return v if isinstance(v, EstadoCarga) else EstadoCarga(v)

    @field_validator("created_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("datetime debe ser UTC-aware (regla 2)")
        return v
