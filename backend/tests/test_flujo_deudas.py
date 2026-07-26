# backend/tests/test_flujo_deudas.py
"""Import del Excel curado 'Flujo de pagos deudas' (Base real egresos/ingresos).

A diferencia de un extracto bancario, aquí la clasificación YA viene hecha por el CEO
(columna `Categoría`) — el parser NO clasifica, solo transforma y valida (regla 7):
fecha/valor inválido o categoría sin rubro = error reportado, jamás adivinado. Reusa
`movimiento_a_transaccion` (id_banco por ID nativo de Global66 o huella determinista).
"""

from datetime import date
from decimal import Decimal

import pytest
from app.cargas.flujo_deudas import (
    FilaFlujoError,
    parse_fila_flujo,
    resolver_rubro_id,
)
from app.domain.bancos import Banco
from app.domain.rubro import TipoFlujo
from app.parsers.bank_parsers import TipoMovimiento
from beanie import PydanticObjectId


def test_egreso_se_transforma_con_id_nativo():
    mov = parse_fila_flujo(
        {
            "fecha": "2026-03-06",
            "descripcion": "Pago prestamo X",
            "valor": "5800000",
            "id_banco": "11499647",
        },
        tipo_flujo=TipoFlujo.EGRESO,
    )
    assert mov.fecha == date(2026, 3, 6)
    assert mov.monto == Decimal("5800000")
    assert mov.tipo is TipoMovimiento.DEBITO  # egreso → débito
    assert mov.banco is Banco.GLOBAL66
    assert mov.referencia == "11499647"  # ID banco nativo → dedup


def test_ingreso_es_credito():
    mov = parse_fila_flujo(
        {"fecha": "2026-03-05", "descripcion": "Abono", "valor": "3800000",
         "id_banco": "11495562"},
        tipo_flujo=TipoFlujo.INGRESO,
    )
    assert mov.tipo is TipoMovimiento.CREDITO  # ingreso → crédito


def test_fila_sin_id_banco_no_lleva_referencia():
    # 56 filas del Excel no traen ID banco → referencia None → el mapper les da
    # una huella determinista (idempotente), no las descarta.
    mov = parse_fila_flujo(
        {"fecha": "2026-04-01", "descripcion": "Ajuste", "valor": "100000",
         "id_banco": None},
        tipo_flujo=TipoFlujo.EGRESO,
    )
    assert mov.referencia is None


def test_valor_no_numerico_es_error_no_se_adivina():
    with pytest.raises(FilaFlujoError):
        parse_fila_flujo(
            {"fecha": "2026-03-06", "descripcion": "X", "valor": "N/D",
             "id_banco": "1"},
            tipo_flujo=TipoFlujo.EGRESO,
        )


def test_fecha_invalida_es_error():
    with pytest.raises(FilaFlujoError):
        parse_fila_flujo(
            {"fecha": "no-es-fecha", "descripcion": "X", "valor": "1000",
             "id_banco": "1"},
            tipo_flujo=TipoFlujo.EGRESO,
        )


def test_resolver_rubro_falla_loud_si_categoria_no_mapea():
    mapa = {"Cafetería": PydanticObjectId()}
    assert resolver_rubro_id("Cafetería", mapa) == mapa["Cafetería"]
    with pytest.raises(FilaFlujoError):
        resolver_rubro_id("Inventada", mapa)  # regla 7: no se inventa rubro
