# backend/tests/test_extraccion_dian.py
"""E2 §4.1 — extractor DIAN. Prueba la LÓGICA con estructuras sintéticas (no requiere
shippear PDFs reales): A8 títulos oficiales + regresión M-1, A4 tipo por NIT, A5 INC>0
(toma IVA, no Total impuesto), A6 coherencia, A7 no-DIAN. A1 (PDF real) se auto-activa
cuando el fixture exista en backend/tests/fixtures/."""

from decimal import Decimal
from pathlib import Path

import pytest
from app.facturas.extraccion import (
    TIPO_SOPORTADO,
    TITULOS_A8,
    DocumentoNoDian,
    TipoNoSoportado,
    _a_decimal,
    es_documento_dian,
    extraer,
    factura_desde_documento,
    tipo_documento,
)

NIT_RODDOS = "901012622"


def _texto(
    titulo: str,
    nit_emisor: str = "890900608",
    nit_adq: str = NIT_RODDOS,
    contrib_emisor: str = "Persona Jurídica",
    contrib_adq: str = "Persona Jurídica",
) -> str:
    """Texto DIAN mínimo válido con el título dado. Refleja la estructura real de
    dos bloques (emisor / adquiriente), cada uno con su Tipo de Contribuyente."""
    return (
        f"{titulo}\n"
        "Representación Gráfica Dian\n"
        "CUFE : abcdef0123456789abcdef0123456789abcdef01\n"
        "Número de Factura: UI90-16716\n"
        "Fecha de Emisión: 28/05/2026\n"
        "Datos del Emisor / Vendedor\n"
        f"Nit del Emisor: {nit_emisor}\n"
        "Razón Social: ALMACENES ÉXITO S.A\n"
        f"Tipo de Contribuyente: {contrib_emisor} Departamento: Bogotá\n"
        "Datos del Adquiriente / Comprador\n"
        f"Número Documento: {nit_adq}\n"
        f"Tipo de Contribuyente: {contrib_adq} Municipio: Bogotá\n"
    )


def _fila(*textos: str) -> list[dict]:
    return [{"text": t, "x0": 0.0, "top": 0.0} for t in textos]


# base 1.000, IVA 190 (19%), INC 100 → Total impuesto 290, Total factura 1.290.
def _filas_inc() -> list[list[dict]]:
    return [
        _fila("Total", "Bruto", "Factura", "1.000,00"),
        _fila("IVA", "IVA", "190,00"),
        _fila("INC", "100,00"),
        _fila("Total", "impuesto", "290,00"),
        _fila("Total", "factura", "1.290,00"),
        _fila("Rete", "IVA", "0,00"),
    ]


def test_a_decimal_formato_cop():
    assert _a_decimal("1.452,94") == Decimal("1452.94")
    assert _a_decimal("32.900,00") == Decimal("32900.00")


# ── A8 + regresión M-1: los cuatro títulos oficiales se rechazan ──
@pytest.mark.parametrize("titulo", TITULOS_A8)
def test_a8_titulos_oficiales_dian_se_rechazan(titulo):
    with pytest.raises(TipoNoSoportado):
        tipo_documento(_texto(titulo))


def test_m1_nota_credito_no_entra_como_factura():
    """La NC oficial contiene 'FACTURA ELECTRÓNICA DE VENTA'; el orden M-1 la rechaza."""  # noqa: E501
    nc = "Nota Crédito de Factura Electrónica de Venta"
    with pytest.raises(TipoNoSoportado):
        tipo_documento(_texto(nc))


def test_a8_factura_de_venta_legitima_se_acepta():
    assert tipo_documento(_texto("FACTURA ELECTRÓNICA DE VENTA")) == TIPO_SOPORTADO


# ── A4: tipo deducido del NIT ──
def test_a4_recibida_cuando_roddos_es_adquiriente():
    f = factura_desde_documento(
        _texto("FACTURA ELECTRÓNICA DE VENTA", nit_emisor="890900608"),
        _filas_inc(),
        "Representación Gráfica Dian",
        NIT_RODDOS,
    )
    assert f.tipo == "recibida"


def test_a4_emitida_cuando_roddos_es_emisor():
    f = factura_desde_documento(
        _texto(
            "FACTURA ELECTRÓNICA DE VENTA", nit_emisor=NIT_RODDOS, nit_adq="800111222"
        ),
        _filas_inc(),
        "Representación Gráfica Dian",
        NIT_RODDOS,
    )
    assert f.tipo == "emitida"


def test_a4_documento_ajeno_se_rechaza():
    with pytest.raises(DocumentoNoDian):
        factura_desde_documento(
            _texto("FACTURA ELECTRÓNICA DE VENTA", nit_emisor="111", nit_adq="222"),
            _filas_inc(),
            "Representación Gráfica Dian",
            NIT_RODDOS,
        )


# ── tipo_contribuyente de la CONTRAPARTE (GO CEO punto 1: enmascaramiento fino) ──
def test_contribuyente_contraparte_es_el_emisor_en_recibida():
    f = factura_desde_documento(
        _texto(
            "FACTURA ELECTRÓNICA DE VENTA",
            contrib_emisor="Persona Natural",
            contrib_adq="Persona Jurídica",
        ),
        _filas_inc(),
        "Representación Gráfica Dian",
        NIT_RODDOS,
    )
    # recibida → la contraparte es el emisor (natural), no el adquiriente RODDOS
    assert f.tipo == "recibida"
    assert f.tipo_contribuyente_contraparte == "persona_natural"


