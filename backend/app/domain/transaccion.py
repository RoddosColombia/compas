# backend/app/domain/transaccion.py
"""Transaccion (Spec §1.5): un movimiento bancario ya normalizado y persistible.

Reglas:
  - Regla 1: `valor` es Money (Decimal), siempre > 0. El signo lo define `tipo_flujo`.
  - Regla 2: `fecha` como string 'YYYY-MM-DD' (mismo criterio que MesControl: BSON
    no tiene fecha-sin-hora). `mes_id` referencia el MesControl derivado de la fecha.
  - Regla 5: deduplicación en la BD por índice ÚNICO PARCIAL (banco, id_banco) con
    `partialFilterExpression {id_banco: {$type:'string'}}`. `id_banco` es determinista
    (ver `derivar_id_banco`) → re-cargar un extracto solapado no duplica.
  - Global66 (regla 7): conserva `moneda_original`/`valor_original`/`tasa_cambio`/
    `tasa_fuente` cuando el extracto no viene en COP (hoy la hoja COP → 'COP'/1).

`id_banco`: de extracto si banco≠manual (Global66: referencia nativa; Bancolombia/
BBVA: huella determinista, no traen ID); manuales 'MAN-'+ULID (F-04, feature aparte).
La inmutabilidad de fecha/valor/moneda/tasa/id_banco/banco (Spec §2.2) se hace cumplir
en la capa de servicio (no se actualizan esos campos), no en el modelo.
"""

import hashlib
import re
from datetime import datetime

from beanie import Document, PydanticObjectId
from pydantic import ConfigDict, Field, field_validator
from pymongo import IndexModel

from app.core.money import Money
from app.domain.bancos import Banco
from app.domain.rubro import TipoFlujo

TRANSACCIONES_COLLECTION = "transacciones"

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def derivar_id_banco(
    *,
    banco: Banco,
    fecha: str,
    descripcion: str,
    valor,
    tipo_flujo: TipoFlujo,
    referencia: str | None = None,
) -> str:
    """Clave de deduplicación estable (regla 5).

    - Global66 trae una referencia de transacción nativa → se usa tal cual.
    - Bancolombia/BBVA no traen ID → huella determinista del contenido
      (banco|fecha|tipo|descripcion|valor), precedente de SISMO v2. MD5 (no
      criptográfico, solo fingerprint) = 32 hex, cabe en String(40).
    """
    if banco is Banco.GLOBAL66 and referencia:
        return referencia
    clave = f"{banco.value}|{fecha}|{tipo_flujo.value}|{descripcion}|{valor:.2f}"
    return hashlib.md5(clave.encode("utf-8"), usedforsecurity=False).hexdigest()


class Transaccion(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    fecha: str  # 'YYYY-MM-DD'
    descripcion: str = Field(max_length=300)
    valor: Money  # > 0 (magnitud); el signo lo da tipo_flujo
    tipo_flujo: TipoFlujo
    rubro_id: PydanticObjectId  # default 'Por clasificar' (lo resuelve el servicio)
    mes_id: PydanticObjectId  # MesControl derivado de la fecha
    banco: Banco
    id_banco: str = Field(max_length=40)
    tardia: bool = False

    # Moneda extranjera (Global66, regla 7) — condicional.
    moneda_original: str | None = None
    valor_original: Money | None = None
    tasa_cambio: Money | None = None
    tasa_fuente: str | None = None

    # Origen y auditoría de clasificación (§1.5).
    carga_id: PydanticObjectId | None = None
    clasificada_por: str | None = None
    clasificada_at: datetime | None = None
    pago_planeado_id: PydanticObjectId | None = None
    factura_id: PydanticObjectId | None = None
    regla_id: PydanticObjectId | None = None

    class Settings:
        name = TRANSACCIONES_COLLECTION
        indexes = [
            # Regla 5: dedup. Único solo donde id_banco es string (siempre, hoy);
            # el partial deja la puerta para docs legacy sin id_banco string.
            IndexModel(
                [("banco", 1), ("id_banco", 1)],
                name="banco_idbanco_unico",
                unique=True,
                partialFilterExpression={"id_banco": {"$type": "string"}},
            ),
            IndexModel([("mes_id", 1)], name="por_mes"),
            IndexModel([("rubro_id", 1)], name="por_rubro"),
            IndexModel([("carga_id", 1)], name="por_carga"),
        ]

    @field_validator("fecha")
    @classmethod
    def _fecha_str(cls, v: object) -> str:
        if not isinstance(v, str) or not _FECHA.match(v):
            raise ValueError("fecha debe ser string 'YYYY-MM-DD'")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"fecha inválida: {v}") from e
        return v

    @field_validator("valor")
    @classmethod
    def _valor_positivo(cls, v):
        if v <= 0:
            raise ValueError("valor debe ser > 0; el signo lo define tipo_flujo")
        return v

    @field_validator("banco", mode="before")
    @classmethod
    def _cast_banco(cls, v: object) -> object:
        return v if isinstance(v, Banco) else Banco(v)

    @field_validator("tipo_flujo", mode="before")
    @classmethod
    def _cast_tipo(cls, v: object) -> object:
        return v if isinstance(v, TipoFlujo) else TipoFlujo(v)

    @field_validator("clasificada_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("datetime debe ser UTC-aware (regla 2)")
        return v
