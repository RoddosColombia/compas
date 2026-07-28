# backend/tests/test_iva_liquidacion.py
"""IVA C11 (PR-2a/2b) — liquidación PURA (sin I/O) del diseño §5.2 de
docs/modelo/AUDITORIA-IVA-ARTIFACT-V2.md. Período CONFIGURABLE (decisión CEO
2026-07-25): default CUATRIMESTRAL, bimestral habilitable cuando la DIAN lo exija.
Decimal, arrastre de saldo a favor. Tarifa 19%; extracción 19/119 verificada al peso.
"""

from decimal import Decimal

from app.iva.liquidacion import (
    FacturaIva,
    Periodicidad,
    cuatrimestre_de,
    iva_desde_base,
    iva_desde_total,
    liquidar,
    periodo_de,
    plan_fondo_provision,
    programar_egresos_iva,
)

_CAL_DIAN = {
    "2026": {"ene_abr": "2026-05-13", "may_ago": "2026-09-10", "sep_dic": "2027-01-14"}
}
# Calendario bimestral (6 períodos/año): fechas de prueba (solo importa el índice).
_CAL_DIAN_BI = {"2026": {"ene_feb": "2026-03-15", "mar_abr": "2026-05-15"}}


def test_cuatrimestre_de():
    # ene-abr → C1 · may-ago → C2 · sep-dic → C3 (default cuatrimestral)
    assert cuatrimestre_de("2026-01-01") == (2026, 1)
    assert cuatrimestre_de("2026-04-30") == (2026, 1)
    assert cuatrimestre_de("2026-05-01") == (2026, 2)
    assert cuatrimestre_de("2026-08-31") == (2026, 2)
    assert cuatrimestre_de("2026-09-01") == (2026, 3)
    assert cuatrimestre_de("2026-12-31") == (2026, 3)
    assert cuatrimestre_de("2027-01-14") == (2027, 1)


def test_periodo_de_bimestral():
    # 6 períodos: ene-feb=1 · mar-abr=2 · may-jun=3 · jul-ago=4 · sep-oct=5 · nov-dic=6
    b = Periodicidad.bimestral
    assert periodo_de("2026-01-15", b) == (2026, 1)
    assert periodo_de("2026-02-28", b) == (2026, 1)
    assert periodo_de("2026-03-01", b) == (2026, 2)
    assert periodo_de("2026-06-30", b) == (2026, 3)
    assert periodo_de("2026-12-31", b) == (2026, 6)


def test_iva_desde_base_y_total():
    assert iva_desde_base(Decimal("1000"), Decimal("0.19")) == Decimal("190.00")
    # total INCLUYE IVA: 1190 → iva 190 (extracción 19/119, verificada al peso)
    assert iva_desde_total(Decimal("1190"), Decimal("0.19")) == Decimal("190.00")
    # exento
    assert iva_desde_base(Decimal("1000"), Decimal("0")) == Decimal("0.00")


def test_liquidar_un_periodo_descontable_solo_deducible():
    facturas = [
        FacturaIva("venta", "2026-02-10", Decimal("190")),  # generado
        FacturaIva("compra", "2026-03-05", Decimal("100"), True),  # descontable
        FacturaIva("compra", "2026-03-20", Decimal("50"), False),  # no deducible
    ]
    liq = liquidar(facturas)
    assert len(liq) == 1
    c = liq[0]
    assert (c.anio, c.periodo) == (2026, 1)
    assert c.generado == Decimal("190")
    assert c.descontable == Decimal("100")  # el no-deducible NO entra
    assert c.saldo == Decimal("90")
    assert c.neto_a_pagar == Decimal("90")
    assert c.saldo_favor_nuevo == Decimal("0")


def test_liquidar_arrastra_saldo_a_favor():
    facturas = [
        # C1 2026: descontable (120) > generado (50) → saldo a favor 70
        FacturaIva("venta", "2026-02-10", Decimal("50")),
        FacturaIva("compra", "2026-02-11", Decimal("120"), True),
        # C2 2026: generado 200, descontable 50 → saldo 150; usa el favor 70 → paga 80
        FacturaIva("venta", "2026-06-10", Decimal("200")),
        FacturaIva("compra", "2026-06-11", Decimal("50"), True),
    ]
    c1, c2 = liquidar(facturas)
    assert c1.saldo == Decimal("-70")
    assert c1.neto_a_pagar == Decimal("0")
    assert c1.saldo_favor_nuevo == Decimal("70")
    assert c2.saldo == Decimal("150")
    assert c2.saldo_favor_previo == Decimal("70")
    assert c2.neto_a_pagar == Decimal("80")  # 150 − 70 arrastrado
    assert c2.saldo_favor_nuevo == Decimal("0")


