# backend/tests/cfo/agente/test_tools.py
from decimal import Decimal

import pytest
from app.cfo.agente import tools
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO


def _res(valor):
    return ResultadoCFO(
        concepto="caja_hoy",
        valor=valor,
        unidad="COP",
        disponible=valor is not None,
        evidencia=Evidencia(fuente="f", fecha_corte="2026-08-11", ref="2026-08"),
    )


def test_schema_tres_tools_sin_parametros():
    nombres = {t["name"] for t in tools.TOOLS_SCHEMA}
    assert nombres == {"caja_disponible_hoy", "runway_meses", "iva_del_cuatrimestre"}
    for t in tools.TOOLS_SCHEMA:
        assert t["input_schema"]["properties"] == {}


def test_resultado_a_dict_serializa_valor_a_string():
    d = tools.resultado_a_dict(_res(Decimal("704722003")))
    assert d["valor"] == "704722003"
    assert d["disponible"] is True
    assert d["evidencia"]["ref"] == "2026-08"
    d0 = tools.resultado_a_dict(_res(None))
    assert d0["valor"] is None
    assert d0["disponible"] is False


def test_resultado_a_dict_cero_legitimo_es_cero_no_none():
    # guard contra una futura regresión a `if r.valor:` (Decimal("0") es falsy en
    # Python, pero caja/IVA en $0 es un dato legítimo, no "falta evidencia").
    d = tools.resultado_a_dict(_res(Decimal("0")))
    assert d["valor"] == "0"
    assert d["disponible"] is True


@pytest.mark.asyncio
async def test_ejecutar_tool_despacha(monkeypatch):
    async def fake():
        return _res(Decimal("123"))

    monkeypatch.setitem(tools.DISPATCH, "caja_disponible_hoy", fake)
    r = await tools.ejecutar_tool("caja_disponible_hoy")
    assert r.valor == Decimal("123")


@pytest.mark.asyncio
async def test_ejecutar_tool_desconocida_falla():
    with pytest.raises(KeyError):
        await tools.ejecutar_tool("no_existe")
