# backend/tests/test_supuestos_mora_y_tramos.py
"""Sprint SUP-1 (CEO 2026-08-17) — dos correcciones/capacidades de Supuestos:

**A · La mora del CEO MANDA (bug reportado: "la mora no impacta en ninguna vía").**
`_armar_parametros` sobrescribía pct_mora/pct_recuperacion con el preset del
escenario y "base" está en los presets → los supuestos del CEO se descartaban
SIEMPRE (prod: mora 8% configurada, motor usando 3%). Regla nueva del CEO: los
supuestos definen el NIVEL y el escenario el DESVÍO — "si subo la mora de 3 a 5,
esos dos puntos se suman también en pesimista y en optimista". Es decir DELTA EN
PUNTOS sobre el preset base, aplicado a los tres escenarios, acotado a [0, 1].

**B · Crecimiento por TRAMOS** (CEO: "después del mes 18 poder tener una tasa
mensual diferente, más baja"): `crec_pct_mensual_2` + `crec_mes_corte` opcionales.
`crec_mes_corte = 18` → los meses 1..18 crecen con la tasa 1 y del 19 en adelante
con la tasa 2. Sin ellos, la serie es IDÉNTICA (candado: golden master intacto).
"""

from decimal import Decimal

import pytest
from app.proyeccion.motor import PRESETS_ESCENARIO, colocacion_mensual
from app.proyeccion.service import _armar_parametros
from pydantic import ValidationError

# ── B · colocación por tramos (motor, compute-only) ──


def test_sin_tramo2_la_serie_es_identica():
    """Candado del golden master: los parámetros nuevos por default no cambian nada."""
    sin = colocacion_mensual(50, Decimal("0.01"), 24)
    con_none = colocacion_mensual(
        50, Decimal("0.01"), 24, None, crec_pct_mensual_2=None, crec_mes_corte=None
    )
    assert sin == con_none
    # el encadenamiento del artefacto se conserva (50,51,52,53…)
    assert sin[:4] == [50, 51, 52, 53]


def test_tramo2_aplica_desde_el_mes_siguiente_al_corte():
    """corte=3 → meses 1..3 con tasa 1; del 4 en adelante con tasa 2."""
    serie = colocacion_mensual(
        100,
        Decimal("0.10"),
        6,
        None,
        crec_pct_mensual_2=Decimal("0"),
        crec_mes_corte=3,
    )
    # m0=100 (base), m1=110, m2=121 (tasa 1); m3..m5 con tasa 0 → se congela en 121
    assert serie == [100, 110, 121, 121, 121, 121]


def test_tramo2_mas_baja_frena_la_curva():
    alta = colocacion_mensual(75, Decimal("0.15"), 36)
    frenada = colocacion_mensual(
        75,
        Decimal("0.15"),
        36,
        None,
        crec_pct_mensual_2=Decimal("0.03"),
        crec_mes_corte=18,
    )
    assert frenada[:18] == alta[:18]  # el primer tramo no se toca
    assert frenada[-1] < alta[-1]  # el segundo tramo frena de verdad


def test_tramo2_respeta_la_rampa():
    """La rampa (unidades REALES) sigue mandando sobre ambos tramos."""
    serie = colocacion_mensual(
        100,
        Decimal("0.10"),
        5,
        [7, 9],
        crec_pct_mensual_2=Decimal("0"),
        crec_mes_corte=1,
    )
    assert serie[:2] == [7, 9]  # los reales, intactos
    assert serie[2] == 100  # post-rampa reinicia en motos_base


# ── A · la mora del CEO manda, con el escenario como desvío ──


