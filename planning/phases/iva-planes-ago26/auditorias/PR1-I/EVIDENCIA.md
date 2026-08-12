# EVIDENCIA — iva-planes-ago26 PR1-I (retroactiva PRs #90-#94)

Diffs REALES de los 5 merges (squash/feature commits en main) + salidas de tests.


---

## Commit 66518ce

```diff
commit 66518ce9fbd3ef233d1a7c903ba704365d140432
Author: roddoscol <info@roddos.com>
Date:   Tue Aug 11 09:17:51 2026 -0500

    feat(iva): C2' — import masivo del Excel de documentos recibidos DIAN
    
    El módulo que faltaba en /iva: cargar de una vez las facturas emitidas A
    NOMBRE DE RODDOS (gasto con IVA potencialmente deducible) desde el Excel
    del portal DIAN, en el MISMO panel de carga de los PDF.
    
    Backend (POST /facturas/cargar-excel, iva:gestionar):
    - Parser excel_dian.py CALIBRADO CONTRA EL EXPORT REAL (528 filas, ene1-
      ago10 2026: 0 errores de parseo en el dry-run): contrato de columnas
      explícito y fail-loud (encabezados que no cuadran → 422 LISTANDO
      esperado vs encontrado — regla 7), fechas dd-mm-yyyy string, montos
      numéricos o texto es-CO, retenciones/INC opcionales mapeadas.
    - Tipos reales del portal: 'Factura electrónica' (a secas) y 'de
      contingencia' entran; notas crédito y documentos equivalentes (POS,
      transporte) se rechazan con motivo (radar E2.1). Filas EMITIDAS por
      RODDOS (36 en el export real) se rechazan con motivo — este importador
      es solo de recibidas; el IVA generado se registra aparte (E3).
    - UN solo camino de escritura: persistir_factura_ingesta() extraído de la
      ingesta PDF (dedup CUFE + índices únicos + factura.creada fail-closed
      saga O1) y compartido por ambas rutas — la PDF queda refactorizada con
      comportamiento idéntico (regresión verde). Deducibilidad: False/sin
      decidir (decide el operador, §2 del spec E2); Auteco por NIT de config
      → deducible/decidida/origen auteco. Resultado POR FILA con los mismos
      estados del lote PDF.
    
    Frontend: el CargaPanel de /iva acepta .xlsx (drag & drop y selector),
    lo enruta al endpoint masivo, y el MOTIVO del backend manda sobre los
    textos fijos de los PDF. 9 tests backend (TDD rojo→verde) + 3 frontend.
    
    El xlsx real NO entra al repo (PII de proveedores); los fixtures son
    sintéticos con el contrato de encabezados real (regla 12).
    
    Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
---
 backend/app/facturas/excel_dian.py              | 267 ++++++++++++++++++++++++
 backend/app/facturas/ingesta.py                 | 219 ++++++++++++++-----
 backend/app/facturas/router.py                  |  30 +++
 backend/tests/test_facturas_cargar_excel.py     | 265 +++++++++++++++++++++++
 frontend/src/components/iva/CargaPanel.test.tsx | 110 ++++++++++
 frontend/src/components/iva/CargaPanel.tsx      |  26 ++-
 frontend/src/lib/facturas.ts                    |  17 ++
 7 files changed, 875 insertions(+), 59 deletions(-)

diff --git a/backend/app/facturas/excel_dian.py b/backend/app/facturas/excel_dian.py
new file mode 100644
index 0000000..cbf1e4f
--- /dev/null
+++ b/backend/app/facturas/excel_dian.py
@@ -0,0 +1,267 @@
+# backend/app/facturas/excel_dian.py
+"""C2' (acta FABS 2026-08-10) — import masivo del Excel de "documentos recibidos"
+del portal DIAN: las facturas emitidas A NOMBRE DE RODDOS (gasto con IVA
+potencialmente deducible), una fila por documento.
+
+Regla 7 (parsers transforman, NUNCA interpretan), aplicada en tres capas:
+  1. CONTRATO DE COLUMNAS explícito (`COLUMNAS`): si los encabezados del archivo
+     real no cuadran, el error LISTA esperado vs encontrado — ese mensaje es el
+     punto de calibración con el export real, no un fallo silencioso.
+  2. Fila ilegible (fecha/monto ambiguos) → error de ESA fila con motivo; las
+     demás siguen (resultado parcial, mismo criterio de la ingesta PDF).
+  3. Nada se adivina: tipo de documento no soportado (NC/ND) o una fila EMITIDA
+     por RODDOS se rechazan con motivo, jamás se ingresan "corregidas".
+
+Persistencia y auditoría: la MISMA ruta que la ingesta PDF (dedup por CUFE +
+DuplicateKeyError + `factura.creada` fail-closed saga O1) vía
+`ingesta.persistir_factura_ingesta` — un solo camino de escritura.
+Deducibilidad: default False/sin decidir (el operador decide, §2 del spec E2);
+Auteco por NIT de Configuracion → True/decidida/origen auteco (CEO 2026-07-31).
+"""
+
+import re
+import unicodedata
+from datetime import date, datetime
+from decimal import Decimal, InvalidOperation
+from io import BytesIO
+
+from openpyxl import load_workbook
+
+from app.domain.factura import OrigenFactura, TipoFactura
+
+MAX_FILAS_BUSQUEDA_ENCABEZADO = 15
+
+# ── Contrato de columnas (EL punto de calibración con el export real) ─────────
+# clave interna → alias aceptados (normalizados: minúsculas, sin tildes).
+# `cufe` matchea por CONTAINS (el portal usa "CUFE/CUDE" o el nombre largo);
+# el resto por igualdad exacta contra alguno de sus alias.
+COLUMNAS: dict[str, tuple[str, ...]] = {
+    "tipo_documento": ("tipo de documento", "tipo documento"),
+    "folio": ("folio", "numero de documento", "número de documento"),
+    "cufe": ("cufe",),  # contains
+    "fecha": ("fecha emision", "fecha de emision"),
+    "nit_emisor": ("nit emisor", "nit del emisor"),
+    "nombre_emisor": ("nombre emisor", "razon social emisor", "nombre del emisor"),
+    "iva": ("iva",),
+    "total": ("total", "total factura"),
+}
+OPCIONALES: dict[str, tuple[str, ...]] = {
+    "prefijo": ("prefijo",),
+    "nit_receptor": ("nit receptor",),
+    "inc": ("inc",),
+    "bolsas": ("inc bolsas",),
+    "rete_iva": ("rete iva",),
+    "rete_fuente": ("rete renta",),
+    "rete_ica": ("rete ica",),
+}
+
+# Calibrado contra el export REAL del portal (FACTURACION DIAN ENE1-AGO10 2026):
+# el tipo viene como "Factura electrónica" (a secas) o "Factura electrónica de
+# contingencia"; las notas crédito como "Nota de crédito electrónica". Los
+# documentos equivalentes (POS, transporte) NO soportan IVA descontable sin
+# factura → se rechazan con motivo.
+_TIPO_FACTURA_PREFIJO = "factura electronica"
+_MONTO_ES_CO = re.compile(r"^\d{1,3}(\.\d{3})*(,\d+)?$")
+_MONTO_PLANO = re.compile(r"^\d+(\.\d+)?$")
+
+
+class EncabezadosNoReconocidos(Exception):
+    """Los encabezados del archivo no cuadran con el contrato (regla 7)."""
+
+
+class FilaIlegible(Exception):
+    """Una fila puntual no se pudo transformar sin interpretar."""
+
+
+def _norm(v: object) -> str:
+    s = str(v or "").strip().lower()
+    s = unicodedata.normalize("NFKD", s)
+    return "".join(c for c in s if not unicodedata.combining(c))
+
+
+def _mapear_encabezados(celdas: list[object]) -> dict[str, int] | None:
+    """Fila de celdas → {clave: índice} si TODAS las requeridas resuelven."""
+    normalizadas = [_norm(c) for c in celdas]
+    mapa: dict[str, int] = {}
+    for clave, alias in {**COLUMNAS, **OPCIONALES}.items():
+        for i, h in enumerate(normalizadas):
+            if not h:
+                continue
+            if clave == "cufe":
+                if "cufe" in h:
+                    mapa[clave] = i
+                    break
+            elif h in alias:
+                mapa[clave] = i
+                break
+    if all(k in mapa for k in COLUMNAS):
+        return mapa
+    return None
+
+
+def _fecha_iso(v: object, fila: int) -> str:
+    if isinstance(v, datetime):
+        return v.date().isoformat()
+    if isinstance(v, date):
+        return v.isoformat()
+    s = str(v or "").strip()
+    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
+        try:
+            return datetime.strptime(s, fmt).date().isoformat()
+        except ValueError:
+            continue
+    raise FilaIlegible(
+        f"fila {fila}: fecha de emisión ilegible ('{s}'); se esperaba una fecha "
+        "de Excel o 'YYYY-MM-DD' / 'DD/MM/YYYY'"
+    )
+
+
+def _monto(v: object, campo: str, fila: int) -> Decimal:
+    if isinstance(v, Decimal):
+        return v
+    if isinstance(v, (int, float)):
+        return Decimal(str(v))
+    s = str(v or "").strip()
+    try:
+        if _MONTO_ES_CO.match(s):
+            return Decimal(s.replace(".", "").replace(",", "."))
+        if _MONTO_PLANO.match(s):
+            return Decimal(s)
+    except InvalidOperation:
+        pass
+    raise FilaIlegible(
+        f"fila {fila}: {campo} ilegible ('{s}'); se esperaba un número o "
+        "formato es-CO ('1.452,94')"
+    )
+
+
+def _monto_opcional(v: object, campo: str, fila: int) -> Decimal:
+    """Columna opcional: celda vacía/ausente → 0 (el export trae '0' explícito;
+    ausencia de la COLUMNA no es dato → 0 sin inventar nada más)."""
+    if v in (None, ""):
+        return Decimal("0.00")
+    return _monto(v, campo, fila)
+
+
+def parsear_excel(contenido: bytes) -> list[dict]:
+    """bytes del .xlsx → filas crudas [{fila, tipo_documento, cufe, numero, ...}].
+
+    Levanta `EncabezadosNoReconocidos` (archivo entero, con esperado vs encontrado)
+    o marca por fila con {'error': motivo} — el lote sigue (regla 7 + parcial)."""
+    wb = load_workbook(BytesIO(contenido), read_only=True, data_only=True)
+    ws = wb.active
+
+    mapa: dict[str, int] | None = None
+    fila_encabezado = 0
+    mejores: list[str] = []
+    for i, row in enumerate(ws.iter_rows(max_row=MAX_FILAS_BUSQUEDA_ENCABEZADO), 1):
+        celdas = [c.value for c in row]
+        mapa = _mapear_encabezados(celdas)
+        if mapa is not None:
+            fila_encabezado = i
+            break
+        con_texto = [str(c) for c in celdas if c not in (None, "")]
+        if len(con_texto) > len(mejores):
+            mejores = con_texto
+    if mapa is None:
+        esperadas = ", ".join(sorted(a[0] for a in COLUMNAS.values()))
+        encontradas = ", ".join(mejores) or "(ninguna)"
+        raise EncabezadosNoReconocidos(
+            "encabezados no reconocidos en el Excel: se esperaba una fila con "
+            f"[{esperadas}] (más 'cufe'); lo más parecido fue [{encontradas}]. "
+            "Verifica que sea el export de 'Documentos recibidos' del portal DIAN."
+        )
+
+    filas: list[dict] = []
+    for n, row in enumerate(
+        ws.iter_rows(min_row=fila_encabezado + 1), fila_encabezado + 1
+    ):
+        celdas = [c.value for c in row]
+        if all(c in (None, "") for c in celdas):
+            continue
+
+        def celda(clave: str, _celdas: list[object] = celdas) -> object:
+            # bind explícito por default-arg (B023): la closure se consume en
+            # este mismo ciclo, pero el bind elimina la clase entera de bug.
+            idx = mapa.get(clave)
+            return (
+                _celdas[idx] if idx is not None and idx < len(_celdas) else None
+            )
+
+        try:
+            prefijo = str(celda("prefijo") or "").strip()
+            folio = str(celda("folio") or "").strip()
+            if not folio:
+                raise FilaIlegible(f"fila {n}: sin folio/número de documento")
+            cufe = str(celda("cufe") or "").strip()
+            if not cufe:
+                raise FilaIlegible(f"fila {n}: sin CUFE")
+            filas.append(
+                {
+                    "fila": n,
+                    "tipo_documento": str(celda("tipo_documento") or "").strip(),
+                    "numero": f"{prefijo}{folio}",
+                    "cufe": cufe,
+                    "fecha": _fecha_iso(celda("fecha"), n),
+                    "nit_emisor": str(celda("nit_emisor") or "").strip(),
+                    "nombre_emisor": str(celda("nombre_emisor") or "").strip(),
+                    "iva": _monto(celda("iva"), "IVA", n),
+                    "total": _monto(celda("total"), "Total", n),
+                    "nit_receptor": str(celda("nit_receptor") or "").strip(),
+                    "inc": _monto_opcional(celda("inc"), "INC", n),
+                    "bolsas": _monto_opcional(celda("bolsas"), "INC Bolsas", n),
+                    "rete_iva": _monto_opcional(celda("rete_iva"), "Rete IVA", n),
+                    "rete_fuente": _monto_opcional(
+                        celda("rete_fuente"), "Rete Renta", n
+                    ),
+                    "rete_ica": _monto_opcional(celda("rete_ica"), "Rete ICA", n),
+                }
+            )
+        except FilaIlegible as e:
+            filas.append({"fila": n, "error": str(e)})
+    return filas
+
+
+def campos_desde_fila(
+    fila: dict, *, nit_auteco: str | None
+) -> dict:
+    """Fila cruda válida → campos del Document Factura (compra recibida).
+
+    Misma semántica de deducibilidad que `ingesta.campos_desde_dian`: Auteco por
+    NIT → deducible/decidida/origen auteco; el resto sin decidir (el operador
+    marca después — contador del §2). El Excel de la DIAN no trae total bruto ni
+    base gravada por línea → None (R5: no se inventa)."""
+    es_auteco = nit_auteco is not None and fila["nit_emisor"] == nit_auteco
+    nombre = fila["nombre_emisor"] or f"NIT {fila['nit_emisor']}"
+    return {
+        "tipo": TipoFactura.compra,
+        "origen": OrigenFactura.auteco if es_auteco else OrigenFactura.sin_clasificar,
+        "numero": fila["numero"],
+        "tercero_nombre": nombre,
+        "tercero_nit": fila["nit_emisor"],
+        "fecha": fila["fecha"],
+        "base_gravable": None,
+        "total_bruto": None,
+        "tarifa_iva": None,
+        "iva_valor": fila["iva"],
+        "total": fila["total"],
+        "deducible": es_auteco,
+        "deducible_decidido": es_auteco,
+        "cufe": fila["cufe"],
+        "tipo_documento": fila["tipo_documento"],
+        "signo": 1,
+        # el export no trae tipo de contribuyente → None = se trata como PII
+        # por precaución (A17), igual que la captura manual.
+        "tipo_contribuyente": None,
+        "inc_valor": fila.get("inc", Decimal("0.00")),
+        "bolsas": fila.get("bolsas", Decimal("0.00")),
+        "otros_impuestos": Decimal("0.00"),
+        "rete_fuente": fila.get("rete_fuente", Decimal("0.00")),
+        "rete_iva": fila.get("rete_iva", Decimal("0.00")),
+        "rete_ica": fila.get("rete_ica", Decimal("0.00")),
+    }
+
+
+def es_tipo_soportado(tipo_documento: str) -> bool:
+    n = _norm(tipo_documento)
+    return n.startswith(_TIPO_FACTURA_PREFIJO) and "nota" not in n
diff --git a/backend/app/facturas/ingesta.py b/backend/app/facturas/ingesta.py
index ae236c8..6e19bb2 100644
--- a/backend/app/facturas/ingesta.py
+++ b/backend/app/facturas/ingesta.py
@@ -41,6 +41,11 @@ from app.audit.service import emit_audit
 from app.core.money import money_str
 from app.domain.configuracion import ClaveConfig, Configuracion
 from app.domain.factura import Factura, OrigenFactura, TipoFactura
+from app.facturas.excel_dian import (
+    campos_desde_fila,
+    es_tipo_soportado,
+    parsear_excel,
+)
 from app.facturas.extraccion import (
     DocumentoNoDian,
     FacturaDian,
@@ -215,6 +220,71 @@ def _resultado(
     }
 
 
+async def persistir_factura_ingesta(
+    campos: dict,
+    *,
+    usuario_id: str,
+    via: str,
+    etiqueta: str,
+    archivo_ref: str | None,
+    datos: dict | None = None,
+) -> dict:
+    """El ÚNICO camino de escritura de la ingesta (PDF y Excel): pre-check de
+    CUFE, insert con la garantía dura de los índices únicos, y `factura.creada`
+    fail-closed (saga O1). Devuelve el dict-resultado de la pieza procesada."""
+    if (
+        campos.get("cufe")
+        and await Factura.find_one(Factura.cufe == campos["cufe"]) is not None
+    ):
+        return _resultado(
+            etiqueta,
+            EstadoIngesta.duplicada,
+            motivo="ya existe una factura con este CUFE",
+            datos=datos,
+        )
+
+    factura = Factura(**campos, archivo_ref=archivo_ref)
+    try:
+        await factura.insert()
+    except DuplicateKeyError:
+        # carrera del pre-check (cufe_unico) o carga manual previa con el mismo
+        # par NIT+número (nit_numero_unico): en ambos casos ya está registrada
+        return _resultado(
+            etiqueta,
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
+                "via": via,
+                "numero": factura.numero,
+                "cufe": factura.cufe,
+                "tipo": factura.tipo.value,
+                "origen": factura.origen.value,
+                "iva_valor": money_str(factura.iva_valor),
+                # deja el valor DECIDIDO en el rastro (Auteco → True por config); no
+                # exige un evento nuevo (la decisión viaja con origen=auteco).
+                "deducible": factura.deducible,
+                "deducible_decidido": factura.deducible_decidido,
+            },
+        )
+    except Exception:
+        await factura.delete()  # saga O1: sin rastro de auditoría no hay alta
+        raise
+    return _resultado(
+        etiqueta, EstadoIngesta.creada, factura_id=str(factura.id), datos=datos
+    )
+
+
 async def _procesar_archivo(
     archivo: UploadFile,
     *,
@@ -268,58 +338,13 @@ async def _procesar_archivo(
             datos=datos,
         )
 
-    # Pre-check de CUFE (legible, NO atómico); la garantía dura es el índice
-    # único cufe_unico + el DuplicateKeyError de abajo.
-    if await Factura.find_one(Factura.cufe == dian.cufe) is not None:
-        return _resultado(
-            nombre,
-            EstadoIngesta.duplicada,
-            motivo="ya existe una factura con este CUFE",
-            datos=datos,
-        )
-
-    factura = Factura(
-        **campos,
+    return await persistir_factura_ingesta(
+        campos,
+        usuario_id=usuario_id,
+        via="ingesta_dian",
+        etiqueta=nombre,
         archivo_ref=f"sha256:{hashlib.sha256(contenido).hexdigest()}",
-    )
-    try:
-        await factura.insert()
-    except DuplicateKeyError:
-        # carrera del pre-check (cufe_unico) o carga manual previa con el mismo
-        # par NIT+número (nit_numero_unico): en ambos casos ya está registrada
-        return _resultado(
-            nombre,
-            EstadoIngesta.duplicada,
-            motivo="ya existe una factura con este CUFE o con el mismo "
-            "número para este NIT",
-            datos=datos,
-        )
-    try:
-        await emit_audit(
-            AuditEvento.factura_creada,
-            entidad="factura",
-            entidad_id=str(factura.id),
-            actor_id=usuario_id,
-            # sin nombre de archivo ni NIT/nombre del tercero: puede ser cédula/
-            # persona natural (PII, Ley 1581 / A17). CUFE+número identifican.
-            metadata={
-                "via": "ingesta_dian",
-                "numero": factura.numero,
-                "cufe": factura.cufe,
-                "tipo": factura.tipo.value,
-                "origen": factura.origen.value,
-                "iva_valor": money_str(factura.iva_valor),
-                # deja el valor DECIDIDO en el rastro (Auteco → True por config); no
-                # exige un evento nuevo (la decisión viaja con origen=auteco).
-                "deducible": factura.deducible,
-                "deducible_decidido": factura.deducible_decidido,
-            },
-        )
-    except Exception:
-        await factura.delete()  # saga O1: sin rastro de auditoría no hay alta
-        raise
-    return _resultado(
-        nombre, EstadoIngesta.creada, factura_id=str(factura.id), datos=datos
+        datos=datos,
     )
 
 
@@ -363,3 +388,95 @@ async def procesar_lote(archivos: list[UploadFile], *, usuario_id: str) -> dict:
     for r in resultados:
         resumen[_PLURAL[EstadoIngesta(r["estado"])]] += 1
     return {"resultados": resultados, "resumen": resumen}
+
+
+async def procesar_lote_excel(
+    contenido: bytes, *, usuario_id: str
+) -> dict:
+    """C2' — import masivo del Excel de documentos recibidos del portal DIAN.
+    Resultado POR FILA con los mismos estados del lote PDF (el frontend pinta
+    ambos con el mismo componente); `EncabezadosNoReconocidos` sube al router
+    (422 con esperado vs encontrado — regla 7)."""
+    nit_propio = await _nit_config(ClaveConfig.NIT_RODDOS)
+    if not nit_propio:
+        raise ConfigFaltanteError(
+            "NIT_RODDOS no está en Configuracion: sin él no se puede validar que "
+            "las filas del Excel sean documentos RECIBIDOS por RODDOS. Corra la "
+            "migración 20260728_e2_facturas_iva."
+        )
+    nit_auteco = await _nit_config(ClaveConfig.NIT_AUTECO)
+    archivo_ref = f"sha256:{hashlib.sha256(contenido).hexdigest()}"
+
+    filas = await to_thread.run_sync(parsear_excel, contenido)
+
+    resultados: list[dict] = []
+    for fila in filas:
+        etiqueta = f"fila {fila['fila']}"
+        try:
+            if "error" in fila:
+                resultados.append(
+                    _resultado(etiqueta, EstadoIngesta.error, motivo=fila["error"])
+                )
+                continue
+            etiqueta = f"fila {fila['fila']} · {fila['numero']}"
+            if not es_tipo_soportado(fila["tipo_documento"]):
+                resultados.append(
+                    _resultado(
+                        etiqueta,
+                        EstadoIngesta.rechazada_tipo_no_soportado,
+                        motivo=f"'{fila['tipo_documento']}' no se procesa todavía "
+                        "(solo facturas electrónicas; notas crédito/débito y "
+                        "documentos equivalentes van a E2.1). No entró a la "
+                        "liquidación.",
+                    )
+                )
+                continue
+            if fila["nit_emisor"] == nit_propio:
+                resultados.append(
+                    _resultado(
+                        etiqueta,
+                        EstadoIngesta.rechazada_tipo_no_soportado,
+                        motivo="es una factura EMITIDA por RODDOS; este importador "
+                        "es solo de recibidas (gasto). El IVA generado del mes se "
+                        "registra aparte.",
+                    )
+                )
+                continue
+            if fila.get("nit_receptor") and fila["nit_receptor"] != nit_propio:
+                resultados.append(
+                    _resultado(
+                        etiqueta,
+                        EstadoIngesta.rechazada_tipo_no_soportado,
+                        motivo="el receptor de esta fila no es RODDOS; no es un "
+                        "documento recibido nuestro.",
+                    )
+                )
+                continue
+            campos = campos_desde_fila(fila, nit_auteco=nit_auteco)
+            resultados.append(
+                await persistir_factura_ingesta(
+                    campos,
+                    usuario_id=usuario_id,
+                    via="import_excel_dian",
+                    etiqueta=etiqueta,
+                    archivo_ref=archivo_ref,
+                )
+            )
+        except Exception:
+            # sin contenido de la fila en el log (puede llevar PII, A17)
+            logger.exception(
+                "import excel: error procesando la fila %s", fila.get("fila")
+            )
+            resultados.append(
+                _resultado(
+                    etiqueta,
+                    EstadoIngesta.error,
+                    motivo="error interno procesando la fila; las demás filas "
+                    "no se afectaron",
+                )
+            )
+
+    resumen = {plural: 0 for plural in _PLURAL.values()}
+    for r in resultados:
+        resumen[_PLURAL[EstadoIngesta(r["estado"])]] += 1
+    return {"resultados": resultados, "resumen": resumen}
diff --git a/backend/app/facturas/router.py b/backend/app/facturas/router.py
index a271a5b..1cecd21 100644
--- a/backend/app/facturas/router.py
+++ b/backend/app/facturas/router.py
@@ -8,6 +8,7 @@ Decimal antes de construir la factura; la respuesta los serializa con `money_str
 Idempotency-Key: no es un movimiento de dinero; el índice único (tercero_nit, numero)
 hace inocuo el replay (→ 409). La liquidación se calcula en el backend."""
 
+import os
 from datetime import date
 from decimal import Decimal, InvalidOperation
 
@@ -28,6 +29,7 @@ from app.domain.factura import (
     TipoFactura,
 )
 from app.facturas import ingesta, service
+from app.facturas.excel_dian import EncabezadosNoReconocidos
 from app.facturas.extraccion import PERSONA_JURIDICA
 from app.iva.liquidacion import Periodicidad, clave_dian, liquidar, periodo_de
 
@@ -208,6 +210,34 @@ async def cargar(
         raise HTTPException(409, str(e)) from e
 
 
+@router.post("/cargar-excel")
+async def cargar_excel(
+    archivo: UploadFile,
+    user: User = Depends(require_permission("iva:gestionar")),
+    _: None = Depends(verify_origin),
+):
+    """C2' (acta FABS): import masivo del Excel de documentos recibidos del portal
+    DIAN — facturas a nombre de RODDOS (gasto con IVA potencialmente deducible).
+    Resultado por FILA con los mismos estados del lote PDF. Encabezados que no
+    cuadran con el contrato → 422 listando esperado vs encontrado (regla 7)."""
+    nombre = archivo.filename or "documentos.xlsx"
+    ext = os.path.splitext(nombre)[1].lower()
+    if ext != ".xlsx":
+        raise HTTPException(
+            422,
+            f"extensión '{ext}' no soportada: el export del portal DIAN es un .xlsx",
+        )
+    contenido = await archivo.read(ingesta.MAX_BYTES_ARCHIVO + 1)
+    if len(contenido) > ingesta.MAX_BYTES_ARCHIVO:
+        raise HTTPException(422, "el archivo supera el límite de 10 MB")
+    try:
+        return await ingesta.procesar_lote_excel(contenido, usuario_id=user.id)
+    except EncabezadosNoReconocidos as e:
+        raise HTTPException(422, str(e)) from e
+    except ingesta.ConfigFaltanteError as e:
+        raise HTTPException(409, str(e)) from e
+
+
 @router.post("", status_code=201)
 async def crear(
     body: FacturaCrearBody,
diff --git a/backend/tests/test_facturas_cargar_excel.py b/backend/tests/test_facturas_cargar_excel.py
new file mode 100644
index 0000000..2e0540a
--- /dev/null
+++ b/backend/tests/test_facturas_cargar_excel.py
@@ -0,0 +1,265 @@
+# backend/tests/test_facturas_cargar_excel.py
+"""C2' (acta FABS 2026-08-10) — POST /api/v1/facturas/cargar-excel: import masivo
+del Excel de "documentos recibidos" del portal DIAN (facturas a nombre de RODDOS,
+gasto con IVA potencialmente deducible).
+
+Reglas cubiertas (regla 7: el parser transforma, NUNCA interpreta):
+  - Encabezados que no cuadran con el contrato → 422 LISTANDO esperado vs
+    encontrado (fail-loud; el contrato es el punto de calibración con el archivo real).
+  - Fila válida → Factura tipo=compra, deducible=False/sin decidir (el operador
+    decide), SALVO Auteco (NIT por Configuracion) → deducible=True/decidida/origen
+    auteco (decisión CEO 2026-07-31, misma regla de la ingesta PDF).
+  - Dedup por CUFE (mismo archivo dos veces → duplicadas).
+  - Nota crédito / tipo no soportado → rechazada_tipo_no_soportado (radar E2.1).
+  - Fila EMITIDA por RODDOS → rechazada (este importador es solo de recibidas).
+  - Fila ilegible (fecha/monto) → error de ESA fila; las demás siguen (parcial).
+  - RBAC iva:gestionar (consulta → 403). Auditoría factura.creada por fila.
+"""
+
+from datetime import date
+from io import BytesIO
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
+from app.main import create_app
+from beanie import init_beanie
+from mongomock_motor import AsyncMongoMockClient
+from openpyxl import Workbook
+
+PWD = "clave-larga-1234"
+NIT_RODDOS = "901012622"
+NIT_AUTECO = "860024781"
+
+ENCABEZADOS = [
+    "Tipo de documento",
+    "Prefijo",
+    "Folio",
+    "CUFE/CUDE",
+    "Fecha Emisión",
+    "NIT Emisor",
+    "Nombre Emisor",
+    "IVA",
+    "Total",
+]
+
+
+def _xlsx(filas: list[list], encabezados: list[str] | None = None) -> bytes:
+    """Arma un xlsx en memoria con filas de título arriba (como exporta la DIAN)."""
+    wb = Workbook()
+    ws = wb.active
+    ws.append(["Documentos Recibidos"])  # fila de título que el parser debe saltar
+    ws.append([])
+    ws.append(encabezados or ENCABEZADOS)
+    for f in filas:
+        ws.append(f)
+    buf = BytesIO()
+    wb.save(buf)
+    return buf.getvalue()
+
+
+def _fila(
+    *,
+    tipo="Factura electrónica de Venta",
+    prefijo="FE",
+    folio="1234",
+    cufe="a1b2c3d4e5f60718293a4b5c6d7e8f901234567890abcdef1234567890abcdef",
+    fecha=None,
+    nit=None,
+    nombre="FERRETERIA EL TORNILLO SAS",
+    iva=1452.94,
+    total=32900.00,
+) -> list:
+    return [
+        tipo,
+        prefijo,
+        folio,
+        cufe,
+        fecha if fecha is not None else date(2026, 5, 28),
+        nit or "890900608",
+        nombre,
+        iva,
+        total,
+    ]
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
+    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
+    repository.configure_auth(c, "compas_test")
+    configure_audit(c, "compas_test")
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
+    transport = httpx.ASGITransport(app=app)
+    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
+        yield ac
+    repository.reset_auth()
+    reset_audit()
+    get_settings.cache_clear()
+
+
+async def _token(ac, email="fin@roddos.com") -> dict:
+    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
+    assert r.status_code == 200
+    return {"Authorization": f"Bearer {r.json()['access_token']}"}
+
+
+async def _cargar(ac, h, contenido: bytes, nombre="documentos_recibidos.xlsx"):
+    return await ac.post(
+        "/api/v1/facturas/cargar-excel",
+        files={
+            "archivo": (
+                nombre,
+                contenido,
+                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
+            )
+        },
+        headers=h,
+    )
+
+
+@pytest.mark.asyncio
+async def test_carga_feliz_con_auteco_autodeducible(api):
+    h = await _token(api)
+    contenido = _xlsx(
+        [
+            _fila(cufe="c1" * 32, folio="1001"),
+            _fila(
+                cufe="c2" * 32,
+                folio="777",
+                nit=NIT_AUTECO,
+                nombre="AUTECO SAS",
+                iva=3800000,
+                total=23800000,
+            ),
+        ]
+    )
+    r = await _cargar(api, h, contenido)
+    assert r.status_code == 200, r.text
+    assert r.json()["resumen"]["creadas"] == 2
+
+    lista = (await api.get("/api/v1/facturas", headers=h)).json()
+    por_numero = {f["numero"]: f for f in lista}
+    normal = por_numero["FE1001"]
+    assert normal["tipo"] == "compra"
+    assert normal["deducible"] is False
+    assert normal["deducible_decidido"] is False
+    assert normal["origen"] == "sin_clasificar"
+    assert normal["iva_valor"] == "1452.94"
+    auteco = por_numero["FE777"]
+    assert auteco["deducible"] is True  # decisión CEO: Auteco descontable por config
+    assert auteco["deducible_decidido"] is True
+    assert auteco["origen"] == "auteco"
+
+
+@pytest.mark.asyncio
+async def test_mismo_archivo_dos_veces_deduplica_por_cufe(api):
+    h = await _token(api)
+    contenido = _xlsx([_fila()])
+    assert (await _cargar(api, h, contenido)).json()["resumen"]["creadas"] == 1
+    r2 = await _cargar(api, h, contenido)
+    assert r2.json()["resumen"]["duplicadas"] == 1
+    assert r2.json()["resumen"]["creadas"] == 0
+
+
+@pytest.mark.asyncio
+async def test_nota_credito_rechazada_con_motivo(api):
+    h = await _token(api)
+    r = await _cargar(
+        api, h, _xlsx([_fila(tipo="Nota Crédito Electrónica", cufe="d1" * 32)])
+    )
+    assert r.json()["resumen"]["rechazadas_tipo_no_soportado"] == 1
+    assert "Nota Crédito" in r.json()["resultados"][0]["motivo"]
+
+
+@pytest.mark.asyncio
+async def test_emitida_por_roddos_se_rechaza(api):
+    """El export de RECIBIDAS no debería traer emitidas; si una fila viene con el
+    NIT propio como emisor, se rechaza con motivo — jamás se crea una venta."""
+    h = await _token(api)
+    r = await _cargar(api, h, _xlsx([_fila(nit=NIT_RODDOS, cufe="e1" * 32)]))
+    assert r.json()["resumen"]["rechazadas_tipo_no_soportado"] == 1
+    assert "emitida" in r.json()["resultados"][0]["motivo"].lower()
+
+
+@pytest.mark.asyncio
+async def test_encabezados_desconocidos_falla_listando(api):
+    """Regla 7: si el archivo real de la DIAN trae otros encabezados, el error DEBE
+    listar esperado vs encontrado — ese mensaje es el punto de calibración."""
+    h = await _token(api)
+    r = await _cargar(
+        api, h, _xlsx([_fila()], encabezados=["Col A", "Col B", "Col C"])
+    )
+    assert r.status_code == 422
+    assert "encabezados" in r.json()["detail"].lower()
+    assert "cufe" in r.json()["detail"].lower()  # dice qué esperaba
+
+
+@pytest.mark.asyncio
+async def test_fila_ilegible_no_frena_el_lote(api):
+    h = await _token(api)
+    contenido = _xlsx(
+        [
+            _fila(cufe="f1" * 32, folio="2001"),
+            _fila(cufe="f2" * 32, folio="2002", fecha="no-es-fecha"),
+            _fila(cufe="f3" * 32, folio="2003"),
+        ]
+    )
+    r = await _cargar(api, h, contenido)
+    assert r.json()["resumen"]["creadas"] == 2
+    assert r.json()["resumen"]["errores"] == 1
+    con_error = [x for x in r.json()["resultados"] if x["estado"] == "error"][0]
+    assert "fecha" in con_error["motivo"].lower()
+
+
+@pytest.mark.asyncio
+async def test_montos_como_texto_es_co(api):
+    """La DIAN a veces exporta montos como texto '1.452,94' — se parsean exactos."""
+    h = await _token(api)
+    r = await _cargar(
+        api,
+        h,
+        _xlsx([_fila(cufe="a9" * 32, iva="1.452,94", total="32.900,00")]),
+    )
+    assert r.json()["resumen"]["creadas"] == 1, r.text
+    lista = (await api.get("/api/v1/facturas", headers=await _token(api))).json()
+    assert lista[0]["iva_valor"] == "1452.94"
+
+
+@pytest.mark.asyncio
+async def test_rbac_iva_gestionar(api):
+    h = await _token(api, "consulta@roddos.com")
+    r = await _cargar(api, h, _xlsx([_fila()]))
+    assert r.status_code == 403
+
+
+@pytest.mark.asyncio
+async def test_extension_no_xlsx_es_422(api):
+    h = await _token(api)
+    r = await _cargar(api, h, b"no soy un excel", nombre="documento.pdf")
+    assert r.status_code == 422
+    assert "xlsx" in r.json()["detail"].lower()
diff --git a/frontend/src/components/iva/CargaPanel.test.tsx b/frontend/src/components/iva/CargaPanel.test.tsx
new file mode 100644
index 0000000..1d41682
--- /dev/null
+++ b/frontend/src/components/iva/CargaPanel.test.tsx
@@ -0,0 +1,110 @@
+// CargaPanel — C2': el mismo panel de carga acepta el Excel de «documentos
+// recibidos» del portal DIAN (masivo, un archivo → cientos de filas) junto a
+// los PDF. El resultado por fila pinta el MOTIVO del backend (sin jerga).
+
+import { fireEvent, render, screen, waitFor } from "@testing-library/react";
+import { beforeEach, describe, expect, it, vi } from "vitest";
+
+import { CargaPanel } from "@/components/iva/CargaPanel";
+
+const mocks = vi.hoisted(() => ({
+  cargarFacturas: vi.fn(),
+  cargarFacturasExcel: vi.fn(),
+}));
+
+vi.mock("@/lib/facturas", async (importOriginal) => {
+  const real = await importOriginal<typeof import("@/lib/facturas")>();
+  return {
+    ...real,
+    cargarFacturas: mocks.cargarFacturas,
+    cargarFacturasExcel: mocks.cargarFacturasExcel,
+  };
+});
+
+beforeEach(() => {
+  vi.clearAllMocks();
+});
+
+function renderPanel() {
+  return render(
+    <CargaPanel
+      onCerrar={() => {}}
+      onCargado={() => {}}
+      onRevisar={() => {}}
+    />,
+  );
+}
+
+describe("CargaPanel — C2' import Excel DIAN", () => {
+  it("la zona de carga anuncia el Excel de documentos recibidos", () => {
+    renderPanel();
+    expect(
+      screen.getByText(/Excel de «documentos recibidos»/),
+    ).toBeInTheDocument();
+  });
+
+  it("un .xlsx va al endpoint masivo y pinta los motivos por fila", async () => {
+    mocks.cargarFacturasExcel.mockResolvedValue({
+      resultados: [
+        {
+          archivo: "fila 2 · FE1001",
+          estado: "creada",
+          motivo: null,
+          factura_id: "f1",
+          datos_extraidos: null,
+        },
+        {
+          archivo: "fila 3 · FE1002",
+          estado: "rechazada_tipo_no_soportado",
+          motivo:
+            "es una factura EMITIDA por RODDOS; este importador es solo de recibidas (gasto).",
+          factura_id: null,
+          datos_extraidos: null,
+        },
+      ],
+      resumen: { creadas: 1, rechazadas_tipo_no_soportado: 1 },
+    });
+    const { container } = renderPanel();
+    const input = container.querySelector(
+      'input[type="file"]',
+    ) as HTMLInputElement;
+    const excel = new File(["x"], "FACTURACION DIAN.xlsx", {
+      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
+    });
+    fireEvent.change(input, { target: { files: [excel] } });
+
+    await waitFor(() =>
+      expect(mocks.cargarFacturasExcel).toHaveBeenCalledTimes(1),
+    );
+    expect(mocks.cargarFacturas).not.toHaveBeenCalled();
+    expect(await screen.findByText("1 factura cargada")).toBeInTheDocument();
+    // el motivo del BACKEND manda (no el texto fijo de los PDF)
+    expect(screen.getByText(/EMITIDA por RODDOS/)).toBeInTheDocument();
+  });
+
+  it("un .pdf sigue yendo al endpoint por documento", async () => {
+    mocks.cargarFacturas.mockResolvedValue({
+      resultados: [
+        {
+          archivo: "factura.pdf",
+          estado: "creada",
+          motivo: null,
+          factura_id: "f1",
+          datos_extraidos: null,
+        },
+      ],
+      resumen: { creadas: 1 },
+    });
+    const { container } = renderPanel();
+    const input = container.querySelector(
+      'input[type="file"]',
+    ) as HTMLInputElement;
+    fireEvent.change(input, {
+      target: {
+        files: [new File(["x"], "factura.pdf", { type: "application/pdf" })],
+      },
+    });
+    await waitFor(() => expect(mocks.cargarFacturas).toHaveBeenCalledTimes(1));
+    expect(mocks.cargarFacturasExcel).not.toHaveBeenCalled();
+  });
+});
diff --git a/frontend/src/components/iva/CargaPanel.tsx b/frontend/src/components/iva/CargaPanel.tsx
index 3b6c3ed..470418c 100644
--- a/frontend/src/components/iva/CargaPanel.tsx
+++ b/frontend/src/components/iva/CargaPanel.tsx
@@ -11,6 +11,7 @@ import {
   type CargaResultado,
   type EstadoCarga,
   cargarFacturas,
+  cargarFacturasExcel,
 } from "@/lib/facturas";
 
 const MAX = 20;
@@ -115,14 +116,19 @@ export function CargaPanel({
     const acc: CargaResultado[] = [];
     for (let i = 0; i < lote.length; i++) {
       setProgreso({ n: i + 1, total: lote.length, archivo: lote[i].name });
+      const esExcel = lote[i].name.toLowerCase().endsWith(".xlsx");
       try {
-        const resp = await cargarFacturas([lote[i]]);
+        // C2': un Excel de la DIAN trae CIENTOS de filas en un solo archivo —
+        // va al endpoint masivo; los PDF siguen de a uno (barra n de N real).
+        const resp = esExcel
+          ? await cargarFacturasExcel(lote[i])
+          : await cargarFacturas([lote[i]]);
         acc.push(...resp.resultados);
-      } catch {
+      } catch (e) {
         acc.push({
           archivo: lote[i].name,
           estado: "error",
-          motivo: null,
+          motivo: e instanceof Error ? e.message : null,
           factura_id: null,
           datos_extraidos: null,
         });
@@ -136,8 +142,10 @@ export function CargaPanel({
   function alSoltar(e: DragEvent) {
     e.preventDefault();
     setArrastrando(false);
-    const files = Array.from(e.dataTransfer.files).filter((f) =>
-      f.name.toLowerCase().endsWith(".pdf"),
+    const files = Array.from(e.dataTransfer.files).filter(
+      (f) =>
+        f.name.toLowerCase().endsWith(".pdf") ||
+        f.name.toLowerCase().endsWith(".xlsx"),
     );
     if (files.length) void subir(files);
   }
@@ -171,12 +179,13 @@ export function CargaPanel({
             Arrastra aquí los PDF que descargas de la DIAN — hasta 20 archivos
           </span>
           <span className="font-sans text-apoyo text-ink-faint">
-            o haz clic para seleccionar archivos
+            o el Excel de «documentos recibidos» del portal (carga masiva) · o
+            haz clic para seleccionar
           </span>
           <input
             ref={inputRef}
             type="file"
-            accept="application/pdf"
+            accept="application/pdf,.xlsx"
             multiple
             className="hidden"
             onChange={(e) => {
@@ -230,7 +239,8 @@ export function CargaPanel({
                         </button>
                       </>
                     ) : (
-                      MOTIVO[r.estado] && ` — ${MOTIVO[r.estado]}`
+                      (r.motivo || MOTIVO[r.estado]) &&
+                      ` — ${r.motivo || MOTIVO[r.estado]}`
                     )}
                   </p>
                 ))}
diff --git a/frontend/src/lib/facturas.ts b/frontend/src/lib/facturas.ts
index 7d3c4a5..82ae34c 100644
--- a/frontend/src/lib/facturas.ts
+++ b/frontend/src/lib/facturas.ts
@@ -96,6 +96,23 @@ export async function cargarFacturas(files: File[]): Promise<CargaRespuesta> {
   return body;
 }
 
+/** C2' (acta FABS): import masivo del Excel de documentos recibidos del portal
+ * DIAN — un solo .xlsx con una fila por factura. Mismo shape de respuesta que el
+ * lote de PDFs (el panel de carga pinta ambos con el mismo componente). */
+export async function cargarFacturasExcel(file: File): Promise<CargaRespuesta> {
+  const fd = new FormData();
+  fd.append("archivo", file);
+  const r = await apiFetch("/facturas/cargar-excel", {
+    method: "POST",
+    body: fd,
+  });
+  const body = await r.json().catch(() => ({}));
+  if (!r.ok) {
+    throw new ApiError(r.status, body.detail ?? "No se pudo cargar el Excel.");
+  }
+  return body;
+}
+
 // ── Editar deducibilidad / origen (PATCH) ──
 export async function editarFactura(
   id: string,
```

---

## Commit 51961e8

```diff
commit 51961e8d59c751130364f114ebd98c2d3c43dad2
Author: RoddosCol <info@roddos.com>
Date:   Tue Aug 11 12:25:14 2026 -0500

    feat(facturas): Auteco con dos NITs en la auto-deduccion (#91)
    
    * feat(facturas): Auteco con dos NITs en la auto-deduccion
    
    Auteco factura con DOS NITs (CEO 2026-08-11): el historico 860024781 y el de
    AUTOTECNICA COLOMBIANA S.A.S. 890900317 (verificado contra la factura real
    E670165520, que cuadra al peso con el Excel DIAN). NIT_AUTECO pasa a
    {nits: [...]} con compatibilidad hacia atras ({nit: ...}); la ingesta
    PDF y el import Excel comparan por pertenencia al conjunto.
    
    TDD: 7 tests nuevos/ajustados primero (rojo) -> implementacion (verde).
    Suite completa: 934 passed.
    
    Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
    
    * style(metas_ingreso): ordenar imports (ruff I001, preexistente en main)
    
    Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
    
    ---------
    
    Co-authored-by: Claude Fable 5 <noreply@anthropic.com>
---
 backend/app/domain/configuracion.py         |  5 +++-
 backend/app/facturas/excel_dian.py          |  9 ++++---
 backend/app/facturas/ingesta.py             | 37 ++++++++++++++++++++------
 backend/app/metas_ingreso/service.py        |  3 +--
 backend/tests/test_domain_configuracion.py  |  3 ++-
 backend/tests/test_facturas_cargar.py       | 24 ++++++++++++++---
 backend/tests/test_facturas_cargar_excel.py | 40 +++++++++++++++++++++++++++++
 7 files changed, 101 insertions(+), 20 deletions(-)

diff --git a/backend/app/domain/configuracion.py b/backend/app/domain/configuracion.py
index 728740e..751033f 100644
--- a/backend/app/domain/configuracion.py
+++ b/backend/app/domain/configuracion.py
@@ -149,8 +149,11 @@ SEMILLA_CONFIGURACION: list[dict] = [
         "vigente_desde": "2026-01-01",
     },
     {
+        # Auteco factura con DOS NITs (CEO 2026-08-11): el histórico y el de
+        # AUTOTECNICA COLOMBIANA S.A.S. (verificado contra factura real E670165520).
+        # La ingesta acepta {"nits": [...]} y la forma histórica {"nit": "..."}.
         "clave": "NIT_AUTECO",
-        "valor_json": {"nit": "860024781"},
+        "valor_json": {"nits": ["860024781", "890900317"]},
         "vigente_desde": "2026-01-01",
     },
     {
diff --git a/backend/app/facturas/excel_dian.py b/backend/app/facturas/excel_dian.py
index cbf1e4f..8e8a9fa 100644
--- a/backend/app/facturas/excel_dian.py
+++ b/backend/app/facturas/excel_dian.py
@@ -223,15 +223,16 @@ def parsear_excel(contenido: bytes) -> list[dict]:
 
 
 def campos_desde_fila(
-    fila: dict, *, nit_auteco: str | None
+    fila: dict, *, nits_auteco: frozenset[str]
 ) -> dict:
     """Fila cruda válida → campos del Document Factura (compra recibida).
 
     Misma semántica de deducibilidad que `ingesta.campos_desde_dian`: Auteco por