def test_liquidar_bimestral_separa_en_seis_periodos():
    # ene (P1) y mar (P2) caen en bimestres DISTINTOS; cuatrimestral los uniría en C1.
    facturas = [
        FacturaIva("venta", "2026-01-10", Decimal("100")),
        FacturaIva("venta", "2026-03-10", Decimal("200")),
    ]
    liq = liquidar(facturas, Periodicidad.bimestral)
    assert [(x.anio, x.periodo) for x in liq] == [(2026, 1), (2026, 2)]
    assert liq[0].generado == Decimal("100")
    assert liq[1].generado == Decimal("200")


def test_programar_egresos_iva_cae_en_el_mes_dian():
    # C1-2026 (neto 190000) paga 13-may-26; C2-2026 (neto 300000) paga 10-sep-26.
    # mes_inicio = ene-2026 → may = índice 4, sep = índice 8.
    liq = [
        FacturaIva("venta", "2026-02-10", Decimal("190000")),
        FacturaIva("venta", "2026-06-10", Decimal("300000")),
    ]
    egresos = programar_egresos_iva(
        liquidar(liq), _CAL_DIAN, mes_inicio=(2026, 1), horizonte_meses=24
    )
    assert egresos == {4: Decimal("190000"), 8: Decimal("300000")}


def test_programar_egresos_iva_bimestral():
    # bimestre ene-feb paga 15-mar-26 (índice 2); mar-abr paga 15-may-26 (índice 4).
    liq = liquidar(
        [
            FacturaIva("venta", "2026-01-10", Decimal("100000")),
            FacturaIva("venta", "2026-03-10", Decimal("200000")),
        ],
        Periodicidad.bimestral,
    )
    egresos = programar_egresos_iva(
        liq,
        _CAL_DIAN_BI,
        mes_inicio=(2026, 1),
        horizonte_meses=24,
        periodicidad=Periodicidad.bimestral,
    )
    assert egresos == {2: Decimal("100000"), 4: Decimal("200000")}


def test_programar_egresos_iva_ignora_neto_cero_y_fuera_de_horizonte():
    # saldo a favor (neto 0) no genera egreso; y un período cuya fecha DIAN cae
    # fuera del horizonte no entra.
    liq = [
        FacturaIva("compra", "2026-02-10", Decimal("500000"), True),  # solo descontable
        FacturaIva("venta", "2026-06-10", Decimal("300000")),
    ]
    egresos = programar_egresos_iva(
        liquidar(liq), _CAL_DIAN, mes_inicio=(2026, 1), horizonte_meses=6
    )
    # C1 neto 0 (saldo a favor) → no entra; C2 paga en sep (índice 8) > horizonte 6 → no
    assert egresos == {}


def test_programar_egresos_iva_no_inventa_anios_sin_calendario():
    # C1-2027 no tiene fecha DIAN en el calendario → NO se proyecta (no se inventa).
    liq = [FacturaIva("venta", "2027-02-10", Decimal("190000"))]
    egresos = programar_egresos_iva(
        liquidar(liq), _CAL_DIAN, mes_inicio=(2026, 1), horizonte_meses=36
    )
    assert egresos == {}


def test_plan_fondo_provision_reserva_durante_el_periodo_y_paga_en_dian():
    # C1-2026 neto 400000, paga 13-may-26. mes_inicio ene-2026, horizonte 6.
    # Se reserva 100000/mes en ene-abr (los 4 meses del período); al terminar abril el
    # fondo tiene 400000; en may (índice 4) el pago lo vacía.
    liq = liquidar([FacturaIva("venta", "2026-02-10", Decimal("400000"))])
    fondo = plan_fondo_provision(
        liq, _CAL_DIAN, mes_inicio=(2026, 1), horizonte_meses=6
    )
    assert len(fondo) == 6

    def _d(*xs):
        return [Decimal(x) for x in xs]

    reservas = [f.reserva for f in fondo]
    pagos = [f.pago for f in fondo]
    saldos = [f.saldo for f in fondo]
    assert reservas == _d("100000", "100000", "100000", "100000", "0", "0")
    assert pagos == _d("0", "0", "0", "0", "400000", "0")
    assert saldos == _d("100000", "200000", "300000", "400000", "0", "0")


def test_plan_fondo_provision_saldo_a_favor_no_reserva():
    # período con neto 0 (saldo a favor) → sin reserva ni pago.
    liq = liquidar([FacturaIva("compra", "2026-02-10", Decimal("500000"), True)])
    fondo = plan_fondo_provision(
        liq, _CAL_DIAN, mes_inicio=(2026, 1), horizonte_meses=6
    )
    assert all(f.reserva == Decimal("0") and f.pago == Decimal("0") for f in fondo)


def test_liquidar_ordena_periodos_cronologicamente():
    # facturas desordenadas → liquidación en orden (el arrastre exige cronología)
    facturas = [
        FacturaIva("venta", "2026-06-10", Decimal("200")),
        FacturaIva("venta", "2026-02-10", Decimal("50")),
        FacturaIva("compra", "2026-02-11", Decimal("120"), True),
    ]
    liq = liquidar(facturas)
    assert [(x.anio, x.periodo) for x in liq] == [(2026, 1), (2026, 2)]
