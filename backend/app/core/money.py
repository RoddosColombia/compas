# backend/app/core/money.py
"""Tipo Money — dinero como Decimal, NUNCA float (regla 1 de CLAUDE.md).

Problema real que resuelve (cazado en Sprint 0b): BSON persiste `Decimal` como
`bson.Decimal128`; al releer desde Mongo, Pydantic con `strict=True` rechaza ese
valor porque no es una instancia de `Decimal`. `Money` coerciona Decimal128→Decimal
en la lectura y sigue rechazando float/bool (la fuente típica de errores de
redondeo). Los enteros y strings también se rechazan: la API parsea el string a
Decimal ANTES de construir el modelo, y el código de dominio pasa Decimal explícito.
"""

from decimal import ROUND_HALF_EVEN, Decimal
from typing import Annotated

from bson import Decimal128
from pydantic import BeforeValidator

_CENTAVO = Decimal("0.01")


def _coerce_decimal(v: object) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if isinstance(v, Decimal128):  # lo que devuelve BSON/Motor al releer
        return v.to_decimal()
    # bool es subclase de int: hay que descartarlo explícitamente.
    if isinstance(v, bool) or isinstance(v, float):
        raise ValueError("dinero debe ser Decimal, nunca float/bool (regla 1)")
    raise ValueError(
        f"dinero debe ser Decimal (o Decimal128 al leer); recibido {type(v).__name__}"
    )


# Decimal con coerción Decimal128→Decimal en la entrada. Úsese en todo campo COP.
Money = Annotated[Decimal, BeforeValidator(_coerce_decimal)]


def money_str(valor: Decimal) -> str:
    """Serializa un monto COP a string con 2 decimales (contrato de API, regla 1).

    Redondeo bancario HALF_EVEN. Los montos viajan como string en el JSON, nunca
    como número (para no perder precisión en el cliente)."""
    return str(valor.quantize(_CENTAVO, rounding=ROUND_HALF_EVEN))