def _params(**over):
    """ParametrosProyeccion mínimo y válido (no toca Mongo)."""
    from app.domain.parametros_proyeccion import ParametrosProyeccion

    base = dict(
        vigente_desde="2026-08-01",
        caja_inicial=Decimal("100000000"),
        caja_minima=Decimal("125000000"),
        motos_base=75,
        crec_pct_mensual=Decimal("0.01"),
        horizonte_meses=36,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=150,
        base_auteco_dias=90,
        tasa_auteco=Decimal("0.016"),
        gastos_fijos=Decimal("208000000"),
        gps_moto=Decimal("33201"),
        costo_moto_nueva=Decimal("691500"),
        deuda=Decimal("25000000"),
        tasa_deuda=Decimal("0.0096"),
        mes_inicio_deuda=2,
        meses_deuda=14,
        pct_mora=Decimal("0.03"),
        pct_recuperacion=Decimal("0.40"),
        pct_default=Decimal("0.03"),
        pct_provision=Decimal("0.02"),
    )
    base.update(over)
    return ParametrosProyeccion(**base)


def _armar(params, escenario: str):
    return _armar_parametros(params, [], escenario, (2026, 8), 12)


def test_base_usa_exactamente_la_mora_del_ceo():
    """El bug: con 8% configurado el motor recibía 3%. Ahora recibe 8%."""
    pm = _armar(_params(pct_mora=Decimal("0.08")), "base")
    assert pm.pct_mora == Decimal("0.08")


def test_el_delta_en_puntos_se_suma_a_los_tres_escenarios():
    """Regla CEO: 'si subo la mora de 3 a 5, esos dos puntos se suman también en
    pesimista y en optimista'."""
    p = _params(pct_mora=Decimal("0.05"))  # +2 puntos sobre el base (3%)
    assert _armar(p, "base").pct_mora == Decimal("0.05")
    assert _armar(p, "pesimista").pct_mora == PRESETS_ESCENARIO["pesimista"][
        "pct_mora"
    ] + Decimal("0.02")
    assert _armar(p, "optimista").pct_mora == PRESETS_ESCENARIO["optimista"][
        "pct_mora"
    ] + Decimal("0.02")


def test_el_delta_tambien_aplica_a_la_recuperacion():
    p = _params(pct_recuperacion=Decimal("0.65"))  # +25 puntos sobre el base (40%)
    assert _armar(p, "base").pct_recuperacion == Decimal("0.65")
    assert _armar(p, "pesimista").pct_recuperacion == Decimal("0.55")  # 0.30 + 0.25


def test_el_desvio_del_escenario_se_conserva():
    """Pesimista sigue siendo PEOR que base y optimista MEJOR, con cualquier nivel."""
    p = _params(pct_mora=Decimal("0.08"))
    assert (
        _armar(p, "optimista").pct_mora
        < _armar(p, "base").pct_mora
        < _armar(p, "pesimista").pct_mora
    )


def test_el_delta_se_acota_a_cero_uno():
    """Una mora del 98% no puede llevar el pesimista a 101% (ni bajar de 0)."""
    alto = _armar(_params(pct_mora=Decimal("0.98")), "pesimista")
    assert alto.pct_mora == Decimal("1")
    bajo = _armar(_params(pct_mora=Decimal("0")), "optimista")
    assert bajo.pct_mora == Decimal("0")


def test_escenario_desconocido_usa_los_supuestos_tal_cual():
    pm = _armar(_params(pct_mora=Decimal("0.08")), "no_existe")
    assert pm.pct_mora == Decimal("0.08")


# ── B · los tramos viajan de los supuestos al motor ──


def test_los_tramos_llegan_al_motor_desde_los_supuestos():
    pm = _armar(_params(crec_pct_mensual_2=Decimal("0.03"), crec_mes_corte=18), "base")
    assert pm.crec_pct_mensual_2 == Decimal("0.03")
    assert pm.crec_mes_corte == 18


def test_tramo2_incompleto_no_se_acepta():
    """Fail-closed (regla 7 en espíritu): la tasa 2 y el mes de corte van JUNTOS."""
    with pytest.raises(ValidationError):
        _params(crec_pct_mensual_2=Decimal("0.03"))  # sin corte
    with pytest.raises(ValidationError):
        _params(crec_mes_corte=18)  # sin tasa
