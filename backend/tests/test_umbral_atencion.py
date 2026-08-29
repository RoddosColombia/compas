# backend/tests/test_umbral_atencion.py
"""RF-F3 · P1 — Umbral de ATENCIÓN administrable (Fundacional D-1).

Segundo umbral entre `crítico` (mínimo) y `sobre umbrales`. Vive en `Configuracion`
(patrón `UMBRAL_DIF_BANCO_CIERRE`): historial temporal por (clave, vigente_desde),
autor. Sin fila vigente → fallback al comportamiento actual de `valles.py`
(`caja_minima × factor_atencion`, default 3×) para no romper la detección de valles.
"""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.configuracion.service import leer_umbral_atencion
from app.domain import DOMAIN_DOCUMENTS
from app.domain.configuracion import ClaveConfig, Configuracion
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield


CRIT = Decimal("30000000")  # umbral crítico del CEO ($30 M)


@pytest.mark.asyncio
async def test_sin_config_devuelve_fallback_3x_del_critico(db):
    """Sin fila en Configuracion, el resolver replica el comportamiento actual
    (caja_minima × 3, el `factor_atencion` de valles.py) para no cambiar la
    detección de valles antes de que el CEO lo configure."""
    val = await leer_umbral_atencion(CRIT)
    assert val == CRIT * 3


@pytest.mark.asyncio
async def test_con_config_vigente_manda_el_valor_del_ceo(db):
    await Configuracion(
        clave=ClaveConfig.UMBRAL_ATENCION,
        valor_decimal=Decimal("250000000"),
        vigente_desde="2026-08-01",
        modificado_por="u-andres",
    ).insert()
    val = await leer_umbral_atencion(CRIT)
    assert val == Decimal("250000000")


@pytest.mark.asyncio
async def test_historial_gana_la_ultima_vigencia(db):
    """Patrón `Configuracion` (D-1): historial por vigente_desde; el resolver toma
    la más reciente."""
    await Configuracion(
        clave=ClaveConfig.UMBRAL_ATENCION,
        valor_decimal=Decimal("100000000"),
        vigente_desde="2026-05-01",
        modificado_por="u-andres",
    ).insert()
    await Configuracion(
        clave=ClaveConfig.UMBRAL_ATENCION,
        valor_decimal=Decimal("250000000"),
        vigente_desde="2026-08-01",
        modificado_por="u-andres",
    ).insert()
    val = await leer_umbral_atencion(CRIT)
    assert val == Decimal("250000000")


@pytest.mark.asyncio
async def test_atencion_no_puede_ser_menor_o_igual_al_critico(db):
    """Regla de dominio D-1: la atención está por encima del crítico. Si por error se
    guarda un valor ≤ crítico (dato malo), el resolver lo descarta y aplica el
    fallback en vez de propagar un umbral inválido. El motor no debe correr con un
    umbral incoherente."""
    await Configuracion(
        clave=ClaveConfig.UMBRAL_ATENCION,
        valor_decimal=CRIT,  # exactamente el crítico → inválido
        vigente_desde="2026-08-01",
        modificado_por="u-andres",
    ).insert()
    val = await leer_umbral_atencion(CRIT)
    assert val == CRIT * 3  # fallback


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
