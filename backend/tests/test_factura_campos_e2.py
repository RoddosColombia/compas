# backend/tests/test_factura_campos_e2.py
"""E2 §3.1 — campos nuevos de Factura (DIAN) y el origen sin_clasificar."""

from decimal import Decimal

from app.domain.factura import (
    TIPO_DOC_FACTURA_VENTA,
    Factura,
    OrigenFactura,
    TipoFactura,
)


def _minima(**over) -> Factura:
    base = dict(
        tipo=TipoFactura.compra,
        origen=OrigenFactura.otra_compra,
        numero="UI90-16716",
        tercero_nombre="ALMACENES ÉXITO S.A",
        tercero_nit="890900608",
        fecha="2026-05-28",
        base_gravable=Decimal("31447.06"),
        tarifa_iva=Decimal("0.19"),
        iva_valor=Decimal("1452.94"),
        total=Decimal("32900.00"),
    )
    base.update(over)
    return Factura(**base)


def test_campos_nuevos_tienen_defaults_seguros():
    f = _minima()
    assert f.cufe is None  # captura manual no trae CUFE
    assert f.tipo_documento == TIPO_DOC_FACTURA_VENTA
    assert f.signo == 1
    assert f.inc_valor == Decimal("0.00")
    assert f.bolsas == Decimal("0.00")
    assert f.otros_impuestos == Decimal("0.00")
    assert f.rete_fuente == Decimal("0.00")
    assert f.rete_iva == Decimal("0.00")
    assert f.rete_ica == Decimal("0.00")
    assert f.archivo_ref is None


def test_origen_sin_clasificar_es_valido():
    f = _minima(origen=OrigenFactura.sin_clasificar)
    assert f.origen is OrigenFactura.sin_clasificar


def test_cufe_se_persiste_cuando_viene():
    f = _minima(cufe="fabdb194877f049b698d92065704f28fec96e9c0")
    assert f.cufe.startswith("fabdb194")


def test_impuestos_dian_se_guardan():
    f = _minima(
        inc_valor=Decimal("100.00"),
        rete_fuente=Decimal("50.00"),
        archivo_ref="s3://facturas/UI90-16716.pdf",
    )
    assert f.inc_valor == Decimal("100.00")
    assert f.rete_fuente == Decimal("50.00")
    assert f.archivo_ref.endswith(".pdf")
