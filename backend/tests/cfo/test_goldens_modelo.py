# backend/tests/cfo/test_goldens_modelo.py
"""Task 7 FABS inc1 — modelo `CFOGolden` (Beanie Document, colección `cfo_goldens`)
registrado en Beanie vía `DOMAIN_DOCUMENTS`. Persiste y relee un caso dorado."""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield c


@pytest.mark.asyncio
async def test_persistir_y_leer_golden(db):
    from app.cfo.goldens.modelo import CFOGolden
    from app.core.time import now_bogota

    g = CFOGolden(
        concepto="runway",
        filtros={},
        valor_esperado=Decimal("18.0"),
        tolerancia=Decimal("0.1"),
        unidad="meses",
        origen="semilla",
        nota="al 2026-08",
        creado_at=now_bogota(),
    )
    await g.insert()
    leido = await CFOGolden.find_one(CFOGolden.concepto == "runway")
    assert leido is not None and leido.valor_esperado == Decimal("18.0")
