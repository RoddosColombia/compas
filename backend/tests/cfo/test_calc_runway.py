from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_runway_sin_config_abstiene(monkeypatch):
    from app.cfo.calc import runway as mod

    async def _boom(**kw):
        from app.proyeccion.service import ProyeccionError

        raise ProyeccionError("no hay parametros", 409)

    monkeypatch.setattr(mod, "_proyectar", _boom)
    r = await mod.runway()
    assert r.disponible is False and r.valor is None and r.unidad == "meses"


@pytest.mark.asyncio
async def test_runway_toma_runway_meses(monkeypatch):
    from app.cfo.calc import runway as mod

    async def _ok(**kw):
        return {"runway_meses": "18.0", "meses": []}

    monkeypatch.setattr(mod, "_proyectar", _ok)
    r = await mod.runway()
    assert r.disponible is True and r.valor == Decimal("18.0")
    assert r.evidencia.fuente.startswith("proyeccion")
