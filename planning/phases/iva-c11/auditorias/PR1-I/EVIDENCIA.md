# EVIDENCIA — iva-c11 PR1-I (E2 backend)

Rama `feat/e2-facturas-iva` → `main`, PR #46. Diff real (fuente + tests) y salidas
reales de tests/migración. Sin secretos (la URI de PROD se leyó en proceso, nunca
se imprimió).

## Salidas reales

### pytest (suite completa, mongomock)
```
728 passed, 62 skipped, 3985 warnings in 478.81s (0:07:58)
```
Suites nuevas/afectadas de E2: test_extraccion_dian, test_facturas_cargar,
test_facturas_endpoints (incl. A10 §6 exacto + enmascaramiento PII),
test_factura_campos_e2, test_domain_persistence (fix semilla), test_rbac_permissions.

### ruff
```
All checks passed!
```

### motor.py — R0 (cero diffs)
```
$ git diff --stat main..HEAD -- backend/app/proyeccion/motor.py
(vacío)
```
`proyeccion/`: solo `service.py` (+24/-1 = CR-E2-COMPUERTA `_iva_plan`, compuerta apagada).

### golden master
Verde SIN regenerar (parte de los 728 passed; `git diff main..HEAD -- backend/**/golden/` vacío).

### Migración en PRODUCCIÓN (idempotencia A13)
1ª corrida:
```
[e2] facturas antes: 0
[e2] índices de facturas: ['_id_', 'cufe_unico', 'nit_numero_unico', 'por_fecha']
[e2] configuracion: 4 claves nuevas insertadas (idempotente).
[e2] facturas después: 0 (sin cambios de datos)
```
2ª corrida:
```
[e2] configuracion: 0 claves nuevas insertadas (idempotente).
[e2] índices de facturas: ['_id_', 'cufe_unico', 'nit_numero_unico', 'por_fecha']
[e2] facturas después: 0 (sin cambios de datos)
```
→ `cufe_unico` confirmado en PROD.

### Protocolo de commit (CLAUDE.md)
```
app.alegra r1: 0 · journal-entries: 0 · estado.*pending: 0
```

## Diff de fuente (backend/app + migración + pyproject)

