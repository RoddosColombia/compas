from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_iva_toma_neto_del_periodo_vigente(monkeypatch):
    from app.cfo.calc import iva as mod

    async def _liq():
        return {
            "periodicidad": "cuatrimestral",
            "periodos": [
                {
                    "anio": 2026,
                    "periodo": 2,
                    "etiqueta": "2026-C2",
                    "neto_a_pagar": "26000000.00",
                    "proximo_pago": {"fecha": "2026-09-10", "dias": 31},
                },
            ],
        }

    monkeypatch.setattr(mod, "_liquidacion", _liq)
    # hoy dentro de C2 (may-ago): 2026-08-10
    monkeypatch.setattr(mod, "_periodo_vigente_idx", lambda: (2026, 2))
    r = await mod.iva_cuatrimestre()
    assert r.disponible is True and r.valor == Decimal("26000000.00")
    assert r.evidencia.fecha_corte == "2026-09-10" and r.evidencia.ref == "2026-C2"


@pytest.mark.asyncio
async def test_iva_sin_periodo_vigente_abstiene(monkeypatch):
    from app.cfo.calc import iva as mod

    async def _liq():
        return {"periodicidad": "cuatrimestral", "periodos": []}

    monkeypatch.setattr(mod, "_liquidacion", _liq)
    monkeypatch.setattr(mod, "_periodo_vigente_idx", lambda: (2026, 3))
    r = await mod.iva_cuatrimestre()
    assert r.disponible is False and r.valor is None
