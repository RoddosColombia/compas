# backend/tests/test_kpis.py
"""KPIs de proyección extraídos a función COMPARTIDA (D1). El motor NO se toca; esta
función reproduce EXACTAMENTE el bloque de KPIs de `motor.proyectar` (motor.py:721-732)
para poder recalcularlos sobre CUALQUIER serie (base o ajustada por impactos).

Test de paridad: sobre la serie base, `calcular_kpis(...)` debe dar bit a bit lo mismo
que la `ResultadoProyeccion` que produjo el motor. Si algún día divergen, este test lo
caza antes de que un KPI ajustado mienta.
"""

from decimal import Decimal

from app.proyeccion.kpis import calcular_kpis
from app.proyeccion.motor import ModeloProyeccion, ParametrosMotor, proyectar


def _params(**over):
    base = dict(
        mes_inicio=(2026, 7),
        horizonte_meses=6,
        modelos=[
            ModeloProyeccion(
                "Raider",
                cuota_semanal=Decimal("100"),
                cuota_inicial=Decimal("1000"),
                plazo_semanas=6,
                mix=Decimal("1"),
                costo_moto=Decimal("5000"),
            )
        ],
        motos_base=2,
        crec_pct_mensual=Decimal("0"),
        rampa=None,
        adelanto_auteco=Decimal("100"),
        plazo_auteco_dias=60,
        base_auteco_dias=30,
        tasa_auteco=Decimal("0"),
        gastos_fijos=Decimal("1000"),
        gps_moto=Decimal("0"),
        costo_moto_nueva=Decimal("0"),
        deuda=Decimal("0"),
        tasa_deuda=Decimal("0"),
        mes_inicio_deuda=0,
        meses_deuda=0,
        pct_mora=Decimal("0"),
        pct_recuperacion=Decimal("0"),
        pct_default=Decimal("0"),
        pct_provision=Decimal("0"),
        overrides_mora=None,
        overrides_default=None,
        caja_inicial=Decimal("50000"),
        caja_minima=Decimal("10000"),
    )
    base.update(over)
    return ParametrosMotor(**base)


def test_calcular_kpis_paridad_bit_a_bit_con_el_motor():
    p = _params()
    r = proyectar(p)
    k = calcular_kpis(
        [m.caja for m in r.meses],
        [m.flujo for m in r.meses],
        [m.mes for m in r.meses],
        p.caja_minima,
    )
    assert k.piso_caja == r.piso_caja
    assert k.mes_mas_ajustado == r.mes_mas_ajustado
    assert k.meses_bajo_minimo == r.meses_bajo_minimo
    assert k.caja_final == r.caja_final
    assert k.capital_requerido == r.capital_requerido
    assert k.runway_meses == r.runway_meses


def test_calcular_kpis_paridad_con_quema_neta_runway():
    # gastos altos => quema neta => runway definido; sigue debiendo empatar al motor.
    p = _params(gastos_fijos=Decimal("30000"), horizonte_meses=8)
    r = proyectar(p)
    k = calcular_kpis(
        [m.caja for m in r.meses],
        [m.flujo for m in r.meses],
        [m.mes for m in r.meses],
        p.caja_minima,
    )
    assert k.runway_meses == r.runway_meses
    assert k.piso_caja == r.piso_caja
    assert k.capital_requerido == r.capital_requerido


def test_calcular_kpis_capital_requerido_cero_si_piso_sobre_umbral():
    p = _params(caja_minima=Decimal("0"))
    r = proyectar(p)
    k = calcular_kpis(
        [m.caja for m in r.meses],
        [m.flujo for m in r.meses],
        [m.mes for m in r.meses],
        Decimal("0"),
    )
    assert k.capital_requerido == Decimal("0.00")
    assert k.capital_requerido == r.capital_requerido
