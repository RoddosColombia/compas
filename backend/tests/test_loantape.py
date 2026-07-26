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


def _raw(**kw) -> dict:
    base = {
        "credito_id": "CR-1",
        "fecha_corte": "2026-07-22",
        "modelo": "Raider",
        "fecha_desembolso": "2026-01-14",
        "monto_financiado": "6435000.00",
        "plazo_semanas": "78",
        "cuota_semanal": "164900.00",
        "cuotas_pagadas": "20",
        "cuotas_vencidas": "2",
        "dias_mora": "14",
        "saldo_en_mora": "329800.00",
        "saldo_pendiente": "9564200.00",
        "fecha_ultimo_pago": "2026-07-01",
        "estado": "en_mora",
        "cliente_id": "CLI-1",
    }
    base.update(kw)
    return base


def test_parse_fila_coacciona_tipos_y_rechaza_ambiguo():
    from decimal import Decimal

    from app.loantape.service import LoanTapeError, parse_fila_loantape

    f = parse_fila_loantape(_raw())
    assert f["monto_financiado"] == Decimal("6435000.00")
    assert f["plazo_semanas"] == 78
    assert f["dias_mora"] == 14
    # monto no numérico → error reportado, NO adivinado (regla 7)
    try:
        parse_fila_loantape(_raw(saldo_en_mora="N/D"))
        raise AssertionError("debió fallar")
    except LoanTapeError:
        pass
    # REQ faltante → error
    try:
        parse_fila_loantape(_raw(credito_id=""))
        raise AssertionError("debió fallar")
    except LoanTapeError:
        pass


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    from app.audit.service import configure_audit, reset_audit

    configure_audit(c, "compas_test")
    yield c
    reset_audit()


async def test_cargar_loantape_upsert_por_corte_e_idempotente(db):
    from app.loantape import service

    n = await service.cargar_loantape(
        [_raw(credito_id="A"), _raw(credito_id="B")], usuario_id="u1"
    )
    assert n == 2
    # recargar el MISMO corte con un valor corregido pisa, no duplica
    await service.cargar_loantape(
        [_raw(credito_id="A", dias_mora="40", saldo_en_mora="500000.00")],
        usuario_id="u1",
    )
    from app.domain.loantape import LoanTapeCredito

    total = await LoanTapeCredito.find_all().count()
    assert total == 2  # A (pisado) + B
    doc = await db["compas_test"]["audit_log"].find_one(
        {"evento": "loantape.cargado"}
    )
    assert doc is not None


async def test_obtener_aging_usa_el_ultimo_corte(db):
    from decimal import Decimal

    from app.loantape import service

    # corte viejo: todos al día
    await service.cargar_loantape(
        [_raw(credito_id="A", fecha_corte="2026-07-15", dias_mora="0",
              saldo_en_mora="0.00")],
        usuario_id="u1",
    )
    # corte nuevo: A cae en mora 40 días (500k) + B a 100 días (900k)
    await service.cargar_loantape(
        [
            _raw(credito_id="A", fecha_corte="2026-07-22", dias_mora="40",
                 saldo_en_mora="500000.00"),
            _raw(credito_id="B", fecha_corte="2026-07-22", dias_mora="100",
                 saldo_en_mora="900000.00"),
        ],
        usuario_id="u1",
    )
    aging = await service.obtener_aging()
    assert aging["fecha_corte"] == "2026-07-22"  # el más reciente
    por = {a["tramo"]: a for a in aging["tramos"]}
    assert por["31_60"]["saldo_en_mora"] == Decimal("500000.00")
    assert por["90_mas"]["saldo_en_mora"] == Decimal("900000.00")
    assert por["al_dia"]["n_creditos"] == 0  # el corte viejo no cuenta


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