-    NIT → deducible/decidida/origen auteco; el resto sin decidir (el operador
-    marca después — contador del §2). El Excel de la DIAN no trae total bruto ni
+    NIT → deducible/decidida/origen auteco (factura con VARIOS NITs — config
+    {"nits": [...]}, CEO 2026-08-11); el resto sin decidir (el operador marca
+    después — contador del §2). El Excel de la DIAN no trae total bruto ni
     base gravada por línea → None (R5: no se inventa)."""
-    es_auteco = nit_auteco is not None and fila["nit_emisor"] == nit_auteco
+    es_auteco = fila["nit_emisor"] in nits_auteco
     nombre = fila["nombre_emisor"] or f"NIT {fila['nit_emisor']}"
     return {
         "tipo": TipoFactura.compra,
diff --git a/backend/app/facturas/ingesta.py b/backend/app/facturas/ingesta.py
index 6e19bb2..122edb3 100644
--- a/backend/app/facturas/ingesta.py
+++ b/backend/app/facturas/ingesta.py
@@ -97,6 +97,26 @@ async def _nit_config(clave: ClaveConfig) -> str | None:
     return None
 
 
+async def _nits_config(clave: ClaveConfig) -> frozenset[str]:
+    """Última vigencia de una clave NIT_* que puede tener VARIOS NITs (Auteco factura
+    con dos: 860024781 y AUTOTECNICA COLOMBIANA 890900317 — CEO 2026-08-11). Acepta
+    {"nits": [...]} y la forma histórica {"nit": "..."}. Ausente → conjunto vacío."""
+    cfg = (
+        await Configuracion.find(Configuracion.clave == clave)
+        .sort(-Configuracion.vigente_desde)
+        .limit(1)
+        .to_list()
+    )
+    if cfg and cfg[0].valor_json:
+        nits = cfg[0].valor_json.get("nits")
+        if isinstance(nits, list):
+            return frozenset(str(n) for n in nits if n)
+        nit = cfg[0].valor_json.get("nit")
+        if nit:
+            return frozenset({str(nit)})
+    return frozenset()
+
+
 def _extraer_bytes(contenido: bytes, nombre: str, nit_propio: str) -> FacturaDian:
     """SÍNCRONA y CPU-bound: llamar SIEMPRE vía `anyio.to_thread` (A16).
 
