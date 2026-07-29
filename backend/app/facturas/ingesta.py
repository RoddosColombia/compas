# backend/app/facturas/ingesta.py
"""Ingesta por documento (E2 §3.3) — el motor de POST /api/v1/facturas/cargar.

Recibe un lote de PDFs (Representación Gráfica DIAN), extrae cada uno FUERA del
event loop (pdfplumber es CPU-bound; dentro de un handler async congelaría el
servidor — criterio A16) y devuelve resultado POR ARCHIVO con estados distinguibles:

  creada | duplicada | rechazada_no_dian | rechazada_tipo_no_soportado |
  requiere_confirmacion | error

`rechazada_tipo_no_soportado` va aparte de los otros rechazos porque alimenta el
contador visible del §2 bis (radar de notas crédito recibidas). `error` (fallo
interno inesperado) existe por el requisito de resultado PARCIAL: si el archivo 7
de 20 falla, los otros 19 se procesan. `requiere_confirmacion` NO persiste nada:
devuelve lo extraído para la pantalla de confirmación (no hay documentos fiscales
a medio registrar).

Dedup por CUFE: pre-check aquí (legible, no atómico) + índice único `cufe_unico`
(la garantía dura, creado por la migración 20260728_e2_facturas_iva). Mapeo de
vocabulario: FacturaDian 'emitida'→venta / 'recibida'→compra, y ⚠ FacturaDian.inc
→ Factura.inc_valor (rename anti-shadow de de36c63): un desajuste ahí guardaría un
cero en silencio — hay candado en tests.

Los NIT (RODDOS/Auteco) vienen de Configuracion, jamás hardcodeados. Sin
NIT_RODDOS no se puede deducir el tipo → `ConfigFaltanteError` (409 accionable).
"""

import hashlib
import logging
import os
from enum import StrEnum
from io import BytesIO

import pdfplumber
from anyio import to_thread
from fastapi import UploadFile
from pymongo.errors import DuplicateKeyError

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.core.money import money_str
from app.domain.configuracion import ClaveConfig, Configuracion
from app.domain.factura import Factura, OrigenFactura, TipoFactura
from app.facturas.extraccion import (
    DocumentoNoDian,
    FacturaDian,
    TipoNoSoportado,
    factura_desde_documento,
    filas_por_posicion,
)

logger = logging.getLogger(__name__)

MAX_ARCHIVOS_LOTE = 20  # coherente con POST /api/v1/cargas (F-22)
MAX_BYTES_ARCHIVO = 10 * 1024 * 1024


class ConfigFaltanteError(Exception):
    """Falta una clave de Configuracion indispensable (el router responde 409)."""


class EstadoIngesta(StrEnum):
    creada = "creada"
    duplicada = "duplicada"
    rechazada_no_dian = "rechazada_no_dian"
    rechazada_tipo_no_soportado = "rechazada_tipo_no_soportado"  # radar §2 bis
    requiere_confirmacion = "requiere_confirmacion"
    error = "error"  # interno inesperado; el resto del lote sigue (parcial)


_PLURAL = {
    EstadoIngesta.creada: "creadas",
    EstadoIngesta.duplicada: "duplicadas",
    EstadoIngesta.rechazada_no_dian: "rechazadas_no_dian",
    EstadoIngesta.rechazada_tipo_no_soportado: "rechazadas_tipo_no_soportado",
    EstadoIngesta.requiere_confirmacion: "requieren_confirmacion",
    EstadoIngesta.error: "errores",
}


async def _nit_config(clave: ClaveConfig) -> str | None:
    """Última vigencia de una clave NIT_* ({"nit": "..."}). Ausente → None."""
    cfg = (
        await Configuracion.find(Configuracion.clave == clave)
        .sort(-Configuracion.vigente_desde)
        .limit(1)
        .to_list()
    )
    if cfg and cfg[0].valor_json:
        nit = cfg[0].valor_json.get("nit")
        return str(nit) if nit else None
    return None


def _extraer_bytes(contenido: bytes, nombre: str, nit_propio: str) -> FacturaDian:
    """SÍNCRONA y CPU-bound: llamar SIEMPRE vía `anyio.to_thread` (A16).

    Paralela a `extraccion.extraer()` (que recibe ruta) pero sobre bytes: evita el
    temp file y conserva el NOMBRE ORIGINAL en los motivos de rechazo (el temp
    tendría un nombre aleatorio inservible para el operador). La lógica de negocio
    sigue viviendo en `factura_desde_documento` (orden M-1 intacto)."""
    with pdfplumber.open(BytesIO(contenido)) as pdf:
        titulo_pdf = (pdf.metadata or {}).get("Title")
        texto = "\n".join((p.extract_text() or "") for p in pdf.pages)
        filas = [f for pagina in pdf.pages for f in filas_por_posicion(pagina)]
    return factura_desde_documento(texto, filas, titulo_pdf, nit_propio, nombre)


