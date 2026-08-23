# backend/tests/test_sup2_variables_editables.py
"""SUP-2 (CEO 2026-08-17/22) — "TODOS los supuestos que pueden afectar la proyección
tienen que ser modificables, adaptables, editables para poder ver cómo impacta cada
variable en el flujo de caja". Cuatro variables que estaban clavadas en el código:

A · **Mora y recuperación de los TRES escenarios** — vivían hardcodeadas en
    `PRESETS_ESCENARIO` (motor.py). Ahora cada escenario tiene sus dos porcentajes
    editables; sin valor explícito se mantiene el comportamiento de SUP-1 (preset +
    delta del base) para no romper nada.
B · **Rezago de la recuperación de mora** — el artefacto recupera en el MISMO mes;
    el modelo v9.1 de Fabián recupera la mora del mes ANTERIOR (`FC!E18 = −D17×E7`),
    que es la verdad del negocio: la mora es diferimiento. Editable en meses; el
    motor mantiene 0 por defecto (candado del golden master) y el dominio 1.
C · **% de prefondeo del IVA** — el plan del fondo reservaba el 100 % del pago
    repartido en el período; v9.1 reserva un % editable (`IVA!C8 = 70 %`).
D · **Fondo AVAL propio / autoseguro** — egreso mensual = % del recaudo de crédito
    (`PARAMETROS!C55 = 1 %` → `FC!33`). No existía en COMPAS. Default 0 = sin cambio.
"""

from decimal import Decimal

import pytest
from app.iva.liquidacion import LiquidacionPeriodo, plan_fondo_provision
from app.proyeccion.motor import (
    ModeloProyeccion,
    ParametrosMotor,
    neto_por_mora,
    proyectar,
)
from app.proyeccion.service import _armar_parametros
from pydantic import ValidationError

# ── A · los tres escenarios, editables ──


def _params(**over):
    from app.domain.parametros_proyeccion import ParametrosProyeccion

    base = dict(
        vigente_desde="2026-08-01",
        caja_inicial=Decimal("100000000"),
        caja_minima=Decimal("125000000"),
        motos_base=70,
        crec_pct_mensual=Decimal("0.10"),
        horizonte_meses=24,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=150,
        base_auteco_dias=90,
        tasa_auteco=Decimal("0.016"),
        gastos_fijos=Decimal("208000000"),
        gps_moto=Decimal("33201"),
        costo_moto_nueva=Decimal("691500"),
        deuda=Decimal("25000000"),
        tasa_deuda=Decimal("0.1157"),
        mes_inicio_deuda=2,
        meses_deuda=14,
        pct_mora=Decimal("0.08"),
        pct_recuperacion=Decimal("0.65"),
        pct_default=Decimal("0.05"),
        pct_provision=Decimal("0.02"),
    )
    base.update(over)
    return ParametrosProyeccion(**base)


def _armar(params, escenario):
    return _armar_parametros(params, [], escenario, (2026, 8), 12)


def test_los_escenarios_editables_mandan_sobre_el_preset():
    """El CEO fija los valores de v9.1 (pesimista 14/50 · optimista 4/90) y esos
    mandan — nada de porcentajes clavados en el código."""
    p = _params(
        pct_mora_pesimista=Decimal("0.14"),
        pct_recuperacion_pesimista=Decimal("0.50"),
        pct_mora_optimista=Decimal("0.04"),
        pct_recuperacion_optimista=Decimal("0.90"),
    )
    pes = _armar(p, "pesimista")
    opt = _armar(p, "optimista")
    assert (pes.pct_mora, pes.pct_recuperacion) == (Decimal("0.14"), Decimal("0.50"))
    assert (opt.pct_mora, opt.pct_recuperacion) == (Decimal("0.04"), Decimal("0.90"))
    # el base sigue siendo el supuesto del CEO (SUP-1, sin cambio)
    assert _armar(p, "base").pct_mora == Decimal("0.08")


def test_sin_valores_explicitos_se_conserva_sup1():
    """Compatibilidad: sin editar los escenarios sigue el delta en puntos de SUP-1."""
    p = _params(pct_mora=Decimal("0.05"))  # +2 puntos sobre el preset base (3 %)
    assert _armar(p, "pesimista").pct_mora == Decimal("0.08")  # 0.06 + 0.02
    assert _armar(p, "optimista").pct_mora == Decimal("0.035")  # 0.015 + 0.02


def test_un_escenario_editado_no_arrastra_al_otro():
    p = _params(pct_mora_pesimista=Decimal("0.20"))
    assert _armar(p, "pesimista").pct_mora == Decimal("0.20")
    # el optimista, sin valor propio, sigue con el delta
    assert _armar(p, "optimista").pct_mora == Decimal("0.065")  # 0.015 + 0.05


def test_escenario_editable_fuera_de_rango_se_rechaza():
    with pytest.raises(ValidationError):
        _params(pct_mora_pesimista=Decimal("1.5"))
    with pytest.raises(ValidationError):
        _params(pct_recuperacion_optimista=Decimal("-0.1"))


# ── B · rezago de la recuperación ──


def test_sin_rezago_la_recuperacion_es_del_mismo_mes():
    """Candado del golden master: el default del motor mantiene la semántica del
    artefacto (recuperar la mora del propio mes)."""
    a = neto_por_mora(
        Decimal("1000"), Decimal("0.10"), Decimal("0.50"), Decimal("0"), Decimal("0")
    )
    assert a.mora == Decimal("-100.00")
    assert a.recuperacion == Decimal("50.00")  # 50 % de la mora del MISMO mes


