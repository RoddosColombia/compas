# backend/tests/modelos_moto/test_mix_activos.py
"""Task 5 (FABS inc4 rebanada 4, sub-rebanada 4b): `mix_activos`.

Devuelve nombre + participación de mix SOLO de los modelos activos, como tuplas
planas (str, Decimal) — sin exponer el tipo de dominio `ModeloMoto` a la capa
cfo/calc (S1)."""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.domain.modelo_moto import ModeloMoto
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)


def _modelo(**extra) -> ModeloMoto:
    base = dict(
        nombre="Raider",
        costo_auteco=Decimal("5000000"),
        precio_venta_con_iva=Decimal("8000000"),
        cuota_inicial=Decimal("1620000"),
        cuota_semanal=Decimal("184900"),
        plazo_semanas=78,
        matricula=Decimal("0"),
        participacion_mix=Decimal("0.35"),
        orden=1,
    )
    base.update(extra)
    return ModeloMoto(**base)


@pytest.mark.asyncio
async def test_mix_activos_solo_devuelve_nombre_y_participacion_de_activos(db):
    from app.modelos_moto.service import mix_activos

    await _modelo(
        nombre="Raider", participacion_mix=Decimal("0.5"), orden=1
    ).insert()
    await _modelo(
        nombre="Apache", participacion_mix=Decimal("0.3"), orden=2
    ).insert()
    await _modelo(
        nombre="Sport",
        participacion_mix=Decimal("0.2"),
        orden=3,
        activo=False,
    ).insert()

    resultado = await mix_activos()

    assert resultado == [("Raider", Decimal("0.5")), ("Apache", Decimal("0.3"))]
    # valores planos: nada de ModeloMoto se filtra a quien consuma esto
    assert all(isinstance(nombre, str) for nombre, _ in resultado)
    assert all(isinstance(mix, Decimal) for _, mix in resultado)
