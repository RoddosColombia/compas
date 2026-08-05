# backend/tests/test_e1_extract_julio.py
"""E1 · Paso 0 — test de la lógica PURA del extractor del fixture de julio.

Hermético: NO toca Mongo ni PROD. Verifica los controles de calidad fail-loud (regla 7)
y el ensamblado del fixture (montos string, ingreso_real excluye neutros, cabecera con
los totales de control). La extracción viva (Mongo) se prueba corriendo el script contra
PROD con los dos controles al peso, no aquí."""

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "extract_e1_julio_2026.py"


def _cargar():
    spec = importlib.util.spec_from_file_location("extract_e1_julio_2026", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _cargar()


def test_verificar_controles_pasa_al_peso():
    # Los valores exactos del CEO no lanzan.
    m.verificar_controles(m.CTRL_EGRESOS, m.CTRL_INGRESO_REAL)


def test_verificar_controles_falla_ruidoso_si_no_cuadra():
    with pytest.raises(SystemExit, match="regla 7"):
        m.verificar_controles(m.CTRL_EGRESOS + Decimal("0.01"), m.CTRL_INGRESO_REAL)
    with pytest.raises(SystemExit, match="regla 7"):
        m.verificar_controles(m.CTRL_EGRESOS, m.CTRL_INGRESO_REAL - Decimal("1"))


def test_construir_fixture_shape_y_montos_string():
    rubros = [
        {"id": "a", "codigo": "0110", "grupo": "ingresos_operativos",
         "nombre": "Recaudo de cartera", "es_sistema": True},
        {"id": "b", "codigo": "1010", "grupo": "costo_producto",
         "nombre": "Producto", "es_sistema": False},
    ]
    egresos = {"b": Decimal("100.00")}
    ingresos = {"a": Decimal("50.00")}
    fx = m.construir_fixture(
        rubros=rubros, egresos=egresos, ingresos=ingresos,
        neutros_ids=set(), extraccion_iso="2026-08-05T00:00:00-05:00",
        comando="python scripts/extract_e1_julio_2026.py",
    )
    # cabecera y controles
    assert fx["_meta"]["mes"] == "2026-07"
    assert fx["_meta"]["controles"]["egresos_total"] == "100.00"
    assert fx["_meta"]["controles"]["ingreso_real"] == "50.00"
    # montos como string (regla 1), nunca float
    assert fx["egresos_por_rubro_id"] == {"b": "100.00"}
    assert fx["ingresos_por_rubro_id"] == {"a": "50.00"}
    assert isinstance(fx["egresos_por_rubro_id"]["b"], str)
    assert fx["rubros"] == rubros


def test_construir_fixture_ingreso_real_excluye_neutros():
    # 'rev' es neutro (grupo otros, NO sistema): NO debe entrar al ingreso_real.
    rubros = [
        {"id": "cuo", "codigo": "0120", "grupo": "ingresos_operativos",
         "nombre": "Cuotas iniciales", "es_sistema": False},
        {"id": "rev", "codigo": None, "grupo": "otros",
         "nombre": "Reversas y devoluciones", "es_sistema": False},
    ]
    ingresos = {"cuo": Decimal("30000"), "rev": Decimal("9999")}
    fx = m.construir_fixture(
        rubros=rubros, egresos={}, ingresos=ingresos, neutros_ids={"rev"},
        extraccion_iso="2026-08-05T00:00:00-05:00", comando="cmd",
    )
    # ingreso_real excluye 'rev'
    assert fx["_meta"]["controles"]["ingreso_real"] == "30000"
    # pero los ingresos crudos por rubro SÍ conservan 'rev' (transparencia)
    assert fx["ingresos_por_rubro_id"]["rev"] == "9999"
    assert fx["neutros_ids"] == ["rev"]
