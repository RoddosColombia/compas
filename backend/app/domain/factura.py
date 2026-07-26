# backend/app/domain/factura.py
"""Factura (C11, PR-2a "Fidelidad de caja") — una factura de compra o venta cargada
para liquidar el IVA cuatrimestral y restar el IVA neto de la caja en la fecha DIAN.

NO es un movimiento bancario (eso es `Transaccion`): es el insumo del liquidador de
IVA. `iva_valor`/`total` los calcula el backend desde `base_gravable`×`tarifa_iva`
(regla 1: todo cálculo de dinero en el backend). Baja LÓGICA (`activo`): una factura
mal cargada se anula, no se borra (regla 4 / auditoría). Dedup (regla 5): índice único
parcial (tercero_nit, numero) — el par NIT+número es el identificador natural de una
factura; dos proveedores con el mismo número NO colisionan. Cuatrimestre = DERIVADO de
`fecha` (no se persiste; lo calcula `iva.liquidacion.periodo_de` según la periodicidad).

Auteco (NIT 860024781) es autorretenedor: su IVA SÍ es descontable (`deducible=True`),
pero NUNCA se le aplica ReteFuente (regla de contabilidad RODDOS). CUATRIMESTRAL 19%.
"""

import re
from datetime import datetime
from enum import StrEnum

from beanie import Document
from pydantic import ConfigDict, Field, field_validator
from pymongo import IndexModel

from app.core.money import Money

FACTURAS_COLLECTION = "facturas"

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TipoFactura(StrEnum):
    venta = "venta"  # genera IVA (débito fiscal)
    compra = "compra"  # IVA descontable si es deducible


class OrigenFactura(StrEnum):
    auteco = "auteco"  # compra del lote de motos a Auteco (autorretenedor)
    otra_compra = "otra_compra"
    moto = "moto"  # venta de moto
    repuesto = "repuesto"
    servicio = "servicio"
    otro = "otro"


class Factura(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    tipo: TipoFactura
    origen: OrigenFactura
    numero: str = Field(min_length=1, max_length=60)
    tercero_nombre: str = Field(min_length=1, max_length=200)
    tercero_nit: str = Field(min_length=1, max_length=30)
    fecha: str  # 'YYYY-MM-DD' (Bogotá); el cuatrimestre se deriva de aquí
    base_gravable: Money
    tarifa_iva: Money  # fracción (0.19 general, 0 exento)
    iva_valor: Money  # = base_gravable × tarifa_iva (lo calcula el servicio)
    total: Money  # = base_gravable + iva_valor
    deducible: bool = False  # solo compras: si su IVA es descontable
    activo: bool = True  # baja lógica (anulación)

    class Settings:
        name = FACTURAS_COLLECTION
        indexes = [
            # Regla 5: dedup por el par natural NIT+número. Único donde numero es
            # string (siempre). En Mongo real lanza DuplicateKeyError; mongomock no lo
            # exige → la unicidad real se prueba con @requires_real_mongo.
            IndexModel(
                [("tercero_nit", 1), ("numero", 1)],
                name="nit_numero_unico",
                unique=True,
                partialFilterExpression={"numero": {"$type": "string"}},
            ),
            IndexModel([("fecha", 1)], name="por_fecha"),
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

    @field_validator("tipo", mode="before")
    @classmethod
    def _cast_tipo(cls, v: object) -> object:
        return v if isinstance(v, TipoFactura) else TipoFactura(v)

    @field_validator("origen", mode="before")
    @classmethod
    def _cast_origen(cls, v: object) -> object:
        return v if isinstance(v, OrigenFactura) else OrigenFactura(v)