```diff
diff --git a/backend/app/auth/permissions.py b/backend/app/auth/permissions.py
index 6dd2343..ab2b4be 100644
--- a/backend/app/auth/permissions.py
+++ b/backend/app/auth/permissions.py
@@ -34,6 +34,11 @@ PERMISSIONS: dict[str, frozenset[Role]] = {
     "proyeccion:gestionar": frozenset({Role.financiero, Role.admin}),
     # ── CR "Fidelidad de caja" (C11 IVA: carga de facturas + liquidación) ──
     "iva:gestionar": frozenset({Role.financiero, Role.admin}),
+    # ── E2 A17 (Ley 1581): PII de facturas. Detalle + archivo original solo para
+    # quien puede ver la contraparte. Permiso PROPIO (no reusar evidencia:ver).
+    # El listado se minimiza para quien NO lo tenga; /liquidacion sigue en
+    # dashboard:leer (el directivo ve el número de IVA, no la contraparte).
+    "facturas:ver_detalle": frozenset({Role.financiero, Role.admin}),
     # ── Spec §2.4 (autoridad del ciclo mensual — manda sobre §4.1) ──
     "ciclo:abrir": frozenset({Role.financiero, Role.directivo, Role.admin}),
     "ciclo:proponer": frozenset({Role.financiero, Role.directivo, Role.admin}),
diff --git a/backend/app/domain/configuracion.py b/backend/app/domain/configuracion.py
index 31f1ebb..728740e 100644
--- a/backend/app/domain/configuracion.py
+++ b/backend/app/domain/configuracion.py
@@ -31,6 +31,12 @@ class ClaveConfig(StrEnum):
     # Período de liquidación del IVA (decisión CEO 2026-07-25): default cuatrimestral;
     # la DIAN puede pasar a RODDOS a bimestral por volumen → configurable por dato.
     PERIODICIDAD_IVA = "PERIODICIDAD_IVA"
+    # E2: NIT propio (RODDOS) y de Auteco a config, no hardcodeados en el extractor.
+    NIT_RODDOS = "NIT_RODDOS"
+    NIT_AUTECO = "NIT_AUTECO"
+    # E2 (CR-E2-COMPUERTA): compuerta IVA→proyección. Apagada por defecto → E2 captura
+    # facturas y liquida el IVA SIN mover la caja proyectada (D-12). Encender es dato.
+    IVA_ALIMENTA_PROYECCION = "IVA_ALIMENTA_PROYECCION"
 
 
 # Tipo esperado por clave (M-03). "decimal" | "fecha" | "json".
@@ -39,6 +45,9 @@ _TIPO_POR_CLAVE: dict[ClaveConfig, str] = {
     ClaveConfig.CALENDARIO_DIAN: "json",
     ClaveConfig.DIAS_CREDITO_POR_PROVEEDOR: "json",
     ClaveConfig.PERIODICIDAD_IVA: "json",
+    ClaveConfig.NIT_RODDOS: "json",
+    ClaveConfig.NIT_AUTECO: "json",
+    ClaveConfig.IVA_ALIMENTA_PROYECCION: "json",
 }
 
 
@@ -134,4 +143,20 @@ SEMILLA_CONFIGURACION: list[dict] = [
         "valor_json": {"periodicidad": "cuatrimestral"},
         "vigente_desde": "2026-01-01",
     },
+    {
+        "clave": "NIT_RODDOS",
+        "valor_json": {"nit": "901012622"},
+        "vigente_desde": "2026-01-01",
+    },
+    {
+        "clave": "NIT_AUTECO",
+        "valor_json": {"nit": "860024781"},
+        "vigente_desde": "2026-01-01",
+    },
+    {
+        # CR-E2-COMPUERTA: IVA→proyección APAGADA por defecto (D-12). Encender = dato.
+        "clave": "IVA_ALIMENTA_PROYECCION",
+        "valor_json": {"activa": False},
+        "vigente_desde": "2026-01-01",
+    },
 ]
diff --git a/backend/app/domain/factura.py b/backend/app/domain/factura.py
index 61b42fe..f2dce7a 100644
--- a/backend/app/domain/factura.py
+++ b/backend/app/domain/factura.py
@@ -16,6 +16,7 @@ pero NUNCA se le aplica ReteFuente (regla de contabilidad RODDOS). CUATRIMESTRAL
 
 import re
 from datetime import datetime
+from decimal import Decimal
 from enum import StrEnum
 
 from beanie import Document
@@ -28,10 +29,21 @@ FACTURAS_COLLECTION = "facturas"
 
 _FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
 
+# Único tipo de documento que E2 procesa (D-16: NC/ND/soporte van a E2.1).
+TIPO_DOC_FACTURA_VENTA = "FACTURA ELECTRÓNICA DE VENTA"
+
+# Pieza 6 (E2 §3.5): tarifas IVA legales en Colombia — 0% (exento/excluido), 5%
+# (reducida) y 19% (general). Lista CERRADA para la captura MANUAL (endurecer, no
+# cambiar el cálculo → sin CR por R6). La ingesta DIAN NO valida contra esto: el PDF
+# puede mezclar tarifas (trampa 4 del §2) y guarda tarifa_iva=None (manda iva_valor).
+TARIFAS_IVA_VALIDAS = frozenset(
+    {Decimal("0"), Decimal("0.05"), Decimal("0.19")}
+)
+
 
 class TipoFactura(StrEnum):
-    venta = "venta"  # genera IVA (débito fiscal)
-    compra = "compra"  # IVA descontable si es deducible
+    venta = "venta"  # genera IVA (débito fiscal) — 'emitida' en el PDF DIAN
+    compra = "compra"  # IVA descontable si es deducible — 'recibida' en el PDF
 
 
 class OrigenFactura(StrEnum):
@@ -41,6 +53,10 @@ class OrigenFactura(StrEnum):
     repuesto = "repuesto"
     servicio = "servicio"
     otro = "otro"
+    # E2: la ingesta NO puede deducir el origen de negocio del PDF (a diferencia del
+    # tipo, que sí sale del NIT). Entra 'sin_clasificar' con contador visible; el CEO
+    # lo reclasifica. Nunca se adivina (R5).
+    sin_clasificar = "sin_clasificar"
 
 
 class Factura(Document):
@@ -52,19 +68,55 @@ class Factura(Document):
     tercero_nombre: str = Field(min_length=1, max_length=200)
     tercero_nit: str = Field(min_length=1, max_length=30)
     fecha: str  # 'YYYY-MM-DD' (Bogotá); el cuatrimestre se deriva de aquí
-    base_gravable: Money
-    tarifa_iva: Money  # fracción (0.19 general, 0 exento)
-    iva_valor: Money  # = base_gravable × tarifa_iva (lo calcula el servicio)
-    total: Money  # = base_gravable + iva_valor
+    # base GRAVADA (la que causa IVA). Manual: obligatoria. Ingesta DIAN: None —
+    # la Representación Gráfica solo trae el "Total Bruto" (que incluye líneas sin
+    # IVA), no la base gravada por línea; guardarlo aquí sería fiscalmente falso
+    # (tarifa implícita absurda, reportes fiscales errados). R5: no se inventa.
+    base_gravable: Money | None
+    # Total Bruto Factura de la DIAN (incluye líneas sin IVA). None en captura
+    # manual (ahí manda base_gravable). Junto con iva/inc/... cuadra el total (A6).
+    total_bruto: Money | None = None
+    # fracción (0.19 general, 0 exento) — informativo si viene iva_valor. None
+    # SOLO en la ingesta DIAN: una factura puede mezclar tarifas (trampa 4 del
+    # §2) y derivar tarifa desde iva/base mete redondeos en un dato fiscal
+    # (alternativa rechazada en §3.2); la captura manual la sigue exigiendo.
+    tarifa_iva: Money | None
+    # E2/D-13: el iva_valor extraído del PDF MANDA; si no, base × tarifa (servicio)
+    iva_valor: Money
+    # = base_gravable + impuestos (se reutiliza; no se agrega total_factura)
+    total: Money
     deducible: bool = False  # solo compras: si su IVA es descontable
     activo: bool = True  # baja lógica (anulación)
 
+    # ── E2: campos de la Representación Gráfica DIAN ──
+    cufe: str | None = None  # identificador único DIAN; None en captura manual
+    tipo_documento: str = TIPO_DOC_FACTURA_VENTA  # radar E2.1 (NC/ND llevarían otro)
+    signo: int = 1  # +1 factura; -1 reservado para notas crédito (E2.1)
+    # Tipo de contribuyente de la CONTRAPARTE (persona_juridica|persona_natural|None).
+    # Gobierna el enmascaramiento del LISTADO (A17): la razón social de una persona
+    # jurídica NO es PII (Ley 1581 protege a la natural). None (manual / PDF sin
+    # dato) → se trata como PII por precaución. El detalle sigue restringido siempre.
+    tipo_contribuyente: str | None = None
+    # `inc_valor` y no `inc`: `inc` pisa un atributo de beanie.Document (UserWarning de
+    # Pydantic; rompería updates a futuro). Desviación del §3.1 documentada en el PR.
+    inc_valor: Money = Decimal("0.00")
+    bolsas: Money = Decimal("0.00")
+    otros_impuestos: Money = Decimal("0.00")
+    rete_fuente: Money = Decimal("0.00")
+    rete_iva: Money = Decimal("0.00")
+    rete_ica: Money = Decimal("0.00")
+    # hash sha256 del PDF cargado. Decisión CEO: NO se guardan los bytes del PDF ni
+    # hay endpoint de descarga — el CUFE es el puntero (con él se re-descarga el
+    # documento de la DIAN, que es el archivo de registro) y el sha256 solo sirve
+    # para verificar un archivo que ya se tenga. Por eso `archivos:descargar` NO
+    # aplica a A17.
+    archivo_ref: str | None = None
+
     class Settings:
         name = FACTURAS_COLLECTION
         indexes = [
-            # Regla 5: dedup por el par natural NIT+número. Único donde numero es
-            # string (siempre). En Mongo real lanza DuplicateKeyError; mongomock no lo
-            # exige → la unicidad real se prueba con @requires_real_mongo.
+            # Regla 5: dedup por el par natural NIT+número. Se conserva porque las
+            # capturas MANUALES no tienen CUFE. Único donde numero es string (siempre).
             IndexModel(
                 [("tercero_nit", 1), ("numero", 1)],
                 name="nit_numero_unico",
@@ -72,6 +124,13 @@ class Factura(Document):
                 partialFilterExpression={"numero": {"$type": "string"}},
             ),
             IndexModel([("fecha", 1)], name="por_fecha"),
+            # ⚠ El índice único de CUFE (A2) va en la MIGRACIÓN, no aquí. El
+            # partialFilterExpression {"cufe": {"$type":"string"}} es correcto en
+            # Mongo real (excluye capturas manuales sin CUFE), pero mongomock IGNORA
+            # el partial y lo trataría como único simple → dos cufe=None colisionan y
+            # rompen la suite rápida. Se crea (cufe_unico) en la migración
+            # 20260728_e2_facturas_iva; la dedup CUFE va además en el servicio y se
+            # verifica @requires_real_mongo.
         ]
 
     @field_validator("fecha")
diff --git a/backend/app/facturas/extraccion.py b/backend/app/facturas/extraccion.py
new file mode 100644
index 0000000..481b044
--- /dev/null
+++ b/backend/app/facturas/extraccion.py
@@ -0,0 +1,299 @@
+# backend/app/facturas/extraccion.py
+"""Extractor de la Representación Gráfica DIAN (PDF) → datos de factura para el módulo
+de IVA (E2). PORTADO de docs/extraer_iva_dian.py (extractor de referencia probado contra
+un PDF real y corregido por el hallazgo M-1). NO reescribir la lógica; NO reordenar la
+detección de tipo (ver bloque M-1).
+
+Trampas reales resueltas (comentadas en el original):
+ 1. NO regex por línea: el layout de dos columnas intercala una barra lateral y duplica
+    etiquetas ("IVA IVA 1.452,94"). Se lee por POSICIÓN (x/y), tomando el último número
+    de la fila.
+ 2. Tomar el campo "IVA", NO "Total impuesto" (este suma IVA+INC+bolsas). Sin un
+    caso con INC>0 el bug queda escondido → test A5.
+ 3. Formato COP (miles ".", decimales ",") → Decimal, jamás float (R1).
+ 4. Una factura puede mezclar tarifas: el valor válido es el del bloque de totales.
+
+Desviación del port (documentada): se separó una costura pura
+`factura_desde_documento(texto, filas, titulo_pdf, nit_propio)` para que A1/A5 se
+prueben con estructuras sintéticas sin shippear PDFs reales al repo. El orden de
+detección de tipo (M-1) queda intacto. `extraer(ruta)` hace solo el I/O de pdfplumber y
+delega en la costura. Vocabulario: este extractor produce tipo 'emitida'|'recibida'; el
+dominio `Factura` usa 'venta'|'compra' → la ingesta mapea emitida→venta,
+recibida→compra.
+"""
+
+from __future__ import annotations
+
+import re
+import unicodedata
+from dataclasses import dataclass
+from datetime import date
+from decimal import Decimal
+from pathlib import Path
+
+import pdfplumber
+
+_NUMERO_COP = re.compile(r"[\d.]+,\d{2}")
+
+TIPO_SOPORTADO = "FACTURA ELECTRÓNICA DE VENTA"
+_TITULO_SOPORTADO = "FACTURA ELECTRONICA DE VENTA"  # normalizado, sin acentos
+
+# ⚠ HALLAZGO M-1 (auditoría externa) — leer antes de tocar este bloque.
+# El nombre oficial DIAN de la nota crédito (cód. 91) es
+#     "Nota Crédito de Factura Electrónica de Venta"
+# y CONTIENE "FACTURA ELECTRÓNICA DE VENTA". Si se evalúa primero el tipo soportado, una
+# nota crédito entra como factura de venta: una NC RECIBIDA inflaría el descontable
+# → RODDOS pagaría menos IVA del debido → riesgo directo con la DIAN.
+# Dos salvaguardas, y EL ORDEN IMPORTA:
+#   (a) los marcadores NO soportados se evalúan PRIMERO, sobre el encabezado completo;
+#   (b) el tipo soportado exige que el TÍTULO (primera línea no vacía) EMPIECE por él.
+MARCADORES_NO_SOPORTADOS = (
+    "NOTA CREDITO",
+    "NOTA DEBITO",
+    "NOTA DE AJUSTE",
+    "DOCUMENTO SOPORTE",
+    "DOCUMENTO EQUIVALENTE",
+)
+
+_LINEAS_ENCABEZADO = 6
+
+# Bloques de la Representación Gráfica (verificado en el PDF real): el Tipo de
+# Contribuyente aparece DOS veces (emisor y adquiriente), con el mismo rótulo. Se
+# aísla por sección para leer el de la CONTRAPARTE correcta (GO CEO punto 1).
+_SEC_EMISOR = "Datos del Emisor"
+_SEC_ADQUIRIENTE = "Datos del Adquiriente"
+_RE_CONTRIB = re.compile(
+    r"Tipo de Contribuyente:\s*(Persona\s+(?:Jur[ií]dica|Natural))", re.IGNORECASE
+)
+# Valores canónicos del tipo de contribuyente (persona natural = PII, Ley 1581).
+PERSONA_JURIDICA = "persona_juridica"
+PERSONA_NATURAL = "persona_natural"
+
+# Fixtures de título para el test A8 (títulos OFICIALES DIAN, no simplificados).
+TITULOS_A8 = (
+    "Nota Crédito de Factura Electrónica de Venta",
+    "Nota Débito de Factura Electrónica de Venta",
+    "Documento Soporte en Adquisiciones Efectuadas a No Obligados a Facturar",
+    "Nota de Ajuste al Documento Soporte",
+)
+
+
+class DocumentoNoDian(Exception):
+    """El PDF no es una Representación Gráfica de la DIAN: no se parsea."""
+
+
+class TipoNoSoportado(Exception):
+    """Documento DIAN válido, pero de un tipo que E2 no procesa (queda para E2.1)."""
+
+
+def _sin_acentos(texto: str) -> str:
+    descompuesto = unicodedata.normalize("NFD", texto)
+    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").upper()
+
+
+def _a_decimal(texto: str) -> Decimal:
+    """'1.452,94' -> Decimal('1452.94')."""
+    return Decimal(texto.replace(".", "").replace(",", "."))
+
+
+@dataclass(frozen=True)
+class FacturaDian:
+    tipo_documento: str
+    cufe: str
+    numero: str
+    fecha: date
+    nit_emisor: str
+    nombre_emisor: str
+    nit_adquiriente: str
+    tipo: str  # "emitida" | "recibida" (la ingesta mapea a venta|compra)
+    tipo_contribuyente_contraparte: str | None  # persona_juridica|persona_natural|None
+    base_gravable: Decimal
+    iva: Decimal
+    inc: Decimal
+    bolsas: Decimal
+    otros_impuestos: Decimal
+    total_impuesto: Decimal
+    total_factura: Decimal
+    rete_fuente: Decimal
+    rete_iva: Decimal
+    rete_ica: Decimal
+
+    def coherente(self) -> bool:
+        """base + IVA + INC + bolsas + otros == total factura (chequeo duro, A6)."""
+        suma = (
+            self.base_gravable
+            + self.iva
+            + self.inc
+            + self.bolsas
+            + self.otros_impuestos
+        )
+        return suma == self.total_factura
+
+
+def es_documento_dian(texto: str, titulo_pdf: str | None) -> bool:
+    return (
+        "Representación Gráfica" in texto
+        and "CUFE" in texto
+        and ("Dian" in (titulo_pdf or "") or "DIAN" in texto)
+    )
+
+
+def tipo_documento(texto: str) -> str:
+    """Tipo soportado o `TipoNoSoportado`. Orden deliberado (M-1): NO soportados primero
+    sobre el encabezado; luego el título soportado anclado al inicio."""
+    lineas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
+    titulo = _sin_acentos(lineas[0]) if lineas else ""
+    encabezado = _sin_acentos(" | ".join(lineas[:_LINEAS_ENCABEZADO]))
+
+    for marcador in MARCADORES_NO_SOPORTADOS:
+        if marcador in encabezado:
+            raise TipoNoSoportado(
+                f"{marcador}: tipo no procesado en E2 (queda para E2.1). "
+                f"El documento NO entra a la liquidación. Título leído: {titulo!r}"
+            )
+
+    if titulo.startswith(_TITULO_SOPORTADO):
+        return TIPO_SOPORTADO
+
+    raise TipoNoSoportado(f"tipo de documento no reconocido. Título leído: {titulo!r}")
+
+
+def filas_por_posicion(pagina) -> list[list[dict]]:
+    """Agrupa las palabras de la página en filas por su coordenada vertical."""
+    filas: dict[int, list[dict]] = {}
+    for palabra in pagina.extract_words():
+        filas.setdefault(round(palabra["top"] / 3), []).append(palabra)
+    return [sorted(ws, key=lambda w: w["x0"]) for _, ws in sorted(filas.items())]
+
+
+def _valor_de(filas: list[list[dict]], etiqueta: str) -> Decimal | None:
+    """Último número COP de la fila que contiene la etiqueta (columna derecha)."""
+    for palabras in filas:
+        texto = " ".join(w["text"] for w in palabras)
+        if etiqueta in texto:
+            numeros = [w["text"] for w in palabras if _NUMERO_COP.fullmatch(w["text"])]
+            if numeros:
+                return _a_decimal(numeros[-1])
+    return None
+
+
+def _seccion(texto: str, inicio: str, fin: str | None) -> str:
+    """Rebana el texto desde el marcador `inicio` hasta `fin` (o el final)."""
+    a = texto.find(inicio)
+    if a < 0:
+        return ""
+    b = texto.find(fin, a + len(inicio)) if fin else -1
+    return texto[a:] if b < 0 else texto[a:b]
+
+
+def tipo_contribuyente_contraparte(texto: str, tipo: str) -> str | None:
+    """Tipo de contribuyente de la CONTRAPARTE (emisor si la factura es recibida,
+    adquiriente si es emitida). Se lee dentro de la sección correcta para no leer el
+    de RODDOS. Ausente/ilegible → None (R5: no se inventa; la ingesta lo trata como
+    PII por precaución)."""
+    if tipo == "recibida":
+        seccion = _seccion(texto, _SEC_EMISOR, _SEC_ADQUIRIENTE)
+    else:  # emitida → la contraparte es el adquiriente
+        seccion = _seccion(texto, _SEC_ADQUIRIENTE, None)
+    m = _RE_CONTRIB.search(seccion)
+    if not m:
+        return None
+    valor = _sin_acentos(m.group(1))  # "PERSONA JURIDICA" | "PERSONA NATURAL"
+    if "JURIDICA" in valor:
+        return PERSONA_JURIDICA
+    if "NATURAL" in valor:
+        return PERSONA_NATURAL
+    return None
+
+
+def factura_desde_documento(
+    texto: str,
+    filas: list[list[dict]],
+    titulo_pdf: str | None,
+    nit_propio: str,
+    nombre: str = "documento",
+) -> FacturaDian:
+    """Costura pura (testeable sin PDF): valida DIAN → tipo → extrae campos por
+    posición. `extraer()` la alimenta con lo leído del PDF."""
+    if not es_documento_dian(texto, titulo_pdf):
+        raise DocumentoNoDian(f"{nombre}: no parece Representación Gráfica DIAN")
+
+    tipo_doc = tipo_documento(texto)  # lanza TipoNoSoportado si aplica (orden M-1)
+
+    def campo(patron: str) -> str | None:
+        m = re.search(patron, texto)
+        return m.group(1).strip() if m else None
+
+    cufe = campo(r"CUFE\s*:\s*\n?([0-9a-fA-F]{40,})")
+    numero = campo(r"Número de Factura:\s*(\S+)")
+    fecha_txt = campo(r"Fecha de Emisión:\s*(\d{2}/\d{2}/\d{4})")
+    nit_emisor = campo(r"Nit del Emisor:\s*(\d+)")
+    nombre_emisor = campo(r"Razón Social:\s*(.+)")
+    nit_adquiriente = campo(r"Número Documento:\s*(\d+)")
+
+    faltantes = [
+        n
+        for n, val in {
+            "CUFE": cufe,
+            "número": numero,
+            "fecha": fecha_txt,
+            "NIT emisor": nit_emisor,
+            "NIT adquiriente": nit_adquiriente,
+        }.items()
+        if not val
+    ]
+    if faltantes:
+        raise DocumentoNoDian(f"{nombre}: no se pudo leer {', '.join(faltantes)}")
+
+    dd, mm, aaaa = fecha_txt.split("/")
+
+    if nit_emisor == nit_propio:
+        tipo = "emitida"
+    elif nit_adquiriente == nit_propio:
+        tipo = "recibida"
+    else:
+        raise DocumentoNoDian(
+            f"{nombre}: ni el emisor ({nit_emisor}) ni el adquiriente "
+            f"({nit_adquiriente}) es {nit_propio} — documento ajeno"
+        )
+
+    cero = Decimal("0.00")
+
+    def v(etiqueta: str) -> Decimal:
+        return _valor_de(filas, etiqueta) or cero
+
+    return FacturaDian(
+        tipo_documento=tipo_doc,
+        cufe=cufe,
+        numero=numero,
+        fecha=date(int(aaaa), int(mm), int(dd)),
+        nit_emisor=nit_emisor,
+        nombre_emisor=nombre_emisor or "",
+        nit_adquiriente=nit_adquiriente,
+        tipo=tipo,
+        tipo_contribuyente_contraparte=tipo_contribuyente_contraparte(texto, tipo),
+        base_gravable=v("Total Bruto Factura"),
+        iva=v("IVA"),  # el campo "IVA", NO "Total impuesto" (trampa 2)
+        inc=v("INC"),
+        bolsas=v("Bolsas"),
+        otros_impuestos=v("Otros impuestos"),
+        total_impuesto=v("Total impuesto"),
+        total_factura=v("Total factura"),
+        rete_fuente=v("Rete fuente"),
+        rete_iva=v("Rete IVA"),
+        rete_ica=v("Rete ICA"),
+    )
+
+
+def extraer(ruta: str | Path, nit_propio: str) -> FacturaDian:
+    """Lee el PDF (I/O) y delega en `factura_desde_documento`. `nit_propio` viene de
+    Configuracion (NIT de RODDOS), NUNCA hardcodeado.
+
+    ⚠ `pdfplumber` es CPU-bound y bloqueante: en FastAPI ejecutar en threadpool
+    (`anyio.to_thread`) y aplicar tope de archivos por lote (§3.3)."""
+    ruta = Path(ruta)
+    with pdfplumber.open(ruta) as pdf:
+        titulo_pdf = (pdf.metadata or {}).get("Title")
+        texto = "\n".join((p.extract_text() or "") for p in pdf.pages)
+        filas = [f for pagina in pdf.pages for f in filas_por_posicion(pagina)]
+    return factura_desde_documento(texto, filas, titulo_pdf, nit_propio, ruta.name)
diff --git a/backend/app/facturas/ingesta.py b/backend/app/facturas/ingesta.py
new file mode 100644
index 0000000..918eec7
--- /dev/null
+++ b/backend/app/facturas/ingesta.py
@@ -0,0 +1,351 @@
+# backend/app/facturas/ingesta.py
+"""Ingesta por documento (E2 §3.3) — el motor de POST /api/v1/facturas/cargar.
+
+Recibe un lote de PDFs (Representación Gráfica DIAN), extrae cada uno FUERA del
+event loop (pdfplumber es CPU-bound; dentro de un handler async congelaría el
+servidor — criterio A16) y devuelve resultado POR ARCHIVO con estados distinguibles:
+
+  creada | duplicada | rechazada_no_dian | rechazada_tipo_no_soportado |
+  requiere_confirmacion | error
+
+`rechazada_tipo_no_soportado` va aparte de los otros rechazos porque alimenta el
+contador visible del §2 bis (radar de notas crédito recibidas). `error` (fallo
+interno inesperado) existe por el requisito de resultado PARCIAL: si el archivo 7
+de 20 falla, los otros 19 se procesan. `requiere_confirmacion` NO persiste nada:
+devuelve lo extraído para la pantalla de confirmación (no hay documentos fiscales
+a medio registrar).
+
+Dedup por CUFE: pre-check aquí (legible, no atómico) + índice único `cufe_unico`
+(la garantía dura, creado por la migración 20260728_e2_facturas_iva). Mapeo de
+vocabulario: FacturaDian 'emitida'→venta / 'recibida'→compra, y ⚠ FacturaDian.inc
+→ Factura.inc_valor (rename anti-shadow de de36c63): un desajuste ahí guardaría un
+cero en silencio — hay candado en tests.
+
+Los NIT (RODDOS/Auteco) vienen de Configuracion, jamás hardcodeados. Sin
+NIT_RODDOS no se puede deducir el tipo → `ConfigFaltanteError` (409 accionable).
+"""
+
+import hashlib
+import logging
+import os
+from enum import StrEnum
+from io import BytesIO
+
+import pdfplumber
+from anyio import to_thread
+from fastapi import UploadFile
+from pymongo.errors import DuplicateKeyError
+
+from app.audit.events import AuditEvento
+from app.audit.service import emit_audit
+from app.core.money import money_str
+from app.domain.configuracion import ClaveConfig, Configuracion
+from app.domain.factura import Factura, OrigenFactura, TipoFactura
+from app.facturas.extraccion import (
+    DocumentoNoDian,
+    FacturaDian,
+    TipoNoSoportado,
+    factura_desde_documento,
+    filas_por_posicion,
+)
+
+logger = logging.getLogger(__name__)
+
+MAX_ARCHIVOS_LOTE = 20  # coherente con POST /api/v1/cargas (F-22)
+MAX_BYTES_ARCHIVO = 10 * 1024 * 1024
+
+
+class ConfigFaltanteError(Exception):
+    """Falta una clave de Configuracion indispensable (el router responde 409)."""
+
+
+class EstadoIngesta(StrEnum):
+    creada = "creada"
+    duplicada = "duplicada"
+    rechazada_no_dian = "rechazada_no_dian"
+    rechazada_tipo_no_soportado = "rechazada_tipo_no_soportado"  # radar §2 bis
+    requiere_confirmacion = "requiere_confirmacion"
+    error = "error"  # interno inesperado; el resto del lote sigue (parcial)
+
+
+_PLURAL = {
+    EstadoIngesta.creada: "creadas",
+    EstadoIngesta.duplicada: "duplicadas",
+    EstadoIngesta.rechazada_no_dian: "rechazadas_no_dian",
+    EstadoIngesta.rechazada_tipo_no_soportado: "rechazadas_tipo_no_soportado",
+    EstadoIngesta.requiere_confirmacion: "requieren_confirmacion",
+    EstadoIngesta.error: "errores",
+}
+
+
+async def _nit_config(clave: ClaveConfig) -> str | None:
+    """Última vigencia de una clave NIT_* ({"nit": "..."}). Ausente → None."""
+    cfg = (
+        await Configuracion.find(Configuracion.clave == clave)
+        .sort(-Configuracion.vigente_desde)
+        .limit(1)
+        .to_list()
+    )
+    if cfg and cfg[0].valor_json:
+        nit = cfg[0].valor_json.get("nit")
+        return str(nit) if nit else None
+    return None
+
+
+def _extraer_bytes(contenido: bytes, nombre: str, nit_propio: str) -> FacturaDian:
+    """SÍNCRONA y CPU-bound: llamar SIEMPRE vía `anyio.to_thread` (A16).
+
+    Paralela a `extraccion.extraer()` (que recibe ruta) pero sobre bytes: evita el
+    temp file y conserva el NOMBRE ORIGINAL en los motivos de rechazo (el temp
+    tendría un nombre aleatorio inservible para el operador). La lógica de negocio
+    sigue viviendo en `factura_desde_documento` (orden M-1 intacto)."""
+    with pdfplumber.open(BytesIO(contenido)) as pdf:
+        titulo_pdf = (pdf.metadata or {}).get("Title")
+        texto = "\n".join((p.extract_text() or "") for p in pdf.pages)
+        filas = [f for pagina in pdf.pages for f in filas_por_posicion(pagina)]
+    return factura_desde_documento(texto, filas, titulo_pdf, nit_propio, nombre)
+
+
+def campos_desde_dian(f: FacturaDian, *, nit_auteco: str | None) -> dict:
+    """Costura PURA (testeable sin PDF): FacturaDian → campos del Document Factura.
+
+    ⚠ `FacturaDian.inc` → `Factura.inc_valor` (rename anti-shadow): NO "corregir"
+    a `inc` — pisaría un atributo de beanie.Document. Candado en tests.
+    `tarifa_iva=None`: una factura DIAN puede mezclar tarifas (trampa 4 del §2) y
+    derivar la tarifa desde iva/base mete redondeos en un dato fiscal (§3.2); el
+    `iva_valor` extraído manda (D-13). `deducible=False`: la decisión es explícita
+    del operador (contador de "recibidas sin marcar deducible" en el listado)."""
+    if f.tipo == "recibida":
+        tercero_nit, tercero_nombre = f.nit_emisor, f.nombre_emisor
+        tipo = TipoFactura.compra
+        es_auteco = nit_auteco is not None and f.nit_emisor == nit_auteco
+        origen = OrigenFactura.auteco if es_auteco else OrigenFactura.sin_clasificar
+    else:  # emitida
+        tercero_nit, tercero_nombre = f.nit_adquiriente, ""
+        tipo = TipoFactura.venta
+        origen = OrigenFactura.sin_clasificar
+    if not tercero_nombre:
+        # el extractor no captura el nombre del adquiriente: se etiqueta con el
+        # NIT real (R5: no se inventa); la pantalla de confirmación lo corrige
+        tercero_nombre = f"NIT {tercero_nit}"
+    return {
+        "tipo": tipo,
+        "origen": origen,
+        "numero": f.numero,
+        "tercero_nombre": tercero_nombre,
+        "tercero_nit": tercero_nit,
+        "fecha": f.fecha.isoformat(),
+        # `FacturaDian.base_gravable` es el Total Bruto (incluye líneas sin IVA):
+        # va a total_bruto. La base GRAVADA real no se conoce sin parsear líneas →
+        # base_gravable=None (R5). Manda el iva_valor extraído (D-13).
+        "base_gravable": None,
+        "total_bruto": f.base_gravable,
+        "tarifa_iva": None,
+        "iva_valor": f.iva,
+        "total": f.total_factura,
+        "deducible": False,
+        "cufe": f.cufe,
+        "tipo_documento": f.tipo_documento,
+        "signo": 1,
+        "tipo_contribuyente": f.tipo_contribuyente_contraparte,
+        "inc_valor": f.inc,  # ← el rename anti-shadow
+        "bolsas": f.bolsas,
+        "otros_impuestos": f.otros_impuestos,
+        "rete_fuente": f.rete_fuente,
+        "rete_iva": f.rete_iva,
+        "rete_ica": f.rete_ica,
+    }
+
+
+def _datos_extraidos(f: FacturaDian, campos: dict) -> dict:
+    """Lo extraído, montos como STRING (regla 1). Viaja al cliente (pantalla de
+    confirmación / resultado por archivo); no persiste nada por sí mismo."""
+    return {
+        "tipo_documento": f.tipo_documento,
+        "cufe": f.cufe,
+        "numero": f.numero,
+        "fecha": campos["fecha"],
+        "tipo": campos["tipo"].value,
+        "origen": campos["origen"].value,
+        "tercero_nit": campos["tercero_nit"],
+        "tercero_nombre": campos["tercero_nombre"],
+        "tipo_contribuyente": f.tipo_contribuyente_contraparte,
+        # base gravada desconocida en la DIAN (R5); el Total Bruto va rotulado aparte
+        "base_gravable": None,
+        "total_bruto": money_str(f.base_gravable),
+        "iva_valor": money_str(f.iva),
+        "inc_valor": money_str(f.inc),
+        "bolsas": money_str(f.bolsas),
+        "otros_impuestos": money_str(f.otros_impuestos),
+        "total_impuesto": money_str(f.total_impuesto),
+        "total_factura": money_str(f.total_factura),
+        "rete_fuente": money_str(f.rete_fuente),
+        "rete_iva": money_str(f.rete_iva),
+        "rete_ica": money_str(f.rete_ica),
+        "coherente": f.coherente(),
+    }
+
+
+def _resultado(
+    archivo: str,
+    estado: EstadoIngesta,
+    *,
+    motivo: str | None = None,
+    factura_id: str | None = None,
+    datos: dict | None = None,
+) -> dict:
+    return {
+        "archivo": archivo,
+        "estado": estado.value,
+        "motivo": motivo,
+        "factura_id": factura_id,
+        "datos_extraidos": datos,
+    }
+
+
+async def _procesar_archivo(
+    archivo: UploadFile,
+    *,
+    nit_propio: str,
+    nit_auteco: str | None,
+    usuario_id: str,
+) -> dict:
+    nombre = archivo.filename or "documento.pdf"
+
+    ext = os.path.splitext(nombre)[1].lower()
+    if ext != ".pdf":
+        return _resultado(
+            nombre,
+            EstadoIngesta.rechazada_no_dian,
+            motivo=f"extensión '{ext}' no soportada; la Representación Gráfica "
+            "DIAN es un .pdf",
+        )
+    contenido = await archivo.read(MAX_BYTES_ARCHIVO + 1)
+    if len(contenido) > MAX_BYTES_ARCHIVO:
+        return _resultado(
+            nombre,
+            EstadoIngesta.rechazada_no_dian,
+            motivo="supera el límite de 10 MB por archivo",
+        )
+
+    try:
+        dian = await to_thread.run_sync(
+            _extraer_bytes, contenido, nombre, nit_propio
+        )
+    except TipoNoSoportado as e:
+        return _resultado(
+            nombre, EstadoIngesta.rechazada_tipo_no_soportado, motivo=str(e)
+        )
+    except DocumentoNoDian as e:
+        return _resultado(nombre, EstadoIngesta.rechazada_no_dian, motivo=str(e))
+
+    campos = campos_desde_dian(dian, nit_auteco=nit_auteco)
+    datos = _datos_extraidos(dian, campos)
+
+    # Pieza 5: la validación de integridad de la extracción es la COHERENCIA A6
+    # (base + iva + inc + bolsas + otros == total), NO `iva ≈ base × tarifa`. Esa
+    # última no aplica al PDF DIAN: `base_gravable` es el Total Bruto (incluye
+    # líneas sin IVA) y el doc puede mezclar tarifas (trampa 4 del §2), así que la
+    # tasa implícita ≠ nominal. Ejemplo real (A1): base 31.447,06 con IVA 1.452,94
+    # → base×0.19 = 5.974,94; un gate base×tarifa marcaría la propia muestra de oro
+    # como requiere_confirmacion. R6: se reporta, no se implementa el gate dañino.
+    if not dian.coherente():  # A6: no se guarda, pide revisión
+        return _resultado(
+            nombre,
+            EstadoIngesta.requiere_confirmacion,
+            motivo="base + impuestos no cuadra con el total de la factura; "
+            "revisar los valores extraídos y confirmar",
+            datos=datos,
+        )
+
+    # Pre-check de CUFE (legible, NO atómico); la garantía dura es el índice
+    # único cufe_unico + el DuplicateKeyError de abajo.
+    if await Factura.find_one(Factura.cufe == dian.cufe) is not None:
+        return _resultado(
+            nombre,
+            EstadoIngesta.duplicada,
+            motivo="ya existe una factura con este CUFE",
+            datos=datos,
+        )
+
+    factura = Factura(
+        **campos,
+        archivo_ref=f"sha256:{hashlib.sha256(contenido).hexdigest()}",
+    )
+    try:
+        await factura.insert()
+    except DuplicateKeyError:
+        # carrera del pre-check (cufe_unico) o carga manual previa con el mismo
+        # par NIT+número (nit_numero_unico): en ambos casos ya está registrada
+        return _resultado(
+            nombre,
+            EstadoIngesta.duplicada,
+            motivo="ya existe una factura con este CUFE o con el mismo "
+            "número para este NIT",
+            datos=datos,
+        )
+    try:
+        await emit_audit(
+            AuditEvento.factura_creada,
+            entidad="factura",
+            entidad_id=str(factura.id),
+            actor_id=usuario_id,
+            # sin nombre de archivo ni NIT/nombre del tercero: puede ser cédula/
+            # persona natural (PII, Ley 1581 / A17). CUFE+número identifican.
+            metadata={
+                "via": "ingesta_dian",
+                "numero": factura.numero,
+                "cufe": factura.cufe,
+                "tipo": factura.tipo.value,
+                "origen": factura.origen.value,
+                "iva_valor": money_str(factura.iva_valor),
+            },
+        )
+    except Exception:
+        await factura.delete()  # saga O1: sin rastro de auditoría no hay alta
+        raise
+    return _resultado(
+        nombre, EstadoIngesta.creada, factura_id=str(factura.id), datos=datos
+    )
+
+
+async def procesar_lote(archivos: list[UploadFile], *, usuario_id: str) -> dict:
+    """Procesa el lote archivo por archivo (resultado PARCIAL: una excepción en
+    uno no frena a los demás) y devuelve {resultados: [...], resumen: {...}}."""
+    nit_propio = await _nit_config(ClaveConfig.NIT_RODDOS)
+    if not nit_propio:
+        raise ConfigFaltanteError(
+            "NIT_RODDOS no está en Configuracion: sin él no se puede deducir si "
+            "una factura es emitida o recibida. Corra la migración "
+            "20260728_e2_facturas_iva."
+        )
+    nit_auteco = await _nit_config(ClaveConfig.NIT_AUTECO)
+
+    resultados: list[dict] = []
+    for i, archivo in enumerate(archivos):
+        nombre = archivo.filename or "documento.pdf"
+        try:
+            resultados.append(
+                await _procesar_archivo(
+                    archivo,
+                    nit_propio=nit_propio,
+                    nit_auteco=nit_auteco,
+                    usuario_id=usuario_id,
+                )
+            )
+        except Exception:
+            # sin nombre de archivo en el log (puede llevar PII, A17)
+            logger.exception("ingesta: error procesando el archivo %d del lote", i)
+            resultados.append(
+                _resultado(
+                    nombre,
+                    EstadoIngesta.error,
+                    motivo="error interno procesando el archivo; los demás "
+                    "archivos del lote no se afectaron",
+                )
+            )
+
+    resumen = {plural: 0 for plural in _PLURAL.values()}
+    for r in resultados:
+        resumen[_PLURAL[EstadoIngesta(r["estado"])]] += 1
+    return {"resultados": resultados, "resumen": resumen}
diff --git a/backend/app/facturas/router.py b/backend/app/facturas/router.py
index ced1b01..8e70cc9 100644
--- a/backend/app/facturas/router.py
+++ b/backend/app/facturas/router.py
@@ -10,15 +10,23 @@ hace inocuo el replay (→ 409). La liquidación se calcula en el backend."""
 
 from decimal import Decimal, InvalidOperation
 
-from fastapi import APIRouter, Depends, HTTPException, Query
+from beanie import PydanticObjectId
+from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
 from pydantic import BaseModel, ConfigDict, Field
 
 from app.auth.deps import require_permission
 from app.auth.models import User
+from app.auth.permissions import has_permission
 from app.auth.router import verify_origin
 from app.core.money import money_str
-from app.domain.factura import Factura, OrigenFactura, TipoFactura
-from app.facturas import service
+from app.domain.factura import (
+    TARIFAS_IVA_VALIDAS,
+    Factura,
+    OrigenFactura,
+    TipoFactura,
+)
+from app.facturas import ingesta, service
+from app.facturas.extraccion import PERSONA_JURIDICA
 from app.iva.liquidacion import Periodicidad, liquidar, periodo_de
 
 router = APIRouter(prefix="/facturas", tags=["facturas"])
@@ -51,18 +59,32 @@ def _etiqueta_periodo(anio: int, idx: int, periodicidad: Periodicidad) -> str:
     return f"{anio}-{prefijo}{idx}"
 
 
-def _serializar(f: Factura, periodicidad: Periodicidad) -> dict:
+def _serializar(
+    f: Factura, periodicidad: Periodicidad, *, ver_pii: bool = True
+) -> dict:
     anio, idx = periodo_de(f.fecha, periodicidad)
+    # A17 (Ley 1581): la Ley protege a la PERSONA NATURAL. La razón social de una
+    # persona jurídica (Auteco, Éxito, Hunter) NO es PII y debe verla el directivo.
+    # Se enmascara SOLO si la contraparte es natural o su tipo es desconocido
+    # (manual / PDF sin dato → por precaución) y el usuario no tiene ver_detalle.
+    es_juridica = f.tipo_contribuyente == PERSONA_JURIDICA
+    ver_contraparte = ver_pii or es_juridica
     return {
         "id": str(f.id),
         "tipo": f.tipo.value,
         "origen": f.origen.value,
         "numero": f.numero,
-        "tercero_nombre": f.tercero_nombre,
-        "tercero_nit": f.tercero_nit,
+        "tercero_nombre": f.tercero_nombre if ver_contraparte else None,
+        "tercero_nit": f.tercero_nit if ver_contraparte else None,
+        "tipo_contribuyente": f.tipo_contribuyente,
         "fecha": f.fecha,
-        "base_gravable": money_str(f.base_gravable),
-        "tarifa_iva": str(f.tarifa_iva),
+        # None (DIAN) → "—" en la UI, nunca un valor prestado (R5)
+        "base_gravable": money_str(f.base_gravable)
+        if f.base_gravable is not None
+        else None,
+        "total_bruto": money_str(f.total_bruto) if f.total_bruto is not None else None,
+        # None = ingesta DIAN (tarifas mezcladas; manda iva_valor, D-13)
+        "tarifa_iva": str(f.tarifa_iva) if f.tarifa_iva is not None else None,
         "iva_valor": money_str(f.iva_valor),
         "total": money_str(f.total),
         "deducible": f.deducible,
@@ -74,11 +96,12 @@ def _serializar(f: Factura, periodicidad: Periodicidad) -> dict:
 @router.get("")
 async def listar(
     activo: bool | None = Query(default=None),
-    _: User = Depends(require_permission("dashboard:leer")),
+    user: User = Depends(require_permission("dashboard:leer")),
 ):
     periodicidad = await service.obtener_periodicidad()
     facturas = await service.listar_facturas(activo=activo)
-    return [_serializar(f, periodicidad) for f in facturas]
+    ver_pii = has_permission(user.rol, "facturas:ver_detalle")
+    return [_serializar(f, periodicidad, ver_pii=ver_pii) for f in facturas]
 
 
 @router.get("/liquidacion")
@@ -107,6 +130,47 @@ async def liquidacion(_: User = Depends(require_permission("dashboard:leer"))):
     }
 
 
+@router.get("/{factura_id}")
+async def detalle(
+    factura_id: str,
+    _: User = Depends(require_permission("facturas:ver_detalle")),
+):
+    """Detalle de una factura con PII completa (A17 / Ley 1581): solo
+    facturas:ver_detalle = {financiero, admin}. La ruta va DESPUÉS de /liquidacion
+    para que ese literal no caiga en {factura_id}."""
+    try:
+        fid = PydanticObjectId(factura_id)
+    except Exception:
+        raise HTTPException(422, "factura_id inválido") from None
+    f = await Factura.get(fid)
+    if f is None:
+        raise HTTPException(404, "la factura no existe")
+    return _serializar(f, await service.obtener_periodicidad(), ver_pii=True)
+
+
+@router.post("/cargar")
+async def cargar(
+    archivos: list[UploadFile],
+    user: User = Depends(require_permission("iva:gestionar")),
+    _: None = Depends(verify_origin),
+):
+    """Ingesta por documento (E2 §3.3): lote de PDFs DIAN → resultado POR ARCHIVO
+    (creada | duplicada | rechazada_no_dian | rechazada_tipo_no_soportado |
+    requiere_confirmacion | error) + resumen. Parseo fuera del event loop (A16);
+    tope de 20 archivos y 10 MB por archivo (coherente con POST /api/v1/cargas).
+    RBAC iva:gestionar: cargar es una mutación fiscal, no una lectura."""
+    if len(archivos) > ingesta.MAX_ARCHIVOS_LOTE:
+        raise HTTPException(
+            413,
+            f"máximo {ingesta.MAX_ARCHIVOS_LOTE} archivos por lote; "
+            f"recibidos {len(archivos)}",
+        )
+    try:
+        return await ingesta.procesar_lote(archivos, usuario_id=user.id)
+    except ingesta.ConfigFaltanteError as e:
+        raise HTTPException(409, str(e)) from e
+
+
 @router.post("", status_code=201)
 async def crear(
     body: FacturaCrearBody,
@@ -117,6 +181,13 @@ async def crear(
         raise HTTPException(422, f"tipo inválido: {body.tipo}")
     if body.origen not in OrigenFactura._value2member_map_:
         raise HTTPException(422, f"origen inválido: {body.origen}")
+    tarifa = _dec(body.tarifa_iva, "tarifa_iva")
+    if tarifa not in TARIFAS_IVA_VALIDAS:
+        raise HTTPException(
+            422,
+            f"tarifa_iva inválida: {body.tarifa_iva}. Tarifas IVA legales en "
+            "Colombia: 0, 0.05, 0.19 (pieza 6)",
+        )
     try:
         factura = await service.crear_factura(
             usuario_id=user.id,
@@ -127,7 +198,7 @@ async def crear(
             tercero_nit=body.tercero_nit,
             fecha=body.fecha,
             base_gravable=_dec(body.base_gravable, "base_gravable"),
-            tarifa_iva=_dec(body.tarifa_iva, "tarifa_iva"),
+            tarifa_iva=tarifa,
             deducible=body.deducible,
         )
     except service.FacturasError as e:
diff --git a/backend/app/proyeccion/service.py b/backend/app/proyeccion/service.py
index a61a5d3..c208972 100644
--- a/backend/app/proyeccion/service.py
+++ b/backend/app/proyeccion/service.py
@@ -200,13 +200,36 @@ async def _calendario_dian() -> dict:
     return cfg[0].valor_json if cfg and cfg[0].valor_json else {}
 
 
+async def _compuerta_iva_activa() -> bool:
+    """CR-E2-COMPUERTA: ¿el IVA de las facturas alimenta la proyección? Clave
+    CONFIGURACION `IVA_ALIMENTA_PROYECCION`. Ausente o apagada → False (D-12: por
+    defecto el IVA NO mueve la caja; encenderla es una decisión de dato del CEO)."""
+    cfg = (
+        await Configuracion.find(
+            Configuracion.clave == ClaveConfig.IVA_ALIMENTA_PROYECCION
+        )
+        .sort(-Configuracion.vigente_desde)
+        .limit(1)
+        .to_list()
+    )
+    if cfg and cfg[0].valor_json:
+        return bool(cfg[0].valor_json.get("activa", False))
+    return False
+
+
 async def _iva_plan(
     mes_inicio: tuple[int, int], horizonte: int
 ) -> tuple[dict[int, object], list]:
     """Puente C11↔C7: liquida las facturas cargadas y devuelve (egreso_por_mes, fondo).
     `egreso_por_mes` = IVA neto de cada período en el índice de su fecha DIAN real
     (PR-2b, entra al motor). `fondo` = plan de provisión mes a mes (P1.4, informativo,
-    NO entra al flujo del motor). Sin facturas → ({}, [])."""
+    NO entra al flujo del motor). Sin facturas → ({}, []).
+
+    CR-E2-COMPUERTA: con la compuerta APAGADA (default) devuelve ({}, []) aunque haya
+    facturas cargadas, de modo que E2 capture facturas y liquide el IVA SIN mover la
+    proyección (D-12). `GET /proyeccion` queda idéntico bit a bit al estado previo."""
+    if not await _compuerta_iva_activa():
+        return {}, []
     facturas = await facturas_service.obtener_facturas_iva()
     if not facturas:
         return {}, []
diff --git a/backend/pyproject.toml b/backend/pyproject.toml
index 87f090c..c45bf6c 100644
--- a/backend/pyproject.toml
+++ b/backend/pyproject.toml
@@ -7,6 +7,15 @@ requires-python = ">=3.12"
 [tool.pytest.ini_options]
 asyncio_mode = "auto"
 testpaths = ["tests"]
+# E2: el shadow de un campo de Document sobre un atributo de beanie/Pydantic
+# (el caso `inc`→`inc_valor` de de36c63) sale como UserWarning y se colaría en
+# silencio. Se promueve SOLO ese mensaje a error — filtro dirigido, no `error`
+# global, para no convertir en fallo el ruido de deprecación de terceros
+# (lazy_model/Pydantic 2.11). Cualquier campo nuevo que pise un atributo padre
+# rompe la suite de inmediato.
+filterwarnings = [
+    "error:Field name.*shadows an attribute:UserWarning",
+]
 # Sin esto, el script de consola `pytest` (CI) no pone backend/ en sys.path y falla
 # `import app` (ModuleNotFoundError). `python -m pytest` sí lo hacía por el cwd; pythonpath
 # lo fija para AMBAS invocaciones y no depende de un tests/__init__.py.
diff --git a/migrations/20260728_e2_facturas_iva.py b/migrations/20260728_e2_facturas_iva.py
new file mode 100644
index 0000000..df7a281
--- /dev/null
+++ b/migrations/20260728_e2_facturas_iva.py
@@ -0,0 +1,78 @@
+#!/usr/bin/env python
+"""Migración idempotente E2 — captura de facturas / módulo de IVA.
+
+Dos cosas, ambas idempotentes (segunda corrida sin cambios, criterio A13):
+  1. Crea el índice único SPARSE sobre `cufe` (y el resto de índices de `Factura`)
+     vía `init_beanie` — crear un índice ya existente con la misma definición es no-op.
+  2. Siembra las claves de Configuracion de E2 (NIT_RODDOS, NIT_AUTECO,
+     IVA_ALIMENTA_PROYECCION apagada) con `seed_configuracion` ($setOnInsert por
+     (clave, vigente_desde)).
+
+La colección `facturas` está VACÍA antes de E2 (verificado en producción), así que la
+creación del índice no tiene riesgo de datos.
+
+Plan de reversa (NO ejecutar sin aprobación): borrar el índice `cufe_unico`
+(`db.facturas.drop_index("cufe_unico")`), quitar los campos nuevos de las facturas
+creadas (`$unset cufe, tipo_documento, signo, inc_valor, bolsas, otros_impuestos,
+rete_fuente, rete_iva, rete_ica, total_bruto, archivo_ref`) y las 3 claves de config
+sembradas. La colección
+estaba vacía → la reversa es limpia.
+
+Uso:  python migrations/20260728_e2_facturas_iva.py "<MONGODB_URI>" [db=compas]
+"""
+
+from __future__ import annotations
+
+import asyncio
+import sys
+
+sys.path.insert(0, "backend")
+
+from app.db import mongo  # noqa: E402
+from app.domain.factura import FACTURAS_COLLECTION  # noqa: E402
+from app.domain.seed import seed_configuracion  # noqa: E402
+
+
+async def _run(uri: str, db_name: str) -> None:
+    client = mongo.create_client(uri)
+    db = client[db_name]
+
+    antes = await db[FACTURAS_COLLECTION].count_documents({})
+    print(f"[e2] facturas antes: {antes}")
+
+    # init_beanie asegura los índices declarados en Settings (nit_numero, por_fecha).
+    await mongo.init_beanie_for(client, db_name)
+
+    # Índice único SPARSE de CUFE (A2). Va aquí y no en Settings: mongomock no honra
+    # partialFilterExpression y rompería la suite rápida (ver factura.py). En Mongo real
+    # el partial excluye las capturas manuales sin CUFE. create_index es idempotente:
+    # re-crear con la misma definición y nombre es no-op.
+    await db[FACTURAS_COLLECTION].create_index(
+        [("cufe", 1)],
+        name="cufe_unico",
+        unique=True,
+        partialFilterExpression={"cufe": {"$type": "string"}},
+    )
+    indices = await db[FACTURAS_COLLECTION].index_information()
+    print(f"[e2] índices de facturas: {sorted(indices)}")
+
+    n = await seed_configuracion(db)
+    print(f"[e2] configuracion: {n} claves nuevas insertadas (idempotente).")
+
+    despues = await db[FACTURAS_COLLECTION].count_documents({})
+    print(f"[e2] facturas después: {despues} (sin cambios de datos)")
+    client.close()
+
+
+def main() -> None:
+    if len(sys.argv) < 2:
+        sys.exit(
+            'Uso: python migrations/20260728_e2_facturas_iva.py "<MONGODB_URI>" [db]'
+        )
+    uri = sys.argv[1]
+    db_name = sys.argv[2] if len(sys.argv) > 2 else "compas"
+    asyncio.run(_run(uri, db_name))
+
+
+if __name__ == "__main__":
+    main()
```

