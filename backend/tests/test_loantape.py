# backend/tests/test_loantape.py
"""LoanTape SISMO-V3 (aging) — derivación PURA de mora por tramo + entidad.

Contrato: docs/CONTRATO-SISMO-V3-LOANTAPE.md. El aging se DERIVA (determinista) de
`dias_mora` + `saldo_en_mora`; no se inventa. Tramos: al día / 1-30 / 31-60 / 61-90 /
90+. Todo monto es Decimal (regla 1).
"""

from decimal import Decimal

import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.loantape.aging import TRAMOS, aging_por_tramo, tramo_de
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


def test_tramo_de_clasifica_por_dias():
    assert tramo_de(0) == "al_dia"
    assert tramo_de(1) == "1_30"
    assert tramo_de(30) == "1_30"
    assert tramo_de(31) == "31_60"
    assert tramo_de(60) == "31_60"
    assert tramo_de(61) == "61_90"
    assert tramo_de(90) == "61_90"
    assert tramo_de(91) == "90_mas"
    assert tramo_de(500) == "90_mas"


def test_aging_por_tramo_agrupa_monto_y_cuenta():
    items = [
        {"dias_mora": 0, "saldo_en_mora": Decimal("0")},
        {"dias_mora": 10, "saldo_en_mora": Decimal("100000")},
        {"dias_mora": 25, "saldo_en_mora": Decimal("200000")},
        {"dias_mora": 45, "saldo_en_mora": Decimal("300000")},
        {"dias_mora": 120, "saldo_en_mora": Decimal("500000")},
    ]
    aging = aging_por_tramo(items)
    # devuelve los 5 tramos SIEMPRE, en orden, con nº y monto
    assert [a["tramo"] for a in aging] == list(TRAMOS)
    por = {a["tramo"]: a for a in aging}
    assert por["al_dia"]["n_creditos"] == 1
    assert por["1_30"]["n_creditos"] == 2
    assert por["1_30"]["saldo_en_mora"] == Decimal("300000")  # 100k + 200k
    assert por["31_60"]["saldo_en_mora"] == Decimal("300000")
    assert por["61_90"]["n_creditos"] == 0
    assert por["61_90"]["saldo_en_mora"] == Decimal("0")
    assert por["90_mas"]["saldo_en_mora"] == Decimal("500000")


def test_aging_vacio_da_todos_los_tramos_en_cero():
    aging = aging_por_tramo([])
    assert [a["tramo"] for a in aging] == list(TRAMOS)
    assert all(
        a["n_creditos"] == 0 and a["saldo_en_mora"] == Decimal("0") for a in aging
    )


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield c


async def test_loantape_credito_persiste(db):
    from app.domain.loantape import LoanTapeCredito

    cr = LoanTapeCredito(
        credito_id="CR-000123",
        fecha_corte="2026-07-22",
        modelo="Raider",
        fecha_desembolso="2026-01-14",
        monto_financiado=Decimal("6435000.00"),
        plazo_semanas=78,
        cuota_semanal=Decimal("164900.00"),
        cuotas_pagadas=20,
        cuotas_vencidas=2,
        dias_mora=14,
        saldo_en_mora=Decimal("329800.00"),
        saldo_pendiente=Decimal("9564200.00"),
        estado="en_mora",
    )
    await cr.insert()
    leido = await LoanTapeCredito.find_one(
        LoanTapeCredito.credito_id == "CR-000123"
    )
    assert leido is not None
    assert leido.saldo_en_mora == Decimal("329800.00")
    assert leido.estado == "en_mora"
