from decimal import Decimal

import pytest
from app.cfo.calc import ratios


@pytest.mark.asyncio
async def test_composicion_gasto_pcts(monkeypatch):
    from app.proyeccion.service import ComposicionGasto

    async def fake(*, ventana):
        return ComposicionGasto(
            ventana="cerrado",
            meses=["2026-07"],
            por_grupo={
                "costo_producto": Decimal("0"),
                "operacion": Decimal("600000"),
                "nomina": Decimal("3400000"),
                "deudas_obligaciones": Decimal("1000000"),
                "otros": Decimal("0"),
            },
            total=Decimal("5000000"),
        )

    monkeypatch.setattr(ratios.proy_service, "composicion_gasto_real", fake)
    rs = await ratios.composicion_gasto(ventana="cerrado")
    by = {r.concepto: r for r in rs}
    assert by["gasto_total_comp"].valor == Decimal("5000000")
    assert by["cop_nomina"].valor == Decimal("3400000")
    assert by["pct_nomina"].valor == Decimal("68.0")  # 3.4M/5M*100
    assert by["pct_nomina"].unidad == "%"
    assert by["pct_deudas"].valor == Decimal("20.0")  # 1M/5M*100
    assert all(r.disponible for r in rs)


@pytest.mark.asyncio
async def test_composicion_abstiene_sin_gasto(monkeypatch):
    from app.proyeccion.service import ComposicionGasto

    async def fake(*, ventana):
        return ComposicionGasto(
            ventana="curso", meses=["2026-08"], por_grupo={}, total=Decimal("0")
        )

    monkeypatch.setattr(ratios.proy_service, "composicion_gasto_real", fake)
    rs = await ratios.composicion_gasto(ventana="curso")
    assert len(rs) == 1 and rs[0].disponible is False


@pytest.mark.asyncio
async def test_mix_modelos_normaliza(monkeypatch):
    async def fake():
        return [
            ("Raider", Decimal("0.5")),
            ("Apache", Decimal("0.3")),
            ("Sport", Decimal("0.2")),
        ]

    monkeypatch.setattr(ratios.modelos_service, "mix_activos", fake)
    rs = await ratios.mix_modelos()
    by = {r.concepto: r for r in rs}
    assert by["mix_raider"].valor == Decimal("50.0")
    assert by["mix_raider"].unidad == "%"
    assert by["mix_apache"].valor == Decimal("30.0")


@pytest.mark.asyncio
async def test_mix_modelos_normaliza_suma_distinta_de_uno(monkeypatch):
    async def fake():  # suman 0.8, no 1.0 -> normaliza por 0.8
        return [("Raider", Decimal("0.4")), ("Apache", Decimal("0.4"))]

    monkeypatch.setattr(ratios.modelos_service, "mix_activos", fake)
    by = {r.concepto: r for r in await ratios.mix_modelos()}
    assert by["mix_raider"].valor == Decimal("50.0")  # 0.4/0.8*100


@pytest.mark.asyncio
async def test_mix_modelos_abstiene_sin_mix(monkeypatch):
    async def fake():
        return []

    monkeypatch.setattr(ratios.modelos_service, "mix_activos", fake)
    rs = await ratios.mix_modelos()
    assert len(rs) == 1 and rs[0].disponible is False
