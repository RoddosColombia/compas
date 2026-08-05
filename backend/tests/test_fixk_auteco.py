# backend/tests/test_fixk_auteco.py
"""FIX-K — cronograma real Auteco sep–dic 2026 (9 facturas del Excel del CEO).

Verifica la derivación del mes de pago (fecha + plazo//30 = +5 meses) y que la suma del
capital por mes cuadra EXACTA con los totales de control (regla 7). capital = saldo; la
reconciliación D2 §4 pone pago_inventario[mes] = -Σ capital[mes], así que la columna
Auteco de la proyección muestra estos valores (el mapeo lo cubren los tests de
reconciliación existentes; aquí verificamos el DATO).
"""

import importlib.util
from decimal import Decimal
from pathlib import Path

from app.obligaciones.calculadora import pago_factura

# cargar el módulo de migración (nombre con fecha, no importable por dotted path)
_MIG = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "20260804_fixk_auteco_facturas.py"
)
_spec = importlib.util.spec_from_file_location("fixk_mig", _MIG)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)


def _mes_de(numero: str) -> str:
    f = next(x for x in mig.FACTURAS if x["numero"] == numero)
    p = pago_factura(
        fecha_factura=f["fecha"],
        valor=Decimal(f["valor"]),
        plazo_elegido_dias=mig.PLAZO_DIAS,
        plazo_base_dias=mig.PLAZO_BASE_DIAS,
        tasa_excedente_mensual=mig.TASA_EXCEDENTE,
    )
    return p.mes


def test_son_9_facturas():
    assert len(mig.FACTURAS) == 9


def test_mes_de_pago_por_factura():
    # +5 meses (150//30): abr→sep, may→oct, jun→nov, jul→dic.
    assert _mes_de("E670161540") == "2026-09"  # abr
    assert _mes_de("E670162095") == "2026-09"  # abr
    assert _mes_de("E670165520") == "2026-10"  # may
    assert _mes_de("E670166361") == "2026-11"  # jun
    assert _mes_de("E670167401") == "2026-11"  # jun
    assert _mes_de("E670169372") == "2026-12"  # jul
    assert _mes_de("E670169887") == "2026-12"  # jul
    assert _mes_de("E670170142") == "2026-12"  # jul
    assert _mes_de("E670170297") == "2026-12"  # jul


def test_verificar_totales_cuadra():
    por_mes = mig.verificar_totales()
    assert por_mes == {
        "2026-09": Decimal("123392031"),
        "2026-10": Decimal("149030808"),
        "2026-11": Decimal("255668507"),
        "2026-12": Decimal("488501741"),
    }
    assert sum(por_mes.values()) == Decimal("1016593087")


def test_capital_es_el_saldo_sin_interes():
    # plazo_base = plazo → sin excedente: capital = valor, interés = 0.
    f = mig.FACTURAS[2]  # E670165520, 149.030.808
    p = pago_factura(
        fecha_factura=f["fecha"],
        valor=Decimal(f["valor"]),
        plazo_elegido_dias=mig.PLAZO_DIAS,
        plazo_base_dias=mig.PLAZO_BASE_DIAS,
        tasa_excedente_mensual=mig.TASA_EXCEDENTE,
    )
    assert p.capital == Decimal("149030808.00")
    assert p.interes == Decimal("0.00")


def test_verificar_totales_falla_ruidoso_si_no_cuadra(monkeypatch):
    # Regla 7: si una fila se corrompe, la verificación FALLA (no adivina).
    corruptas = [dict(x) for x in mig.FACTURAS]
    corruptas[0]["valor"] = "1"  # rompe septiembre
    monkeypatch.setattr(mig, "FACTURAS", corruptas)
    import pytest

    with pytest.raises(SystemExit):
        mig.verificar_totales()
