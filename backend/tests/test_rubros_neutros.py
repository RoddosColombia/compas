# backend/tests/test_rubros_neutros.py
"""E1 · P3 — el resolver nombre→id de rubros neutros vive en `domain.rubros_neutros`
(una verdad, un lugar, junto al set). `metas_ingreso` lo re-exporta para no romper
importadores y el loader E1 lo importa de ahí — sin dos copias que puedan divergir."""

from decimal import Decimal  # noqa: F401  (paridad con el resto de tests del dominio)

import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
from app.domain.rubros_neutros import _ids_rubros_neutros
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield c


async def _rubro(grupo: RubroGrupo, nombre: str, orden: int) -> Rubro:
    r = Rubro(grupo=grupo, nombre=nombre, tipo_flujo=TipoFlujo.INGRESO, orden=orden)
    await r.insert()
    return r


@pytest.mark.asyncio
async def test_resuelve_solo_los_neutros_presentes(db):
    n1 = await _rubro(RubroGrupo.OTROS, "Reversas y devoluciones", 1)
    n2 = await _rubro(RubroGrupo.OTROS, "Ajuste de conciliación", 2)
    _normal = await _rubro(RubroGrupo.INGRESOS_OPERATIVOS, "Recaudo de cartera", 3)
    ids = await _ids_rubros_neutros()
    assert ids == {n1.id, n2.id}


@pytest.mark.asyncio
async def test_vacio_si_no_existen(db):
    assert await _ids_rubros_neutros() == set()


@pytest.mark.asyncio
async def test_metas_ingreso_reexporta_el_mismo_resolver(db):
    """El re-export no rompe importadores y apunta al MISMO objeto (una verdad)."""
    from app.metas_ingreso.service import _ids_rubros_neutros as reexport

    assert reexport is _ids_rubros_neutros
