from decimal import Decimal

from app.cfo.calc.iva_tesoreria import armar_conceptos


def _by(cs):
    return {c.concepto: c for c in cs}


def test_conceptos_completos_y_cobertura_cubierta():
    cs = _by(
        armar_conceptos(
            reserva_objetivo=Decimal("1000"),
            reserva_mes=Decimal("250"),
            proximo_monto=Decimal("3000"),
            proximo_fecha="2027-01-14",
            disponible=Decimal("1500"),
        )
    )
    assert cs["ivates_reserva_objetivo"].valor == Decimal("1000")
    assert cs["ivates_disponible_neto"].valor == Decimal("500")  # 1500 - 1000
    assert cs["ivates_faltante"].valor == Decimal("0")  # cubierto
    assert cs["ivates_proximo_pago"].evidencia.fecha_corte == "2027-01-14"


def test_descubierto_faltante_positivo_y_neto_negativo():
    cs = _by(
        armar_conceptos(
            reserva_objetivo=Decimal("1000"),
            reserva_mes=Decimal("250"),
            proximo_monto=Decimal("3000"),
            proximo_fecha="2027-01-14",
            disponible=Decimal("600"),
        )
    )
    assert cs["ivates_disponible_neto"].valor == Decimal("-400")
    assert cs["ivates_faltante"].valor == Decimal("400")


def test_sin_disponible_abstiene_neto_y_faltante():
    cs = _by(
        armar_conceptos(
            reserva_objetivo=Decimal("1000"),
            reserva_mes=Decimal("250"),
            proximo_monto=Decimal("3000"),
            proximo_fecha="2027-01-14",
            disponible=None,
        )
    )
    assert cs["ivates_disponible_neto"].disponible is False
    assert cs["ivates_faltante"].disponible is False
    # este no depende del disponible
    assert cs["ivates_reserva_objetivo"].disponible is True