def campos_desde_dian(f: FacturaDian, *, nit_auteco: str | None) -> dict:
    """Costura PURA (testeable sin PDF): FacturaDian → campos del Document Factura.

    ⚠ `FacturaDian.inc` → `Factura.inc_valor` (rename anti-shadow): NO "corregir"
    a `inc` — pisaría un atributo de beanie.Document. Candado en tests.
    `tarifa_iva=None`: una factura DIAN puede mezclar tarifas (trampa 4 del §2) y
    derivar la tarifa desde iva/base mete redondeos en un dato fiscal (§3.2); el
    `iva_valor` extraído manda (D-13). `deducible=False`: la decisión es explícita
    del operador (contador de "recibidas sin marcar deducible" en el listado)."""
    if f.tipo == "recibida":
        tercero_nit, tercero_nombre = f.nit_emisor, f.nombre_emisor
        tipo = TipoFactura.compra
        es_auteco = nit_auteco is not None and f.nit_emisor == nit_auteco
        origen = OrigenFactura.auteco if es_auteco else OrigenFactura.sin_clasificar
    else:  # emitida
        tercero_nit, tercero_nombre = f.nit_adquiriente, ""
        tipo = TipoFactura.venta
        origen = OrigenFactura.sin_clasificar
    if not tercero_nombre:
        # el extractor no captura el nombre del adquiriente: se etiqueta con el
        # NIT real (R5: no se inventa); la pantalla de confirmación lo corrige
        tercero_nombre = f"NIT {tercero_nit}"
    return {
        "tipo": tipo,
        "origen": origen,
        "numero": f.numero,
        "tercero_nombre": tercero_nombre,
        "tercero_nit": tercero_nit,
        "fecha": f.fecha.isoformat(),
        "base_gravable": f.base_gravable,
        "tarifa_iva": None,
        "iva_valor": f.iva,
        "total": f.total_factura,
        "deducible": False,
        "cufe": f.cufe,
        "tipo_documento": f.tipo_documento,
        "signo": 1,
        "inc_valor": f.inc,  # ← el rename anti-shadow
        "bolsas": f.bolsas,
        "otros_impuestos": f.otros_impuestos,
        "rete_fuente": f.rete_fuente,
        "rete_iva": f.rete_iva,
        "rete_ica": f.rete_ica,
    }


def _datos_extraidos(f: FacturaDian, campos: dict) -> dict:
    """Lo extraído, montos como STRING (regla 1). Viaja al cliente (pantalla de
    confirmación / resultado por archivo); no persiste nada por sí mismo."""
    return {
        "tipo_documento": f.tipo_documento,
        "cufe": f.cufe,
        "numero": f.numero,
        "fecha": campos["fecha"],
        "tipo": campos["tipo"].value,
        "origen": campos["origen"].value,
        "tercero_nit": campos["tercero_nit"],
        "tercero_nombre": campos["tercero_nombre"],
        "base_gravable": money_str(f.base_gravable),
        "iva_valor": money_str(f.iva),
        "inc_valor": money_str(f.inc),
        "bolsas": money_str(f.bolsas),
        "otros_impuestos": money_str(f.otros_impuestos),
        "total_impuesto": money_str(f.total_impuesto),
        "total_factura": money_str(f.total_factura),
        "rete_fuente": money_str(f.rete_fuente),
        "rete_iva": money_str(f.rete_iva),
        "rete_ica": money_str(f.rete_ica),
        "coherente": f.coherente(),
    }


def _resultado(
    archivo: str,
    estado: EstadoIngesta,
    *,
    motivo: str | None = None,
    factura_id: str | None = None,
    datos: dict | None = None,
) -> dict:
    return {
        "archivo": archivo,
        "estado": estado.value,
        "motivo": motivo,
        "factura_id": factura_id,
        "datos_extraidos": datos,
    }


