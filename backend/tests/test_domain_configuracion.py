# backend/tests/test_domain_configuracion.py
"""Configuracion (Spec §1.10): valor tipado por clave (Kimi M-03) + semilla real.

CALENDARIO_DIAN con las fechas REALES de RODDOS (NIT 901012622, dígito 2):
ene–abr → 13-may-26, may–ago → 10-sep-26, sep–dic → 14-ene-27."""

from decimal import Decimal

import pytest
from app.domain.configuracion import (
    SEMILLA_CONFIGURACION,
    Configuracion,
)
from pydantic import ValidationError


def test_umbral_es_decimal():
    c = Configuracion(
        clave="UMBRAL_DIF_BANCO_CIERRE",
        valor_decimal=Decimal("50000"),
        vigente_desde="2026-01-01",
    )
    assert c.valor_decimal == Decimal("50000")


def test_calendario_es_json():
    c = Configuracion(
        clave="CALENDARIO_DIAN",
        valor_json={"2026": {"may_ago": "2026-09-10"}},
        vigente_desde="2026-01-01",
    )
    assert c.valor_json["2026"]["may_ago"] == "2026-09-10"


def test_exactamente_un_valor():
    # cero valores -> error
    with pytest.raises(ValidationError):
        Configuracion(clave="UMBRAL_DIF_BANCO_CIERRE", vigente_desde="2026-01-01")
    # dos valores -> error
    with pytest.raises(ValidationError):
        Configuracion(
            clave="UMBRAL_DIF_BANCO_CIERRE",
            valor_decimal=Decimal("1"),
            valor_json={"x": 1},
            vigente_desde="2026-01-01",
        )


def test_tipo_debe_coincidir_con_la_clave():
    # UMBRAL_DIF_BANCO_CIERRE es Decimal: pasarle json debe fallar (M-03)
    with pytest.raises(ValidationError):
        Configuracion(
            clave="UMBRAL_DIF_BANCO_CIERRE",
            valor_json={"x": 1},
            vigente_desde="2026-01-01",
        )


def test_umbral_no_admite_float():
    with pytest.raises(ValidationError):
        Configuracion(
            clave="UMBRAL_DIF_BANCO_CIERRE",
            valor_decimal=50000.0,
            vigente_desde="2026-01-01",
        )


# ---- Semilla ----


def test_semilla_tiene_las_tres_claves():
    claves = {c["clave"] for c in SEMILLA_CONFIGURACION}
    assert claves == {
        "UMBRAL_DIF_BANCO_CIERRE",
        "CALENDARIO_DIAN",
        "DIAS_CREDITO_POR_PROVEEDOR",
    }


def test_semilla_umbral_50000():
    umbral = next(
        c for c in SEMILLA_CONFIGURACION if c["clave"] == "UMBRAL_DIF_BANCO_CIERRE"
    )
    assert umbral["valor_decimal"] == Decimal("50000")


def test_semilla_calendario_dian_fechas_reales():
    cal = next(c for c in SEMILLA_CONFIGURACION if c["clave"] == "CALENDARIO_DIAN")
    v = cal["valor_json"]["2026"]
    assert v["ene_abr"] == "2026-05-13"
    assert v["may_ago"] == "2026-09-10"
    assert v["sep_dic"] == "2027-01-14"


def test_semilla_construye_modelos_validos():
    for c in SEMILLA_CONFIGURACION:
        Configuracion(**c)
