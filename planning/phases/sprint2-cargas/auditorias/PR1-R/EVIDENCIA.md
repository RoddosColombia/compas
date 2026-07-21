# EVIDENCIA — sprint2-cargas · PR1-R (fixes de I-PR1)

Fix commit `f9985fe` sobre `54f12d6`. Solo el diff de los hallazgos + salidas.

## 1. pytest
```
238 passed, 23 skipped (6 nuevos: creada, carrera 409, consulta 403 x2, tope filas x2, zip bomb)
```

## 2. ruff
```
All checks passed!
```

## 3. Protocolo
```
r1:0 | journal-entries:0 | estado-pending:0
```

## 4. git diff --stat (f9985fe^..f9985fe)
```
CLAUDE.md                                          |  2 +-
 backend/app/audit/events.py                        | 13 +++++---
 backend/app/parsers/bank_parsers.py                | 35 ++++++++++++++++++++
 backend/app/transacciones/router.py                | 10 +++++-
 backend/app/transacciones/service.py               | 19 +++++++++--
 backend/tests/test_audit_events.py                 | 10 +++---
 backend/tests/test_bank_parsers.py                 | 38 ++++++++++++++++++++++
 backend/tests/test_cargas_endpoint.py              | 29 ++++++++++++-----
 backend/tests/test_transacciones_manual.py         | 31 ++++++++++++++++++
 .../sprint2-cargas/auditorias/PR1-I/RESPUESTA.md   | 16 +++++++++
 10 files changed, 183 insertions(+), 20 deletions(-)
```

