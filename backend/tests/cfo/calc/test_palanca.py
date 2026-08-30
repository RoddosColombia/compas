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
    assert by["piso_sin_palanca"].valor == Decimal("100000000")
    assert by["piso_con_palanca"].valor == Decimal("120000000")
    assert by["piso_con_palanca"].evidencia.ref == "quiebre:nunca"
    assert by["impacto_palanca"].valor == Decimal("20000000")
    assert all(r.disponible for r in rs)


def _fake_raw_impacto(impacto: str, piso_sin: str = "100000000"):
    from app.proyeccion.service import PalancaImpacto

    piso_con = str(Decimal(piso_sin) + Decimal(impacto))

    async def fake_raw(**kw):
        return PalancaImpacto(
            piso_sin=Decimal(piso_sin),
            piso_con=Decimal(piso_con),
            mes_quiebre="nunca",
            impacto=Decimal(impacto),
        )

    return fake_raw


@pytest.mark.asyncio
async def test_plazo_sin_efecto_en_horizonte_marca_ref(monkeypatch):
    # plazo con impacto 0 (52->78 en horizonte corto): el ref de impacto_palanca
    # señala la salvedad para que FABS explique que el efecto del plazo es de largo
    # plazo, en vez de reportar "$0" a secas.
    monkeypatch.setattr(
        palanca.proy_service, "impacto_palanca_raw", _fake_raw_impacto("0")
    )
    rs = await palanca.impacto_palanca(
        palanca="plazo_semanas", nuevo_valor=Decimal("78"), modelo="todos"
    )
    by = {r.concepto: r for r in rs}
    assert by["impacto_palanca"].valor == Decimal("0")
    assert by["impacto_palanca"].evidencia.ref == "plazo-sin-efecto-horizonte"


@pytest.mark.asyncio
async def test_plazo_con_efecto_conserva_ancla_horizonte(monkeypatch):
    # plazo con impacto != 0: NO se marca; el ref sigue siendo el ancla de horizonte.
    import re

    monkeypatch.setattr(
        palanca.proy_service, "impacto_palanca_raw", _fake_raw_impacto("5000000")
    )
    rs = await palanca.impacto_palanca(
        palanca="plazo_semanas", nuevo_valor=Decimal("78")
    )
    ref = {r.concepto: r for r in rs}["impacto_palanca"].evidencia.ref
    assert ref != "plazo-sin-efecto-horizonte"
    assert re.fullmatch(r"\d{4}-\d{2}", ref)


@pytest.mark.asyncio
async def test_cuota_con_impacto_cero_no_se_marca(monkeypatch):
    # la salvedad es SOLO del plazo: una cuota con impacto 0 NO lleva la marca.
    monkeypatch.setattr(
        palanca.proy_service, "impacto_palanca_raw", _fake_raw_impacto("0")
    )
    rs = await palanca.impacto_palanca(
        palanca="cuota_inicial", nuevo_valor=Decimal("500000")
    )
    ref = {r.concepto: r for r in rs}["impacto_palanca"].evidencia.ref
    assert ref != "plazo-sin-efecto-horizonte"


@pytest.mark.asyncio
async def test_impacto_palanca_abstiene(monkeypatch):
    async def boom(**kw):
        raise palanca.ProyeccionError("sin config", 409)

    monkeypatch.setattr(palanca.proy_service, "impacto_palanca_raw", boom)
    rs = await palanca.impacto_palanca(
        palanca="plazo_semanas", nuevo_valor=Decimal("78")
    )
    assert len(rs) == 1 and rs[0].disponible is False
