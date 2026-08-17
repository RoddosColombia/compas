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


# ---- B-2 gate Kimi 9.4 (2026-08-13): NITs de config = SOLO dígitos ----
# Un NIT con guión, espacios o dígito de verificación jamás matchearía la
# igualdad exacta de la ingesta → deducción perdida en silencio. Fail-loud al
# ESCRIBIR la config (este Document es el único camino de escritura: semilla,
# migraciones y scripts construyen Configuracion).


def test_nit_config_solo_digitos_ok():
    c = Configuracion(
        clave="NIT_AUTECO",
        valor_json={"nits": ["860024781", "890900317"]},
        vigente_desde="2026-01-01",
    )
    assert c.valor_json["nits"] == ["860024781", "890900317"]
    c2 = Configuracion(
        clave="NIT_RODDOS",
        valor_json={"nit": "901012622"},
        vigente_desde="2026-01-01",
    )
    assert c2.valor_json["nit"] == "901012622"


@pytest.mark.parametrize(
    "valor_json",
    [
        {"nit": "901012622-1"},  # con dígito de verificación
        {"nit": "901 012 622"},  # con espacios
        {"nits": ["860024781", "890.900.317"]},  # con puntos en la lista
        {"nits": ["860024781", ""]},  # vacío en la lista
        {"nit": ""},  # vacío
    ],
)
def test_nit_config_malformado_falla_al_escribir(valor_json):
    clave = "NIT_AUTECO" if "nits" in valor_json else "NIT_RODDOS"
    with pytest.raises(ValidationError):
        Configuracion(clave=clave, valor_json=valor_json, vigente_desde="2026-01-01")


# ---- Semilla ----


def test_semilla_tiene_las_claves_esperadas():
    claves = {c["clave"] for c in SEMILLA_CONFIGURACION}
    assert claves == {
        "UMBRAL_DIF_BANCO_CIERRE",
        "CALENDARIO_DIAN",
        "DIAS_CREDITO_POR_PROVEEDOR",
        "PERIODICIDAD_IVA",
        "NIT_RODDOS",
        "NIT_AUTECO",
        "IVA_ALIMENTA_PROYECCION",
    }


def test_semilla_e2_nits_y_compuerta_apagada():
    d = {c["clave"]: c for c in SEMILLA_CONFIGURACION}
    assert d["NIT_RODDOS"]["valor_json"] == {"nit": "901012622"}
    # Auteco factura con DOS NITs (CEO 2026-08-11): histórico + AUTOTECNICA COLOMBIANA
    assert d["NIT_AUTECO"]["valor_json"] == {"nits": ["860024781", "890900317"]}
    # compuerta IVA→proyección apagada por defecto (D-12 / CR-E2-COMPUERTA)
    assert d["IVA_ALIMENTA_PROYECCION"]["valor_json"] == {"activa": False}


def test_semilla_periodicidad_iva_default_cuatrimestral():
    p = next(c for c in SEMILLA_CONFIGURACION if c["clave"] == "PERIODICIDAD_IVA")
    assert p["valor_json"] == {"periodicidad": "cuatrimestral"}


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