def test_con_rezago_recupera_la_mora_del_mes_anterior():
    """v9.1: la recuperación de este mes sale de la mora del mes pasado."""
    a = neto_por_mora(
        Decimal("1000"),
        Decimal("0.10"),
        Decimal("0.50"),
        Decimal("0"),
        Decimal("0"),
        mora_a_recuperar=Decimal("-400"),  # la mora del mes anterior
    )
    assert a.mora == Decimal("-100.00")  # su propia mora no cambia
    assert a.recuperacion == Decimal("200.00")  # 50 % de los 400 del mes pasado


def test_el_primer_mes_con_rezago_no_recupera_nada():
    """No hay mes anterior del que recuperar (y no se inventa)."""
    pm = _motor(meses_rezago_recuperacion=1, pct_mora=Decimal("0.10"))
    r = proyectar(pm)
    assert Decimal(r.meses[0].neto) <= Decimal(r.meses[0].ingreso_bruto)


def test_el_rezago_difiere_plata_sin_perderla():
    """Con rezago, el mes 0 recibe menos (no recupera) — la plata llega después."""
    sin = proyectar(_motor(meses_rezago_recuperacion=0, pct_mora=Decimal("0.10")))
    con = proyectar(_motor(meses_rezago_recuperacion=1, pct_mora=Decimal("0.10")))
    assert Decimal(con.meses[0].neto) < Decimal(sin.meses[0].neto)


# ── C · % de prefondeo del IVA ──


def _liq(neto: str) -> list[LiquidacionPeriodo]:
    return [
        LiquidacionPeriodo(
            anio=2026,
            periodo=2,
            generado=Decimal("0"),
            descontable=Decimal("0"),
            saldo=Decimal(neto),
            saldo_favor_previo=Decimal("0"),
            neto_a_pagar=Decimal(neto),
            saldo_favor_nuevo=Decimal("0"),
        )
    ]


_CAL = {"2026": {"may_ago": "2026-09-10"}}


def test_prefondeo_100_es_el_comportamiento_de_hoy():
    fondo = plan_fondo_provision(
        _liq("4000000"), _CAL, mes_inicio=(2026, 5), horizonte_meses=6
    )
    # 4 meses del período (may–ago) × 1.000.000 de reserva
    assert [f.reserva for f in fondo[:4]] == [Decimal("1000000.00")] * 4


def test_prefondeo_editable_reserva_solo_ese_porcentaje():
    fondo = plan_fondo_provision(
        _liq("4000000"),
        _CAL,
        mes_inicio=(2026, 5),
        horizonte_meses=6,
        pct_prefondeo=Decimal("0.70"),
    )
    assert [f.reserva for f in fondo[:4]] == [Decimal("700000.00")] * 4


# ── D · fondo AVAL propio (autoseguro) ──


def _motor(**over) -> ParametrosMotor:
    base = dict(
        mes_inicio=(2026, 8),
        horizonte_meses=6,
        modelos=[
            ModeloProyeccion(
                nombre="Raider",
                cuota_semanal=Decimal("184900"),
                cuota_inicial=Decimal("1620000"),
                plazo_semanas=78,
                mix=Decimal("1"),
                costo_moto=Decimal("6720557"),
            )
        ],
        motos_base=70,
        crec_pct_mensual=Decimal("0.10"),
        rampa=None,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=150,
        base_auteco_dias=90,
        tasa_auteco=Decimal("0.016"),
        gastos_fijos=Decimal("208000000"),
        gps_moto=Decimal("33201"),
        costo_moto_nueva=Decimal("691500"),
        deuda=Decimal("25000000"),
        tasa_deuda=Decimal("0.1157"),
        mes_inicio_deuda=2,
        meses_deuda=14,
        pct_mora=Decimal("0.08"),
        pct_recuperacion=Decimal("0.65"),
        pct_default=Decimal("0.05"),
        pct_provision=Decimal("0.02"),
        overrides_mora=None,
        overrides_default=None,
        caja_inicial=Decimal("700000000"),
        caja_minima=Decimal("125000000"),
    )
    base.update(over)
    return ParametrosMotor(**base)


def test_sin_aval_no_hay_egreso_nuevo():
    """Default 0 = la proyección de siempre (candado del golden)."""
    r = proyectar(_motor())
    assert all(m.aval == Decimal("0.00") for m in r.meses)


def test_el_aval_es_un_porcentaje_del_recaudo_de_credito():
    """v9.1 FC!33: −recaudo × %. Es egreso (reserva de autoseguro)."""
    r = proyectar(_motor(pct_aval_recaudo=Decimal("0.01")))
    m = r.meses[3]  # un mes con recaudo ya corriendo
    assert m.recaudo_credito > 0
    assert m.aval == -(m.recaudo_credito * Decimal("0.01")).quantize(Decimal("0.01"))
    # y entra en los egresos del mes
    assert m.aval < 0


def test_el_aval_empeora_la_caja():
    sin = proyectar(_motor())
    con = proyectar(_motor(pct_aval_recaudo=Decimal("0.01")))
    assert con.piso_caja < sin.piso_caja


def test_el_aval_viaja_desde_los_supuestos():
    pm = _armar(_params(pct_aval_recaudo=Decimal("0.01")), "base")
    assert pm.pct_aval_recaudo == Decimal("0.01")


def test_el_rezago_viaja_desde_los_supuestos():
    pm = _armar(_params(meses_rezago_recuperacion=2), "base")
    assert pm.meses_rezago_recuperacion == 2
