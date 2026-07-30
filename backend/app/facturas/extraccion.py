# backend/app/facturas/extraccion.py
"""Extractor de la Representación Gráfica DIAN (PDF) → datos de factura para el módulo
de IVA (E2). PORTADO de docs/extraer_iva_dian.py (extractor de referencia probado contra
un PDF real y corregido por el hallazgo M-1). NO reescribir la lógica; NO reordenar la
detección de tipo (ver bloque M-1).

Trampas reales resueltas (comentadas en el original):
 1. NO regex por línea: el layout de dos columnas intercala una barra lateral y duplica
    etiquetas ("IVA IVA 1.452,94"). Se lee por POSICIÓN (x/y), tomando el último número
    de la fila.
 2. Tomar el campo "IVA", NO "Total impuesto" (este suma IVA+INC+bolsas). Sin un
    caso con INC>0 el bug queda escondido → test A5.
 3. Formato COP (miles ".", decimales ",") → Decimal, jamás float (R1).
 4. Una factura puede mezclar tarifas: el valor válido es el del bloque de totales.

Desviación del port (documentada): se separó una costura pura
`factura_desde_documento(texto, filas, titulo_pdf, nit_propio)` para que A1/A5 se
prueben con estructuras sintéticas sin shippear PDFs reales al repo. El orden de
detección de tipo (M-1) queda intacto. `extraer(ruta)` hace solo el I/O de pdfplumber y
delega en la costura. Vocabulario: este extractor produce tipo 'emitida'|'recibida'; el
dominio `Factura` usa 'venta'|'compra' → la ingesta mapea emitida→venta,
recibida→compra.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pdfplumber

_NUMERO_COP = re.compile(r"[\d.]+,\d{2}")

TIPO_SOPORTADO = "FACTURA ELECTRÓNICA DE VENTA"
_TITULO_SOPORTADO = "FACTURA ELECTRONICA DE VENTA"  # normalizado, sin acentos

# ⚠ HALLAZGO M-1 (auditoría externa) — leer antes de tocar este bloque.
# El nombre oficial DIAN de la nota crédito (cód. 91) es
#     "Nota Crédito de Factura Electrónica de Venta"
# y CONTIENE "FACTURA ELECTRÓNICA DE VENTA". Si se evalúa primero el tipo soportado, una
# nota crédito entra como factura de venta: una NC RECIBIDA inflaría el descontable
# → RODDOS pagaría menos IVA del debido → riesgo directo con la DIAN.
# Dos salvaguardas, y EL ORDEN IMPORTA:
#   (a) los marcadores NO soportados se evalúan PRIMERO, sobre el encabezado completo;
#   (b) el tipo soportado exige que el TÍTULO (primera línea no vacía) EMPIECE por él.
MARCADORES_NO_SOPORTADOS = (
    "NOTA CREDITO",
    "NOTA DEBITO",
    "NOTA DE AJUSTE",
    "DOCUMENTO SOPORTE",
    "DOCUMENTO EQUIVALENTE",
)

_LINEAS_ENCABEZADO = 6

# Bloques de la Representación Gráfica (verificado en el PDF real): el Tipo de
# Contribuyente aparece DOS veces (emisor y adquiriente), con el mismo rótulo. Se
# aísla por sección para leer el de la CONTRAPARTE correcta (GO CEO punto 1).
_SEC_EMISOR = "Datos del Emisor"
_SEC_ADQUIRIENTE = "Datos del Adquiriente"
_RE_CONTRIB = re.compile(
    r"Tipo de Contribuyente:\s*(Persona\s+(?:Jur[ií]dica|Natural))", re.IGNORECASE
)
# Valores canónicos del tipo de contribuyente (persona natural = PII, Ley 1581).
PERSONA_JURIDICA = "persona_juridica"
PERSONA_NATURAL = "persona_natural"

# Fixtures de título para el test A8 (títulos OFICIALES DIAN, no simplificados).
TITULOS_A8 = (
    "Nota Crédito de Factura Electrónica de Venta",
    "Nota Débito de Factura Electrónica de Venta",
    "Documento Soporte en Adquisiciones Efectuadas a No Obligados a Facturar",
    "Nota de Ajuste al Documento Soporte",
)


class DocumentoNoDian(Exception):
    """El PDF no es una Representación Gráfica de la DIAN: no se parsea."""


class TipoNoSoportado(Exception):
    """Documento DIAN válido, pero de un tipo que E2 no procesa (queda para E2.1)."""


def _sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").upper()


def _a_decimal(texto: str) -> Decimal:
    """'1.452,94' -> Decimal('1452.94')."""
    return Decimal(texto.replace(".", "").replace(",", "."))


@dataclass(frozen=True)
class FacturaDian:
    tipo_documento: str
    cufe: str
    numero: str
    fecha: date
    nit_emisor: str
    nombre_emisor: str
    nit_adquiriente: str
    tipo: str  # "emitida" | "recibida" (la ingesta mapea a venta|compra)
    tipo_contribuyente_contraparte: str | None  # persona_juridica|persona_natural|None
    base_gravable: Decimal
    iva: Decimal
    inc: Decimal
    bolsas: Decimal
    otros_impuestos: Decimal
    total_impuesto: Decimal
    total_factura: Decimal
    rete_fuente: Decimal
    rete_iva: Decimal
    rete_ica: Decimal

    def coherente(self) -> bool:
        """base + IVA + INC + bolsas + otros == total factura (chequeo duro, A6)."""
        suma = (
            self.base_gravable
            + self.iva
            + self.inc
            + self.bolsas
            + self.otros_impuestos
        )
        return suma == self.total_factura


def es_documento_dian(texto: str, titulo_pdf: str | None) -> bool:
    return (
        "Representación Gráfica" in texto
        and "CUFE" in texto
        and ("Dian" in (titulo_pdf or "") or "DIAN" in texto)
    )


def tipo_documento(texto: str) -> str:
    """Tipo soportado o `TipoNoSoportado`. Orden deliberado (M-1): NO soportados primero
    sobre el encabezado; luego el título soportado anclado al inicio."""
    lineas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
    titulo = _sin_acentos(lineas[0]) if lineas else ""
    encabezado = _sin_acentos(" | ".join(lineas[:_LINEAS_ENCABEZADO]))

    for marcador in MARCADORES_NO_SOPORTADOS:
        if marcador in encabezado:
            raise TipoNoSoportado(
                f"{marcador}: tipo no procesado en E2 (queda para E2.1). "
                f"El documento NO entra a la liquidación. Título leído: {titulo!r}"
            )

    if titulo.startswith(_TITULO_SOPORTADO):
        return TIPO_SOPORTADO

    raise TipoNoSoportado(f"tipo de documento no reconocido. Título leído: {titulo!r}")


def filas_por_posicion(pagina) -> list[list[dict]]:
    """Agrupa las palabras de la página en filas por su coordenada vertical."""
    filas: dict[int, list[dict]] = {}
    for palabra in pagina.extract_words():
        filas.setdefault(round(palabra["top"] / 3), []).append(palabra)
    return [sorted(ws, key=lambda w: w["x0"]) for _, ws in sorted(filas.items())]


def _valor_de(filas: list[list[dict]], etiqueta: str) -> Decimal | None:
    """Último número COP de la fila que contiene la etiqueta (columna derecha)."""
    for palabras in filas:
        texto = " ".join(w["text"] for w in palabras)
        if etiqueta in texto:
            numeros = [w["text"] for w in palabras if _NUMERO_COP.fullmatch(w["text"])]
            if numeros:
                return _a_decimal(numeros[-1])
    return None


def _seccion(texto: str, inicio: str, fin: str | None) -> str:
    """Rebana el texto desde el marcador `inicio` hasta `fin` (o el final)."""
    a = texto.find(inicio)
    if a < 0:
        return ""
    b = texto.find(fin, a + len(inicio)) if fin else -1
    return texto[a:] if b < 0 else texto[a:b]


def tipo_contribuyente_contraparte(texto: str, tipo: str) -> str | None:
    """Tipo de contribuyente de la CONTRAPARTE (emisor si la factura es recibida,
    adquiriente si es emitida). Se lee dentro de la sección correcta para no leer el
    de RODDOS. Ausente/ilegible → None (R5: no se inventa; la ingesta lo trata como
    PII por precaución)."""
    if tipo == "recibida":
        seccion = _seccion(texto, _SEC_EMISOR, _SEC_ADQUIRIENTE)
    else:  # emitida → la contraparte es el adquiriente
        seccion = _seccion(texto, _SEC_ADQUIRIENTE, None)
    m = _RE_CONTRIB.search(seccion)
    if not m:
        return None
    valor = _sin_acentos(m.group(1))  # "PERSONA JURIDICA" | "PERSONA NATURAL"
    if "JURIDICA" in valor:
        return PERSONA_JURIDICA
    if "NATURAL" in valor:
        return PERSONA_NATURAL
    return None


def factura_desde_documento(
    texto: str,
    filas: list[list[dict]],
    titulo_pdf: str | None,
    nit_propio: str,
    nombre: str = "documento",
) -> FacturaDian:
    """Costura pura (testeable sin PDF): valida DIAN → tipo → extrae campos por
    posición. `extraer()` la alimenta con lo leído del PDF."""
    if not es_documento_dian(texto, titulo_pdf):
        raise DocumentoNoDian(f"{nombre}: no parece Representación Gráfica DIAN")

    tipo_doc = tipo_documento(texto)  # lanza TipoNoSoportado si aplica (orden M-1)

    def campo(patron: str) -> str | None:
        m = re.search(patron, texto)
        return m.group(1).strip() if m else None

    cufe = campo(r"CUFE\s*:\s*\n?([0-9a-fA-F]{40,})")
    numero = campo(r"Número de Factura:\s*(\S+)")
    fecha_txt = campo(r"Fecha de Emisión:\s*(\d{2}/\d{2}/\d{4})")
    nit_emisor = campo(r"Nit del Emisor:\s*(\d+)")
    nombre_emisor = campo(r"Razón Social:\s*(.+)")
    nit_adquiriente = campo(r"Número Documento:\s*(\d+)")

    faltantes = [
        n
        for n, val in {
            "CUFE": cufe,
            "número": numero,
            "fecha": fecha_txt,
            "NIT emisor": nit_emisor,
            "NIT adquiriente": nit_adquiriente,
        }.items()
        if not val
    ]
    if faltantes:
        raise DocumentoNoDian(f"{nombre}: no se pudo leer {', '.join(faltantes)}")

    dd, mm, aaaa = fecha_txt.split("/")

    if nit_emisor == nit_propio:
        tipo = "emitida"
    elif nit_adquiriente == nit_propio:
        tipo = "recibida"
    else:
        raise DocumentoNoDian(
            f"{nombre}: ni el emisor ({nit_emisor}) ni el adquiriente "
            f"({nit_adquiriente}) es {nit_propio} — documento ajeno"
        )

    cero = Decimal("0.00")

    def v(etiqueta: str) -> Decimal:
        return _valor_de(filas, etiqueta) or cero

    return FacturaDian(
        tipo_documento=tipo_doc,
        cufe=cufe,
        numero=numero,
        fecha=date(int(aaaa), int(mm), int(dd)),
        nit_emisor=nit_emisor,
        nombre_emisor=nombre_emisor or "",
        nit_adquiriente=nit_adquiriente,
        tipo=tipo,
        tipo_contribuyente_contraparte=tipo_contribuyente_contraparte(texto, tipo),
        base_gravable=v("Total Bruto Factura"),
        iva=v("IVA"),  # el campo "IVA", NO "Total impuesto" (trampa 2)
        inc=v("INC"),
        bolsas=v("Bolsas"),
        otros_impuestos=v("Otros impuestos"),
        total_impuesto=v("Total impuesto"),
        total_factura=v("Total factura"),
        rete_fuente=v("Rete fuente"),
        rete_iva=v("Rete IVA"),
        rete_ica=v("Rete ICA"),
    )


def extraer(ruta: str | Path, nit_propio: str) -> FacturaDian:
    """Lee el PDF (I/O) y delega en `factura_desde_documento`. `nit_propio` viene de
    Configuracion (NIT de RODDOS), NUNCA hardcodeado.

    ⚠ `pdfplumber` es CPU-bound y bloqueante: en FastAPI ejecutar en threadpool
    (`anyio.to_thread`) y aplicar tope de archivos por lote (§3.3)."""
    ruta = Path(ruta)
    with pdfplumber.open(ruta) as pdf:
        titulo_pdf = (pdf.metadata or {}).get("Title")
        texto = "\n".join((p.extract_text() or "") for p in pdf.pages)
        filas = [f for pagina in pdf.pages for f in filas_por_posicion(pagina)]
    return factura_desde_documento(texto, filas, titulo_pdf, nit_propio, ruta.name)