@@ -111,7 +131,7 @@ def _extraer_bytes(contenido: bytes, nombre: str, nit_propio: str) -> FacturaDia
     return factura_desde_documento(texto, filas, titulo_pdf, nit_propio, nombre)
 
 
-def campos_desde_dian(f: FacturaDian, *, nit_auteco: str | None) -> dict:
+def campos_desde_dian(f: FacturaDian, *, nits_auteco: frozenset[str]) -> dict:
     """Costura PURA (testeable sin PDF): FacturaDian → campos del Document Factura.
 
     ⚠ `FacturaDian.inc` → `Factura.inc_valor` (rename anti-shadow): NO "corregir"
@@ -126,7 +146,8 @@ def campos_desde_dian(f: FacturaDian, *, nit_auteco: str | None) -> dict:
     if f.tipo == "recibida":
         tercero_nit, tercero_nombre = f.nit_emisor, f.nombre_emisor
         tipo = TipoFactura.compra
-        es_auteco = nit_auteco is not None and f.nit_emisor == nit_auteco
+        # Auteco factura con VARIOS NITs (config {"nits": [...]}): cualquiera deduce.
+        es_auteco = f.nit_emisor in nits_auteco
         origen = OrigenFactura.auteco if es_auteco else OrigenFactura.sin_clasificar
         # Auteco: descontable por configuración (decidido por el documento, no el
         # operador). Las demás recibidas quedan "sin decidir" para el contador del §2.
@@ -289,7 +310,7 @@ async def _procesar_archivo(
     archivo: UploadFile,
     *,
     nit_propio: str,
-    nit_auteco: str | None,
+    nits_auteco: frozenset[str],
     usuario_id: str,
 ) -> dict:
     nombre = archivo.filename or "documento.pdf"
@@ -319,7 +340,7 @@ async def _procesar_archivo(
     except DocumentoNoDian as e:
         return _resultado(nombre, EstadoIngesta.rechazada_no_dian, motivo=str(e))
 
-    campos = campos_desde_dian(dian, nit_auteco=nit_auteco)
+    campos = campos_desde_dian(dian, nits_auteco=nits_auteco)
     datos = _datos_extraidos(dian, campos)
 
     # Pieza 5: la validación de integridad de la extracción es la COHERENCIA A6
@@ -358,7 +379,7 @@ async def procesar_lote(archivos: list[UploadFile], *, usuario_id: str) -> dict:
             "una factura es emitida o recibida. Corra la migración "
             "20260728_e2_facturas_iva."
         )
-    nit_auteco = await _nit_config(ClaveConfig.NIT_AUTECO)
+    nits_auteco = await _nits_config(ClaveConfig.NIT_AUTECO)
 
     resultados: list[dict] = []
     for i, archivo in enumerate(archivos):
@@ -368,7 +389,7 @@ async def procesar_lote(archivos: list[UploadFile], *, usuario_id: str) -> dict:
                 await _procesar_archivo(
                     archivo,
                     nit_propio=nit_propio,
-                    nit_auteco=nit_auteco,
+                    nits_auteco=nits_auteco,
                     usuario_id=usuario_id,
                 )
             )
@@ -404,7 +425,7 @@ async def procesar_lote_excel(
             "las filas del Excel sean documentos RECIBIDOS por RODDOS. Corra la "
             "migración 20260728_e2_facturas_iva."
         )
-    nit_auteco = await _nit_config(ClaveConfig.NIT_AUTECO)
+    nits_auteco = await _nits_config(ClaveConfig.NIT_AUTECO)
     archivo_ref = f"sha256:{hashlib.sha256(contenido).hexdigest()}"
 
     filas = await to_thread.run_sync(parsear_excel, contenido)
@@ -452,7 +473,7 @@ async def procesar_lote_excel(
                     )
                 )
                 continue
-            campos = campos_desde_fila(fila, nit_auteco=nit_auteco)
+            campos = campos_desde_fila(fila, nits_auteco=nits_auteco)
             resultados.append(
                 await persistir_factura_ingesta(
                     campos,
diff --git a/backend/app/metas_ingreso/service.py b/backend/app/metas_ingreso/service.py
index a8eeb64..171d37a 100644
--- a/backend/app/metas_ingreso/service.py
+++ b/backend/app/metas_ingreso/service.py
@@ -14,7 +14,6 @@ from app.audit.service import emit_audit
 from app.core.money import Money
 from app.core.time import now_bogota
 from app.domain.mes_control import MesControl
-from app.domain.transaccion import pares_clasificacion
 from app.domain.obligacion import LineaMeta, MetaIngreso
 
 # El set de neutros Y su resolver nombre→id viven en `app.domain.rubros_neutros` (E1 lo
@@ -26,7 +25,7 @@ from app.domain.rubros_neutros import (
 from app.domain.rubros_neutros import (
     _ids_rubros_neutros as _ids_rubros_neutros,
 )
-from app.domain.transaccion import TipoFlujo, Transaccion
+from app.domain.transaccion import TipoFlujo, Transaccion, pares_clasificacion
 
 
 class MetasError(Exception):
diff --git a/backend/tests/test_domain_configuracion.py b/backend/tests/test_domain_configuracion.py
index d544309..a8eac92 100644
--- a/backend/tests/test_domain_configuracion.py
+++ b/backend/tests/test_domain_configuracion.py
@@ -84,7 +84,8 @@ def test_semilla_tiene_las_claves_esperadas():
 def test_semilla_e2_nits_y_compuerta_apagada():
     d = {c["clave"]: c for c in SEMILLA_CONFIGURACION}
     assert d["NIT_RODDOS"]["valor_json"] == {"nit": "901012622"}
-    assert d["NIT_AUTECO"]["valor_json"] == {"nit": "860024781"}
+    # Auteco factura con DOS NITs (CEO 2026-08-11): histórico + AUTOTECNICA COLOMBIANA
+    assert d["NIT_AUTECO"]["valor_json"] == {"nits": ["860024781", "890900317"]}
     # compuerta IVA→proyección apagada por defecto (D-12 / CR-E2-COMPUERTA)
     assert d["IVA_ALIMENTA_PROYECCION"]["valor_json"] == {"activa": False}
 
diff --git a/backend/tests/test_facturas_cargar.py b/backend/tests/test_facturas_cargar.py
index c985b2f..87fc2b8 100644
--- a/backend/tests/test_facturas_cargar.py
+++ b/backend/tests/test_facturas_cargar.py
@@ -280,7 +280,7 @@ async def test_iva_extraido_manda_sobre_base_por_tarifa(api, monkeypatch):
 def test_campos_desde_dian_mapea_inc_a_inc_valor():
     """Costura pura: el desajuste FacturaDian.inc→Factura.inc_valor guardaría un
     cero en silencio; este test lo hace imposible."""
-    campos = ingesta.campos_desde_dian(_dian(), nit_auteco=NIT_AUTECO)
+    campos = ingesta.campos_desde_dian(_dian(), nits_auteco=frozenset({NIT_AUTECO}))
     assert campos["inc_valor"] == Decimal("100.00")
     assert "inc" not in campos  # el campo del Document se llama inc_valor
 
@@ -288,7 +288,7 @@ def test_campos_desde_dian_mapea_inc_a_inc_valor():
 def test_campos_desde_dian_queda_sin_decidir():
     """DIAN no decide la deducibilidad: deducible_decidido=False para que el §2 cuente
     las recibidas sin decidir. La decisión la fija el operador (PATCH/manual)."""
-    campos = ingesta.campos_desde_dian(_dian(), nit_auteco=NIT_AUTECO)
+    campos = ingesta.campos_desde_dian(_dian(), nits_auteco=frozenset({NIT_AUTECO}))
     assert campos["deducible"] is False
     assert campos["deducible_decidido"] is False
 
@@ -296,7 +296,7 @@ def test_campos_desde_dian_queda_sin_decidir():
 def test_campos_desde_dian_total_bruto_no_base_gravable():
     """Total Bruto DIAN → total_bruto; base_gravable=None (no es la base gravada)."""
     campos = ingesta.campos_desde_dian(
-        _dian(base_gravable=Decimal("31447.06")), nit_auteco=NIT_AUTECO
+        _dian(base_gravable=Decimal("31447.06")), nits_auteco=frozenset({NIT_AUTECO})
     )
     assert campos["total_bruto"] == Decimal("31447.06")
     assert campos["base_gravable"] is None
@@ -343,13 +343,29 @@ def test_campos_desde_dian_auteco_es_deducible_decidido():
     viene del DOCUMENTO+CONFIG, no del operador (no entra al contador 'sin decidir')."""
     campos = ingesta.campos_desde_dian(
         _dian(nit_emisor=NIT_AUTECO, nombre_emisor="AUTECO S.A.S."),
-        nit_auteco=NIT_AUTECO,
+        nits_auteco=frozenset({NIT_AUTECO}),
     )
     assert campos["origen"] == OrigenFactura.auteco
     assert campos["deducible"] is True
     assert campos["deducible_decidido"] is True
 
 
