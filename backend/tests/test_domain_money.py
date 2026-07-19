# backend/tests/test_domain_money.py
"""Tipo Money: Decimal end-to-end, jamás float (regla 1 de CLAUDE.md).

BSON persiste Decimal como Decimal128; al releer, Pydantic strict lo rechaza
salvo que lo coercionemos a Decimal. Este tipo es la defensa: acepta Decimal y
Decimal128, y RECHAZA float/bool (la fuente típica de errores de redondeo)."""

from decimal import Decimal

import pytest
from app.core.money import Money, money_str
from bson import Decimal128
from pydantic import BaseModel, ConfigDict, ValidationError


class _M(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    v: Money


def test_acepta_decimal():
    assert _M(v=Decimal("1234567.89")).v == Decimal("1234567.89")


def test_acepta_decimal128_de_mongo():
    # Lo que devuelve BSON/Motor al releer un Decimal.
    m = _M(v=Decimal128("50000.00"))
    assert isinstance(m.v, Decimal)
    assert m.v == Decimal("50000.00")


@pytest.mark.parametrize("malo", [1234.5, 0.1, True, False])
def test_rechaza_float_y_bool(malo):
    with pytest.raises(ValidationError):
        _M(v=malo)


@pytest.mark.parametrize("malo", ["1000", 1000, None])
def test_rechaza_str_int_none(malo):
    # Forzamos a los llamadores a pasar Decimal explícito (la API parsea el
    # string a Decimal ANTES de construir el modelo).
    with pytest.raises(ValidationError):
        _M(v=malo)


def test_money_str_dos_decimales():
    assert money_str(Decimal("50000")) == "50000.00"
    assert money_str(Decimal("1234567.891")) == "1234567.89"  # HALF_EVEN
