# backend/tests/test_e1_precedencia.py
"""E1 · P3 — precedencia y no-colisión con D2 (capa pura de reconciliación).

La reconciliación D2 (Auteco) debe EXCLUIR los meses que E1 ya ancló: no netea su
paramétrico ni aplica pagos reales ahí (esa realidad ya la puso E1; tocarla sería doble
conteo). `meses_anclados` es aditivo: vacío ⇒ la serie es idéntica a hoy (candado de
no-regresión de D2).

B7  — factura que paga en un mes anclado → D2 la SALTA; en un mes no-anclado → normal.
Candado — `meses_anclados=frozenset()` ⇒ resultado idéntico al de hoy."""

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


def _dos_facturas():
    # una paga 2026-10 (plazo 60), otra 2026-12 (plazo 120)
    return [
        FacturaReconciliar(
            fecha_factura="2026-08-15",
            valor=Decimal("1000000"),
            plazo_elegido_dias=60,
            plazo_base_dias=30,
            tasa_excedente_mensual=Decimal("0.016"),
        ),
        FacturaReconciliar(
            fecha_factura="2026-08-15",
            valor=Decimal("2000000"),
            plazo_elegido_dias=120,
            plazo_base_dias=30,
            tasa_excedente_mensual=Decimal("0.016"),
        ),
    ]


def test_candado_vacio_identico_a_hoy():
    """`meses_anclados=frozenset()` ⇒ serie idéntica a hoy (candado no-regresión D2)."""
    r, cm = _base()
    facturas = _dos_facturas()
    hoy = reconciliar(r, facturas, cm)
    con_default = reconciliar(r, facturas, cm, meses_anclados=frozenset())
    assert con_default.ventana == hoy.ventana
    assert con_default.capital_por_mes == hoy.capital_por_mes
    assert con_default.interes_por_mes == hoy.interes_por_mes
    for a, b in zip(con_default.ajustado.meses, hoy.ajustado.meses, strict=True):
        assert a.flujo == b.flujo
        assert a.caja == b.caja
        assert a.pago_inventario == b.pago_inventario
        assert a.fondeo == b.fondeo


def test_b7_d2_salta_el_mes_anclado_y_reconcilia_el_resto():
    """B7: 2026-10 anclado por E1 → D2 no lo netea ni aplica su pago (queda como el
    motor lo dejó, para que E1 lo reescriba); 2026-12 (no anclado) → reconcilia normal.
    Ningún peso contado dos veces."""
    r, cm = _base()
    facturas = _dos_facturas()
    idx = {m.mes: i for i, m in enumerate(r.meses)}
    oct_i, dic_i = idx["2026-10"], idx["2026-12"]

    rec = reconciliar(r, facturas, cm, meses_anclados=frozenset({"2026-10"}))

    # el pago de octubre queda FUERA de la reconciliación (es territorio de E1)
    assert rec.capital_por_mes == {"2026-12": "2000000.00"}
    assert rec.interes_por_mes == {"2026-12": "96000.00"}  # 2M × 1,6% × 3 meses
    assert rec.ventana == ("2026-12", "2026-12")

    # octubre (anclado): D2 NO lo tocó → Auteco paramétrico intacto (== base del motor)
    assert rec.ajustado.meses[oct_i].pago_inventario == r.meses[oct_i].pago_inventario
    assert rec.ajustado.meses[oct_i].fondeo == r.meses[oct_i].fondeo

    # diciembre (no anclado): reconciliado con el pago REAL
    assert rec.ajustado.meses[dic_i].pago_inventario == Decimal("-2000000.00")
    assert rec.ajustado.meses[dic_i].fondeo == Decimal("-96000.00")