+def test_campos_desde_dian_auteco_segundo_nit_tambien_deducible():
+    """Auteco factura con DOS NITs (CEO 2026-08-11): el histórico 860024781 y el de
+    AUTOTECNICA COLOMBIANA 890900317. La config guarda el CONJUNTO y cualquiera de
+    los dos auto-deduce; un tercero cualquiera sigue sin decidir."""
+    nits = frozenset({NIT_AUTECO, "890900317"})
+    campos = ingesta.campos_desde_dian(
+        _dian(nit_emisor="890900317", nombre_emisor="AUTOTECNICA COLOMBIANA S.A.S."),
+        nits_auteco=nits,
+    )
+    assert campos["origen"] == OrigenFactura.auteco
+    assert campos["deducible"] is True
+    assert campos["deducible_decidido"] is True
+    ajeno = ingesta.campos_desde_dian(_dian(), nits_auteco=nits)
+    assert ajeno["deducible_decidido"] is False
+
+
 async def test_cargar_auteco_queda_deducible_decidido(api):
     """El PDF de Auteco entra deducible=True + decidido=True; otro NIT sigue sin
     decidir (cubierto por test_cargar_recibida_crea_factura)."""
diff --git a/backend/tests/test_facturas_cargar_excel.py b/backend/tests/test_facturas_cargar_excel.py
index 2e0540a..ed48e67 100644
--- a/backend/tests/test_facturas_cargar_excel.py
+++ b/backend/tests/test_facturas_cargar_excel.py
@@ -37,6 +37,9 @@ from openpyxl import Workbook
 PWD = "clave-larga-1234"
 NIT_RODDOS = "901012622"
 NIT_AUTECO = "860024781"
