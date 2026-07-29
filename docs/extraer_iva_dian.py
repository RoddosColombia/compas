"""
Extractor de referencia — Representación Gráfica DIAN (PDF) → datos de factura para el módulo de IVA de COMPAS.

VERIFICADO contra un documento real: "ALMACENES ÉXITO S.A mayo 28.pdf" (Carulla → RODDOS, 28/05/2026).
Resultado de esa corrida:
    tipo_documento=FACTURA ELECTRÓNICA DE VENTA, cufe=fabdb194...c01be1..., numero=UI90-16716,
    fecha=2026-05-28, nit_emisor=890900608, nit_adquiriente=901012622, tipo=recibida,
    base=31447.06, iva=1452.94, inc=0.00, total=32900.00,
    rete_fuente=0.00, rete_iva=0.00, rete_ica=0.00
    coherencia base+iva+inc+bolsas+otros == total  ->  OK

POR QUÉ ASÍ (trampas reales encontradas, no teóricas):

 1. NO usar regex por línea. El layout de dos columnas de la DIAN intercala una barra
    lateral ("Documento generado el:", "PDF Generado por:") DENTRO de las filas de
    totales, y además duplica las etiquetas ("IVA IVA 1.452,94"). Un `^IVA\\s+(...)$`
    encuentra unos campos y falla en otros (falló con INC y Total factura).
    Se resuelve leyendo por POSICIÓN de palabra (x/y) y tomando el último número de la fila.

 2. Tomar el campo "IVA", NO "Total impuesto". "Total impuesto" suma IVA + INC + bolsas.
    En el documento de muestra coinciden porque INC = 0, así que el error quedaría
    ESCONDIDO. Hace falta un caso de prueba con INC > 0 o con impuesto de bolsas.

 3. Formato COP: miles con "." y decimales con ",". Parseo a Decimal, jamás float (regla 1).

 4. Una misma factura puede mezclar tarifas (en el documento de muestra, dos líneas sin
    IVA y una al 19 %). Por eso el valor válido es el del bloque de totales, no el de las líneas.

 5. Rechazar lo que no sea representación DIAN antes de parsear (es_documento_dian):
    un PDF de otro proveedor con otro layout se parsearía mal en silencio.

 6. TIPO DE DOCUMENTO — ver el bloque M-1 más abajo. Las notas crédito, notas débito,
    notas de ajuste, documentos soporte y equivalentes NO se procesan en E2 (decisión
    D-16: RODDOS no ha emitido ninguna nota crédito) y deben RECHAZARSE CON MOTIVO
    EXPLÍCITO, nunca ingresarse como factura. Ojo: una nota crédito RECIBIDA de un
    proveedor sí puede aparecer y bajaría el IVA descontable.

Requisitos: pdfplumber
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import pdfplumber

# NIT de RODDOS S.A.S. — debe vivir en configuración, no aquí.
NIT_RODDOS = "901012622"

_NUMERO_COP = re.compile(r"[\d.]+,\d{2}")

TIPO_SOPORTADO = "FACTURA ELECTRÓNICA DE VENTA"
_TITULO_SOPORTADO = "FACTURA ELECTRONICA DE VENTA"  # normalizado, sin acentos

# ⚠ HALLAZGO M-1 (auditoría externa, 2026-07-28) — leer antes de tocar este bloque.
#
# El nombre oficial DIAN de la nota crédito (código 91) es
#     "Nota Crédito de Factura Electrónica de Venta"
# y CONTIENE la subcadena "FACTURA ELECTRÓNICA DE VENTA". La versión anterior de este
# módulo evaluaba primero el tipo soportado, así que **una nota crédito entraba como
# factura de venta**: exactamente lo que el docstring jura impedir.
#
# Consecuencia si se ignora: una NC RECIBIDA infla el IVA descontable → RODDOS pagaría
# menos IVA del que debe → riesgo directo con la DIAN.
#
# Dos salvaguardas, y el orden importa:
#   (a) los marcadores NO soportados se evalúan PRIMERO, sobre el encabezado completo;
#   (b) el tipo soportado exige que el TÍTULO (primera línea no vacía) EMPIECE por él,
#       no que la cadena aparezca en cualquier parte del documento.
MARCADORES_NO_SOPORTADOS = (
    "NOTA CREDITO",
    "NOTA DEBITO",
    "NOTA DE AJUSTE",
    "DOCUMENTO SOPORTE",
    "DOCUMENTO EQUIVALENTE",
)

_LINEAS_ENCABEZADO = 6


class DocumentoNoDian(Exception):
    """El PDF no es una Representación Gráfica de la DIAN: no se parsea."""


class TipoNoSoportado(Exception):
    """Es un documento DIAN válido, pero de un tipo que E2 no procesa (queda para E2.1)."""


def _sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").upper()


def _a_decimal(texto: str) -> Decimal:
    """'1.452,94' -> Decimal('1452.94')."""
    return Decimal(texto.replace(".", "").replace(",", "."))


@dataclass
class FacturaDian:
    tipo_documento: str
    cufe: str
    numero: str
    fecha: date
    nit_emisor: str
    nombre_emisor: str
    nit_adquiriente: str
    tipo: str  # "emitida" | "recibida"
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
        """Chequeo duro: base + IVA + INC + bolsas + otros == total factura."""
        suma = self.base_gravable + self.iva + self.inc + self.bolsas + self.otros_impuestos
        return suma == self.total_factura


def es_documento_dian(texto: str, titulo_pdf: str | None) -> bool:
    return (
        "Representación Gráfica" in texto
        and "CUFE" in texto
        and ("Dian" in (titulo_pdf or "") or "DIAN" in texto)
    )


def tipo_documento(texto: str) -> str:
    """
    Devuelve el tipo de documento si es soportado; lanza TipoNoSoportado si no.

    Orden deliberado (M-1): primero los marcadores no soportados sobre el encabezado,
    después el título soportado anclado al inicio de la primera línea.
    """
    lineas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
    titulo = _sin_acentos(lineas[0]) if lineas else ""
    encabezado = _sin_acentos(" | ".join(lineas[:_LINEAS_ENCABEZADO]))

    # (a) NO soportados primero — una NC oficial contiene la cadena de factura.
    for marcador in MARCADORES_NO_SOPORTADOS:
        if marcador in encabezado:
            raise TipoNoSoportado(
                f"{marcador}: tipo no procesado en E2 (queda para E2.1). "
                f"El documento NO entra a la liquidación. Título leído: {titulo!r}"
            )

    # (b) Soportado, anclado al inicio del título.
    if titulo.startswith(_TITULO_SOPORTADO):
        return TIPO_SOPORTADO

    raise TipoNoSoportado(f"tipo de documento no reconocido. Título leído: {titulo!r}")


def _filas_por_posicion(pagina) -> list[list[dict]]:
    """Agrupa las palabras de la página en filas usando su coordenada vertical."""
    filas: dict[int, list[dict]] = {}
    for palabra in pagina.extract_words():
        filas.setdefault(round(palabra["top"] / 3), []).append(palabra)
    return [sorted(ws, key=lambda w: w["x0"]) for _, ws in sorted(filas.items())]


def _valor_de(filas: list[list[dict]], etiqueta: str) -> Decimal | None:
    """Último número COP de la fila que contiene la etiqueta (columna derecha del layout)."""
    for palabras in filas:
        texto = " ".join(w["text"] for w in palabras)
        if etiqueta in texto:
            numeros = [w["text"] for w in palabras if _NUMERO_COP.fullmatch(w["text"])]
            if numeros:
                return _a_decimal(numeros[-1])
    return None


def extraer(ruta: str | Path, nit_propio: str = NIT_RODDOS) -> FacturaDian:
    """
    NOTA DE INTEGRACIÓN (hallazgo bajo de la auditoría): `pdfplumber` es CPU-bound y
    bloqueante. En FastAPI, invocar esto dentro de un handler `async` congelaría el event
    loop con cada carga. Ejecutar en threadpool (`run_in_executor` / `anyio.to_thread`)
    y aplicar tope de archivos por lote.
    """
    ruta = Path(ruta)
    with pdfplumber.open(ruta) as pdf:
        titulo_pdf = (pdf.metadata or {}).get("Title")
        texto = "\n".join((p.extract_text() or "") for p in pdf.pages)
        filas = [f for pagina in pdf.pages for f in _filas_por_posicion(pagina)]

    if not es_documento_dian(texto, titulo_pdf):
        raise DocumentoNoDian(f"{ruta.name}: no parece Representación Gráfica DIAN")

    tipo_doc = tipo_documento(texto)  # lanza TipoNoSoportado si aplica

    def campo(patron: str) -> str | None:
        m = re.search(patron, texto)
        return m.group(1).strip() if m else None

    cufe = campo(r"CUFE\s*:\s*\n?([0-9a-fA-F]{40,})")
    numero = campo(r"Número de Factura:\s*(\S+)")
    fecha_txt = campo(r"Fecha de Emisión:\s*(\d{2}/\d{2}/\d{4})")
    nit_emisor = campo(r"Nit del Emisor:\s*(\d+)")
    nombre_emisor = campo(r"Razón Social:\s*(.+)")
    nit_adquiriente = campo(r"Número Documento:\s*(\d+)")

    faltantes = [n for n, v in {
        "CUFE": cufe, "número": numero, "fecha": fecha_txt,
        "NIT emisor": nit_emisor, "NIT adquiriente": nit_adquiriente,
    }.items() if not v]
    if faltantes:
        raise DocumentoNoDian(f"{ruta.name}: no se pudo leer {', '.join(faltantes)}")

    dd, mm, aaaa = fecha_txt.split("/")

    if nit_emisor == nit_propio:
        tipo = "emitida"
    elif nit_adquiriente == nit_propio:
        tipo = "recibida"
    else:
        raise DocumentoNoDian(
            f"{ruta.name}: ni el emisor ({nit_emisor}) ni el adquiriente "
            f"({nit_adquiriente}) es {nit_propio} — documento ajeno"
        )

    cero = Decimal("0.00")
    v = lambda etiqueta, defecto=cero: (_valor_de(filas, etiqueta) or defecto)  # noqa: E731

    return FacturaDian(
        tipo_documento=tipo_doc,
        cufe=cufe,
        numero=numero,
        fecha=date(int(aaaa), int(mm), int(dd)),
        nit_emisor=nit_emisor,
        nombre_emisor=nombre_emisor or "",
        nit_adquiriente=nit_adquiriente,
        tipo=tipo,
        base_gravable=v("Total Bruto Factura"),
        iva=v("IVA"),  # el campo "IVA", NO "Total impuesto" (ver nota 2)
        inc=v("INC"),
        bolsas=v("Bolsas"),
        otros_impuestos=v("Otros impuestos"),
        total_impuesto=v("Total impuesto"),
        total_factura=v("Total factura"),
        rete_fuente=v("Rete fuente"),
        rete_iva=v("Rete IVA"),
        rete_ica=v("Rete ICA"),
    )


# ── Período cuatrimestral: may–ago · sep–dic · ene–abr ────────────────────────
def cuatrimestre(f: date) -> str:
    if 5 <= f.month <= 8:
        return f"{f.year}-C2 (may–ago)"
    if 9 <= f.month <= 12:
        return f"{f.year}-C3 (sep–dic)"
    return f"{f.year}-C1 (ene–abr)"


# ── Fixtures de título para el test A8 (títulos OFICIALES, no simplificados) ──
TITULOS_A8 = (
    "Nota Crédito de Factura Electrónica de Venta",
    "Nota Débito de Factura Electrónica de Venta",
    "Documento Soporte en Adquisiciones Efectuadas a No Obligados a Facturar",
    "Nota de Ajuste al Documento Soporte",
)


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        try:
            f = extraer(arg)
        except TipoNoSoportado as e:
            print(f"[NO SOPORTADO] {Path(arg).name}: {e}")
            continue
        except DocumentoNoDian as e:
            print(f"[RECHAZADO] {e}")
            continue
        for clave, valor in asdict(f).items():
            print(f"  {clave:16} = {valor}")
        print(f"  {'cuatrimestre':16} = {cuatrimestre(f.fecha)}")
        print(f"  {'coherente':16} = {f.coherente()}")
        if not f.coherente():
            print("  ⚠ base + impuestos ≠ total factura — NO guardar sin revisión humana")
