from decimal import Decimal

import pytest
from app.cfo.calc import tendencias


def _actual(mes, ing, gas, caja):
    from app.proyeccion.service import ActualMes

    return ActualMes(
        mes=mes,
        ingreso_real=Decimal(ing),
        gasto_real=Decimal(gas),
        caja_real=Decimal(caja),
    )


@pytest.mark.asyncio
async def test_tendencia_gasto_sube(monkeypatch):
    async def fake(*, meses=3):
        return [
            _actual("2026-05", "0", "800000", "0"),
            _actual("2026-06", "0", "1000000", "0"),
            _actual("2026-07", "0", "1500000", "0"),
        ]

    monkeypatch.setattr(tendencias.proy_service, "actuals_mensuales", fake)
    rs = await tendencias.tendencia_real(metrica="gasto")
    by = {r.concepto: r for r in rs}
    assert by["gasto_real_m0"].valor == Decimal("1500000")  # más reciente
    assert by["gasto_real_m1"].valor == Decimal("1000000")
    assert by["gasto_real_m2"].valor == Decimal("800000")
    assert by["delta_gasto_real"].valor == Decimal("500000")  # 1.5M - 1.0M
    assert by["delta_gasto_real"].evidencia.ref == "direccion:sube"
    assert all(r.disponible for r in rs)


@pytest.mark.asyncio
async def test_tendencia_caja_baja_y_metrica_caja(monkeypatch):
    async def fake(*, meses=3):
        return [
            _actual("2026-06", "0", "0", "5000000"),
            _actual("2026-07", "0", "0", "4000000"),
        ]

    monkeypatch.setattr(tendencias.proy_service, "actuals_mensuales", fake)
    rs = await tendencias.tendencia_real(metrica="caja")
    by = {r.concepto: r for r in rs}
    assert by["caja_real_m0"].valor == Decimal("4000000")
    assert by["delta_caja_real"].valor == Decimal("-1000000")
    assert by["delta_caja_real"].evidencia.ref == "direccion:baja"
    assert "caja_real_m2" not in by  # solo 2 meses


@pytest.mark.asyncio
async def test_tendencia_abstiene_sin_historia(monkeypatch):
    async def fake(*, meses=3):
        return [_actual("2026-07", "0", "0", "4000000")]  # 1 mes

    monkeypatch.setattr(tendencias.proy_service, "actuals_mensuales", fake)
    rs = await tendencias.tendencia_real(metrica="caja")
    assert len(rs) == 1 and rs[0].disponible is False


@pytest.mark.asyncio
async def test_tendencia_metrica_invalida():
    with pytest.raises(ValueError):
        await tendencias.tendencia_real(metrica="no-existe")


@pytest.mark.asyncio
async def test_rumbo_caja_arma_real_y_proyectado(monkeypatch):
    async def fake_comp(**kw):
        return {
            "ancla": {"mes": "2026-07", "caja_real": "4000000"},
            "actuals": [
                {"mes": "2026-06", "caja_real": "5000000"},
                {"mes": "2026-07", "caja_real": "4000000"},
            ],
            "forecast": [{"mes": "2026-08", "caja": "3500000"}],
        }

    async def fake_proy(**kw):
        return {
            "piso_caja": "3000000",
            "runway_meses": None,
            "meses": [
                {"mes": "2026-08", "estado": "ok"},
                {"mes": "2026-09", "estado": "critico"},
            ],
        }

    monkeypatch.setattr(tendencias.proy_service, "comparar_vigente", fake_comp)
    monkeypatch.setattr(tendencias.proy_service, "proyectar_vigente", fake_proy)
    rs = await tendencias.rumbo_caja()
    by = {r.concepto: r for r in rs}
    assert by["caja_real_ult"].valor == Decimal("4000000")
    assert by["caja_real_previo"].valor == Decimal("5000000")
    assert by["piso_proyectado"].valor == Decimal("3000000")
    assert by["piso_proyectado"].evidencia.ref == "quiebre:2026-09"
    assert by["delta_caja_rumbo"].valor == Decimal("-1000000")
    assert by["delta_caja_rumbo"].evidencia.ref == "direccion:baja"


@pytest.mark.asyncio
async def test_rumbo_caja_abstiene_sin_actuals(monkeypatch):
    async def fake_comp(**kw):
        return {"ancla": None, "actuals": [], "forecast": []}

    async def fake_proy(**kw):
        return {"piso_caja": "0", "runway_meses": None, "meses": []}

    monkeypatch.setattr(tendencias.proy_service, "comparar_vigente", fake_comp)
    monkeypatch.setattr(tendencias.proy_service, "proyectar_vigente", fake_proy)
    rs = await tendencias.rumbo_caja()
    assert len(rs) == 1 and rs[0].disponible is False