+# Auteco factura con DOS NITs (CEO 2026-08-11): el histórico y el de AUTOTECNICA
+# COLOMBIANA S.A.S. — ambos deben auto-deducir.
+NIT_AUTOTECNICA = "890900317"
 
 ENCABEZADOS = [
     "Tipo de documento",
@@ -176,6 +179,43 @@ async def test_carga_feliz_con_auteco_autodeducible(api):
     assert auteco["origen"] == "auteco"
 
 
+@pytest.mark.asyncio
+async def test_auteco_con_dos_nits_ambos_autodeducibles(api):
+    """Auteco factura con DOS NITs (CEO 2026-08-11). Con la config en la forma
+    {"nits": [...]}, una fila de CUALQUIERA de los dos entra deducible/decidida/
+    origen auteco; el fixture (forma vieja {"nit": ...}) prueba la compatibilidad."""
+    await Configuracion(
+        clave="NIT_AUTECO",
+        valor_json={"nits": [NIT_AUTECO, NIT_AUTOTECNICA]},
+        vigente_desde="2026-02-01",  # vigencia más nueva que la del fixture
+    ).insert()
+    h = await _token(api)
+    contenido = _xlsx(
+        [
+            _fila(cufe="a1" * 32, folio="111", nit=NIT_AUTECO, nombre="AUTECO SAS"),
+            _fila(
+                cufe="a2" * 32,
+                folio="222",
+                nit=NIT_AUTOTECNICA,
+                nombre="AUTOTECNICA COLOMBIANA S.A.S.",
+            ),
+            _fila(cufe="a3" * 32, folio="333"),  # tercero cualquiera: sin decidir
+        ]
+    )
+    r = await _cargar(api, h, contenido)
+    assert r.status_code == 200, r.text
+    assert r.json()["resumen"]["creadas"] == 3
+
+    lista = (await api.get("/api/v1/facturas", headers=h)).json()
+    por_numero = {f["numero"]: f for f in lista}
+    for numero in ("FE111", "FE222"):
+        assert por_numero[numero]["deducible"] is True, numero
+        assert por_numero[numero]["deducible_decidido"] is True, numero
+        assert por_numero[numero]["origen"] == "auteco", numero
+    assert por_numero["FE333"]["deducible_decidido"] is False
+    assert por_numero["FE333"]["origen"] == "sin_clasificar"
+
+
 @pytest.mark.asyncio
 async def test_mismo_archivo_dos_veces_deduplica_por_cufe(api):
     h = await _token(api)
```

---

## Commit 1a7e7ad

```diff
commit 1a7e7add1886ac5278a3d6e23e514cb7a86e9d73
Author: RoddosCol <info@roddos.com>
Date:   Tue Aug 11 15:15:48 2026 -0500

    feat(iva): saldo a favor declarado de la DIAN entra a la liquidacion (#92)
    
    El saldo a favor de la declaracion anterior a los datos de COMPAS
    (28.950.000, CEO 2026-08-11) se captura como dato oficial en la config
    SALDO_FAVOR_IVA_DECLARADO ({aplica_desde, valor}). liquidar() lo usa como
    saldo_favor_previo del periodo configurado, REEMPLAZANDO el arrastre
    derivado (la declaracion oficial ya incorpora todo lo anterior; sumar
    seria doble conteo). Aplica en GET /facturas/liquidacion y en los egresos
    IVA de la proyeccion (coherencia con el fondo de provision). Sin semilla:
    ausente = no aplica; valor ilegible = no aplica (R5, jamas se adivina).
    
    TDD: 4 tests primero en rojo (3 del nucleo compute-only + 1 del endpoint
    con config sembrada). Suite completa: 938 passed + ruff limpio.
    
    Co-authored-by: Claude Fable 5 <noreply@anthropic.com>
---
 backend/app/domain/configuracion.py      |  6 +++++
 backend/app/facturas/router.py           |  3 ++-
 backend/app/facturas/service.py          | 33 ++++++++++++++++++++++++-
 backend/app/iva/liquidacion.py           | 26 +++++++++++++++++++-
 backend/app/proyeccion/service.py        |  3 ++-
 backend/tests/test_facturas_endpoints.py | 37 ++++++++++++++++++++++++++++
 backend/tests/test_iva_liquidacion.py    | 41 ++++++++++++++++++++++++++++++++
 7 files changed, 145 insertions(+), 4 deletions(-)

diff --git a/backend/app/domain/configuracion.py b/backend/app/domain/configuracion.py
index 751033f..523afb7 100644
--- a/backend/app/domain/configuracion.py
+++ b/backend/app/domain/configuracion.py
@@ -37,6 +37,11 @@ class ClaveConfig(StrEnum):
     # E2 (CR-E2-COMPUERTA): compuerta IVA→proyección. Apagada por defecto → E2 captura
     # facturas y liquida el IVA SIN mover la caja proyectada (D-12). Encender es dato.
     IVA_ALIMENTA_PROYECCION = "IVA_ALIMENTA_PROYECCION"
+    # Saldo a favor de la declaración DIAN anterior a los datos de COMPAS (CEO
+    # 2026-08-11): {"aplica_desde": "YYYY-MM-DD", "valor": "monto"}. Entra como
+    # saldo_favor_previo del período de aplica_desde, REEMPLAZANDO el arrastre
+    # derivado. Sin semilla: es un dato de la empresa, ausente → no aplica.
+    SALDO_FAVOR_IVA_DECLARADO = "SALDO_FAVOR_IVA_DECLARADO"
 
 
 # Tipo esperado por clave (M-03). "decimal" | "fecha" | "json".
@@ -48,6 +53,7 @@ _TIPO_POR_CLAVE: dict[ClaveConfig, str] = {
     ClaveConfig.NIT_RODDOS: "json",
     ClaveConfig.NIT_AUTECO: "json",
     ClaveConfig.IVA_ALIMENTA_PROYECCION: "json",
+    ClaveConfig.SALDO_FAVOR_IVA_DECLARADO: "json",
 }
 
 
diff --git a/backend/app/facturas/router.py b/backend/app/facturas/router.py
index 1cecd21..29ffa96 100644
--- a/backend/app/facturas/router.py
+++ b/backend/app/facturas/router.py
@@ -147,6 +147,7 @@ async def liquidacion(_: User = Depends(require_permission("dashboard:leer"))):
     periodicidad = await service.obtener_periodicidad()
     items = await service.obtener_facturas_iva()
     calendario = await service.obtener_calendario_dian()
+    declarado = await service.obtener_saldo_favor_declarado()
     return {
         "periodicidad": periodicidad.value,
         "periodos": [
@@ -164,7 +165,7 @@ async def liquidacion(_: User = Depends(require_permission("dashboard:leer"))):
                     c.anio, c.periodo, periodicidad, calendario
                 ),
             }
-            for c in liquidar(items, periodicidad)
+            for c in liquidar(items, periodicidad, saldo_declarado=declarado)
         ],
     }
 
diff --git a/backend/app/facturas/service.py b/backend/app/facturas/service.py
index 98c6f3a..4995f66 100644
--- a/backend/app/facturas/service.py
+++ b/backend/app/facturas/service.py
@@ -18,7 +18,12 @@ from app.audit.events import AuditEvento
 from app.audit.service import emit_audit
 from app.domain.configuracion import ClaveConfig, Configuracion
 from app.domain.factura import Factura, OrigenFactura, TipoFactura
-from app.iva.liquidacion import FacturaIva, Periodicidad, iva_desde_base
+from app.iva.liquidacion import (
+    FacturaIva,
+    Periodicidad,
+    SaldoFavorDeclarado,
+    iva_desde_base,
+)
 
 _MES = re.compile(r"^\d{4}-\d{2}$")
 
@@ -313,6 +318,32 @@ async def obtener_periodicidad() -> Periodicidad:
     return Periodicidad.cuatrimestral
 
 
+async def obtener_saldo_favor_declarado() -> SaldoFavorDeclarado | None:
+    """Última vigencia de `SALDO_FAVOR_IVA_DECLARADO` (la cifra oficial de la
+    declaración DIAN anterior a los datos de COMPAS — CEO 2026-08-11). Ausente o
+    incompleta → None (no aplica; NUNCA se inventa un saldo, R5)."""
+    cfg = (
+        await Configuracion.find(
+            Configuracion.clave == ClaveConfig.SALDO_FAVOR_IVA_DECLARADO
+        )
+        .sort(-Configuracion.vigente_desde)
+        .limit(1)
+        .to_list()
+    )
+    if not (cfg and cfg[0].valor_json):
+        return None
+    aplica_desde = cfg[0].valor_json.get("aplica_desde")
+    valor = cfg[0].valor_json.get("valor")
+    if not aplica_desde or valor is None:
+        return None
+    try:
+        return SaldoFavorDeclarado(
+            aplica_desde=str(aplica_desde), valor=Decimal(str(valor))
+        )
+    except Exception:
+        return None  # valor ilegible = no aplica; jamás se adivina (regla 7)
+
+
 async def obtener_calendario_dian() -> dict:
     """Última vigencia de `CALENDARIO_DIAN` ({"2026": {"ene_abr": "2026-05-13", ...}}).
     Ausente → {} (la UI omite la línea del próximo pago; NUNCA se inventa una fecha,
diff --git a/backend/app/iva/liquidacion.py b/backend/app/iva/liquidacion.py
index 4db373a..c855d96 100644
--- a/backend/app/iva/liquidacion.py
+++ b/backend/app/iva/liquidacion.py
@@ -95,6 +95,17 @@ class FacturaIva:
     deducible: bool = False
 
 
+@dataclass(frozen=True)
+class SaldoFavorDeclarado:
+    """Saldo a favor de la declaración DIAN anterior a los datos de COMPAS (CEO
+    2026-08-11). `aplica_desde` (YYYY-MM-DD) marca el período donde ENTRA como
+    `saldo_favor_previo`; ahí REEMPLAZA el arrastre derivado — la declaración
+    oficial ya incorpora todo lo anterior (sumarlos sería doble conteo)."""
+
+    aplica_desde: str  # 'YYYY-MM-DD' (el período se deriva con la periodicidad)
+    valor: Decimal
+
+
 @dataclass(frozen=True)
 class LiquidacionPeriodo:
     anio: int
@@ -214,16 +225,29 @@ def programar_egresos_iva(
 def liquidar(
     facturas: list[FacturaIva],
     periodicidad: Periodicidad = Periodicidad.cuatrimestral,
+    saldo_declarado: SaldoFavorDeclarado | None = None,
 ) -> list[LiquidacionPeriodo]:
     """Liquida cada período en orden CRONOLÓGICO (el arrastre lo exige). Devuelve una
-    `LiquidacionPeriodo` por período con facturas, según la periodicidad."""
+    `LiquidacionPeriodo` por período con facturas, según la periodicidad.
+
+    `saldo_declarado`: al llegar al PRIMER período >= su `aplica_desde`, el arrastre
+    se REEMPLAZA por el valor declarado (una sola vez; si ese período no tiene
+    facturas, fluye al siguiente con datos). Los períodos anteriores no cambian."""
     grupos: dict[tuple[int, int], list[FacturaIva]] = {}
     for f in facturas:
         grupos.setdefault(periodo_de(f.fecha, periodicidad), []).append(f)
 
+    clave_declarado = (
+        periodo_de(saldo_declarado.aplica_desde, periodicidad)
+        if saldo_declarado is not None
+        else None
+    )
     out: list[LiquidacionPeriodo] = []
     favor = Decimal("0")
     for anio, c in sorted(grupos):
