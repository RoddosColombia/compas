from decimal import Decimal

import pytest
from app.cfo.calc import palanca


@pytest.mark.asyncio
async def test_impacto_palanca_arma_conceptos(monkeypatch):
    from app.proyeccion.service import PalancaImpacto

    async def fake_raw(**kw):
        return PalancaImpacto(
            piso_sin=Decimal("100000000"),
            piso_con=Decimal("120000000"),
            mes_quiebre="nunca",
            impacto=Decimal("20000000"),
        )

    monkeypatch.setattr(palanca.proy_service, "impacto_palanca_raw", fake_raw)
    rs = await palanca.impacto_palanca(
        palanca="plazo_semanas", nuevo_valor=Decimal("78"), modelo="todos"
    )
    by = {r.concepto: r for r in rs}
    assert by["piso_sin"].valor == Decimal("100000000")
    assert by["piso_con"].valor == Decimal("120000000")
    assert by["piso_con"].evidencia.ref == "quiebre:nunca"
    assert by["impacto"].valor == Decimal("20000000")
    assert all(r.disponible for r in rs)


@pytest.mark.asyncio
async def test_impacto_palanca_abstiene(monkeypatch):
    async def boom(**kw):
        raise palanca.ProyeccionError("sin config", 409)

    monkeypatch.setattr(palanca.proy_service, "impacto_palanca_raw", boom)
    rs = await palanca.impacto_palanca(
        palanca="plazo_semanas", nuevo_valor=Decimal("78")
    )
    assert len(rs) == 1 and rs[0].disponible is False
