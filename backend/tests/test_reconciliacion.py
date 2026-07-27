# backend/tests/test_reconciliacion.py
"""Reconciliación anti-doble-conteo (D2 §4). Sin facturas == base bit a bit; con una
factura, el mes de pago netea el paramétrico y aparece el pago real con su interés
separado; ni un peso doble. Motor intacto (capa post-motor)."""

from decimal import Decimal

from app.obligaciones.reconciliacion import FacturaReconciliar, reconciliar
from app.proyeccion.motor import ModeloProyeccion, ParametrosMotor, proyectar


def _params(**over):
    base = dict(
        mes_inicio=(2026, 7),
        horizonte_meses=12,
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
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=60,
        base_auteco_dias=30,
        tasa_auteco=Decimal("0.016"),
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
        caja_inicial=Decimal("500000"),
        caja_minima=Decimal("10000"),
    )
    base.update(over)
    return ParametrosMotor(**base)


def _base():
    p = _params()
    return proyectar(p), p.caja_minima


def test_sin_facturas_es_base_bit_a_bit():
    r, cm = _base()
    rec = reconciliar(r, [], cm)
    assert rec.ventana is None
    assert rec.interes_por_mes == {}
    for a, b in zip(rec.ajustado.meses, r.meses, strict=True):
        assert a.flujo == b.flujo
        assert a.caja == b.caja


def test_pagos_fuera_del_horizonte_no_reconcilian():
    r, cm = _base()
    # factura cuyo pago cae en 2030 (fuera del horizonte de 12 meses)
    f = FacturaReconciliar(
        fecha_factura="2030-01-10",
        valor=Decimal("1000000"),
        plazo_elegido_dias=60,
        plazo_base_dias=30,
        tasa_excedente_mensual=Decimal("0.016"),
    )
    rec = reconciliar(r, [f], cm)
    assert rec.ventana is None
    for a, b in zip(rec.ajustado.meses, r.meses, strict=True):
        assert a.flujo == b.flujo


def test_una_factura_netea_el_parametrico_y_suma_el_real():
    r, cm = _base()
    f = FacturaReconciliar(
        fecha_factura="2026-08-15",  # + 60 días (2 meses) → paga 2026-10
        valor=Decimal("1000000"),
        plazo_elegido_dias=60,
        plazo_base_dias=30,
        tasa_excedente_mensual=Decimal("0.016"),
    )
    rec = reconciliar(r, [f], cm)
    assert rec.ventana == ("2026-10", "2026-10")
    # interés separado: 1 M × 1,6% × 1 mes excedente
    assert rec.interes_por_mes == {"2026-10": "16000.00"}
    assert rec.capital_por_mes == {"2026-10": "1000000.00"}

    idx = {m.mes: i for i, m in enumerate(r.meses)}
    m = idx["2026-10"]
    base_fila = r.meses[m]
    # flujo reconciliado = base − paramétrico(pago_inv+fondeo) − real(capital+interés)
    esperado = (
        base_fila.flujo
        - base_fila.pago_inventario
        - base_fila.fondeo
        - Decimal("1000000.00")
        - Decimal("16000.00")
    ).quantize(Decimal("0.01"))
    assert rec.ajustado.meses[m].flujo == esperado


def test_meses_fuera_de_la_ventana_intactos():
    r, cm = _base()
    f = FacturaReconciliar(
        fecha_factura="2026-08-15",
        valor=Decimal("1000000"),
        plazo_elegido_dias=60,
        plazo_base_dias=30,
        tasa_excedente_mensual=Decimal("0.016"),
    )
    rec = reconciliar(r, [f], cm)
    idx = {m.mes: i for i, m in enumerate(r.meses)}
    ventana = idx["2026-10"]
    for i, (a, b) in enumerate(zip(rec.ajustado.meses, r.meses, strict=True)):
        if i != ventana:
            assert a.flujo == b.flujo  # fuera de la ventana, intacto