+        if clave_declarado is not None and (anio, c) >= clave_declarado:
+            favor = saldo_declarado.valor  # reemplaza el derivado (doble conteo no)
+            clave_declarado = None  # se consume una sola vez
         fs = grupos[(anio, c)]
         generado = sum((f.iva_valor for f in fs if f.tipo == "venta"), Decimal("0"))
         descontable = sum(
diff --git a/backend/app/proyeccion/service.py b/backend/app/proyeccion/service.py
index 5dfafa3..17c010a 100644
--- a/backend/app/proyeccion/service.py
+++ b/backend/app/proyeccion/service.py
@@ -279,7 +279,8 @@ async def _iva_plan(
         return {}, []
     periodicidad = await facturas_service.obtener_periodicidad()
     calendario = await _calendario_dian()
-    liquidaciones = liquidar(facturas, periodicidad)
+    declarado = await facturas_service.obtener_saldo_favor_declarado()
+    liquidaciones = liquidar(facturas, periodicidad, saldo_declarado=declarado)
     egreso = programar_egresos_iva(
         liquidaciones,
         calendario,
diff --git a/backend/tests/test_facturas_endpoints.py b/backend/tests/test_facturas_endpoints.py
index 5689b4e..39d1847 100644
--- a/backend/tests/test_facturas_endpoints.py
+++ b/backend/tests/test_facturas_endpoints.py
@@ -665,6 +665,43 @@ async def test_a10_ejemplo_aritmetico_spec_6_end_to_end(api):
     assert any(f["numero"] == "R-4" for f in rl.json())
 
 
+async def test_liquidacion_usa_saldo_favor_declarado_de_config(api):
+    """CEO 2026-08-11: el saldo a favor de la declaración DIAN anterior (períodos
+    pre-COMPAS) se captura en la config SALDO_FAVOR_IVA_DECLARADO y entra como
+    `saldo_favor_previo` del período configurado, REEMPLAZANDO el arrastre derivado."""
+    from app.domain.configuracion import Configuracion
+
+    ac, _ = api
+    h = await _token(ac)
+    await Configuracion(
+        clave="SALDO_FAVOR_IVA_DECLARADO",
+        valor_json={"aplica_desde": "2026-05-01", "valor": "28950000.00"},
+        vigente_desde="2026-08-11",
+    ).insert()
+    # venta C2 (may–ago): generado 190000; sin el declarado pagaría 190000
+    await ac.post(
+        "/api/v1/facturas",
+        json={
+            "tipo": "venta",
+            "origen": "moto",
+            "numero": "FV-DECL",
+            "tercero_nombre": "Cliente",
+            "tercero_nit": "79",
+            "fecha": "2026-06-01",
+            "base_gravable": "1000000",
+            "tarifa_iva": "0.19",
+            "deducible": False,
+        },
+        headers=h,
+    )
+    r = await ac.get("/api/v1/facturas/liquidacion", headers=h)
+    per = {p["etiqueta"]: p for p in r.json()["periodos"]}
+    c2 = per["2026-C2"]
+    assert c2["saldo_favor_previo"] == "28950000.00"
+    assert c2["neto_a_pagar"] == "0.00"
+    assert c2["saldo_favor_nuevo"] == "28760000.00"  # 28.950.000 − 190.000
+
+
 # ── PASO 1c: proximo_pago {fecha, dias} en /liquidacion desde CALENDARIO_DIAN ──
 async def test_liquidacion_incluye_proximo_pago_dian(api):
     from datetime import date
diff --git a/backend/tests/test_iva_liquidacion.py b/backend/tests/test_iva_liquidacion.py
index 012aa3c..c52871d 100644
--- a/backend/tests/test_iva_liquidacion.py
+++ b/backend/tests/test_iva_liquidacion.py
@@ -10,6 +10,7 @@ from decimal import Decimal
 from app.iva.liquidacion import (
     FacturaIva,
     Periodicidad,
+    SaldoFavorDeclarado,
     cuatrimestre_de,
     iva_desde_base,
     iva_desde_total,
@@ -91,6 +92,46 @@ def test_liquidar_arrastra_saldo_a_favor():
     assert c2.saldo_favor_nuevo == Decimal("0")
 
 
+def test_liquidar_saldo_declarado_reemplaza_el_arrastre():
+    """Saldo a favor DECLARADO (la cifra oficial de la declaración DIAN anterior,
+    capturada por config — CEO 2026-08-11): al llegar a su período REEMPLAZA el
+    arrastre derivado (la declaración oficial ya incorpora todo lo anterior —
+    sumarlos sería doble conteo). Los períodos anteriores no cambian."""
+    facturas = [
+        # C1: favor derivado 70 (descontable 120 > generado 50)
+        FacturaIva("venta", "2026-02-10", Decimal("50")),
+        FacturaIva("compra", "2026-02-11", Decimal("120"), True),
+        # C2: generado 200
+        FacturaIva("venta", "2026-06-10", Decimal("200")),
+    ]
+    decl = SaldoFavorDeclarado(aplica_desde="2026-05-01", valor=Decimal("100"))
+    c1, c2 = liquidar(facturas, saldo_declarado=decl)
+    assert c1.saldo_favor_nuevo == Decimal("70")  # C1 intacto
+    assert c2.saldo_favor_previo == Decimal("100")  # reemplaza: ni 70 ni 170
+    assert c2.neto_a_pagar == Decimal("100")  # 200 − 100
+    assert c2.saldo_favor_nuevo == Decimal("0")
+
+
+def test_liquidar_saldo_declarado_sin_facturas_en_su_periodo_fluye():
+    """Si el período donde entra el declarado no tiene facturas, el saldo fluye al
+    primer período posterior con datos (no se pierde)."""
+    facturas = [FacturaIva("venta", "2026-10-10", Decimal("300"))]  # solo C3
+    decl = SaldoFavorDeclarado(aplica_desde="2026-05-01", valor=Decimal("100"))
+    (c3,) = liquidar(facturas, saldo_declarado=decl)
+    assert c3.saldo_favor_previo == Decimal("100")
+    assert c3.neto_a_pagar == Decimal("200")
+
+
+def test_liquidar_saldo_declarado_no_toca_periodos_anteriores():
+    """Un declarado que entra en C2 no altera la liquidación de C1 (el pasado ya
+    declarado no se reescribe — regla 4)."""
+    facturas = [FacturaIva("venta", "2026-02-10", Decimal("90"))]  # solo C1
+    decl = SaldoFavorDeclarado(aplica_desde="2026-05-01", valor=Decimal("100"))
+    (c1,) = liquidar(facturas, saldo_declarado=decl)
+    assert c1.saldo_favor_previo == Decimal("0")
+    assert c1.neto_a_pagar == Decimal("90")
+
+
 def test_liquidar_bimestral_separa_en_seis_periodos():
     # ene (P1) y mar (P2) caen en bimestres DISTINTOS; cuatrimestral los uniría en C1.
     facturas = [
```

---

## Commit 589c7e4

```diff
commit 589c7e4de6efb7f07809427335868f864dcb981a
Author: RoddosCol <info@roddos.com>
Date:   Tue Aug 11 20:31:56 2026 -0500

    feat(modelos): segundo plan de pago por modelo (78/52) con peso editable (#93)
    
    Cada modelo puede ofrecer dos planes de pago (CEO 2026-08-11): el actual
    (78 sem) y uno opcional (p. ej. 52 sem) con su propia cuota semanal;
    comparten precio, inicial, matricula y costo Auteco. Reparto POR MODELO
    editable (peso_plan1, arranque 70/30).
    
    Capa ADITIVA: _modelo_a_lineas expande cada modelo en una linea de motor
    por plan (mix = participacion x peso). motor.py CERO diffs; golden master
    intacto. Sport 110 queda de un solo plan (peso 1) sin caso especial.
    Validaciones fail-closed (plan 2 incompleto / peso fuera de 0..1 / peso
    menor a 1 sin plan 2 dan 422); quitar_plan2 vuelve a un solo plan; el
    fingerprint del cache de sensibilidad invalida con los campos nuevos.
    UI: tabla con los dos planes + seccion "Segundo plan de pago" en el
    dialogo de edicion.
    
    TDD: 10 tests primero en rojo. Candados: sin plan 2 = linea identica; la
    particion no inventa plata (iniciales exactas, recaudo <=0.5%/mes por la
    colocacion semanal entera del motor certificado). Backend 948 passed +
    ruff; frontend 257 + build + biome.
    
    Co-authored-by: Claude Fable 5 <noreply@anthropic.com>
---
 backend/app/domain/modelo_moto.py     |   9 +
 backend/app/modelos_moto/router.py    |  22 +++
 backend/app/modelos_moto/service.py   |  58 ++++++
 backend/app/proyeccion/service.py     |  32 +++-
 backend/tests/test_modelos_planes.py  | 326 ++++++++++++++++++++++++++++++++++
 frontend/src/lib/modelosMoto.ts       |  13 ++
 frontend/src/pages/DatosPage.test.tsx |   3 +
 frontend/src/pages/DatosPage.tsx      |  97 ++++++++--
 8 files changed, 539 insertions(+), 21 deletions(-)

diff --git a/backend/app/domain/modelo_moto.py b/backend/app/domain/modelo_moto.py
index ffd48ad..a1b4baa 100644
--- a/backend/app/domain/modelo_moto.py
+++ b/backend/app/domain/modelo_moto.py
@@ -10,6 +10,8 @@ inicial · cuota semanal · plazo · matrícula) + participación en el mix. El
 recaudo. Todo monto es Decimal/Money (regla 1); `participacion_mix` es fracción 0..1.
 """
 
+from decimal import Decimal
+
 from beanie import Document
 from pydantic import ConfigDict, Field
 from pymongo import IndexModel
@@ -30,6 +32,13 @@ class ModeloMoto(Document):
     plazo_semanas: int = Field(gt=0)
     matricula: Money
     participacion_mix: Money  # fracción 0..1 (participación en la colocación)
+    # PLAN-52 (CEO 2026-08-11): segundo plan de pago OPCIONAL (p. ej. 52 semanas)
+    # con su propia cuota; comparte precio, inicial, matrícula y costo Auteco.
+    # `peso_plan1` = fracción 0..1 del mix del modelo que va al plan 1 (el resto al
+    # plan 2); sin plan 2 debe ser 1. La coherencia la valida el servicio (422).
+    plan2_plazo_semanas: int | None = Field(default=None, gt=0)
+    plan2_cuota_semanal: Money | None = None
+    peso_plan1: Money = Decimal("1")
     orden: int
     activo: bool = True
     es_sistema: bool = False
diff --git a/backend/app/modelos_moto/router.py b/backend/app/modelos_moto/router.py
index a4cce69..85a8083 100644
--- a/backend/app/modelos_moto/router.py
+++ b/backend/app/modelos_moto/router.py
@@ -41,6 +41,10 @@ class ModeloCrearBody(BaseModel):
     plazo_semanas: int = Field(gt=0)
     matricula: str
     participacion_mix: str
+    # PLAN-52: segundo plan opcional (plazo + cuota juntos) y reparto entre planes
+    plan2_plazo_semanas: int | None = Field(default=None, gt=0)
+    plan2_cuota_semanal: str | None = None
+    peso_plan1: str = "1"
 
 
 class ModeloEditarBody(BaseModel):
@@ -49,6 +53,8 @@ class ModeloEditarBody(BaseModel):
     nombre: str | None = Field(default=None, min_length=1, max_length=60)
     orden: int | None = None
     plazo_semanas: int | None = Field(default=None, gt=0)
+    plan2_plazo_semanas: int | None = Field(default=None, gt=0)
+    quitar_plan2: bool = False  # PLAN-52: vuelve a un solo plan (peso regresa a 1)
     activo: bool | None = None  # solo true (reactivar, B-3); false → 422
     costo_auteco: str | None = None
     precio_venta_con_iva: str | None = None
@@ -56,6 +62,8 @@ class ModeloEditarBody(BaseModel):
     cuota_semanal: str | None = None
     matricula: str | None = None
     participacion_mix: str | None = None
+    plan2_cuota_semanal: str | None = None
+    peso_plan1: str | None = None
 
 
 def _serializar(m: ModeloMoto) -> dict:
@@ -69,6 +77,11 @@ def _serializar(m: ModeloMoto) -> dict:
         "plazo_semanas": m.plazo_semanas,
         "matricula": str(m.matricula),
         "participacion_mix": str(m.participacion_mix),
+        "plan2_plazo_semanas": m.plan2_plazo_semanas,
+        "plan2_cuota_semanal": (
+            str(m.plan2_cuota_semanal) if m.plan2_cuota_semanal is not None else None
+        ),
+        "peso_plan1": str(m.peso_plan1),
         "orden": m.orden,
         "activo": m.activo,
         "es_sistema": m.es_sistema,
@@ -103,6 +116,13 @@ async def crear(
             matricula=_dec(body.matricula, "matricula"),
             participacion_mix=_dec(body.participacion_mix, "participacion_mix"),
             usuario_id=user.id,
+            plan2_plazo_semanas=body.plan2_plazo_semanas,
+            plan2_cuota_semanal=(
+                _dec(body.plan2_cuota_semanal, "plan2_cuota_semanal")
+                if body.plan2_cuota_semanal is not None
+                else None
+            ),
+            peso_plan1=_dec(body.peso_plan1, "peso_plan1"),
         )
     except service.ModelosMotoError as e:
         raise HTTPException(e.status, e.detalle) from e
@@ -128,6 +148,8 @@ async def editar(
             nombre=body.nombre,
             orden=body.orden,
             plazo_semanas=body.plazo_semanas,
+            plan2_plazo_semanas=body.plan2_plazo_semanas,
+            quitar_plan2=body.quitar_plan2,
             activo=body.activo,
             campos_money=campos_money or None,
         )
diff --git a/backend/app/modelos_moto/service.py b/backend/app/modelos_moto/service.py
index 15a102e..24733d7 100644
--- a/backend/app/modelos_moto/service.py
+++ b/backend/app/modelos_moto/service.py
@@ -47,6 +47,24 @@ async def listar_modelos(*, activo: bool | None = None) -> list[ModeloMoto]:
     return await ModeloMoto.find(*filtros).sort(+ModeloMoto.orden).to_list()
 
 
+def _validar_planes(modelo: ModeloMoto) -> None:
+    """PLAN-52: coherencia fail-closed del segundo plan. (plazo, cuota) del plan 2 van
+    JUNTOS; `peso_plan1` es fracción 0..1 y sin plan 2 debe ser exactamente 1 (el mix
+    completo del modelo va al único plan)."""
+    tiene_plazo = modelo.plan2_plazo_semanas is not None
+    tiene_cuota = modelo.plan2_cuota_semanal is not None
+    if tiene_plazo != tiene_cuota:
+        raise ModelosMotoError(
+            "plan 2 incompleto: plazo y cuota semanal del plan 2 van juntos", 422
+        )
+    if not (Decimal("0") <= modelo.peso_plan1 <= Decimal("1")):
+        raise ModelosMotoError("peso_plan1 debe ser una fracción entre 0 y 1", 422)
+    if not tiene_plazo and modelo.peso_plan1 != Decimal("1"):
+        raise ModelosMotoError(
+            "sin plan 2, peso_plan1 debe ser 1 (todo el mix va al único plan)", 422
+        )
+
+
 async def crear_modelo(
     *,
     nombre: str,
@@ -58,6 +76,9 @@ async def crear_modelo(
     matricula: Decimal,
     participacion_mix: Decimal,
     usuario_id: str,
+    plan2_plazo_semanas: int | None = None,
+    plan2_cuota_semanal: Decimal | None = None,
+    peso_plan1: Decimal = Decimal("1"),
 ) -> ModeloMoto:
     """POST: crea con `orden` = máx+1 y emite `modelo_moto.creado` (fail-closed)."""
     if await ModeloMoto.find_one(ModeloMoto.nombre == nombre) is not None:
@@ -72,8 +93,12 @@ async def crear_modelo(
         plazo_semanas=plazo_semanas,
         matricula=matricula,
         participacion_mix=participacion_mix,
+        plan2_plazo_semanas=plan2_plazo_semanas,
+        plan2_cuota_semanal=plan2_cuota_semanal,
+        peso_plan1=peso_plan1,
         orden=(ultimo.orden if ultimo is not None else 0) + 1,
     )
+    _validar_planes(modelo)
     try:
         await modelo.insert()
     except DuplicateKeyError:
@@ -100,6 +125,9 @@ _EDITABLES_MONEY = (
     "cuota_semanal",
     "matricula",
     "participacion_mix",
+    # PLAN-52: cuota del segundo plan y reparto entre planes (fracción 0..1)
+    "plan2_cuota_semanal",
+    "peso_plan1",
 )
 
 
@@ -110,6 +138,8 @@ async def editar_modelo(
     nombre: str | None = None,
     orden: int | None = None,
     plazo_semanas: int | None = None,
+    plan2_plazo_semanas: int | None = None,
+    quitar_plan2: bool = False,
     activo: bool | None = None,
     campos_money: dict[str, Decimal] | None = None,
 ) -> ModeloMoto:
@@ -140,6 +170,32 @@ async def editar_modelo(
         }
         modelo.plazo_semanas = plazo_semanas
 
+    if plan2_plazo_semanas is not None and (
+        plan2_plazo_semanas != modelo.plan2_plazo_semanas
+    ):
+        previos["plan2_plazo_semanas"] = modelo.plan2_plazo_semanas
+        cambios["plan2_plazo_semanas"] = {
+            "anterior": modelo.plan2_plazo_semanas,
+            "nuevo": plan2_plazo_semanas,
+        }
+        modelo.plan2_plazo_semanas = plan2_plazo_semanas
+
+    if quitar_plan2 and (
+        modelo.plan2_plazo_semanas is not None
+        or modelo.plan2_cuota_semanal is not None
+        or modelo.peso_plan1 != Decimal("1")
+    ):
+        for campo, nuevo in (
+            ("plan2_plazo_semanas", None),
+            ("plan2_cuota_semanal", None),
+            ("peso_plan1", Decimal("1")),
+        ):
+            actual = getattr(modelo, campo)
+            if nuevo != actual:
+                previos[campo] = actual
+                cambios[campo] = {"anterior": str(actual), "nuevo": str(nuevo)}
+                setattr(modelo, campo, nuevo)
+
     if activo is not None:
         if activo is False:
             raise ModelosMotoError(
@@ -165,6 +221,8 @@ async def editar_modelo(
     if not cambios:
         raise ModelosMotoError("nada que editar (ningún campo cambia)", 422)
 
+    _validar_planes(modelo)  # PLAN-52: el estado FINAL debe ser coherente (422)
+
     try:
         await modelo.save()
     except DuplicateKeyError:
diff --git a/backend/app/proyeccion/service.py b/backend/app/proyeccion/service.py
index 17c010a..8d98094 100644
--- a/backend/app/proyeccion/service.py
+++ b/backend/app/proyeccion/service.py
@@ -64,8 +64,12 @@ class ProyeccionError(Exception):
         self.status = status
 
 
-def _modelo_a_motor(m: ModeloMoto) -> ModeloProyeccion:
-    return ModeloProyeccion(
+def _modelo_a_lineas(m: ModeloMoto) -> list[ModeloProyeccion]:
+    """PLAN-52 (CEO 2026-08-11): expande un modelo en UNA línea de motor por plan de
+    pago, con mix = participación del modelo × peso del plan. El motor certificado no
+    cambia (consume líneas como siempre); sin plan 2 la línea es IDÉNTICA a la de
+    siempre — candado golden-master en test_modelos_planes."""
+    base = ModeloProyeccion(
         nombre=m.nombre,
         cuota_semanal=m.cuota_semanal,
         cuota_inicial=m.cuota_inicial,
@@ -73,6 +77,22 @@ def _modelo_a_motor(m: ModeloMoto) -> ModeloProyeccion:
         mix=m.participacion_mix,
         costo_moto=m.costo_auteco,
     )
+    if m.plan2_cuota_semanal is None or m.plan2_plazo_semanas is None:
+        return [base]
+    return [
+        replace(
+            base,
+            nombre=f"{m.nombre} · {m.plazo_semanas} sem",
+            mix=m.participacion_mix * m.peso_plan1,
+        ),
+        replace(
+            base,
+            nombre=f"{m.nombre} · {m.plan2_plazo_semanas} sem",
+            cuota_semanal=m.plan2_cuota_semanal,
+            plazo_semanas=m.plan2_plazo_semanas,
+            mix=m.participacion_mix * (Decimal("1") - m.peso_plan1),
+        ),
+    ]
 
 
 def _rampa_a_lista(
@@ -111,7 +131,7 @@ def _armar_parametros(
     return ParametrosMotor(
         mes_inicio=mes_inicio,
         horizonte_meses=horizonte_meses,
-        modelos=[_modelo_a_motor(m) for m in modelos],
+        modelos=[ln for m in modelos for ln in _modelo_a_lineas(m)],
         motos_base=params.motos_base,
         crec_pct_mensual=params.crec_pct_mensual,
         rampa=_rampa_a_lista(params.rampa_unidades, mes_inicio),
@@ -726,7 +746,7 @@ async def operacion_vigente(
         raise ProyeccionError(
             f"horizonte_meses debe estar en [1, {HORIZONTE_MAX}]", 422
         )
-    modelos_m = [_modelo_a_motor(m) for m in modelos]
+    modelos_m = [ln for m in modelos for ln in _modelo_a_lineas(m)]
     _, activos_previos = await cartera_previa_service.obtener_series()
 
     colocacion = colocacion_mensual(
@@ -865,6 +885,10 @@ def _fingerprint(params: ParametrosProyeccion, modelos: list[ModeloMoto]) -> tup
                 m.plazo_semanas,
                 str(m.participacion_mix),
                 str(m.costo_auteco),
+                # PLAN-52: el segundo plan y su peso también invalidan el cache
+                m.plan2_plazo_semanas,
+                str(m.plan2_cuota_semanal),
+                str(m.peso_plan1),
             )
             for m in modelos
         ),
diff --git a/backend/tests/test_modelos_planes.py b/backend/tests/test_modelos_planes.py
new file mode 100644
index 0000000..2bd37d9
--- /dev/null
+++ b/backend/tests/test_modelos_planes.py
@@ -0,0 +1,326 @@
+# backend/tests/test_modelos_planes.py
+"""PLAN-52 (CEO 2026-08-11) — segundo plan de pago por modelo de moto.
+
+Cada modelo puede ofrecer DOS planes (p. ej. 78 y 52 semanas) con su propia cuota
+semanal; comparten precio, cuota inicial, matrícula y costo Auteco. El reparto entre
+planes es POR MODELO y editable (`peso_plan1`, fracción 0..1; arranque 70/30).
+
+El MOTOR CERTIFICADO NO SE TOCA: el puente `_modelo_a_lineas` expande cada modelo en
+una línea de motor por plan con mix = participación × peso. Candados:
+  - Sin plan 2 → UNA línea idéntica a la de siempre (golden master intacto).
+  - Plan 2 idéntico al 1 → proyección EXACTAMENTE igual a la de un solo plan
+    (la partición no inventa ni pierde plata).
+  - Validaciones fail-closed: plan 2 incompleto, peso fuera de 0..1, peso < 1 sin
+    plan 2 → 422.
+"""
+
+from decimal import Decimal
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
+from app.domain.modelo_moto import ModeloMoto
+from app.main import create_app
+from app.proyeccion.service import _modelo_a_lineas
+from beanie import init_beanie
+from mongomock_motor import AsyncMongoMockClient
+
+PWD = "clave-larga-1234"
+
+
+def _modelo(**extra) -> ModeloMoto:
+    base = dict(
+        nombre="Raider",
+        costo_auteco=Decimal("5000000"),
+        precio_venta_con_iva=Decimal("8000000"),
+        cuota_inicial=Decimal("1620000"),
+        cuota_semanal=Decimal("184900"),
+        plazo_semanas=78,
+        matricula=Decimal("0"),
+        participacion_mix=Decimal("0.35"),
+        orden=1,
+    )
+    base.update(extra)
+    return ModeloMoto(**base)
+
+
+# ── Puente (compute-only): expansión modelo → líneas de plan ──
+
+
+def test_sin_plan2_una_linea_identica():
+    """Candado golden-master: un modelo sin plan 2 produce UNA línea con los mismos
+    valores de siempre (nombre sin sufijo, mix completo)."""
+    (linea,) = _modelo_a_lineas(_modelo())
+    assert linea.nombre == "Raider"
+    assert linea.cuota_semanal == Decimal("184900")
+    assert linea.plazo_semanas == 78
+    assert linea.mix == Decimal("0.35")
+    assert linea.cuota_inicial == Decimal("1620000")
+    assert linea.costo_moto == Decimal("5000000")
+
+
+def test_con_plan2_dos_lineas_con_mix_repartido():
+    m = _modelo(
+        plan2_plazo_semanas=52,
+        plan2_cuota_semanal=Decimal("214900"),
+        peso_plan1=Decimal("0.70"),
+    )
+    l1, l2 = _modelo_a_lineas(m)
+    assert l1.nombre == "Raider · 78 sem"
+    assert l1.cuota_semanal == Decimal("184900")
+    assert l1.plazo_semanas == 78
+    assert l1.mix == Decimal("0.35") * Decimal("0.70")  # 0.245
+    assert l2.nombre == "Raider · 52 sem"
+    assert l2.cuota_semanal == Decimal("214900")
+    assert l2.plazo_semanas == 52
+    assert l2.mix == Decimal("0.35") * Decimal("0.30")  # 0.105
+    # los planes comparten inicial y costo (decisión CEO: solo cambia cuota+plazo)
+    for ln in (l1, l2):
+        assert ln.cuota_inicial == Decimal("1620000")
+        assert ln.costo_moto == Decimal("5000000")
+    # el mix del modelo se conserva completo entre sus líneas
+    assert l1.mix + l2.mix == Decimal("0.35")
+
+
+# ── API: CRUD con plan 2 + validaciones + proyección end-to-end ──
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
+    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
+    repository.configure_auth(c, "compas_test")
+    configure_audit(c, "compas_test")
+    await repository.create_user(
+        User(
+            email="fin@roddos.com",
+            password_hash=passwords.hash_password(PWD),
+            rol=Role.financiero,
+        )
+    )
+    transport = httpx.ASGITransport(app=app)
+    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
+        yield ac
+    repository.reset_auth()
+    reset_audit()
+    get_settings.cache_clear()
+
+
+async def _token(ac) -> dict:
+    r = await ac.post(
+        "/api/v1/auth/login", json={"email": "fin@roddos.com", "password": PWD}
+    )
+    assert r.status_code == 200
+    return {"Authorization": f"Bearer {r.json()['access_token']}"}
+
+
+def _body(nombre="Raider", mix="1", **extra) -> dict:
+    b = {
+        "nombre": nombre,
+        "costo_auteco": "5000000",
+        "precio_venta_con_iva": "8000000",
+        "cuota_inicial": "1620000",
+        "cuota_semanal": "184900",
+        "plazo_semanas": 78,
+        "matricula": "0",
+        "participacion_mix": mix,
+    }
+    b.update(extra)
+    return b
+
+
+def _params_body() -> dict:
+    return {
+        "vigente_desde": "2026-07-01",
+        "caja_inicial": "24000000",
+        "caja_minima": "125000000",
+        "motos_base": 50,
+        "crec_pct_mensual": "0.01",
+        "horizonte_meses": 12,
+        "adelanto_auteco": "970000",
+        "plazo_auteco_dias": 150,
+        "base_auteco_dias": 90,
+        "tasa_auteco": "0.016",
+        "gastos_fijos": "125000000",
+        "gps_moto": "33201",
+        "costo_moto_nueva": "692005",
+        "deuda": "28527080",
+        "tasa_deuda": "0.011",
+        "mes_inicio_deuda": 2,
+        "meses_deuda": 14,
+        "pct_mora": "0.03",
+        "pct_recuperacion": "0.40",
+        "pct_default": "0.03",
+        "pct_provision": "0.02",
+    }
+
+
+@pytest.mark.asyncio
+async def test_crear_con_plan2_y_serializacion(api):
+    h = await _token(api)
+    r = await api.post(
+        "/api/v1/modelos-moto",
+        json=_body(
+            plan2_plazo_semanas=52,
+            plan2_cuota_semanal="214900",
+            peso_plan1="0.70",
+        ),
+        headers=h,
+    )
+    assert r.status_code == 201, r.text
+    d = r.json()
+    assert d["plan2_plazo_semanas"] == 52
+    assert d["plan2_cuota_semanal"] == "214900"
+    assert d["peso_plan1"] == "0.70"
+
+
+@pytest.mark.asyncio
+async def test_crear_sin_plan2_serializa_defaults(api):
+    h = await _token(api)
+    r = await api.post("/api/v1/modelos-moto", json=_body(), headers=h)
+    assert r.status_code == 201, r.text
+    d = r.json()
+    assert d["plan2_plazo_semanas"] is None
+    assert d["plan2_cuota_semanal"] is None
+    assert d["peso_plan1"] == "1"
+
+
+@pytest.mark.asyncio
+async def test_plan2_incompleto_es_422(api):
+    h = await _token(api)
+    r = await api.post(
+        "/api/v1/modelos-moto",
+        json=_body(plan2_plazo_semanas=52),  # sin cuota del plan 2
+        headers=h,
+    )
+    assert r.status_code == 422
+    assert "plan 2" in r.json()["detail"].lower()
+
+
+@pytest.mark.asyncio
+async def test_peso_fuera_de_rango_es_422(api):
+    h = await _token(api)
+    r = await api.post(
+        "/api/v1/modelos-moto",
+        json=_body(
+            plan2_plazo_semanas=52,
+            plan2_cuota_semanal="214900",
+            peso_plan1="1.2",
+        ),
+        headers=h,
+    )
+    assert r.status_code == 422
+
+
+@pytest.mark.asyncio
+async def test_peso_menor_a_uno_sin_plan2_es_422(api):
+    h = await _token(api)
+    r = await api.post(
+        "/api/v1/modelos-moto", json=_body(peso_plan1="0.70"), headers=h
+    )
+    assert r.status_code == 422
+    assert "plan" in r.json()["detail"].lower()
+
+
+@pytest.mark.asyncio
+async def test_editar_agrega_y_quita_plan2(api):
+    h = await _token(api)
+    r = await api.post("/api/v1/modelos-moto", json=_body(), headers=h)
+    mid = r.json()["id"]
+
+    # agregar el plan 2 con su peso
+    r = await api.patch(
+        f"/api/v1/modelos-moto/{mid}",
+        json={
+            "plan2_plazo_semanas": 52,
+            "plan2_cuota_semanal": "214900",
+            "peso_plan1": "0.70",
+        },
+        headers=h,
+    )
+    assert r.status_code == 200, r.text
+    assert r.json()["plan2_plazo_semanas"] == 52
+    assert r.json()["peso_plan1"] == "0.70"
+
+    # quitarlo: vuelve a un solo plan y el peso regresa a 1
+    r = await api.patch(
+        f"/api/v1/modelos-moto/{mid}", json={"quitar_plan2": True}, headers=h
+    )
+    assert r.status_code == 200, r.text
+    d = r.json()
+    assert d["plan2_plazo_semanas"] is None
+    assert d["plan2_cuota_semanal"] is None
+    assert d["peso_plan1"] == "1"
+
+
+@pytest.mark.asyncio
+async def test_editar_dejando_plan2_incompleto_es_422(api):
+    h = await _token(api)
+    r = await api.post("/api/v1/modelos-moto", json=_body(), headers=h)
+    mid = r.json()["id"]
+    r = await api.patch(
+        f"/api/v1/modelos-moto/{mid}",
+        json={"plan2_cuota_semanal": "214900"},  # sin plazo del plan 2
+        headers=h,
+    )
+    assert r.status_code == 422
+
+
+@pytest.mark.asyncio
+async def test_proyeccion_con_dos_planes_particion_no_inventa_plata(api):
+    """Candado de partición: un modelo dividido en dos planes IDÉNTICOS (misma cuota y
+    plazo) con peso 0.70 proyecta lo MISMO que sin dividir. Exacto en cuotas
+    iniciales (camino fraccionario `total×mix×inicial`); en el recaudo la igualdad es
+    APROXIMADA (≤0.5% mensual) porque el motor certificado coloca las ALTAS en
+    semanas enteras por línea — repartir n motos en dos grupos mueve algunas altas de
+    semana (mismo efecto tendría el artefacto con dos filas). Partir el mix no crea
+    ni pierde plata más allá de ese corrimiento semanal."""
+    h = await _token(api)
+    r = await api.post("/api/v1/modelos-moto", json=_body(), headers=h)
+    assert r.status_code == 201
+    mid = r.json()["id"]
+    r = await api.put(
+        "/api/v1/parametros-proyeccion", json=_params_body(), headers=h
+    )
+    assert r.status_code == 200
+
+    base = await api.get("/api/v1/proyeccion?horizonte_meses=12", headers=h)
+    assert base.status_code == 200
+
+    r = await api.patch(
+        f"/api/v1/modelos-moto/{mid}",
+        json={
+            "plan2_plazo_semanas": 78,  # plan 2 idéntico al 1
+            "plan2_cuota_semanal": "184900",
+            "peso_plan1": "0.70",
+        },
+        headers=h,
+    )
+    assert r.status_code == 200, r.text
+    dividido = await api.get("/api/v1/proyeccion?horizonte_meses=12", headers=h)
+    assert dividido.status_code == 200
+
+    for m_base, m_div in zip(
+        base.json()["meses"], dividido.json()["meses"], strict=True
+    ):
+        # cuotas iniciales: camino fraccionario → igualdad EXACTA
+        assert m_base["cuotas_iniciales"] == m_div["cuotas_iniciales"]
+        # recaudo: igualdad aproximada (corrimiento de altas por semanas enteras)
+        rb = Decimal(m_base["recaudo_credito"])
+        rd = Decimal(m_div["recaudo_credito"])
+        assert abs(rb - rd) <= abs(rb) * Decimal("0.005"), (
+            f"recaudo se desvía más de 0.5%: base {rb} vs dividido {rd}"
+        )
diff --git a/frontend/src/lib/modelosMoto.ts b/frontend/src/lib/modelosMoto.ts
index 3b9d439..fe6d320 100644
--- a/frontend/src/lib/modelosMoto.ts
+++ b/frontend/src/lib/modelosMoto.ts
@@ -17,6 +17,11 @@ export interface ModeloMoto {
   plazo_semanas: number;
   matricula: string;
   participacion_mix: string;
+  /** PLAN-52: segundo plan de pago opcional (comparte precio/inicial/costo). */
+  plan2_plazo_semanas: number | null;
+  plan2_cuota_semanal: string | null;
+  /** Fracción 0..1 del mix del modelo que va al plan 1; sin plan 2 es "1". */
+  peso_plan1: string;
   orden: number;
   activo: boolean;
   es_sistema: boolean;
@@ -31,6 +36,9 @@ export interface ModeloCrearInput {
   plazo_semanas: number;
   matricula: string;
   participacion_mix: string;
+  plan2_plazo_semanas?: number;
+  plan2_cuota_semanal?: string;
+  peso_plan1?: string;
 }
 
 export interface ModeloEditarInput {
@@ -46,6 +54,11 @@ export interface ModeloEditarInput {
   cuota_semanal?: string;
   matricula?: string;
   participacion_mix?: string;
+  plan2_plazo_semanas?: number;
+  plan2_cuota_semanal?: string;
+  peso_plan1?: string;
+  /** PLAN-52: vuelve el modelo a un solo plan (el peso regresa a 1). */
+  quitar_plan2?: true;
 }
 
 export async function listarModelos(activo?: boolean): Promise<ModeloMoto[]> {
diff --git a/frontend/src/pages/DatosPage.test.tsx b/frontend/src/pages/DatosPage.test.tsx
index 83b918b..db82959 100644
--- a/frontend/src/pages/DatosPage.test.tsx
+++ b/frontend/src/pages/DatosPage.test.tsx
@@ -101,6 +101,9 @@ const MODELO = {
   plazo_semanas: 78,
   matricula: "500000",
   participacion_mix: "1",
+  plan2_plazo_semanas: null,
+  plan2_cuota_semanal: null,
+  peso_plan1: "1",
   activo: true,
   es_sistema: false,
 };
diff --git a/frontend/src/pages/DatosPage.tsx b/frontend/src/pages/DatosPage.tsx
index 12a0823..1b9cbe6 100644
--- a/frontend/src/pages/DatosPage.tsx
+++ b/frontend/src/pages/DatosPage.tsx
@@ -1594,6 +1594,21 @@ const CAMPOS_MODELO: { key: keyof ModeloEditarInput; label: string }[] = [
   { key: "participacion_mix", label: "Participación en ventas (%)" },
 ];
 
+// PLAN-52: campos del segundo plan (vacíos ambos = el modelo vuelve a un solo plan)
+const CAMPOS_PLAN2: {
+  key: keyof ModeloEditarInput;
+  label: string;
+  hint?: string;
+}[] = [
+  { key: "plan2_plazo_semanas", label: "Plan 2 · plazo (semanas)" },
+  { key: "plan2_cuota_semanal", label: "Plan 2 · cuota semanal" },
+  {
+    key: "peso_plan1",
+    label: "Peso del plan 1",
+    hint: "fracción — ej: 0.7 = 70 % de las ventas del modelo al plan 1, el resto al plan 2",
+  },
+];
+
 function EditarModeloDialog({
   m,
   guardando,
@@ -1607,24 +1622,22 @@ function EditarModeloDialog({
   onCerrar: () => void;
   onGuardar: (cambios: ModeloEditarInput) => void;
 }) {
-  const [v, setV] = useState<Record<string, string>>({
-    nombre: m.nombre,
-    cuota_semanal: m.cuota_semanal,
-    cuota_inicial: m.cuota_inicial,
-    plazo_semanas: String(m.plazo_semanas),
-    costo_auteco: m.costo_auteco,
-    precio_venta_con_iva: m.precio_venta_con_iva,
-    participacion_mix: m.participacion_mix,
+  const valores = (mm: ModeloMoto): Record<string, string> => ({
+    nombre: mm.nombre,
+    cuota_semanal: mm.cuota_semanal,
+    cuota_inicial: mm.cuota_inicial,
+    plazo_semanas: String(mm.plazo_semanas),
+    costo_auteco: mm.costo_auteco,
+    precio_venta_con_iva: mm.precio_venta_con_iva,
+    participacion_mix: mm.participacion_mix,
+    plan2_plazo_semanas: mm.plan2_plazo_semanas
+      ? String(mm.plan2_plazo_semanas)
+      : "",
+    plan2_cuota_semanal: mm.plan2_cuota_semanal ?? "",
+    peso_plan1: mm.peso_plan1 ?? "1",
   });
-  const actual: Record<string, string> = {
-    nombre: m.nombre,
-    cuota_semanal: m.cuota_semanal,
-    cuota_inicial: m.cuota_inicial,
-    plazo_semanas: String(m.plazo_semanas),
-    costo_auteco: m.costo_auteco,
-    precio_venta_con_iva: m.precio_venta_con_iva,
-    participacion_mix: m.participacion_mix,
-  };
+  const [v, setV] = useState<Record<string, string>>(valores(m));
+  const actual: Record<string, string> = valores(m);
 
   function onSubmit(e: FormEvent) {
     e.preventDefault();
@@ -1635,6 +1648,25 @@ function EditarModeloDialog({
         cambios[key] = key === "plazo_semanas" ? Number(nuevo) : nuevo;
       }
     }
+    // PLAN-52: los dos campos del plan 2 vacíos = quitar el plan (peso vuelve a 1);
+    // si hay valores, solo viajan los que cambian (el backend valida coherencia).
+    const p2Plazo = (v.plan2_plazo_semanas ?? "").trim();
+    const p2Cuota = (v.plan2_cuota_semanal ?? "").trim();
+    const teniaPlan2 = m.plan2_plazo_semanas !== null;
+    if (!p2Plazo && !p2Cuota) {
+      if (teniaPlan2) cambios.quitar_plan2 = true;
+    } else {
+      if (p2Plazo !== actual.plan2_plazo_semanas) {
+        cambios.plan2_plazo_semanas = Number(p2Plazo);
+      }
+      if (p2Cuota !== actual.plan2_cuota_semanal) {
+        cambios.plan2_cuota_semanal = p2Cuota;
+      }
+    }
+    const peso = (v.peso_plan1 ?? "").trim();
+    if (peso && peso !== actual.peso_plan1 && !cambios.quitar_plan2) {
+      cambios.peso_plan1 = peso;
+    }
     onGuardar(cambios as unknown as ModeloEditarInput);
   }
 
@@ -1663,6 +1695,21 @@ function EditarModeloDialog({
               />
             ))}
           </div>
+          <p className="mt-4 mb-2 font-sans text-apoyo font-semibold tracking-wider text-ink-faint uppercase">
+            Segundo plan de pago (opcional — vacío = un solo plan)
+          </p>
+          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
+            {CAMPOS_PLAN2.map((c) => (
+              <CampoModelo
+                key={c.key}
+                label={c.label}
+                hint={c.hint}
+                inputMode="decimal"
+                value={v[c.key] ?? ""}
+                onChange={(nv) => setV((s) => ({ ...s, [c.key]: nv }))}
+              />
+            ))}
+          </div>
           {error && (
             <div className="mt-3">
               <AlertBanner variant="danger">{error}</AlertBanner>
@@ -1707,6 +1754,11 @@ function ModeloFila({
       </td>
       <td className="tabular px-3 py-2 text-right text-ink-soft">
         {formatCOP(m.cuota_semanal)}
+        {m.plan2_cuota_semanal ? (
+          <div className="text-ink-faint">
+            {formatCOP(m.plan2_cuota_semanal)}
+          </div>
+        ) : null}
       </td>
       <td
         className="tabular px-3 py-2 text-right text-ink-soft"
@@ -1716,9 +1768,20 @@ function ModeloFila({
       </td>
       <td className="tabular px-3 py-2 text-right text-ink-soft">
         {m.plazo_semanas} sem
+        {m.plan2_plazo_semanas ? (
+          <div className="text-ink-faint">{m.plan2_plazo_semanas} sem</div>
+        ) : null}
       </td>
       <td className="tabular px-3 py-2 text-right text-ink-soft">
         {m.participacion_mix}
+        {m.plan2_plazo_semanas ? (
+          <div
+            className="text-ink-faint"
+            title={`Reparto entre planes: ${m.peso_plan1} del mix al plan de ${m.plazo_semanas} sem; el resto al de ${m.plan2_plazo_semanas} sem`}
+          >
+            peso {m.peso_plan1}
+          </div>
+        ) : null}
       </td>
       <td className="px-3 py-2">
         <span
```

---

## Commit f011ea5

```diff
commit f011ea5b13d4e41f768c502f9ae9f9a77e8e4666
Author: RoddosCol <info@roddos.com>
Date:   Wed Aug 12 09:31:29 2026 -0500

    fix(proyeccion): el tornado mide la misma pista que la pantalla (#94)
    
    Bug reportado por el CEO 2026-08-11: el tornado de sensibilidad quedo
    "todo en $0". Causa raiz: sensibilidad_vigente corria el motor CRUDO,
    sin las capas que GET /proyeccion si aplica (E1 anclaje a la ejecucion
    real + D2 reconciliacion de obligaciones). Cuando esas capas arrastran
    el minimo de la curva a un mes futuro (hoy: feb-2027, $492,5M), el piso
    crudo queda clavado en la caja del arranque ($704,7M) y ninguna
    variable lo mueve -> deltas $0 enganosos.
    
    Fix: cada una de las 14 corridas pasa por la MISMA tuberia (motor ->
    E1 -> D2, mismo orden de precedencia de _resultado_con). El cache
    incluye ahora la huella de las capas (_fingerprint_capas): un cierre
    nuevo o una factura de obligacion invalidan el tornado aunque los
    supuestos no cambien.
    
    TDD: test rojo primero (piso del tornado == piso_caja de la pantalla a
    60m + una factura D2 mueve el piso). Verificado contra PROD: piso base
    492.513.306 con deltas reales (colocacion +-10% -> +150,4M/-178,6M).
    Suite completa: 966 passed + ruff limpio.
    
    Co-authored-by: Claude Fable 5 <noreply@anthropic.com>
---
 backend/app/proyeccion/service.py             | 70 ++++++++++++++++++++++++---
 backend/tests/test_proyeccion_sensibilidad.py | 57 ++++++++++++++++++++++
 2 files changed, 121 insertions(+), 6 deletions(-)

diff --git a/backend/app/proyeccion/service.py b/backend/app/proyeccion/service.py
index 8d98094..c73dd75 100644
--- a/backend/app/proyeccion/service.py
+++ b/backend/app/proyeccion/service.py
@@ -895,11 +895,42 @@ def _fingerprint(params: ParametrosProyeccion, modelos: list[ModeloMoto]) -> tup
     )
 
 
+def _fingerprint_capas(anclas: dict, facturas: list[FacturaReconciliar]) -> tuple:
+    """Huella de las capas E1/D2 para el cache del tornado: un cierre nuevo o una
+    factura de obligación cambian el piso aunque los supuestos no cambien (bug CEO
+    2026-08-11 — el cache servía el mundo sin la factura)."""
+    return (
+        tuple(sorted((mes, repr(a)) for mes, a in anclas.items())),
+        tuple(
+            (
+                f.fecha_factura,
+                str(f.valor),
+                f.plazo_elegido_dias,
+                f.plazo_base_dias,
+                str(f.tasa_excedente_mensual),
+            )
+            for f in facturas
+        ),
+    )
+
+
 async def sensibilidad_vigente(*, escenario: str, mes_inicio: tuple[int, int]) -> dict:
-    """El tornado '¿qué mueve mi umbral?': 7 variables × ± → 14 corridas del motor
-    puro a 60 meses sobre el set vigente. Compute-only; cache por vigencia."""
+    """El tornado '¿qué mueve mi umbral?': 7 variables × ± → 14 corridas a 60 meses
+    sobre el set vigente, cada una por la MISMA tubería que GET /proyeccion
+    (motor → E1 anclaje → D2 reconciliación — bug CEO 2026-08-11: el motor crudo
+    dejaba el piso clavado en la caja del arranque y todos los deltas en $0).
+    Compute-only; cache por vigencia + huella de las capas."""
     params, modelos = await _cargar_config_vigente()
-    clave = (_fingerprint(params, modelos), escenario, mes_inicio)
+    anclas, rubros_e1, neutros_e1 = await cargar_anclas(
+        mes_inicio, SENSIBILIDAD_HORIZONTE
+    )
+    facturas = await _facturas_reconciliar()
+    clave = (
+        _fingerprint(params, modelos),
+        escenario,
+        mes_inicio,
+        _fingerprint_capas(anclas, facturas),
+    )
     if clave in _sensibilidad_cache:
         return _sensibilidad_cache[clave]
 
@@ -915,7 +946,34 @@ async def sensibilidad_vigente(*, escenario: str, mes_inicio: tuple[int, int]) -
         activos_previos,
         iva_egreso,
     )
-    piso_base = proyectar(pm).piso_caja
+
+    def piso_con_capas(pm_x: ParametrosMotor):
+        """Motor + E1 + D2 (mismo orden de precedencia de `_resultado_con`): el piso
+        que ve la pantalla. Los meses anclados no responden a las variaciones — el
+        pasado es del libro; el tornado mide el FUTURO, que es lo decidible."""
+        r = proyectar(pm_x)
+        meses_anclados: frozenset[str] = frozenset()
+        if anclas:
+            r = _kpis_a_resultado(
+                anclar(
+                    resultado=r,
+                    caja_minima=params.caja_minima,
+                    anclas=anclas,
+                    rubros=rubros_e1,
+                    neutros_ids=neutros_e1,
+                )
+            )
+            meses_anclados = frozenset(
+                m for m, a in anclas.items() if a.estado == CERRADO
+            )
+        if facturas:
+            rec = reconciliar(
+                r, facturas, params.caja_minima, meses_anclados=meses_anclados
+            )
+            r = _kpis_a_resultado(rec.ajustado)
+        return r.piso_caja
+
+    piso_base = piso_con_capas(pm)
 
     variables = []
     for v in _variaciones(pm):
@@ -925,8 +983,8 @@ async def sensibilidad_vigente(*, escenario: str, mes_inicio: tuple[int, int]) -
                 "etiqueta": v["etiqueta"],
                 "variacion": v["variacion"],
                 "piso_base": money_str(piso_base),
-                "piso_mas": money_str(proyectar(v["mas"]).piso_caja),
-                "piso_menos": money_str(proyectar(v["menos"]).piso_caja),
+                "piso_mas": money_str(piso_con_capas(v["mas"])),
+                "piso_menos": money_str(piso_con_capas(v["menos"])),
             }
         )
 
diff --git a/backend/tests/test_proyeccion_sensibilidad.py b/backend/tests/test_proyeccion_sensibilidad.py
index 568aa71..10b73f3 100644
--- a/backend/tests/test_proyeccion_sensibilidad.py
+++ b/backend/tests/test_proyeccion_sensibilidad.py
@@ -163,6 +163,63 @@ async def test_sensibilidad_sin_config_es_409(api):
     assert r.status_code == 409
 
 
+@pytest.mark.asyncio
+async def test_sensibilidad_mide_la_misma_pista_que_la_pantalla(api):
+    """Bug CEO 2026-08-11 ('el tornado quedó todo en $0'): el tornado corría el motor
+    CRUDO, sin las capas que GET /proyeccion sí aplica (E1 anclaje + D2
+    reconciliación). Cuando las capas arrastran el mínimo de la curva a un mes
+    futuro, el piso crudo queda clavado en la caja del arranque y ninguna variable
+    lo mueve → deltas $0 engañosos. Contrato: (a) el piso base del tornado ==
+    el piso de la pantalla a 60 meses; (b) una factura real de obligación (D2)
+    cambia el piso del tornado (el cache no puede servir el mundo sin factura)."""
+    h = await _setup_config(api)
+
+    r0 = await api.get(
+        "/api/v1/proyeccion/sensibilidad?mes_inicio=2026-07", headers=h
+    )
+    piso_sin_factura = r0.json()["piso_base"]
+
+    # obligación de facturación + factura grande que golpea la caja en nov-2026
+    oid = (
+        await api.post(
+            "/api/v1/obligaciones",
+            json={
+                "nombre": "Auteco",
+                "acreedor": "Auteco S.A.S.",
+                "naturaleza": "facturacion",
+                "plazo_base_dias": 90,
+                "plazo_max_dias": 150,
+                "tasa_excedente_mensual": "0.016",
+            },
+            headers=h,
+        )
+    ).json()["id"]
+    rf = await api.post(
+        f"/api/v1/obligaciones/{oid}/facturas",
+        json={
+            "fecha_factura": "2026-08-15",
+            "valor": "500000000",
+            "plazo_elegido_dias": 90,
+        },
+        headers=h,
+    )
+    assert rf.status_code in (200, 201), rf.text
+
+    p = await api.get(
+        "/api/v1/proyeccion?mes_inicio=2026-07&horizonte_meses=60", headers=h
+    )
+    assert p.status_code == 200, p.text
+    s = await api.get(
+        "/api/v1/proyeccion/sensibilidad?mes_inicio=2026-07", headers=h
+    )
+    assert s.status_code == 200, s.text
+
+    # (a) misma pista que la pantalla
+    assert s.json()["piso_base"] == p.json()["piso_caja"]
+    # (b) la factura D2 SÍ movió el piso del tornado (y el cache no sirvió lo viejo)
+    assert s.json()["piso_base"] != piso_sin_factura
+
+
 @pytest.mark.asyncio
 async def test_editar_dos_veces_el_mismo_dia_no_sirve_cache_viejo(api):
     """Bug QA C3: el upsert por vigente_desde deja id/fecha/autor idénticos al
```

---

## Salidas de tests (locales, reales)

- Suite tras #94: 966 passed, 95 skipped (requires_real_mongo) - All checks passed! (ruff)
- Suites en cada merge: #90=932, #91=934, #92=938, #93=948, #94=966 passed.
- Frontend: 257 passed (vitest) + npm run build verde (tsc -b + vite).
- Golden master del motor: verde en los 5 merges (motor.py cero diffs).

