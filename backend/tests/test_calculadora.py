# backend/tests/test_calculadora.py
"""Calculadora de obligaciones (D2 §3) + el CANDADO DE PARIDAD con el motor.

El criterio literal del brief: "la lógica existente produce los mismos resultados que
antes". El candado importa `inventario_auteco_mensual` de `motor.py` (SIN tocarla) y
verifica al peso que la calculadora por-factura, agregada al mes, reproduce su régimen
estacionario. La convención del motor (//30) es la fuente única (spec §3).
"""

from decimal import Decimal

from app.obligaciones.calculadora import (
    calendario_cuotas,
    pago_factura,
)
from app.proyeccion.motor import inventario_auteco_mensual

# ── Facturación: el caso del §1 (prueba de terminado) ─────────────────────────


def test_pago_factura_180m_plazo_150():
    p = pago_factura(
        fecha_factura="2026-08-15",
        valor=Decimal("180000000"),
        plazo_elegido_dias=150,
        plazo_base_dias=90,
        tasa_excedente_mensual=Decimal("0.016"),
    )
    assert p.mes == "2027-01"  # 15-ago + 5 meses (150 // 30)
    assert p.capital == Decimal("180000000.00")
    # interés = 180 M × 1,6% × 2 meses excedentes
    assert p.interes == Decimal("5760000.00")


def test_pago_factura_plazo_base_sin_interes():
    p = pago_factura(
        fecha_factura="2026-08-15",
        valor=Decimal("180000000"),
        plazo_elegido_dias=90,
        plazo_base_dias=90,
        tasa_excedente_mensual=Decimal("0.016"),
    )
    assert p.mes == "2026-11"  # 15-ago + 3 meses
    assert p.interes == Decimal("0.00")  # plazo == base → sin excedente


# ── El CANDADO de paridad con inventario_auteco_mensual ───────────────────────


def test_candado_paridad_con_inventario_auteco():
    n = 12
    lote = [Decimal("1000000")] * n  # $1 M colocado cada mes
    adelanto = [Decimal("0")] * n  # Auteco: adelanto $0 (decisión CEO)
    plazo, base = 150, 90
    tasa = Decimal("0.016")

    pago_inv, fondeo = inventario_auteco_mensual(lote, adelanto, plazo, base, tasa)

    # Agregación por-factura: el lote del mes k es una factura con ese valor y plazo.
    delay = plazo // 30
    cap_por_mes = [Decimal("0")] * n
    int_por_mes = [Decimal("0")] * n
    for k in range(n):
        p = pago_factura(
            fecha_factura=f"2026-{k + 1:02d}-01",
            valor=lote[k],
            plazo_elegido_dias=plazo,
            plazo_base_dias=base,
            tasa_excedente_mensual=tasa,
        )
        idx = k + delay
        if idx < n:
            cap_por_mes[idx] += p.capital
            int_por_mes[idx] += p.interes

    # Régimen estacionario (m ≥ delay): la calculadora reproduce el motor AL PESO.
    for m in range(delay, n):
        assert -pago_inv[m] == cap_por_mes[m], f"capital difiere en m={m}"
        assert -fondeo[m] == int_por_mes[m], f"interés difiere en m={m}"


def test_candado_arranque_es_del_motor_documentado():
    # El motor tiene un fondeo de ARRANQUE en delay_base+1 (coste de sostener el primer
    # lote entre base y plazo) que la calculadora por-factura no modela: es del motor y
    # la reconciliación §4 lo netea. Se documenta que existe y queda fuera del candado.
    n = 12
    lote = [Decimal("1000000")] * n
    adelanto = [Decimal("0")] * n
    _pago, fondeo = inventario_auteco_mensual(lote, adelanto, 150, 90, Decimal("0.016"))
    # delay_base = 3 → fondeo de arranque en m=4, antes de delay_pago=5.
    assert fondeo[4] != Decimal("0.00")


# ── Cuotas ────────────────────────────────────────────────────────────────────


def test_calendario_cuotas_cierra_el_saldo():
    pagos = calendario_cuotas(
        monto_total=Decimal("12000000"),
        n_cuotas=12,
        periodicidad_meses=1,
        tasa_mensual=Decimal("0.01"),
        fecha_inicio="2026-09-01",
        meses_gracia=0,
    )
    assert len(pagos) == 12
    assert pagos[0].mes == "2026-09"
    assert pagos[-1].mes == "2027-08"
    # el capital suma exactamente el monto (última cuota ajusta)
    assert sum((p.capital for p in pagos), Decimal("0")) == Decimal("12000000.00")
    # interés decreciente sobre el saldo
    assert pagos[0].interes > pagos[-1].interes


def test_calendario_cuotas_gracia_desplaza():
    pagos = calendario_cuotas(
        monto_total=Decimal("6000000"),
        n_cuotas=6,
        periodicidad_meses=1,
        tasa_mensual=Decimal("0.01"),
        fecha_inicio="2026-09-01",
        meses_gracia=2,
    )
    assert pagos[0].mes == "2026-11"  # 2 meses de gracia