async def _procesar_archivo(
    archivo: UploadFile,
    *,
    nit_propio: str,
    nit_auteco: str | None,
    usuario_id: str,
) -> dict:
    nombre = archivo.filename or "documento.pdf"

    ext = os.path.splitext(nombre)[1].lower()
    if ext != ".pdf":
        return _resultado(
            nombre,
            EstadoIngesta.rechazada_no_dian,
            motivo=f"extensión '{ext}' no soportada; la Representación Gráfica "
            "DIAN es un .pdf",
        )
    contenido = await archivo.read(MAX_BYTES_ARCHIVO + 1)
    if len(contenido) > MAX_BYTES_ARCHIVO:
        return _resultado(
            nombre,
            EstadoIngesta.rechazada_no_dian,
            motivo="supera el límite de 10 MB por archivo",
        )

    try:
        dian = await to_thread.run_sync(
            _extraer_bytes, contenido, nombre, nit_propio
        )
    except TipoNoSoportado as e:
        return _resultado(
            nombre, EstadoIngesta.rechazada_tipo_no_soportado, motivo=str(e)
        )
    except DocumentoNoDian as e:
        return _resultado(nombre, EstadoIngesta.rechazada_no_dian, motivo=str(e))

    campos = campos_desde_dian(dian, nit_auteco=nit_auteco)
    datos = _datos_extraidos(dian, campos)

    if not dian.coherente():  # A6: no se guarda, pide revisión
        return _resultado(
            nombre,
            EstadoIngesta.requiere_confirmacion,
            motivo="base + impuestos no cuadra con el total de la factura; "
            "revisar los valores extraídos y confirmar",
            datos=datos,
        )

    # Pre-check de CUFE (legible, NO atómico); la garantía dura es el índice
    # único cufe_unico + el DuplicateKeyError de abajo.
    if await Factura.find_one(Factura.cufe == dian.cufe) is not None:
        return _resultado(
            nombre,
            EstadoIngesta.duplicada,
            motivo="ya existe una factura con este CUFE",
            datos=datos,
        )

    factura = Factura(
        **campos,
        archivo_ref=f"sha256:{hashlib.sha256(contenido).hexdigest()}",
    )
    try:
        await factura.insert()
    except DuplicateKeyError:
        # carrera del pre-check (cufe_unico) o carga manual previa con el mismo
        # par NIT+número (nit_numero_unico): en ambos casos ya está registrada
        return _resultado(
            nombre,
            EstadoIngesta.duplicada,
            motivo="ya existe una factura con este CUFE o con el mismo "
            "número para este NIT",
            datos=datos,
        )
    try:
        await emit_audit(
            AuditEvento.factura_creada,
            entidad="factura",
            entidad_id=str(factura.id),
            actor_id=usuario_id,
            # sin nombre de archivo ni NIT/nombre del tercero: puede ser cédula/
            # persona natural (PII, Ley 1581 / A17). CUFE+número identifican.
            metadata={
                "via": "ingesta_dian",
                "numero": factura.numero,
                "cufe": factura.cufe,
                "tipo": factura.tipo.value,
                "origen": factura.origen.value,
                "iva_valor": money_str(factura.iva_valor),
            },
        )
    except Exception:
        await factura.delete()  # saga O1: sin rastro de auditoría no hay alta
        raise
    return _resultado(
        nombre, EstadoIngesta.creada, factura_id=str(factura.id), datos=datos
    )


async def procesar_lote(archivos: list[UploadFile], *, usuario_id: str) -> dict:
    """Procesa el lote archivo por archivo (resultado PARCIAL: una excepción en
    uno no frena a los demás) y devuelve {resultados: [...], resumen: {...}}."""
    nit_propio = await _nit_config(ClaveConfig.NIT_RODDOS)
    if not nit_propio:
        raise ConfigFaltanteError(
            "NIT_RODDOS no está en Configuracion: sin él no se puede deducir si "
            "una factura es emitida o recibida. Corra la migración "
            "20260728_e2_facturas_iva."
        )
    nit_auteco = await _nit_config(ClaveConfig.NIT_AUTECO)

    resultados: list[dict] = []
    for i, archivo in enumerate(archivos):
        nombre = archivo.filename or "documento.pdf"
        try:
            resultados.append(
                await _procesar_archivo(
                    archivo,
                    nit_propio=nit_propio,
                    nit_auteco=nit_auteco,
                    usuario_id=usuario_id,
                )
            )
        except Exception:
            # sin nombre de archivo en el log (puede llevar PII, A17)
            logger.exception("ingesta: error procesando el archivo %d del lote", i)
            resultados.append(
                _resultado(
                    nombre,
                    EstadoIngesta.error,
                    motivo="error interno procesando el archivo; los demás "
                    "archivos del lote no se afectaron",
                )
            )

    resumen = {plural: 0 for plural in _PLURAL.values()}
    for r in resultados:
        resumen[_PLURAL[EstadoIngesta(r["estado"])]] += 1
    return {"resultados": resultados, "resumen": resumen}
