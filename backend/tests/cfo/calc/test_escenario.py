from decimal import Decimal

import pytest
from app.cfo.calc import escenario


@pytest.mark.asyncio
async def test_impacto_arma_conceptos_y_mes_de_quiebre(monkeypatch):
    async def fake_impactos(*, ajustes, escenario, mes_inicio, horizonte_meses):
        return {
            "base": {"piso_caja": "100000000"},
            "ajustada": {
                "piso_caja": "40000000",
                "meses": [
                    {"mes": "2026-09", "estado": "ok", "caja": "90000000"},
                    {"mes": "2026-10", "estado": "ok", "caja": "60000000"},
                    {"mes": "2026-11", "estado": "critico", "caja": "40000000"},
                ],
            },
            "delta_por_mes": ["-20000000", "-20000000", "-20000000"],
        }

    monkeypatch.setattr(escenario.proy_service, "proyectar_impactos", fake_impactos)
    rs = await escenario.impacto_escenario(
        naturaleza="gasto", monto=Decimal("20000000"), mes_inicio="2026-09"
    )
    by = {r.concepto: r for r in rs}
    assert by["piso_sin"].valor == Decimal("100000000")
    assert by["piso_con"].valor == Decimal("40000000")
    assert by["piso_con"].evidencia.ref == "quiebre:2026-11"
    assert by["impacto_mensual"].valor == Decimal("20000000")
    assert all(r.disponible for r in rs)


@pytest.mark.asyncio
async def test_impacto_abstiene_sin_config(monkeypatch):
    async def boom(**kw):
        raise escenario.ProyeccionError("sin config")

    monkeypatch.setattr(escenario.proy_service, "proyectar_impactos", boom)
    rs = await escenario.impacto_escenario(
        naturaleza="gasto", monto=Decimal("20000000"), mes_inicio="2026-09"
    )
    assert len(rs) == 1 and rs[0].disponible is False