def test_contribuyente_contraparte_es_el_adquiriente_en_emitida():
    f = factura_desde_documento(
        _texto(
            "FACTURA ELECTRÓNICA DE VENTA",
            nit_emisor=NIT_RODDOS,
            nit_adq="800111222",
            contrib_emisor="Persona Jurídica",
            contrib_adq="Persona Natural",
        ),
        _filas_inc(),
        "Representación Gráfica Dian",
        NIT_RODDOS,
    )
    # emitida → la contraparte es el adquiriente (natural)
    assert f.tipo == "emitida"
    assert f.tipo_contribuyente_contraparte == "persona_natural"


def test_contribuyente_juridica_se_reconoce():
    f = factura_desde_documento(
        _texto("FACTURA ELECTRÓNICA DE VENTA"),  # ambos jurídica por defecto
        _filas_inc(),
        "Representación Gráfica Dian",
        NIT_RODDOS,
    )
    assert f.tipo_contribuyente_contraparte == "persona_juridica"


def test_contribuyente_ausente_es_none():
    # texto sin la línea de Tipo de Contribuyente en el bloque del emisor
    texto = (
        "FACTURA ELECTRÓNICA DE VENTA\n"
        "Representación Gráfica Dian\n"
        "CUFE : abcdef0123456789abcdef0123456789abcdef01\n"
        "Número de Factura: UI90-1\n"
        "Fecha de Emisión: 28/05/2026\n"
        "Datos del Emisor / Vendedor\n"
        "Nit del Emisor: 890900608\n"
        "Razón Social: PROVEEDOR\n"
        "Datos del Adquiriente / Comprador\n"
        f"Número Documento: {NIT_RODDOS}\n"
    )
    f = factura_desde_documento(
        texto, _filas_inc(), "Representación Gráfica Dian", NIT_RODDOS
    )
    assert f.tipo_contribuyente_contraparte is None


# ── A5 (OBLIGATORIO): con INC>0 se toma el IVA, NO Total impuesto ──
def test_a5_toma_iva_no_total_impuesto():
    f = factura_desde_documento(
        _texto("FACTURA ELECTRÓNICA DE VENTA"),
        _filas_inc(),
        "Representación Gráfica Dian",
        NIT_RODDOS,
    )
    assert f.iva == Decimal("190.00")  # el campo IVA
    assert f.inc == Decimal("100.00")
    assert f.total_impuesto == Decimal("290.00")  # IVA+INC — NO es el IVA
    assert f.iva != f.total_impuesto


# ── A6: coherencia base + impuestos == total ──
def test_a6_coherente_true():
    f = factura_desde_documento(
        _texto("FACTURA ELECTRÓNICA DE VENTA"),
        _filas_inc(),
        "Representación Gráfica Dian",
        NIT_RODDOS,
    )
    # 1.000 + 190 + 100 + 0 + 0 == 1.290
    assert f.coherente() is True


def test_a6_incoherente_false():
    filas = _filas_inc()
    filas[-2] = _fila("Total", "factura", "9.999,00")  # total inconsistente
    f = factura_desde_documento(
        _texto("FACTURA ELECTRÓNICA DE VENTA"),
        filas,
        "Representación Gráfica Dian",
        NIT_RODDOS,
    )
    assert f.coherente() is False


# ── A7: PDF que no es representación DIAN ──
def test_a7_no_dian_se_rechaza():
    assert es_documento_dian("factura de otro sistema", None) is False
    with pytest.raises(DocumentoNoDian):
        factura_desde_documento(
            "un PDF cualquiera sin marcadores", [], None, NIT_RODDOS
        )


# ── A1: caso de oro sobre el PDF real. Es TAMBIÉN el candado del pin de versión:
# el extractor se validó en pdfplumber 0.11.9 (el repo AHORA pinea esa misma versión,
# tras subir de 0.11.4 para cerrar los CVE de pdfminer.six PYSEC-2026-1761/1762); la
# extracción por POSICIÓN puede variar entre versiones, y este es el único test que lo
# atraparía. Si falla por versión, es un HALLAZGO (no se ajusta el valor esperado). ──
_FIXTURE = (
    Path(__file__).parent / "fixtures" / "dian_factura_venta_exito_2026-05-28.pdf"
)


@pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="A1: falta el PDF de muestra — dejar en backend/tests/fixtures/",
)
def test_a1_pdf_de_muestra():
    from app.iva.liquidacion import cuatrimestre_de

    f = extraer(_FIXTURE, nit_propio=NIT_RODDOS)
    assert f.iva == Decimal("1452.94")
    assert f.base_gravable == Decimal("31447.06")
    assert f.total_factura == Decimal("32900.00")
    assert f.tipo == "recibida"
    # contraparte (emisor Éxito) = persona jurídica → NO es PII (Ley 1581)
    assert f.tipo_contribuyente_contraparte == "persona_juridica"
    assert f.coherente() is True
    # cuatrimestre may–ago = C2 (28-may-2026)
    assert cuatrimestre_de(f.fecha.isoformat()) == (2026, 2)