## 5. Diff completo de los fixes
```diff
diff --git a/CLAUDE.md b/CLAUDE.md
index 7f03261..382f34d 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -29,7 +29,7 @@ Los documentos en `/docs` son el contrato. Ante cualquier duda, leerlos ANTES de
 8. **Transacciones multi-documento de MongoDB** en los 3 flujos: aprobación de presupuesto, finalización de carga, cierre de mes.
 9. **RBAC por dependencia FastAPI** según la matriz del Spec §4.1. La tabla de autoridad §2.4 manda sobre cualquier otra redacción. Navbar del frontend derivado de un único config de permisos.
 10. **Fórmula del sugerido = la del Excel, exacta** (Spec §1.4.1): prom_3m + tendencia + prom_3m × crec_pct. Los compromisos programados son fila informativa, NO entran en la fórmula. Todas las líneas en `modo_calculo='historico'` (el modo ventas es Fase 1.5).
-11. **Eventos de auditoría:** catálogo cerrado de 30 (29 del Spec §1.11 + `extracto.cargado` de CR-001). No inventar eventos nuevos sin CR.
+11. **Eventos de auditoría:** catálogo cerrado de 31 (29 del Spec §1.11 + `extracto.cargado` de CR-001 + `transaccion.creada` de CR-S2, exigida por Kimi M-1 sprint2-cargas). No inventar eventos nuevos sin CR.
 12. **Ningún secreto en el repo** — EXCEPTO `docs/INVENTARIO-SECRETOS.xlsx`, que por **decisión del CEO** (2026-07-20; repo privado, sin cara al público) guarda los valores reales de secretos y está en el allowlist de gitleaks. Se acepta que esos valores queden en el historial de git (sacarlos exigiría rotarlos) y que el repo NO se haga público sin revisarlo. gitleaks corre en CI y bloquea todo lo demás. Fixtures bancarios solo anonimizados.
 
 ## Estructura
diff --git a/backend/app/audit/events.py b/backend/app/audit/events.py
index e36eca0..7146276 100644
--- a/backend/app/audit/events.py
+++ b/backend/app/audit/events.py
@@ -1,7 +1,9 @@
 # backend/app/audit/events.py
-"""Catálogo CERRADO de eventos de auditoría (regla 11 / Spec §1.11 / CR-001).
+"""Catálogo CERRADO de eventos de auditoría (regla 11 / Spec §1.11 / CR-001 / CR-S2).
 
-29 del Spec §1.11 (10 v1.0 + 12 v1.1 + 7 v1.1.1) + `extracto.cargado` (CR-001) = 30.
+29 del Spec §1.11 (10 v1.0 + 12 v1.1 + 7 v1.1.1) + `extracto.cargado` (CR-001)
++ `transaccion.creada` (CR-S2 — Kimi M-1 sprint2-cargas: rastro forense permanente
+del POST manual, la única vía de dinero sin archivo de banco) = 31.
 NO se inventan eventos sin CR. El nombre del miembro usa `_`; el valor usa
 `<dominio>.<acción>`."""
 
@@ -44,9 +46,12 @@ class AuditEvento(StrEnum):
     factura_emitida_editada = "factura_emitida.editada"
     factura_emitida_anulada = "factura_emitida.anulada"
 
-    # ── CR-001 (1) → total 30 ──
+    # ── CR-001 (1) ──
     extracto_cargado = "extracto.cargado"
 
+    # ── CR-S2 (1) → total 31 ──
+    transaccion_creada = "transaccion.creada"
 
-# Conjunto de los 30 valores canónicos (para validación/tests de completitud).
+
+# Conjunto de los 31 valores canónicos (para validación/tests de completitud).
 CATALOGO_EVENTOS: frozenset[str] = frozenset(e.value for e in AuditEvento)
diff --git a/backend/app/parsers/bank_parsers.py b/backend/app/parsers/bank_parsers.py
index 5461909..66507bb 100644
--- a/backend/app/parsers/bank_parsers.py
+++ b/backend/app/parsers/bank_parsers.py
@@ -25,6 +25,7 @@ Formatos (heredados de la realidad de cada banco):
 import os
 import shutil
 import tempfile
+import zipfile
 from datetime import date, datetime
 from decimal import Decimal, InvalidOperation
 from enum import StrEnum
@@ -84,8 +85,32 @@ class _FilaError(Exception):
 # ── Utilidades ───────────────────────────────────────────────────────────
 
 
+# F-22 (Kimi M-2): topes duros ANTES de gastar CPU/memoria en un archivo hostil.
+MAX_FILAS = 20_000
+_MAX_DESCOMPRIMIDO = 200 * 1024 * 1024  # xlsx = zip; 200 MB descomprimidos
+_MAX_RATIO = 100  # ratio descomprimido/comprimido típico de una zip-bomb: >1000
+
+
+def _validar_zip(file_path: str) -> None:
+    """F-22: acota el ratio de descompresión (un .xlsx es un zip; una bomba de
+    10 MB puede expandir a GB). Lanza ValueError antes de abrir con openpyxl."""
+    try:
+        comprimido = os.path.getsize(file_path)
+        with zipfile.ZipFile(file_path) as z:
+            total = sum(i.file_size for i in z.infolist())
+    except zipfile.BadZipFile:
+        return  # no es zip (p. ej. .xls binario legacy): openpyxl decidirá
+    ratio_excedido = comprimido > 0 and total / comprimido > _MAX_RATIO
+    if total > _MAX_DESCOMPRIMIDO or ratio_excedido:
+        raise ValueError(
+            "el extracto excede el límite de descompresión permitido (F-22): "
+            f"{total // (1024 * 1024)} MB descomprimidos"
+        )
+
+
 def _open_workbook(file_path: str):
     """Abre el .xlsx; si la extensión .xls confunde a openpyxl, copia a temp."""
+    _validar_zip(file_path)  # F-22 (Kimi M-2)
     try:
         return openpyxl.load_workbook(file_path, data_only=True)
     except Exception:
@@ -94,6 +119,14 @@ def _open_workbook(file_path: str):
         return openpyxl.load_workbook(tmp, data_only=True)
 
 
+def _check_tope_filas(fila_datos: int) -> None:
+    """F-22: tope de filas de datos (Kimi M-2). Error explícito, no minutos de CPU."""
+    if fila_datos > MAX_FILAS:
+        raise ValueError(
+            f"el extracto supera el tope de {MAX_FILAS} filas de datos (F-22)"
+        )
+
+
 def _cell(row: tuple, idx: int):
     return row[idx] if idx is not None and idx < len(row) else None
 
@@ -244,6 +277,7 @@ def _parse_signo(
         for r_idx, row in enumerate(
             ws.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1
         ):
+            _check_tope_filas(r_idx - header_row)  # F-22 (Kimi M-2)
             if _fila_vacia(row):
                 continue
             try:
@@ -295,6 +329,7 @@ def parse_global66(file_path: str) -> ResultadoParseo:
         if ws is None:
             raise ValueError("No se encontró la hoja 'Movimientos de cuenta COP'.")
         for r_idx, row in enumerate(ws.iter_rows(min_row=5, values_only=True), start=5):
+            _check_tope_filas(r_idx - 4)  # F-22 (Kimi M-2)
             if _fila_vacia(row):
                 continue
             debito, credito = _cell(row, 2), _cell(row, 3)
diff --git a/backend/app/transacciones/router.py b/backend/app/transacciones/router.py
index b23421c..11433ab 100644
--- a/backend/app/transacciones/router.py
+++ b/backend/app/transacciones/router.py
@@ -13,6 +13,7 @@ from decimal import Decimal, InvalidOperation
 from fastapi import APIRouter, Depends, Header, HTTPException
 from fastapi.responses import JSONResponse
 from pydantic import BaseModel, ConfigDict, Field, field_validator
+from pymongo.errors import DuplicateKeyError
 
 from app.auth.deps import require_permission
 from app.auth.models import User
@@ -107,7 +108,14 @@ async def crear_manual(
         key=idempotency_key,
         request_hash=req_hash,
     )
-    await marca.insert()
+    try:
+        await marca.insert()
+    except DuplicateKeyError:
+        # Kimi B-1: doble-clic real (2 requests concurrentes) — el índice único
+        # `scope_unico` atrapa al 2º → 409, no 500.
+        raise HTTPException(
+            409, "petición con esta Idempotency-Key en curso"
+        ) from None
 
     try:
         tx = await service.crear_transaccion_manual(
diff --git a/backend/app/transacciones/service.py b/backend/app/transacciones/service.py
index 9a62221..ac1f51f 100644
--- a/backend/app/transacciones/service.py
+++ b/backend/app/transacciones/service.py
@@ -7,8 +7,9 @@ Reglas: id_banco = 'MAN-'+ULID (único por construcción → dos manuales idént
 coexisten, F-04); el mes de la fecha debe existir y NO estar cerrado (regla 4 —
 las tardías llegan con el flujo de cierre, Sprint 4); rubro explícito debe existir,
 estar activo y ser coherente con tipo_flujo (regla 7: no se adivina); sin rubro →
-'Por clasificar'. Evento `transaccion.clasificada` SOLO con rubro explícito (el
-catálogo cerrado no tiene 'creación manual'; declarado al gate Kimi — regla 11)."""
+'Por clasificar'. Eventos: `transaccion.creada` en TODA creación manual (CR-S2,
+Kimi M-1 — rastro forense permanente) + `transaccion.clasificada` si además el
+usuario clasificó (rubro explícito)."""
 
 from decimal import Decimal
 
@@ -87,6 +88,20 @@ async def crear_transaccion_manual(
     )
     await tx.insert()
 
+    # CR-S2 (Kimi M-1): TODA creación manual deja rastro forense permanente —
+    # es la única vía por la que entra dinero sin archivo de banco.
+    await emit_audit(
+        AuditEvento.transaccion_creada,
+        entidad="transaccion",
+        entidad_id=str(tx.id),
+        actor_id=usuario_id,
+        metadata={
+            "origen": "manual",
+            "valor": f"{valor:.2f}",
+            "tipo_flujo": tipo_flujo.value,
+        },
+    )
+
     if clasificada:
         await emit_audit(
             AuditEvento.transaccion_clasificada,
diff --git a/backend/tests/test_audit_events.py b/backend/tests/test_audit_events.py
index 28bd649..75406ff 100644
--- a/backend/tests/test_audit_events.py
+++ b/backend/tests/test_audit_events.py
@@ -1,14 +1,15 @@
 # backend/tests/test_audit_events.py
 """Catálogo CERRADO de auditoría — regla 11 / Spec §1.11 / CR-001.
 
-29 (Spec §1.11) + extracto.cargado (CR-001) = 30. No se inventan eventos."""
+29 (Spec §1.11) + extracto.cargado (CR-001) + transaccion.creada (CR-S2, Kimi
+M-1 sprint2-cargas) = 31. No se inventan eventos sin CR."""
 
 from app.audit.events import CATALOGO_EVENTOS, AuditEvento
 
 
-def test_catalogo_tiene_exactamente_30_eventos():
-    assert len(AuditEvento) == 30
-    assert len(CATALOGO_EVENTOS) == 30
+def test_catalogo_tiene_exactamente_31_eventos():
+    assert len(AuditEvento) == 31
+    assert len(CATALOGO_EVENTOS) == 31
 
 
 def test_extracto_cargado_es_el_evento_30_de_cr001():
@@ -27,6 +28,7 @@ def test_eventos_clave_presentes():
         "presupuesto.definido",
         "iva_generado.override",
         "factura_emitida.anulada",
+        "transaccion.creada",  # CR-S2 (Kimi M-1): rastro forense del POST manual
     ):
         assert esperado in CATALOGO_EVENTOS
 
diff --git a/backend/tests/test_bank_parsers.py b/backend/tests/test_bank_parsers.py
index 4ccfe91..10cc438 100644
--- a/backend/tests/test_bank_parsers.py
+++ b/backend/tests/test_bank_parsers.py
@@ -284,6 +284,44 @@ class TestFronteraAnio:
         assert m.fecha == date(2027, 1, 1)
 
 
+class TestLimitesF22:
+    def test_tope_de_filas(self, tmp_path, monkeypatch):
+        # Kimi M-2 (F-22): más de MAX_FILAS → error explícito, no minutos de CPU.
+        import app.parsers.bank_parsers as bp
+
+        monkeypatch.setattr(bp, "MAX_FILAS", 3)
+        p = tmp_path / "muchas.xlsx"
+        _crear_bbva(p, [(f"1{d}-03-2026", "X", -1000) for d in range(5)])
+        with pytest.raises(ValueError, match="filas"):
+            parse_bbva(str(p))
+
+    def test_tope_20001_filas_real(self, tmp_path):
+        # El tope real del Spec (~20.000): 20.001 filas de datos → rechazo.
+        p = tmp_path / "tope.xlsx"
+        wb = openpyxl.Workbook(write_only=True)
+        ws = wb.create_sheet()
+        for _ in range(13):
+            ws.append([])
+        ws.append(["FECHA DE OPERACIÓN", "CONCEPTO", "IMPORTE"])
+        for _ in range(20_001):
+            ws.append(["15-03-2026", "X", -1000])
+        wb.save(str(p))
+        with pytest.raises(ValueError, match="filas"):
+            parse_bbva(str(p))
+
+    def test_zip_bomb_rechazada(self, tmp_path):
+        # Kimi M-2 (F-22): ratio de descompresión acotado (xlsx = zip).
+        import zipfile
+
+        from app.parsers.bank_parsers import _validar_zip
+
+        p = tmp_path / "bomba.xlsx"
+        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
+            z.writestr("xl/worksheets/sheet1.xml", b"\x00" * (60 * 1024 * 1024))
+        with pytest.raises(ValueError, match="descompr"):
+            _validar_zip(str(p))
+
+
 class TestParseExtracto:
     def test_autodetecta_y_rutea(self, tmp_path):
         p = tmp_path / "g.xlsx"
diff --git a/backend/tests/test_cargas_endpoint.py b/backend/tests/test_cargas_endpoint.py
index bbb2fc0..4b5a8a4 100644
--- a/backend/tests/test_cargas_endpoint.py
+++ b/backend/tests/test_cargas_endpoint.py
@@ -42,10 +42,13 @@ async def api(monkeypatch, tmp_path):
     await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
     repository.configure_auth(c, "compas_test")
     configure_audit(c, "compas_test")
-    await repository.create_user(
-        User(email="fin@roddos.com",
-             password_hash=passwords.hash_password(PWD), rol=Role.financiero)
-    )
+    for correo, rol in [
+        ("fin@roddos.com", Role.financiero),
+        ("consulta@roddos.com", Role.consulta),
+    ]:
+        await repository.create_user(
+            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
+        )
     await Rubro(
         grupo="otros", nombre="Por clasificar", orden=98, es_sistema=True
     ).insert()
@@ -59,10 +62,8 @@ async def api(monkeypatch, tmp_path):
     get_settings.cache_clear()
 
 
-async def _h(ac) -> dict:
-    r = await ac.post(
-        "/api/v1/auth/login", json={"email": "fin@roddos.com", "password": PWD}
-    )
+async def _h(ac, email: str = "fin@roddos.com") -> dict:
+    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
     return {"Authorization": f"Bearer {r.json()['access_token']}"}
 
 
@@ -125,3 +126,15 @@ async def test_listar_cargas_vacio(api):
     r = await api.get("/api/v1/cargas", headers=h)
     assert r.status_code == 200
     assert r.json() == {"items": [], "next_cursor": None}
+
+
+async def test_consulta_403_en_cargas(api):
+    # Kimi B-2 / M13.1: Consulta no gestiona cargas (su visibilidad es el dashboard).
+    h = await _h(api, "consulta@roddos.com")
+    assert (await api.get("/api/v1/cargas", headers=h)).status_code == 403
+    r = await api.post(
+        "/api/v1/cargas",
+        files={"archivo": ("e.xlsx", b"PK", "application/x")},
+        headers=h,
+    )
+    assert r.status_code == 403
diff --git a/backend/tests/test_transacciones_manual.py b/backend/tests/test_transacciones_manual.py
index 8308b96..b576fb2 100644
--- a/backend/tests/test_transacciones_manual.py
+++ b/backend/tests/test_transacciones_manual.py
@@ -184,6 +184,37 @@ async def test_mes_inexistente_422(api):
     assert r.status_code == 422
 
 
+async def test_toda_creacion_manual_emite_creada(api):
+    # Kimi M-1 (CR-S2): el POST manual es la única vía de dinero sin archivo de
+    # banco → TODA creación manual deja `transaccion.creada` (aunque caiga en
+    # 'Por clasificar'); la IdempotencyKey expira a 24h y no sirve de rastro.
+    ac, c = api
+    h = await _token(ac)
+    r = await _post(ac, h, _body())  # sin rubro explícito
+    assert r.status_code == 201
+    ev = await c["compas_test"]["audit_log"].find_one({"evento": "transaccion.creada"})
+    assert ev is not None
+    assert ev["entidad_id"] == r.json()["id"]
+    assert ev["metadata"]["origen"] == "manual"
+
+
+async def test_carrera_idempotency_key_da_409(api, monkeypatch):
+    # Kimi B-1: dos requests concurrentes con la misma key → el 2º insert choca
+    # con el índice único → 409 (no 500). Se simula el DuplicateKeyError.
+    from app.domain.idempotency import IdempotencyKey
+    from pymongo.errors import DuplicateKeyError
+
+    ac, _ = api
+    h = await _token(ac)
+
+    async def _choca(self):
+        raise DuplicateKeyError("E11000 duplicate key")
+
+    monkeypatch.setattr(IdempotencyKey, "insert", _choca)
+    r = await _post(ac, h, _body(), key="k-race")
+    assert r.status_code == 409
+
+
 async def test_rubro_explicito_emite_clasificada(api):
     ac, c = api
     h = await _token(ac)
diff --git a/planning/phases/sprint2-cargas/auditorias/PR1-I/RESPUESTA.md b/planning/phases/sprint2-cargas/auditorias/PR1-I/RESPUESTA.md
new file mode 100644
index 0000000..1232426
--- /dev/null
+++ b/planning/phases/sprint2-cargas/auditorias/PR1-I/RESPUESTA.md
@@ -0,0 +1,16 @@
+# RESPUESTA KIMI — sprint2-cargas · PR1-I
+
+**Veredicto:** NO-GO condicionado — **8.8 / 10** (umbral 9.0). Fecha: 2026-07-20.
+
+Reconocido: §1.12 fiel al contrato (scope único, TTL E-6, replay con status original probado, 422 payload distinto, 409 en curso, key fallida no se quema), F-04 con ULID propio, valor string anti-number, F-22 (.xlsm/10MB/413), mapeo de errores exacto, y **proceso correcto (gate antes del merge)**.
+
+## Hallazgos
+- **M-1** — Creación manual SIN rubro explícito queda sin evento permanente (la IdempotencyKey expira a 24h → forensemente invisible). El POST manual es la única vía de dinero sin archivo de banco. **Corrección exigida: CR al catálogo (patrón E-9) añadiendo `transaccion.creada`** y emitirla en TODA creación manual (+ test).
+- **M-2** — F-22 incompleto: falta tope de filas (~20.000) y ratio de descompresión (Spec §1.6). Fix: contar filas en el loop → fallida si excede (+ test 20.001).
+- **B-1** — Carrera del índice idempotente cae en 500; capturar `DuplicateKeyError` del insert → 409.
+- **B-2** — Falta test de Consulta 403 en `/cargas`.
+
+## Decisiones declaradas
+D1 → exige la CR (M-1). D2 (idempotencia solo en POST manual) correcta. D3 (key fallida no se quema) correcta. D4 (happy path vía servicio) suficiente. RBAC 403 para Consulta correcto (M13.1).
+
+**Camino:** M-1 + M-2 + B-1 + B-2 → diff → verificación. Estimación ≥ 9.4 → GO.
```