## Diff de tests

```diff
diff --git a/backend/tests/fixtures/dian_factura_venta_exito_2026-05-28.pdf b/backend/tests/fixtures/dian_factura_venta_exito_2026-05-28.pdf
new file mode 100644
index 0000000..e0278be
Binary files /dev/null and b/backend/tests/fixtures/dian_factura_venta_exito_2026-05-28.pdf differ
diff --git a/backend/tests/test_domain_configuracion.py b/backend/tests/test_domain_configuracion.py
index 5905c55..d544309 100644
--- a/backend/tests/test_domain_configuracion.py
+++ b/backend/tests/test_domain_configuracion.py
@@ -75,9 +75,20 @@ def test_semilla_tiene_las_claves_esperadas():
         "CALENDARIO_DIAN",
         "DIAS_CREDITO_POR_PROVEEDOR",
         "PERIODICIDAD_IVA",
+        "NIT_RODDOS",
+        "NIT_AUTECO",
+        "IVA_ALIMENTA_PROYECCION",
     }
 
 
+def test_semilla_e2_nits_y_compuerta_apagada():
+    d = {c["clave"]: c for c in SEMILLA_CONFIGURACION}
+    assert d["NIT_RODDOS"]["valor_json"] == {"nit": "901012622"}
+    assert d["NIT_AUTECO"]["valor_json"] == {"nit": "860024781"}
+    # compuerta IVA→proyección apagada por defecto (D-12 / CR-E2-COMPUERTA)
+    assert d["IVA_ALIMENTA_PROYECCION"]["valor_json"] == {"activa": False}
+
+
 def test_semilla_periodicidad_iva_default_cuatrimestral():
     p = next(c for c in SEMILLA_CONFIGURACION if c["clave"] == "PERIODICIDAD_IVA")
     assert p["valor_json"] == {"periodicidad": "cuatrimestral"}
diff --git a/backend/tests/test_domain_indexes.py b/backend/tests/test_domain_indexes.py
index aaf0236..d5efd63 100644
--- a/backend/tests/test_domain_indexes.py
+++ b/backend/tests/test_domain_indexes.py
@@ -10,6 +10,7 @@ from decimal import Decimal
 import pytest
 from app.domain import DOMAIN_DOCUMENTS
 from app.domain.configuracion import Configuracion
+from app.domain.factura import Factura
 from app.domain.rubro import Rubro
 from beanie import init_beanie
 from motor.motor_asyncio import AsyncIOMotorClient
@@ -78,6 +79,43 @@ async def test_regla_patron_activo_unico_parcial(real_db):
         ).insert()  # segunda ACTIVA idéntica → colisión
 
 
+def _factura(**over) -> Factura:
+    base = dict(
+        tipo="compra",
+        origen="otra_compra",
+        numero="F1",
+        tercero_nombre="Proveedor",
+        tercero_nit="900",
+        fecha="2026-05-28",
+        base_gravable=Decimal("1000.00"),
+        tarifa_iva=Decimal("0.19"),
+        iva_valor=Decimal("190.00"),
+        total=Decimal("1190.00"),
+    )
+    base.update(over)
+    return Factura(**base)
+
+
+async def test_cufe_unico_sparse_en_mongo_real(real_db):
+    """E2/A2: el índice cufe_unico (creado en la migración, NO en Settings) impide dos
+    facturas con el mismo CUFE, pero admite VARIAS capturas manuales sin CUFE
+    (partialFilterExpression $type:string). Se crea aquí igual que en la migración."""
+    await real_db["facturas"].create_index(
+        [("cufe", 1)],
+        name="cufe_unico",
+        unique=True,
+        partialFilterExpression={"cufe": {"$type": "string"}},
+    )
+    cufe = "fabdb194877f049b698d92065704f28fec96e9c0abcd"
+    await _factura(cufe=cufe, numero="F1", tercero_nit="900").insert()
+    with pytest.raises(DuplicateKeyError):
+        await _factura(cufe=cufe, numero="F2", tercero_nit="901").insert()
+
+    # dos capturas MANUALES (cufe=None) NO colisionan: el partial las excluye del índice
+    await _factura(cufe=None, numero="M1", tercero_nit="902").insert()
+    await _factura(cufe=None, numero="M2", tercero_nit="903").insert()
+
+
 async def test_configuracion_clave_vigencia_unica(real_db):
     await Configuracion(
         clave="UMBRAL_DIF_BANCO_CIERRE",
diff --git a/backend/tests/test_domain_persistence.py b/backend/tests/test_domain_persistence.py
index 63b7c6d..5a3226e 100644
--- a/backend/tests/test_domain_persistence.py
+++ b/backend/tests/test_domain_persistence.py
@@ -7,7 +7,7 @@ from decimal import Decimal
 
 import pytest
 from app.domain import DOMAIN_DOCUMENTS
-from app.domain.configuracion import Configuracion
+from app.domain.configuracion import SEMILLA_CONFIGURACION, Configuracion
 from app.domain.mes_control import MesControl
 from app.domain.rubro import Rubro
 from app.domain.seed import (
@@ -102,7 +102,10 @@ async def test_seed_configuracion_idempotente(db):
     await seed_configuracion(db)
     await seed_configuracion(db)
     total = await Configuracion.find_all().count()
-    assert total == 4  # + PERIODICIDAD_IVA (CR IVA período configurable)
+    # 7 = las 4 previas (+ PERIODICIDAD_IVA, CR IVA período configurable) + las 3
+    # de E2 (NIT_RODDOS, NIT_AUTECO, IVA_ALIMENTA_PROYECCION). Atado a la semilla
+    # real para que agregar una clave sin pasar por aquí no pase desapercibido.
+    assert total == len(SEMILLA_CONFIGURACION) == 7
 
 
 # ── C3: semilla de reglas de clasificación (GO Kimi PLAN-I 9.3) ──
diff --git a/backend/tests/test_extraccion_dian.py b/backend/tests/test_extraccion_dian.py
new file mode 100644
index 0000000..23a0ea1
--- /dev/null
+++ b/backend/tests/test_extraccion_dian.py
@@ -0,0 +1,260 @@
+# backend/tests/test_extraccion_dian.py
+"""E2 §4.1 — extractor DIAN. Prueba la LÓGICA con estructuras sintéticas (no requiere
+shippear PDFs reales): A8 títulos oficiales + regresión M-1, A4 tipo por NIT, A5 INC>0
+(toma IVA, no Total impuesto), A6 coherencia, A7 no-DIAN. A1 (PDF real) se auto-activa
+cuando el fixture exista en backend/tests/fixtures/."""
+
+from decimal import Decimal
+from pathlib import Path
+
+import pytest
+from app.facturas.extraccion import (
+    TIPO_SOPORTADO,
+    TITULOS_A8,
+    DocumentoNoDian,
+    TipoNoSoportado,
+    _a_decimal,
+    es_documento_dian,
+    extraer,
+    factura_desde_documento,
+    tipo_documento,
+)
+
+NIT_RODDOS = "901012622"
+
+
+def _texto(
+    titulo: str,
+    nit_emisor: str = "890900608",
+    nit_adq: str = NIT_RODDOS,
+    contrib_emisor: str = "Persona Jurídica",
+    contrib_adq: str = "Persona Jurídica",
+) -> str:
+    """Texto DIAN mínimo válido con el título dado. Refleja la estructura real de
+    dos bloques (emisor / adquiriente), cada uno con su Tipo de Contribuyente."""
+    return (
+        f"{titulo}\n"
+        "Representación Gráfica Dian\n"
+        "CUFE : abcdef0123456789abcdef0123456789abcdef01\n"
+        "Número de Factura: UI90-16716\n"
+        "Fecha de Emisión: 28/05/2026\n"
+        "Datos del Emisor / Vendedor\n"
+        f"Nit del Emisor: {nit_emisor}\n"
+        "Razón Social: ALMACENES ÉXITO S.A\n"
+        f"Tipo de Contribuyente: {contrib_emisor} Departamento: Bogotá\n"
+        "Datos del Adquiriente / Comprador\n"
+        f"Número Documento: {nit_adq}\n"
+        f"Tipo de Contribuyente: {contrib_adq} Municipio: Bogotá\n"
+    )
+
+
+def _fila(*textos: str) -> list[dict]:
+    return [{"text": t, "x0": 0.0, "top": 0.0} for t in textos]
+
+
+# base 1.000, IVA 190 (19%), INC 100 → Total impuesto 290, Total factura 1.290.
+def _filas_inc() -> list[list[dict]]:
+    return [
+        _fila("Total", "Bruto", "Factura", "1.000,00"),
+        _fila("IVA", "IVA", "190,00"),
+        _fila("INC", "100,00"),
+        _fila("Total", "impuesto", "290,00"),
+        _fila("Total", "factura", "1.290,00"),
+        _fila("Rete", "IVA", "0,00"),
+    ]
+
+
+def test_a_decimal_formato_cop():
+    assert _a_decimal("1.452,94") == Decimal("1452.94")
+    assert _a_decimal("32.900,00") == Decimal("32900.00")
+
+
+# ── A8 + regresión M-1: los cuatro títulos oficiales se rechazan ──
+@pytest.mark.parametrize("titulo", TITULOS_A8)
+def test_a8_titulos_oficiales_dian_se_rechazan(titulo):
+    with pytest.raises(TipoNoSoportado):
+        tipo_documento(_texto(titulo))
+
+
+def test_m1_nota_credito_no_entra_como_factura():
+    """La NC oficial contiene 'FACTURA ELECTRÓNICA DE VENTA'; el orden M-1 la rechaza."""  # noqa: E501
+    nc = "Nota Crédito de Factura Electrónica de Venta"
+    with pytest.raises(TipoNoSoportado):
+        tipo_documento(_texto(nc))
+
+
+def test_a8_factura_de_venta_legitima_se_acepta():
+    assert tipo_documento(_texto("FACTURA ELECTRÓNICA DE VENTA")) == TIPO_SOPORTADO
+
+
+# ── A4: tipo deducido del NIT ──
+def test_a4_recibida_cuando_roddos_es_adquiriente():
+    f = factura_desde_documento(
+        _texto("FACTURA ELECTRÓNICA DE VENTA", nit_emisor="890900608"),
+        _filas_inc(),
+        "Representación Gráfica Dian",
+        NIT_RODDOS,
+    )
+    assert f.tipo == "recibida"
+
+
+def test_a4_emitida_cuando_roddos_es_emisor():
+    f = factura_desde_documento(
+        _texto(
+            "FACTURA ELECTRÓNICA DE VENTA", nit_emisor=NIT_RODDOS, nit_adq="800111222"
+        ),
+        _filas_inc(),
+        "Representación Gráfica Dian",
+        NIT_RODDOS,
+    )
+    assert f.tipo == "emitida"
+
+
+def test_a4_documento_ajeno_se_rechaza():
+    with pytest.raises(DocumentoNoDian):
+        factura_desde_documento(
+            _texto("FACTURA ELECTRÓNICA DE VENTA", nit_emisor="111", nit_adq="222"),
+            _filas_inc(),
+            "Representación Gráfica Dian",
+            NIT_RODDOS,
+        )
+
+
+# ── tipo_contribuyente de la CONTRAPARTE (GO CEO punto 1: enmascaramiento fino) ──
+def test_contribuyente_contraparte_es_el_emisor_en_recibida():
+    f = factura_desde_documento(
+        _texto(
+            "FACTURA ELECTRÓNICA DE VENTA",
+            contrib_emisor="Persona Natural",
+            contrib_adq="Persona Jurídica",
+        ),
+        _filas_inc(),
+        "Representación Gráfica Dian",
+        NIT_RODDOS,
+    )
+    # recibida → la contraparte es el emisor (natural), no el adquiriente RODDOS
+    assert f.tipo == "recibida"
+    assert f.tipo_contribuyente_contraparte == "persona_natural"
+
+
+def test_contribuyente_contraparte_es_el_adquiriente_en_emitida():
+    f = factura_desde_documento(
+        _texto(
+            "FACTURA ELECTRÓNICA DE VENTA",
+            nit_emisor=NIT_RODDOS,
+            nit_adq="800111222",
+            contrib_emisor="Persona Jurídica",
+            contrib_adq="Persona Natural",
+        ),
+        _filas_inc(),
+        "Representación Gráfica Dian",
+        NIT_RODDOS,
+    )
+    # emitida → la contraparte es el adquiriente (natural)
+    assert f.tipo == "emitida"
+    assert f.tipo_contribuyente_contraparte == "persona_natural"
+
+
+def test_contribuyente_juridica_se_reconoce():
+    f = factura_desde_documento(
+        _texto("FACTURA ELECTRÓNICA DE VENTA"),  # ambos jurídica por defecto
+        _filas_inc(),
+        "Representación Gráfica Dian",
+        NIT_RODDOS,
+    )
+    assert f.tipo_contribuyente_contraparte == "persona_juridica"
+
+
+def test_contribuyente_ausente_es_none():
+    # texto sin la línea de Tipo de Contribuyente en el bloque del emisor
+    texto = (
+        "FACTURA ELECTRÓNICA DE VENTA\n"
+        "Representación Gráfica Dian\n"
+        "CUFE : abcdef0123456789abcdef0123456789abcdef01\n"
+        "Número de Factura: UI90-1\n"
+        "Fecha de Emisión: 28/05/2026\n"
+        "Datos del Emisor / Vendedor\n"
+        "Nit del Emisor: 890900608\n"
+        "Razón Social: PROVEEDOR\n"
+        "Datos del Adquiriente / Comprador\n"
+        f"Número Documento: {NIT_RODDOS}\n"
+    )
+    f = factura_desde_documento(
+        texto, _filas_inc(), "Representación Gráfica Dian", NIT_RODDOS
+    )
+    assert f.tipo_contribuyente_contraparte is None
+
+
+# ── A5 (OBLIGATORIO): con INC>0 se toma el IVA, NO Total impuesto ──
+def test_a5_toma_iva_no_total_impuesto():
+    f = factura_desde_documento(
+        _texto("FACTURA ELECTRÓNICA DE VENTA"),
+        _filas_inc(),
+        "Representación Gráfica Dian",
+        NIT_RODDOS,
+    )
+    assert f.iva == Decimal("190.00")  # el campo IVA
+    assert f.inc == Decimal("100.00")
+    assert f.total_impuesto == Decimal("290.00")  # IVA+INC — NO es el IVA
+    assert f.iva != f.total_impuesto
+
+
+# ── A6: coherencia base + impuestos == total ──
+def test_a6_coherente_true():
+    f = factura_desde_documento(
+        _texto("FACTURA ELECTRÓNICA DE VENTA"),
+        _filas_inc(),
+        "Representación Gráfica Dian",
+        NIT_RODDOS,
+    )
+    # 1.000 + 190 + 100 + 0 + 0 == 1.290
+    assert f.coherente() is True
+
+
+def test_a6_incoherente_false():
+    filas = _filas_inc()
+    filas[-2] = _fila("Total", "factura", "9.999,00")  # total inconsistente
+    f = factura_desde_documento(
+        _texto("FACTURA ELECTRÓNICA DE VENTA"),
+        filas,
+        "Representación Gráfica Dian",
+        NIT_RODDOS,
+    )
+    assert f.coherente() is False
+
+
+# ── A7: PDF que no es representación DIAN ──
+def test_a7_no_dian_se_rechaza():
+    assert es_documento_dian("factura de otro sistema", None) is False
+    with pytest.raises(DocumentoNoDian):
+        factura_desde_documento(
+            "un PDF cualquiera sin marcadores", [], None, NIT_RODDOS
+        )
+
+
+# ── A1: caso de oro sobre el PDF real. Es TAMBIÉN el candado del pin de versión:
+# el extractor se validó en pdfplumber 0.11.9 y el repo pinó 0.11.4; la extracción por
+# POSICIÓN puede variar entre versiones, y este es el único test que lo atraparía. Si
+# falla por versión, es un HALLAZGO (no se ajusta el valor esperado). ──
+_FIXTURE = (
+    Path(__file__).parent / "fixtures" / "dian_factura_venta_exito_2026-05-28.pdf"
+)
+
+
+@pytest.mark.skipif(
+    not _FIXTURE.exists(),
+    reason="A1: falta el PDF de muestra — dejar en backend/tests/fixtures/",
+)
+def test_a1_pdf_de_muestra():
+    from app.iva.liquidacion import cuatrimestre_de
+
+    f = extraer(_FIXTURE, nit_propio=NIT_RODDOS)
+    assert f.iva == Decimal("1452.94")
+    assert f.base_gravable == Decimal("31447.06")
+    assert f.total_factura == Decimal("32900.00")
+    assert f.tipo == "recibida"
+    # contraparte (emisor Éxito) = persona jurídica → NO es PII (Ley 1581)
+    assert f.tipo_contribuyente_contraparte == "persona_juridica"
+    assert f.coherente() is True
+    # cuatrimestre may–ago = C2 (28-may-2026)
+    assert cuatrimestre_de(f.fecha.isoformat()) == (2026, 2)
diff --git a/backend/tests/test_factura_campos_e2.py b/backend/tests/test_factura_campos_e2.py
new file mode 100644
index 0000000..37ef504
--- /dev/null
+++ b/backend/tests/test_factura_campos_e2.py
@@ -0,0 +1,63 @@
+# backend/tests/test_factura_campos_e2.py
+"""E2 §3.1 — campos nuevos de Factura (DIAN) y el origen sin_clasificar."""
+
+from decimal import Decimal
+
+from app.domain.factura import (
+    TIPO_DOC_FACTURA_VENTA,
+    Factura,
+    OrigenFactura,
+    TipoFactura,
+)
+
+
+def _minima(**over) -> Factura:
+    base = dict(
+        tipo=TipoFactura.compra,
+        origen=OrigenFactura.otra_compra,
+        numero="UI90-16716",
+        tercero_nombre="ALMACENES ÉXITO S.A",
+        tercero_nit="890900608",
+        fecha="2026-05-28",
+        base_gravable=Decimal("31447.06"),
+        tarifa_iva=Decimal("0.19"),
+        iva_valor=Decimal("1452.94"),
+        total=Decimal("32900.00"),
+    )
+    base.update(over)
+    return Factura(**base)
+
+
+def test_campos_nuevos_tienen_defaults_seguros():
+    f = _minima()
+    assert f.cufe is None  # captura manual no trae CUFE
+    assert f.tipo_documento == TIPO_DOC_FACTURA_VENTA
+    assert f.signo == 1
+    assert f.inc_valor == Decimal("0.00")
+    assert f.bolsas == Decimal("0.00")
+    assert f.otros_impuestos == Decimal("0.00")
+    assert f.rete_fuente == Decimal("0.00")
+    assert f.rete_iva == Decimal("0.00")
+    assert f.rete_ica == Decimal("0.00")
+    assert f.archivo_ref is None
+
+
+def test_origen_sin_clasificar_es_valido():
+    f = _minima(origen=OrigenFactura.sin_clasificar)
+    assert f.origen is OrigenFactura.sin_clasificar
+
+
+def test_cufe_se_persiste_cuando_viene():
+    f = _minima(cufe="fabdb194877f049b698d92065704f28fec96e9c0")
+    assert f.cufe.startswith("fabdb194")
+
+
+def test_impuestos_dian_se_guardan():
+    f = _minima(
+        inc_valor=Decimal("100.00"),
+        rete_fuente=Decimal("50.00"),
+        archivo_ref="s3://facturas/UI90-16716.pdf",
+    )
+    assert f.inc_valor == Decimal("100.00")
+    assert f.rete_fuente == Decimal("50.00")
+    assert f.archivo_ref.endswith(".pdf")
diff --git a/backend/tests/test_facturas.py b/backend/tests/test_facturas.py
index bda99f4..b80ef13 100644
--- a/backend/tests/test_facturas.py
+++ b/backend/tests/test_facturas.py
@@ -120,9 +120,12 @@ async def test_anular_factura_es_baja_logica_y_emite_evento(db):
     assert e.value.status == 409
 
 
-async def test_proyeccion_resta_iva_en_el_mes_dian(db):
-    """Puente C11↔C7 (PR-2b): una venta con IVA en C1-2026 hace que la proyección reste
-    ese IVA de la caja en el mes de la fecha DIAN real (13-may-26 → índice 4)."""
+@pytest.mark.parametrize("compuerta_activa", [True, False])
+async def test_proyeccion_iva_segun_compuerta(db, compuerta_activa):
+    """CR-E2-COMPUERTA (parametriza el antiguo test_proyeccion_resta_iva...):
+    con la compuerta ENCENDIDA una venta con IVA en C1-2026 hace que la proyección
+    reste ese IVA en el mes DIAN (13-may-26 → índice 4); APAGADA (default) el IVA NO
+    alimenta la proyección y la serie queda en cero, aunque la factura esté cargada."""
     from decimal import Decimal
 
     from app.domain.configuracion import Configuracion
@@ -131,6 +134,11 @@ async def test_proyeccion_resta_iva_en_el_mes_dian(db):
     from app.facturas import service
     from app.proyeccion import service as proy
 
+    await Configuracion(
+        clave="IVA_ALIMENTA_PROYECCION",
+        valor_json={"activa": compuerta_activa},
+        vigente_desde="2026-01-01",
+    ).insert()
     await Configuracion(
         clave="CALENDARIO_DIAN",
         valor_json={
@@ -192,25 +200,143 @@ async def test_proyeccion_resta_iva_en_el_mes_dian(db):
     res = await proy.proyectar_vigente(
         escenario="base", mes_inicio=(2026, 1), horizonte_meses=8
     )
-    # 13-may-26 = índice 4 desde ene-2026; el IVA sale ahí (negativo) y solo ahí
-    assert res["meses"][4]["iva"] == "-190000.00"
-    assert res["meses"][3]["iva"] == "0.00"
-    # fondo de provisión: reserva 47500/mes en ene-abr (190000/4); saldo lleno en abr,
-    # el pago de may lo vacía. Serie informativa (no mueve la caja del motor).
-    fondo = res["fondo_provision"]
-    assert fondo[0] == {
-        "mes": "2026-01",
-        "reserva": "47500.00",
-        "pago": "0.00",
-        "saldo": "47500.00",
-    }
-    assert fondo[3]["saldo"] == "190000.00"
-    assert fondo[4] == {
-        "mes": "2026-05",
-        "reserva": "0.00",
-        "pago": "190000.00",
-        "saldo": "0.00",
-    }
+    if compuerta_activa:
+        # 13-may-26 = índice 4 desde ene-2026; el IVA sale ahí (negativo) y solo ahí
+        assert res["meses"][4]["iva"] == "-190000.00"
+        assert res["meses"][3]["iva"] == "0.00"
+        # fondo de provisión: reserva 47500/mes en ene-abr (190000/4); saldo lleno en
+        # abr, el pago de may lo vacía. Serie informativa (no mueve la caja del motor).
+        fondo = res["fondo_provision"]
+        assert fondo[0] == {
+            "mes": "2026-01",
+            "reserva": "47500.00",
+            "pago": "0.00",
+            "saldo": "47500.00",
+        }
+        assert fondo[3]["saldo"] == "190000.00"
+        assert fondo[4] == {
+            "mes": "2026-05",
+            "reserva": "0.00",
+            "pago": "190000.00",
+            "saldo": "0.00",
+        }
+    else:
+        # compuerta apagada: la factura NO mueve la proyección (D-12)
+        assert all(m["iva"] == "0.00" for m in res["meses"])
+        assert res["fondo_provision"] == []
+
+
+async def test_a14_compuerta_apagada_proyeccion_identica_bit_a_bit(db):
+    """A14 / CR-E2-COMPUERTA (criterio central del CEO): con facturas cargadas y la
+    compuerta APAGADA, GET /proyeccion es idéntico BIT A BIT al estado sin facturas
+    (candado de D-12). Con CONTROL NEGATIVO en el mismo test y el mismo fixture: al
+    ENCENDER la compuerta la proyección SÍ cambia (si no cambiara, el escenario no
+    ejercita el puente y el candado sería vacuo). Se siembra CALENDARIO_DIAN para que el
+    egreso de IVA tenga una fecha real y el escenario sea sensible."""
+    from decimal import Decimal
+
+    from app.domain.configuracion import Configuracion
+    from app.domain.modelo_moto import ModeloMoto
+    from app.domain.parametros_proyeccion import ParametrosProyeccion
+    from app.facturas import service
+    from app.proyeccion import service as proy
+
+    # calendario real: sin esto el egreso saldría vacío por otra razón (test vacuo)
+    await Configuracion(
+        clave="CALENDARIO_DIAN",
+        valor_json={
+            "2026": {
+                "ene_abr": "2026-05-13",
+                "may_ago": "2026-09-10",
+                "sep_dic": "2027-01-14",
+            }
+        },
+        vigente_desde="2026-01-01",
+    ).insert()
+    await ParametrosProyeccion(
+        vigente_desde="2026-01-01",
+        caja_inicial=Decimal("0"),
+        caja_minima=Decimal("0"),
+        motos_base=0,
+        crec_pct_mensual=Decimal("0"),
+        horizonte_meses=8,
+        adelanto_auteco=Decimal("0"),
+        plazo_auteco_dias=0,
+        base_auteco_dias=0,
+        tasa_auteco=Decimal("0"),
+        gastos_fijos=Decimal("0"),
+        gps_moto=Decimal("0"),
+        costo_moto_nueva=Decimal("0"),
+        deuda=Decimal("0"),
+        tasa_deuda=Decimal("0"),
+        mes_inicio_deuda=0,
+        meses_deuda=0,
+        pct_mora=Decimal("0"),
+        pct_recuperacion=Decimal("0"),
+        pct_default=Decimal("0"),
+        pct_provision=Decimal("0"),
+    ).insert()
+    await ModeloMoto(
+        nombre="Raider",
+        costo_auteco=Decimal("0"),
+        precio_venta_con_iva=Decimal("0"),
+        cuota_inicial=Decimal("0"),
+        cuota_semanal=Decimal("0"),
+        plazo_semanas=6,
+        matricula=Decimal("0"),
+        participacion_mix=Decimal("1"),
+        orden=0,
+    ).insert()
+
+    antes = await proy.proyectar_vigente(
+        escenario="base", mes_inicio=(2026, 1), horizonte_meses=8
+    )
+
+    # facturas de venta y compra que moverían el IVA con la compuerta encendida
+    await service.crear_factura(
+        usuario_id="u1",
+        tipo="venta",
+        origen="moto",
+        numero="FV-9",
+        tercero_nombre="Cliente",
+        tercero_nit="79",
+        fecha="2026-02-01",
+        base_gravable=Decimal("1000000"),
+        tarifa_iva=Decimal("0.19"),
+        deducible=False,
+    )
+    await service.crear_factura(
+        usuario_id="u1",
+        tipo="compra",
+        origen="auteco",
+        numero="FC-9",
+        tercero_nombre="Auteco",
+        tercero_nit="860024781",
+        fecha="2026-06-01",
+        base_gravable=Decimal("2000000"),
+        tarifa_iva=Decimal("0.19"),
+        deducible=True,
+    )
+
+    # compuerta APAGADA (default, no sembrada) → proyección idéntica bit a bit (D-12)
+    despues_off = await proy.proyectar_vigente(
+        escenario="base", mes_inicio=(2026, 1), horizonte_meses=8
+    )
+    assert despues_off == antes
+
+    # CONTROL NEGATIVO: al ENCENDER la compuerta, la MISMA factura SÍ mueve la
+    # proyección. Si esto no cambia, el escenario no ejercita el puente → candado vacuo.
+    await Configuracion(
+        clave="IVA_ALIMENTA_PROYECCION",
+        valor_json={"activa": True},
+        vigente_desde="2026-01-02",  # vigencia más nueva → gana
+    ).insert()
+    despues_on = await proy.proyectar_vigente(
+        escenario="base", mes_inicio=(2026, 1), horizonte_meses=8
+    )
+    assert despues_on != antes
+    # y concretamente: el IVA generado por la venta sale en el mes DIAN (13-may → idx 4)
+    assert despues_on["meses"][4]["iva"] == "-190000.00"
 
 
 async def test_obtener_facturas_iva_solo_activas_para_liquidar(db):
diff --git a/backend/tests/test_facturas_cargar.py b/backend/tests/test_facturas_cargar.py
new file mode 100644
index 0000000..5145ebe
--- /dev/null
+++ b/backend/tests/test_facturas_cargar.py
@@ -0,0 +1,463 @@
+# backend/tests/test_facturas_cargar.py
+"""E2 §4.3 — POST /api/v1/facturas/cargar (ingesta de PDFs DIAN por lote).
+
+Contrato por archivo: creada | duplicada | rechazada_no_dian |
+rechazada_tipo_no_soportado | requiere_confirmacion | error (interno inesperado —
+exigido por el resultado PARCIAL: si el archivo 7 falla, los otros 19 se procesan).
+Idempotencia (A2), tope de lote (A16), mapeo emitida→venta / recibida→compra,
+FacturaDian.inc → Factura.inc_valor (candado del rename: INC>0 NUNCA queda en 0.00),
+requiere_confirmacion NO persiste, RBAC iva:gestionar.
+
+El parseo real (pdfplumber) se cubre con el PDF real en el test E2E; el resto
+monkeypatchea la costura `ingesta._extraer_bytes` y dispatchea por CONTENIDO del
+archivo (el nombre original no llega al extractor)."""
+
+import hashlib
+from datetime import date
+from decimal import Decimal
+from pathlib import Path
+
+import httpx
+import pytest
+import pytest_asyncio
+from app.audit.service import configure_audit, reset_audit
+from app.auth import passwords, repository
+from app.auth.models import User
+from app.auth.roles import Role
+from app.config import get_settings
+from app.domain import DOMAIN_DOCUMENTS
+from app.domain.configuracion import Configuracion
+from app.domain.factura import Factura
+from app.facturas import ingesta
+from app.facturas.extraccion import DocumentoNoDian, FacturaDian, TipoNoSoportado
+from app.main import create_app
+from mongomock_motor import AsyncMongoMockClient
+
+PWD = "clave-larga-1234"
+NIT_RODDOS = "901012622"
+NIT_AUTECO = "860024781"
+URL = "/api/v1/facturas/cargar"
+
+
+def _dian(**kw) -> FacturaDian:
+    """FacturaDian sintética coherente (base 1.000 + IVA 190 + INC 100 = 1.290)."""
+    campos = dict(
+        tipo_documento="FACTURA ELECTRÓNICA DE VENTA",
+        cufe="cufe-defecto",
+        numero="UI90-1",
+        fecha=date(2026, 5, 28),
+        nit_emisor="890900608",
+        nombre_emisor="ALMACENES ÉXITO S.A",
+        nit_adquiriente=NIT_RODDOS,
+        tipo="recibida",
+        tipo_contribuyente_contraparte="persona_juridica",
+        base_gravable=Decimal("1000.00"),
+        iva=Decimal("190.00"),
+        inc=Decimal("100.00"),
+        bolsas=Decimal("0.00"),
+        otros_impuestos=Decimal("0.00"),
+        total_impuesto=Decimal("290.00"),
+        total_factura=Decimal("1290.00"),
+        rete_fuente=Decimal("0.00"),
+        rete_iva=Decimal("0.00"),
+        rete_ica=Decimal("0.00"),
+    )
+    campos.update(kw)
+    return FacturaDian(**campos)
+
+
+def _cufe_de(contenido: bytes) -> str:
+    return "cufe-" + hashlib.sha256(contenido).hexdigest()[:40]
+
+
+def _fake_extraer_bytes(contenido: bytes, nombre: str, nit_propio: str) -> FacturaDian:
+    """Doble de `ingesta._extraer_bytes`: dispatch por contenido. Mismo contenido →
+    mismo CUFE (indispensable para el test de idempotencia)."""
+    cufe = _cufe_de(contenido)
+    if contenido == b"PDF-NC":
+        raise TipoNoSoportado("NOTA CREDITO: tipo no procesado en E2")
+    if contenido == b"PDF-AJENO":
+        raise DocumentoNoDian("no parece Representación Gráfica DIAN")
+    if contenido == b"PDF-CRASH":
+        raise RuntimeError("boom interno")
+    if contenido == b"PDF-INCOHERENTE":
+        return _dian(cufe=cufe, numero="UI90-9", total_factura=Decimal("9999.00"))
+    if contenido == b"PDF-EMITIDA":
+        return _dian(
+            cufe=cufe,
+            numero="FV-77",
+            tipo="emitida",
+            nit_emisor=NIT_RODDOS,
+            nombre_emisor="RODDOS S.A.S.",
+            nit_adquiriente="800111222",
+        )
+    if contenido == b"PDF-AUTECO":
+        return _dian(
+            cufe=cufe,
+            numero="AU-1",
+            nit_emisor=NIT_AUTECO,
+            nombre_emisor="AUTECO S.A.S.",
+        )
+    return _dian(cufe=cufe, numero=f"UI90-{cufe[-6:]}")
+
+
+@pytest_asyncio.fixture
+async def api(monkeypatch):
+    monkeypatch.setenv("APP_ENV", "development")
+    monkeypatch.setenv("JWT_SECRET", "x" * 40)
+    monkeypatch.setenv("COOKIE_SECURE", "False")
+    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
+    get_settings.cache_clear()
+
+    app = create_app()
+    c = AsyncMongoMockClient(tz_aware=True)
+    await init_db(c)
+    for correo, rol in [
+        ("consulta@roddos.com", Role.consulta),
+        ("fin@roddos.com", Role.financiero),
+    ]:
+        await repository.create_user(
+            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
+        )
+    for clave, nit in [("NIT_RODDOS", NIT_RODDOS), ("NIT_AUTECO", NIT_AUTECO)]:
+        await Configuracion(
+            clave=clave, valor_json={"nit": nit}, vigente_desde="2026-01-01"
+        ).insert()
+    monkeypatch.setattr(ingesta, "_extraer_bytes", _fake_extraer_bytes)
+    transport = httpx.ASGITransport(app=app)
+    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
+        yield ac, c
+    repository.reset_auth()
+    reset_audit()
+    get_settings.cache_clear()
+
+
+async def init_db(c) -> None:
+    from beanie import init_beanie
+
+    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
+    repository.configure_auth(c, "compas_test")
+    configure_audit(c, "compas_test")
+
+
+async def _token(ac, email="fin@roddos.com") -> dict:
+    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
+    assert r.status_code == 200
+    return {"Authorization": f"Bearer {r.json()['access_token']}"}
+
+
+def _archivos(*contenidos: bytes, nombres: list[str] | None = None) -> list:
+    return [
+        (
+            "archivos",
+            ((nombres[i] if nombres else f"doc{i}.pdf"), cont, "application/pdf"),
+        )
+        for i, cont in enumerate(contenidos)
+    ]
+
+
+# ── RBAC: cargar exige iva:gestionar ({financiero, admin}), no dashboard:leer ──
+async def test_cargar_consulta_es_403(api):
+    ac, _ = api
+    h = await _token(ac, "consulta@roddos.com")
+    r = await ac.post(URL, files=_archivos(b"PDF-OK"), headers=h)
+    assert r.status_code == 403
+
+
+# ── Tope de lote: 20 archivos máximo (coherente con POST /api/v1/cargas) ──
+async def test_mas_de_20_archivos_413(api):
+    ac, _ = api
+    h = await _token(ac)
+    lote = _archivos(*[f"PDF-{i}".encode() for i in range(21)])
+    r = await ac.post(URL, files=lote, headers=h)
+    assert r.status_code == 413
+
+
+async def test_archivo_de_mas_de_10mb_se_rechaza_y_el_resto_se_procesa(api):
+    ac, _ = api
+    h = await _token(ac)
+    gordo = b"x" * (10 * 1024 * 1024 + 1)
+    r = await ac.post(URL, files=_archivos(gordo, b"PDF-OK"), headers=h)
+    assert r.status_code == 200
+    res = r.json()["resultados"]
+    assert res[0]["estado"] == "rechazada_no_dian"
+    assert "10 MB" in res[0]["motivo"]
+    assert res[1]["estado"] == "creada"
+
+
+async def test_extension_no_pdf_se_rechaza(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(
+        URL, files=_archivos(b"PDF-OK", nombres=["extracto.xlsx"]), headers=h
+    )
+    assert r.status_code == 200
+    res = r.json()["resultados"][0]
+    assert res["estado"] == "rechazada_no_dian"
+    assert ".pdf" in res["motivo"]
+    assert await Factura.count() == 0
+
+
+# ── Camino feliz: crea la factura con los campos DIAN mapeados ──
+async def test_cargar_recibida_crea_factura(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(URL, files=_archivos(b"PDF-OK"), headers=h)
+    assert r.status_code == 200
+    data = r.json()
+    assert data["resumen"]["creadas"] == 1
+    res = data["resultados"][0]
+    assert res["estado"] == "creada"
+    assert res["factura_id"]
+    # montos como string (regla 1)
+    assert res["datos_extraidos"]["iva_valor"] == "190.00"
+    assert res["datos_extraidos"]["total_factura"] == "1290.00"
+
+    f = await Factura.find_one(Factura.cufe == _cufe_de(b"PDF-OK"))
+    assert f is not None
+    assert f.tipo.value == "compra"  # recibida → compra
+    assert f.origen.value == "sin_clasificar"  # NIT no-Auteco → sin_clasificar
+    assert f.tercero_nit == "890900608"
+    assert f.tercero_nombre == "ALMACENES ÉXITO S.A"
+    assert f.iva_valor == Decimal("190.00")  # el IVA extraído, NO base×tarifa
+    assert f.total == Decimal("1290.00")
+    assert f.tarifa_iva is None  # DIAN puede mezclar tarifas; no se inventa una
+    # el Total Bruto DIAN va a total_bruto; base_gravable (base GRAVADA real) NO se
+    # conoce sin parsear líneas → None (R5: no se inventa). El "1000" del _dian es
+    # Total Bruto, no base gravada.
+    assert f.total_bruto == Decimal("1000.00")
+    assert f.base_gravable is None
+    assert f.archivo_ref is not None and "sha256:" in f.archivo_ref
+    assert f.deducible is False  # decisión explícita pendiente (pieza 7)
+
+
+# ── Candado del rename inc→inc_valor: INC>0 NUNCA se guarda en 0.00 ──
+async def test_inc_mayor_a_cero_queda_en_inc_valor(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(URL, files=_archivos(b"PDF-OK"), headers=h)
+    assert r.status_code == 200
+    f = await Factura.find_one(Factura.cufe == _cufe_de(b"PDF-OK"))
+    assert f.inc_valor == Decimal("100.00")
+    assert f.inc_valor != Decimal("0.00")
+
+
+# ── Pieza 5: PRECEDENCIA del iva_valor extraído sobre base×tarifa (D-13/§3.2) ──
+async def test_iva_extraido_manda_sobre_base_por_tarifa(api, monkeypatch):
+    """El iva_valor del bloque de totales DIAN se guarda tal cual; NO se recalcula
+    como base×0.19. Números del A1 real: base_gravable (Total Bruto, incluye líneas
+    sin IVA) 31.447,06 con IVA 1.452,94 → base×0.19 daría 5.974,94. Se guarda
+    1.452,94 y tarifa_iva=None (la DIAN puede mezclar tarifas)."""
+
+    def _mixta(contenido, nombre, nit_propio):
+        return _dian(
+            cufe=_cufe_de(contenido),
+            numero="MIX-1",
+            base_gravable=Decimal("31447.06"),
+            iva=Decimal("1452.94"),
+            inc=Decimal("0.00"),
+            total_impuesto=Decimal("1452.94"),
+            total_factura=Decimal("32900.00"),
+        )
+
+    monkeypatch.setattr(ingesta, "_extraer_bytes", _mixta)
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(URL, files=_archivos(b"PDF-MIXTA"), headers=h)
+    assert r.status_code == 200
+    assert r.json()["resultados"][0]["estado"] == "creada"
+    f = await Factura.find_one(Factura.cufe == _cufe_de(b"PDF-MIXTA"))
+    assert f.iva_valor == Decimal("1452.94")  # el extraído
+    assert f.iva_valor != Decimal("31447.06") * Decimal("0.19")  # NO total_bruto×tarifa
+    assert f.total_bruto == Decimal("31447.06")  # Total Bruto, no base gravada
+    assert f.base_gravable is None
+    assert f.tarifa_iva is None
+
+
+def test_campos_desde_dian_mapea_inc_a_inc_valor():
+    """Costura pura: el desajuste FacturaDian.inc→Factura.inc_valor guardaría un
+    cero en silencio; este test lo hace imposible."""
+    campos = ingesta.campos_desde_dian(_dian(), nit_auteco=NIT_AUTECO)
+    assert campos["inc_valor"] == Decimal("100.00")
+    assert "inc" not in campos  # el campo del Document se llama inc_valor
+
+
+def test_campos_desde_dian_total_bruto_no_base_gravable():
+    """Total Bruto DIAN → total_bruto; base_gravable=None (no es la base gravada)."""
+    campos = ingesta.campos_desde_dian(
+        _dian(base_gravable=Decimal("31447.06")), nit_auteco=NIT_AUTECO
+    )
+    assert campos["total_bruto"] == Decimal("31447.06")
+    assert campos["base_gravable"] is None
+
+
+async def test_datos_extraidos_muestra_total_bruto_no_base(api):
+    """El resultado por archivo rotula el Total Bruto como tal; base_gravable None."""
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(URL, files=_archivos(b"PDF-OK"), headers=h)
+    datos = r.json()["resultados"][0]["datos_extraidos"]
+    assert datos["total_bruto"] == "1000.00"
+    assert datos["base_gravable"] is None
+
+
+# ── Mapeos: emitida→venta · Auteco→origen auteco ──
+async def test_emitida_es_venta_con_tercero_adquiriente(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(URL, files=_archivos(b"PDF-EMITIDA"), headers=h)
+    assert r.status_code == 200
+    f = await Factura.find_one(Factura.cufe == _cufe_de(b"PDF-EMITIDA"))
+    assert f.tipo.value == "venta"
+    assert f.tercero_nit == "800111222"  # el adquiriente, no RODDOS
+    # el extractor no captura el nombre del adquiriente: se etiqueta con el NIT
+    # real (R5: no se inventa), la pantalla de confirmación lo corrige (pieza 7)
+    assert f.tercero_nombre == "NIT 800111222"
+    assert f.origen.value == "sin_clasificar"
+
+
+async def test_recibida_de_auteco_queda_origen_auteco(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(URL, files=_archivos(b"PDF-AUTECO"), headers=h)
+    assert r.status_code == 200
+    f = await Factura.find_one(Factura.cufe == _cufe_de(b"PDF-AUTECO"))
+    assert f.origen.value == "auteco"
+
+
+# ── Idempotencia (A2): mismo lote dos veces → todas duplicadas, ninguna nueva ──
+async def test_mismo_lote_dos_veces_todas_duplicadas(api):
+    ac, _ = api
+    h = await _token(ac)
+    lote = _archivos(b"PDF-OK", b"PDF-EMITIDA")
+    r1 = await ac.post(URL, files=lote, headers=h)
+    assert r1.json()["resumen"]["creadas"] == 2
+    r2 = await ac.post(URL, files=lote, headers=h)
+    assert r2.status_code == 200
+    assert [x["estado"] for x in r2.json()["resultados"]] == [
+        "duplicada",
+        "duplicada",
+    ]
+    assert r2.json()["resumen"]["creadas"] == 0
+    assert await Factura.count() == 2
+
+
+# ── Resultado PARCIAL con estados distinguibles (§2 bis: el radar de NC) ──
+async def test_resultado_parcial_y_estados_distinguibles(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(
+        URL,
+        files=_archivos(b"PDF-OK", b"PDF-NC", b"PDF-AJENO", b"PDF-CRASH"),
+        headers=h,
+    )
+    assert r.status_code == 200
+    estados = [x["estado"] for x in r.json()["resultados"]]
+    assert estados == [
+        "creada",
+        "rechazada_tipo_no_soportado",  # alimenta el contador del §2 bis
+        "rechazada_no_dian",
+        "error",
+    ]
+    resumen = r.json()["resumen"]
+    assert resumen["creadas"] == 1
+    assert resumen["rechazadas_tipo_no_soportado"] == 1
+    assert resumen["rechazadas_no_dian"] == 1
+    assert resumen["errores"] == 1
+    assert await Factura.count() == 1  # el crash del archivo 4 no frenó al 1
+
+
+# ── A6: incoherente → requiere_confirmacion, NADA se persiste ──
+async def test_incoherente_requiere_confirmacion_sin_persistir(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(URL, files=_archivos(b"PDF-INCOHERENTE"), headers=h)
+    assert r.status_code == 200
+    res = r.json()["resultados"][0]
+    assert res["estado"] == "requiere_confirmacion"
+    assert res["factura_id"] is None
+    # los datos extraídos viajan al cliente para la pantalla de confirmación
+    assert res["datos_extraidos"]["total_factura"] == "9999.00"
+    assert res["datos_extraidos"]["iva_valor"] == "190.00"
+    assert await Factura.count() == 0  # ningún documento fiscal a medio registrar
+
+
+# ── Config ausente: sin NIT_RODDOS no se puede deducir el tipo → 409 accionable ──
+async def test_sin_nit_roddos_configurado_409(monkeypatch):
+    monkeypatch.setenv("APP_ENV", "development")
+    monkeypatch.setenv("JWT_SECRET", "x" * 40)
+    monkeypatch.setenv("COOKIE_SECURE", "False")
+    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
+    get_settings.cache_clear()
+    app = create_app()
+    c = AsyncMongoMockClient(tz_aware=True)
+    await init_db(c)  # SIN sembrar NIT_RODDOS
+    await repository.create_user(
+        User(
+            email="fin@roddos.com",
+            password_hash=passwords.hash_password(PWD),
+            rol=Role.financiero,
+        )
+    )
+    transport = httpx.ASGITransport(app=app)
+    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
+        h = await _token(ac)
+        r = await ac.post(URL, files=_archivos(b"PDF-OK"), headers=h)
+        assert r.status_code == 409
+        assert "NIT_RODDOS" in r.json()["detail"]
+    repository.reset_auth()
+    reset_audit()
+
+
+# ── Auditoría: factura.creada por cada creada; fail-closed → compensar ──
+async def test_cargar_emite_factura_creada(api):
+    ac, c = api
+    h = await _token(ac)
+    await ac.post(URL, files=_archivos(b"PDF-OK"), headers=h)
+    eventos = await c["compas_test"]["audit_log"].find(
+        {"evento": "factura.creada"}
+    ).to_list(10)
+    assert len(eventos) == 1
+
+
+async def test_audit_caido_no_deja_factura(api, monkeypatch):
+    async def _explota(*a, **kw):
+        raise RuntimeError("audit caído")
+
+    monkeypatch.setattr(ingesta, "emit_audit", _explota)
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(URL, files=_archivos(b"PDF-OK"), headers=h)
+    assert r.status_code == 200
+    assert r.json()["resultados"][0]["estado"] == "error"
+    assert await Factura.count() == 0  # saga O1: sin rastro no hay alta
+
+
+# ── E2E con el PDF real (cubre _extraer_bytes + threadpool de verdad, A16) ──
+_FIXTURE = (
+    Path(__file__).parent / "fixtures" / "dian_factura_venta_exito_2026-05-28.pdf"
+)
+
+
+# Capturado ANTES de que el fixture `api` monkeypatchee el módulo: el E2E lo
+# restaura para cubrir pdfplumber + temp file + threadpool de verdad.
+_REAL_EXTRAER = ingesta._extraer_bytes
+
+
+@pytest.mark.skipif(
+    not _FIXTURE.exists(),
+    reason="falta el PDF de muestra en backend/tests/fixtures/",
+)
+async def test_e2e_pdf_real_crea_y_deduplica(api, monkeypatch):
+    monkeypatch.setattr(ingesta, "_extraer_bytes", _REAL_EXTRAER)
+    ac, _ = api
+    h = await _token(ac)
+    contenido = _FIXTURE.read_bytes()
+    files = _archivos(contenido, nombres=[_FIXTURE.name])
+    r1 = await ac.post(URL, files=files, headers=h)
+    assert r1.status_code == 200
+    res = r1.json()["resultados"][0]
+    assert res["estado"] == "creada"
+    assert res["datos_extraidos"]["iva_valor"] == "1452.94"  # A1
+    r2 = await ac.post(URL, files=files, headers=h)
+    assert r2.json()["resultados"][0]["estado"] == "duplicada"
diff --git a/backend/tests/test_facturas_endpoints.py b/backend/tests/test_facturas_endpoints.py
index 66b1c7d..fedd230 100644
--- a/backend/tests/test_facturas_endpoints.py
+++ b/backend/tests/test_facturas_endpoints.py
@@ -6,6 +6,8 @@ admin} → consulta/directivo reciben 403. Montos como string (regla 1). La liqu
 se calcula en el backend y se sirve por GET /facturas/liquidacion (lo consume la vista).
 """
 
+from decimal import Decimal
+
 import httpx
 import pytest_asyncio
 from app.audit.service import configure_audit, reset_audit
@@ -83,6 +85,40 @@ async def test_crear_factura_201_calcula_iva(api):
     assert data["periodo"] == "2026-C1"  # derivado de la fecha (cuatrimestral default)
 
 
+async def test_crear_factura_tarifa_no_legal_es_422(api):
+    """Pieza 6: endurecer tarifa_iva a las tarifas IVA legales en Colombia
+    (0, 0.05, 0.19). 0.16 (tarifa vieja) → 422, no se guarda."""
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post("/api/v1/facturas", json=_compra(tarifa_iva="0.16"), headers=h)
+    assert r.status_code == 422
+    assert "tarifa" in r.json()["detail"].lower()
+
+
+async def test_crear_factura_tarifa_exenta_cero_ok(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(
+        "/api/v1/facturas",
+        json=_compra(numero="FC-EX", tarifa_iva="0", base_gravable="1000000"),
+        headers=h,
+    )
+    assert r.status_code == 201
+    assert r.json()["iva_valor"] == "0.00"
+
+
+async def test_crear_factura_tarifa_reducida_5pct_ok(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(
+        "/api/v1/facturas",
+        json=_compra(numero="FC-5", tarifa_iva="0.05", base_gravable="1000000"),
+        headers=h,
+    )
+    assert r.status_code == 201
+    assert r.json()["iva_valor"] == "50000.00"
+
+
 async def test_crear_factura_consulta_es_403(api):
     ac, _ = api
     h = await _token(ac, "consulta@roddos.com")
@@ -114,6 +150,181 @@ async def test_listar_y_anular(api):
     assert rl.json() == []
 
 
+# ── A17 / punto 4: PII (Ley 1581) — facturas:ver_detalle {financiero, admin} ──
+async def test_listado_minimiza_pii_sin_ver_detalle(api):
+    """consulta tiene dashboard:leer pero NO facturas:ver_detalle → el listado le
+    oculta tercero_nombre/tercero_nit (PII); el resto de campos visibles."""
+    ac, _ = api
+    hfin = await _token(ac)
+    await ac.post("/api/v1/facturas", json=_compra(), headers=hfin)
+
+    hcon = await _token(ac, "consulta@roddos.com")
+    r = await ac.get("/api/v1/facturas", headers=hcon)
+    assert r.status_code == 200
+    fila = r.json()[0]
+    assert fila["tercero_nombre"] is None
+    assert fila["tercero_nit"] is None
+    assert fila["iva_valor"] == "190000.00"  # el número de IVA sí es visible
+
+
+async def _insert_factura(numero, tipo_contribuyente):
+    from app.domain.factura import Factura
+
+    await Factura(
+        tipo="compra",
+        origen="sin_clasificar",
+        numero=numero,
+        tercero_nombre="Contraparte X",
+        tercero_nit="900123",
+        fecha="2026-05-10",
+        base_gravable=None,
+        total_bruto=Decimal("1000.00"),
+        tarifa_iva=None,
+        iva_valor=Decimal("190.00"),
+        total=Decimal("1190.00"),
+        deducible=False,
+        tipo_contribuyente=tipo_contribuyente,
+    ).insert()
+
+
+async def test_listado_persona_juridica_visible_para_consulta(api):
+    """La razón social de una persona jurídica NO es PII → visible para consulta
+    aunque no tenga facturas:ver_detalle."""
+    ac, _ = api
+    await _token(ac)  # asegura beanie/app arriba
+    await _insert_factura("J-1", "persona_juridica")
+    r = await ac.get(
+        "/api/v1/facturas", headers=await _token(ac, "consulta@roddos.com")
+    )
+    fila = next(f for f in r.json() if f["numero"] == "J-1")
+    assert fila["tercero_nombre"] == "Contraparte X"
+    assert fila["tercero_nit"] == "900123"
+
+
+async def test_listado_persona_natural_enmascarada_para_consulta(api):
+    ac, _ = api
+    await _token(ac)
+    await _insert_factura("N-1", "persona_natural")
+    # consulta (sin ver_detalle) → enmascarada
+    rc = await ac.get(
+        "/api/v1/facturas", headers=await _token(ac, "consulta@roddos.com")
+    )
+    fc = next(f for f in rc.json() if f["numero"] == "N-1")
+    assert fc["tercero_nombre"] is None and fc["tercero_nit"] is None
+    # financiero (con ver_detalle) → visible
+    rf = await ac.get("/api/v1/facturas", headers=await _token(ac))
+    ff = next(f for f in rf.json() if f["numero"] == "N-1")
+    assert ff["tercero_nombre"] == "Contraparte X"
+
+
+async def test_listado_contribuyente_desconocido_enmascarado_para_consulta(api):
+    """None (captura manual o PDF sin dato) → PII por precaución."""
+    ac, _ = api
+    await _token(ac)
+    await _insert_factura("U-1", None)
+    r = await ac.get(
+        "/api/v1/facturas", headers=await _token(ac, "consulta@roddos.com")
+    )
+    fila = next(f for f in r.json() if f["numero"] == "U-1")
+    assert fila["tercero_nombre"] is None and fila["tercero_nit"] is None
+
+
+async def test_listado_muestra_pii_con_ver_detalle(api):
+    ac, _ = api
+    h = await _token(ac)  # financiero
+    await ac.post("/api/v1/facturas", json=_compra(), headers=h)
+    r = await ac.get("/api/v1/facturas", headers=h)
+    fila = r.json()[0]
+    assert fila["tercero_nombre"] == "Auteco S.A.S."
+    assert fila["tercero_nit"] == "860024781"
+
+
+async def test_detalle_factura_requiere_ver_detalle(api):
+    ac, _ = api
+    h = await _token(ac)
+    fid = (await ac.post("/api/v1/facturas", json=_compra(), headers=h)).json()["id"]
+
+    rcon = await ac.get(
+        f"/api/v1/facturas/{fid}", headers=await _token(ac, "consulta@roddos.com")
+    )
+    assert rcon.status_code == 403
+
+    rfin = await ac.get(f"/api/v1/facturas/{fid}", headers=h)
+    assert rfin.status_code == 200
+    assert rfin.json()["tercero_nit"] == "860024781"  # PII completa para autorizado
+
+
+async def test_liquidacion_visible_para_directivo(api):
+    """GET /liquidacion se queda bajo dashboard:leer: el directivo ve el número de
+    IVA (lo que NO ve es la contraparte, cubierto por el listado/detalle)."""
+    ac, _ = api
+    r = await ac.get(
+        "/api/v1/facturas/liquidacion", headers=await _token(ac, "consulta@roddos.com")
+    )
+    assert r.status_code == 200
+
+
+async def test_a10_ejemplo_aritmetico_spec_6_end_to_end(api):
+    """A10: el ejemplo §6 reproduce EXACTO el arrastre y el pago, vía el endpoint
+    real GET /facturas/liquidacion. IVA exacto (sin base×tarifa) insertando facturas
+    estilo DIAN (base_gravable=None). La NO deducible queda registrada pero excluida
+    del descontable."""
+    from app.domain.factura import Factura
+
+    async def _ins(numero, tipo, fecha, iva, deducible):
+        iva_d = Decimal(iva)
+        # total_bruto plausible (base 19% = iva/0.19) y total = total_bruto + iva:
+        # una factura aritméticamente válida (no total == solo el impuesto). Las
+        # aserciones de la liquidación dependen de iva_valor+deducible, no de esto.
+        bruto = (iva_d / Decimal("0.19")).quantize(Decimal("0.01"))
+        await Factura(
+            tipo=tipo,
+            origen="sin_clasificar",
+            numero=numero,
+            tercero_nombre="Contraparte",
+            tercero_nit="900",
+            fecha=fecha,
+            base_gravable=None,
+            total_bruto=bruto,
+            tarifa_iva=None,
+            iva_valor=iva_d,
+            total=bruto + iva_d,
+            deducible=deducible,
+        ).insert()
+
+    # C2-2026 (may–ago)
+    await _ins("R-1", "compra", "2026-05-28", "1452.94", True)
+    await _ins("R-2", "compra", "2026-06-15", "19000000.00", True)
+    await _ins("E-1", "venta", "2026-05-10", "8000000.00", False)
+    # C3-2026 (sep–dic)
+    await _ins("E-2", "venta", "2026-09-15", "15000000.00", False)
+    await _ins("R-3", "compra", "2026-10-01", "2000000.00", True)
+    await _ins("R-4", "compra", "2026-11-01", "500000.00", False)  # NO deducible
+
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.get("/api/v1/facturas/liquidacion", headers=h)
+    assert r.status_code == 200
+    periodos = {p["etiqueta"]: p for p in r.json()["periodos"]}
+
+    c2 = periodos["2026-C2"]
+    assert c2["generado"] == "8000000.00"
+    assert c2["descontable"] == "19001452.94"  # 1452.94 + 19.000.000
+    assert c2["neto_a_pagar"] == "0.00"  # saldo a favor, nunca pago negativo
+    assert c2["saldo_favor_nuevo"] == "11001452.94"  # se arrastra
+
+    c3 = periodos["2026-C3"]
+    assert c3["generado"] == "15000000.00"
+    assert c3["descontable"] == "2000000.00"  # los 500.000 NO deducibles quedan fuera
+    assert c3["saldo_favor_previo"] == "11001452.94"  # arrastre del C2
+    assert c3["neto_a_pagar"] == "1998547.06"
+    assert c3["saldo_favor_nuevo"] == "0.00"  # arrastre agotado
+
+    # la NO deducible SÍ está registrada (excluida del descontable, no del registro)
+    rl = await ac.get("/api/v1/facturas?activo=true", headers=h)
+    assert any(f["numero"] == "R-4" for f in rl.json())
+
+
 async def test_liquidacion_cuatrimestral(api):
     ac, _ = api
     h = await _token(ac)
diff --git a/backend/tests/test_rbac_permissions.py b/backend/tests/test_rbac_permissions.py
index 21b53dd..c192cb3 100644
--- a/backend/tests/test_rbac_permissions.py
+++ b/backend/tests/test_rbac_permissions.py
@@ -32,6 +32,8 @@ CANONICA: dict[str, set[Role]] = {
     "proyeccion:gestionar": {Role.financiero, Role.admin},
     # CR "Fidelidad de caja" (C11 IVA): carga de facturas + liquidación
     "iva:gestionar": {Role.financiero, Role.admin},
+    # E2 A17 (Ley 1581): ver detalle de factura + PII de la contraparte
+    "facturas:ver_detalle": {Role.financiero, Role.admin},
     # §2.4 — autoridad del ciclo (manda sobre §4.1)
     "ciclo:abrir": {Role.financiero, Role.directivo, Role.admin},
     "ciclo:proponer": {Role.financiero, Role.directivo, Role.admin},
```
