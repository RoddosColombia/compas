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
async def test_runner_ok_fallo_y_abstencion(db, monkeypatch):
    from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
    from app.cfo.goldens import runner
    from app.cfo.goldens.modelo import CFOGolden
    from app.core.time import now_bogota

    def _res(concepto, valor, unidad, disp=True):
        return ResultadoCFO(
            concepto=concepto,
            valor=valor,
            unidad=unidad,
            disponible=disp,
            evidencia=Evidencia(fuente="x", fecha_corte=None, ref="r"),
        )

    async def _runway():
        return _res("runway", Decimal("18.05"), "meses")

    async def _caja():
        return _res("caja_hoy", Decimal("700000000"), "COP")

    async def _iva():
        return _res("iva_cuatrimestre", None, "COP", disp=False)  # abstención

    monkeypatch.setattr(
        runner,
        "CONCEPTOS",
        {"runway": _runway, "caja_hoy": _caja, "iva_cuatrimestre": _iva},
    )

    now = now_bogota()
    await CFOGolden(
        concepto="runway",
        valor_esperado=Decimal("18.0"),
        tolerancia=Decimal("0.1"),
        unidad="meses",
        origen="semilla",
        creado_at=now,
    ).insert()  # OK (delta 0.05<0.1)
    await CFOGolden(
        concepto="caja_hoy",
        valor_esperado=Decimal("500000000"),
        tolerancia=Decimal("1"),
        unidad="COP",
        origen="semilla",
        creado_at=now,
    ).insert()  # FALLO
    await CFOGolden(
        concepto="iva_cuatrimestre",
        valor_esperado=None,
        tolerancia=Decimal("1"),
        unidad="COP",
        origen="semilla",
        creado_at=now,
    ).insert()  # abstención OK

    rep = await runner.correr_goldens()
    assert rep["total"] == 3 and rep["ok"] == 1 and rep["abstenciones_ok"] == 1
    assert len(rep["fallos"]) == 1 and rep["fallos"][0]["concepto"] == "caja_hoy"
