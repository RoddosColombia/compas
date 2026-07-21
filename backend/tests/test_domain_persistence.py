# backend/tests/test_domain_persistence.py
"""Round-trip contra Beanie+mongomock: Decimal sobrevive (Decimal128→Decimal) y
la semilla es idempotente. La UNICIDAD de índices NO se prueba aquí (mongomock no
la exige) — eso está en test_domain_indexes.py con @requires_real_mongo."""

from decimal import Decimal

import pytest
from app.domain import DOMAIN_DOCUMENTS
from app.domain.configuracion import Configuracion
from app.domain.mes_control import MesControl
from app.domain.rubro import Rubro
from app.domain.seed import seed_configuracion, seed_rubros
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest.fixture
async def db():
    client = AsyncMongoMockClient()
    database = client["compas_test"]
    await init_beanie(database=database, document_models=DOMAIN_DOCUMENTS)
    return database


async def test_rubro_round_trip(db):
    await Rubro(grupo="operacion", nombre="Arriendos", orden=4).insert()
    got = await Rubro.find_one(Rubro.nombre == "Arriendos")
    assert got is not None and got.grupo.value == "operacion"


async def test_mes_control_decimal_round_trip(db):
    await MesControl(
        mes="2026-07-01", saldo_inicial_caja=Decimal("675967053.19")
    ).insert()
    got = await MesControl.find_one(MesControl.mes == "2026-07-01")
    assert isinstance(got.saldo_inicial_caja, Decimal)
    assert got.saldo_inicial_caja == Decimal("675967053.19")


async def test_configuracion_decimal_round_trip(db):
    await Configuracion(
        clave="UMBRAL_DIF_BANCO_CIERRE",
        valor_decimal=Decimal("50000"),
        vigente_desde="2026-01-01",
    ).insert()
    got = await Configuracion.find_one(Configuracion.clave == "UMBRAL_DIF_BANCO_CIERRE")
    assert got.valor_decimal == Decimal("50000")


async def test_seed_rubros_idempotente(db):
    n1 = await seed_rubros(db)
    total1 = await Rubro.find_all().count()
    n2 = await seed_rubros(db)  # segunda corrida: no debe duplicar
    total2 = await Rubro.find_all().count()
    assert n1 == 33 and total1 == 33
    assert n2 == 0 and total2 == 33
    sistema = await Rubro.find(Rubro.es_sistema == True).count()  # noqa: E712
    assert sistema == 3


async def test_seed_configuracion_idempotente(db):
    await seed_configuracion(db)
    await seed_configuracion(db)
    total = await Configuracion.find_all().count()
    assert total == 3
