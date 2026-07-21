# EVIDENCIA — sprint1-parsers · PR1-R (fixes de I-PR1)

Fix commit `375bdae` sobre `0a3f1fa`. Solo el diff de los hallazgos + salidas reales.

## 1. pytest (local, mongomock)
```
212 passed, 23 skipped, 9 warnings (local, mongomock)
```

## 2. pytest @requires_real_mongo (carga + dedup, Mongo real)
```
13 passed, 4 deselected (carga + dedup, Mongo real)
```

Nuevos vs I-PR1: A-01 (identicos no colapsan, solape dedup), M-04 (rechazo sin preservación, preserva local), valor_crudo. La finalización corre en transacción real (with_transaction).

## 3. ruff
```
All checks passed!
```

## 4. Protocolo de commit
```
r1:0 | journal-entries:0 | estado-pending:0
```

## 5. git diff --stat (375bdae^..375bdae)
```
backend/app/cargas/mapper.py            |   7 +-
 backend/app/cargas/service.py           | 157 +++++++++++++++++++++++---------
 backend/app/domain/carga.py             |   1 +
 backend/app/domain/transaccion.py       |  14 ++-
 backend/app/parsers/bank_parsers.py     |  30 ++++--
 backend/tests/test_bank_parsers.py      |  19 ++++
 backend/tests/test_carga.py             |  54 ++++++++++-
 backend/tests/test_real_mongo_marker.py |  16 ----
 backend/tests/test_transaccion.py       |  13 ++-
 9 files changed, 234 insertions(+), 77 deletions(-)
```

## 6. Diff completo de los fixes
```diff
diff --git a/backend/app/cargas/mapper.py b/backend/app/cargas/mapper.py
index 66dde23..33f25c8 100644
--- a/backend/app/cargas/mapper.py
+++ b/backend/app/cargas/mapper.py
@@ -25,8 +25,12 @@ def movimiento_a_transaccion(
     rubro_id: PydanticObjectId,
     mes_id: PydanticObjectId,
     carga_id: PydanticObjectId | None = None,
+    ocurrencia: int = 1,
 ) -> Transaccion:
-    """Construye una Transaccion 'Por clasificar' a partir de un movimiento parseado."""
+    """Construye una Transaccion 'Por clasificar' a partir de un movimiento parseado.
+
+    `ocurrencia` es el ordinal de la huella dentro del archivo (Kimi A-01): lo asigna
+    el servicio de carga contando repeticiones por (fecha, tipo, desc, monto)."""
     fecha = mov.fecha.isoformat()  # date → 'YYYY-MM-DD'
     tipo_flujo = _TIPO_A_FLUJO[mov.tipo]
     id_banco = derivar_id_banco(
@@ -36,6 +40,7 @@ def movimiento_a_transaccion(
         valor=mov.monto,
         tipo_flujo=tipo_flujo,
         referencia=mov.referencia,
+        ocurrencia=ocurrencia,
     )
     # Moneda extranjera (Global66): si el parser capturó moneda, se conserva el
     # original re-derivable (hoy la hoja COP → 'COP'/1; valor_original == valor).
diff --git a/backend/app/cargas/service.py b/backend/app/cargas/service.py
index cb218e3..2b7a665 100644
--- a/backend/app/cargas/service.py
+++ b/backend/app/cargas/service.py
@@ -3,22 +3,32 @@
 
 MARCADO PARA AUDITORÍA KIMI (flujo crítico: cargas bancarias).
 
-Contrato seguido (§1.6, el data dictionary manda): inserción idempotente por lotes
-`insertMany ordered=False`; los duplicados se cuentan por DuplicateKeyError contra el
-índice único parcial (banco, id_banco). Esto NO es una transacción multi-documento
-(la regla 8 la pide para 'finalización de carga', pero es incompatible con el
-conteo-y-continúa del §1.6 → nota/CR pendiente, se resuelve en el gate Kimi).
-
-F-02 (reproceso): se rechaza solo si ya hay una carga 'completada' con el mismo
-archivo_hash; si la previa quedó 'fallida', la re-carga se permite y la dedup por
-(banco, id_banco) evita duplicar lo ya insertado.
+Contrato: inserción idempotente con dedup por índice único parcial (banco, id_banco)
++ **transacción multi-documento** en la finalización (regla 8).
+
+Sobre §1.6 vs regla 8 (Kimi M-02, corregido): la nota original decía que eran
+incompatibles; NO lo son, pero la vía literal de Kimi (`insertMany ordered=False` +
+capturar `BulkWriteError` + commit DENTRO de la transacción) **no funciona**: se
+verificó contra Mongo real que un dup-key (11000) marca la transacción como
+`TransientTransactionError` y la aborta (nInserted=0). La forma correcta —y la que se
+implementa— es **pre-filtrar** los duplicados con la sesión y luego insertar SOLO los
+nuevos dentro de la transacción (sin dups → no aborta) junto al update de la carga.
+El ordinal de ocurrencia (Kimi A-01) garantiza ids únicos por archivo, así que el
+único duplicado posible es cross-archivo, que el pre-filtro detecta. `with_transaction`
+reintenta ante errores transitorios (TOCTOU con una carga concurrente).
+
+F-02 (reproceso): se rechaza solo si ya hay una carga 'completada' con el mismo hash.
+M-04: el original debe quedar re-procesable (Spec §1.6); sin S3 (diferido) se conserva
+una copia local (`dir_originales`); sin ningún destino se rechaza (regla dura).
 """
 
 import hashlib
+import shutil
+from pathlib import Path
 
 from anyio import to_thread
 from beanie import PydanticObjectId
-from pymongo.errors import BulkWriteError
+from beanie.operators import In
 
 from app.audit.events import AuditEvento
 from app.audit.service import emit_audit
@@ -44,17 +54,40 @@ class RubroPorClasificarAusenteError(CargaError):
     """Falta el rubro de sistema 'Por clasificar' (no se corrieron las semillas)."""
 
 
+class OriginalNoPreservableError(CargaError):
+    """No hay dónde preservar el original (ni S3 ni dir local) — regla dura M-04."""
+
+
 def _mes_de(fecha_iso: str) -> str:
-    """Mes-llave (YYYY-MM-01) derivado de la fecha 'YYYY-MM-DD'."""
     return fecha_iso[:7] + "-01"
 
 
 def _hash_archivo(archivo_path: str) -> str:
-    """SHA-256 del archivo. Bloqueante → se corre en threadpool (§1.6)."""
     with open(archivo_path, "rb") as f:
         return hashlib.sha256(f.read()).hexdigest()
 
 
+def _clave_ocurrencia(mov) -> tuple:
+    """Identidad de la huella para contar ocurrencias dentro del archivo (A-01).
+    (banco es fijo por carga; discrimina por fecha/tipo/desc/monto)."""
+    return (mov.fecha.isoformat(), mov.tipo.value, mov.descripcion, f"{mov.monto:.2f}")
+
+
+def _parse(archivo_path: str, banco: Banco):
+    from app.parsers.bank_parsers import parse_extracto
+
+    return parse_extracto(archivo_path, banco)
+
+
+def _finalizar_carga_doc(carga, resultado, errores, nuevas, duplicadas) -> None:
+    carga.total_filas = len(resultado.movimientos) + len(resultado.errores)
+    carga.nuevas = nuevas
+    carga.duplicadas = duplicadas
+    carga.errores = len(errores)
+    carga.errores_detalle = errores
+    carga.estado = EstadoCarga.COMPLETADA
+
+
 async def procesar_carga(
     *,
     banco: Banco,
@@ -62,12 +95,22 @@ async def procesar_carga(
     archivo_nombre: str,
     usuario_id: PydanticObjectId,
     archivo_s3_key: str | None = None,
+    dir_originales: str | None = None,
+    permitir_sin_preservar: bool = False,
 ) -> CargaBancaria:
     """Parsea un extracto y persiste sus movimientos como Transaccion 'Por
     clasificar', idempotentemente. Devuelve la CargaBancaria con los conteos."""
     if banco is Banco.MANUAL:
         raise CargaError("una carga proviene de un banco real, no 'manual'")
 
+    # M-04 (regla dura): el original debe quedar re-procesable.
+    if archivo_s3_key is None and dir_originales is None and not permitir_sin_preservar:
+        raise OriginalNoPreservableError(
+            "sin S3 ni dir_originales no se puede preservar el original (Spec §1.6, "
+            "Kimi M-04). Provisionar S3 (bloque C), pasar dir_originales, o "
+            "permitir_sin_preservar=True (solo dev)."
+        )
+
     archivo_hash = await to_thread.run_sync(_hash_archivo, archivo_path)
 
     # F-02: solo bloquea una carga PREVIA COMPLETADA con el mismo hash.
@@ -86,6 +129,13 @@ async def procesar_carga(
             "falta el rubro de sistema 'Por clasificar' (correr semillas de rubros)"
         )
 
+    # Preservar el original localmente (interim S3, M-04).
+    if archivo_s3_key is None and dir_originales is not None:
+        ext = Path(archivo_nombre).suffix or ".bin"
+        destino = Path(dir_originales) / f"{archivo_hash}{ext}"
+        await to_thread.run_sync(_preservar, archivo_path, destino)
+        archivo_s3_key = f"local://{destino}"
+
     carga = CargaBancaria(
         banco=banco,
         archivo_nombre=archivo_nombre,
@@ -96,14 +146,20 @@ async def procesar_carga(
     await carga.insert()
 
     try:
-        # Parseo en threadpool para no bloquear el event loop (§1.6).
-        resultado = await to_thread.run_sync(parse_extracto_seguro, archivo_path, banco)
-        errores = [ErrorCarga(fila=e.fila, motivo=e.motivo) for e in resultado.errores]
+        resultado = await to_thread.run_sync(_parse, archivo_path, banco)
+        errores = [
+            ErrorCarga(fila=e.fila, motivo=e.motivo, valor_crudo=e.valor_crudo)
+            for e in resultado.errores
+        ]
 
         docs: list[Transaccion] = []
+        mes_cache: dict[str, object] = {}  # M-03: 1 lookup por mes, no por fila
+        conteo: dict[tuple, int] = {}  # A-01: ordinal de ocurrencia por huella
         for mov in resultado.movimientos:
             mes = _mes_de(mov.fecha.isoformat())
-            mc = await MesControl.find_one(MesControl.mes == mes)
+            if mes not in mes_cache:
+                mes_cache[mes] = await MesControl.find_one(MesControl.mes == mes)
+            mc = mes_cache[mes]
             if mc is None:
                 errores.append(
                     ErrorCarga(
@@ -112,32 +168,47 @@ async def procesar_carga(
                     )
                 )
                 continue
+            clave = _clave_ocurrencia(mov)
+            conteo[clave] = conteo.get(clave, 0) + 1
             docs.append(
                 movimiento_a_transaccion(
-                    mov, rubro_id=rubro.id, mes_id=mc.id, carga_id=carga.id
+                    mov,
+                    rubro_id=rubro.id,
+                    mes_id=mc.id,
+                    carga_id=carga.id,
+                    ocurrencia=conteo[clave],
                 )
             )
 
-        nuevas = duplicadas = 0
+        holder = {"nuevas": 0, "duplicadas": 0}
         if docs:
-            try:
-                res = await Transaccion.insert_many(docs, ordered=False)
-                nuevas = len(res.inserted_ids)
-            except BulkWriteError as bwe:
-                write_errors = bwe.details.get("writeErrors", [])
-                otros = [e for e in write_errors if e.get("code") != 11000]
-                if otros:
-                    raise  # error real (no un duplicado) → carga fallida
-                duplicadas = len(write_errors)
-                nuevas = bwe.details.get("nInserted", len(docs) - duplicadas)
-
-        carga.total_filas = len(resultado.movimientos) + len(resultado.errores)
-        carga.nuevas = nuevas
-        carga.duplicadas = duplicadas
-        carga.errores = len(errores)
-        carga.errores_detalle = errores
-        carga.estado = EstadoCarga.COMPLETADA
-        await carga.save()
+            ids = [d.id_banco for d in docs]
+            client = Transaccion.get_pymongo_collection().database.client
+
+            async def _finalizar(session):
+                # Pre-filtro dentro de la sesión (M-02): ids ya presentes de OTRAS
+                # cargas (el ordinal hace únicos los de ESTE archivo).
+                existentes = set()
+                async for t in Transaccion.find(
+                    Transaccion.banco == banco, In(Transaccion.id_banco, ids),
+                    session=session,
+                ):
+                    existentes.add(t.id_banco)
+                nuevos = [d for d in docs if d.id_banco not in existentes]
+                if nuevos:
+                    await Transaccion.insert_many(nuevos, session=session)
+                holder["nuevas"] = len(nuevos)
+                holder["duplicadas"] = len(docs) - len(nuevos)
+                _finalizar_carga_doc(
+                    carga, resultado, errores, holder["nuevas"], holder["duplicadas"]
+                )
+                await carga.save(session=session)
+
+            async with await client.start_session() as session:
+                await session.with_transaction(_finalizar)
+        else:
+            _finalizar_carga_doc(carga, resultado, errores, 0, 0)
+            await carga.save()
 
         await emit_audit(
             AuditEvento.carga_completada,
@@ -146,8 +217,8 @@ async def procesar_carga(
             actor_id=str(usuario_id),
             metadata={
                 "banco": banco.value,
-                "nuevas": nuevas,
-                "duplicadas": duplicadas,
+                "nuevas": holder["nuevas"],
+                "duplicadas": holder["duplicadas"],
                 "errores": len(errores),
             },
         )
@@ -167,13 +238,11 @@ async def procesar_carga(
                 actor_id=str(usuario_id),
                 metadata={"motivo": carga.motivo_fallo},
             )
-        except Exception:  # noqa: BLE001 — no enmascarar el error original de la carga
+        except Exception:  # noqa: BLE001 — no enmascarar el error original
             pass
         raise
 
 
-def parse_extracto_seguro(archivo_path: str, banco: Banco):
-    """Wrapper síncrono para el threadpool (import perezoso del parser)."""
-    from app.parsers.bank_parsers import parse_extracto
-
-    return parse_extracto(archivo_path, banco)
+def _preservar(origen: str, destino: Path) -> None:
+    destino.parent.mkdir(parents=True, exist_ok=True)
+    shutil.copy2(origen, destino)
diff --git a/backend/app/domain/carga.py b/backend/app/domain/carga.py
index 2ff9599..5ba5f79 100644
--- a/backend/app/domain/carga.py
+++ b/backend/app/domain/carga.py
@@ -40,6 +40,7 @@ class ErrorCarga(BaseModel):
 
     fila: int  # número de fila del extracto; -1 = error no ligado a una fila
     motivo: str
+    valor_crudo: str | None = None  # texto crudo para el Financiero (regla 7)
 
 
 class CargaBancaria(Document):
diff --git a/backend/app/domain/transaccion.py b/backend/app/domain/transaccion.py
index 0a4c75e..0b1f404 100644
--- a/backend/app/domain/transaccion.py
+++ b/backend/app/domain/transaccion.py
@@ -42,18 +42,24 @@ def derivar_id_banco(
     valor,
     tipo_flujo: TipoFlujo,
     referencia: str | None = None,
+    ocurrencia: int = 1,
 ) -> str:
     """Clave de deduplicación estable (regla 5).
 
-    - Global66 trae una referencia de transacción nativa → se usa tal cual.
+    - Global66 trae una referencia de transacción nativa → se usa tal cual (única).
     - Bancolombia/BBVA no traen ID → huella determinista del contenido
-      (banco|fecha|tipo|descripcion|valor), precedente de SISMO v2. MD5 (no
-      criptográfico, solo fingerprint) = 32 hex, cabe en String(40).
+      (banco|fecha|tipo|descripcion|valor), precedente de SISMO v2 (MD5, no
+      criptográfico, solo fingerprint), con el **ordinal de ocurrencia dentro del
+      archivo** (`…|1`, `…|2`) — Kimi A-01: dos movimientos legítimos idénticos el
+      mismo día (p. ej. dos cuotas de igual valor con descripción 'Abono') NO
+      colapsan; y el solape re-subido, al ir en el mismo orden de fila, conserva el
+      mismo ordinal → la dedup sigue detectándolo. MD5(32)+'|'+ordinal cabe en 40.
     """
     if banco is Banco.GLOBAL66 and referencia:
         return referencia
     clave = f"{banco.value}|{fecha}|{tipo_flujo.value}|{descripcion}|{valor:.2f}"
-    return hashlib.md5(clave.encode("utf-8"), usedforsecurity=False).hexdigest()
+    huella = hashlib.md5(clave.encode("utf-8"), usedforsecurity=False).hexdigest()
+    return f"{huella}|{ocurrencia}"
 
 
 class Transaccion(Document):
diff --git a/backend/app/parsers/bank_parsers.py b/backend/app/parsers/bank_parsers.py
index aa7e1a1..5461909 100644
--- a/backend/app/parsers/bank_parsers.py
+++ b/backend/app/parsers/bank_parsers.py
@@ -33,7 +33,7 @@ import openpyxl
 from pydantic import BaseModel, ConfigDict
 
 from app.core.money import Money
-from app.core.time import now_bogota
+from app.core.time import today_bogota
 from app.domain.bancos import Banco
 
 
@@ -156,16 +156,26 @@ def _fecha_dmy(raw, con_anio: bool) -> date:
             return datetime.strptime(s, "%d-%m-%Y").date()
         except (ValueError, TypeError):
             raise _FilaError("fecha inválida", s) from None
-    # Bancolombia: d/m (sin año) → completar con el año actual (Bogotá); o d/m/Y
-    # explícito. Se antepone el año en vez de usar el default yearless de strptime
-    # (DeprecationWarning en py3.15, y falla el 29-feb).
-    anio = now_bogota().year
-    for candidato in (f"{s}/{anio}", s):
+    # d/m/Y explícito (con año) → tal cual.
+    try:
+        return datetime.strptime(s, "%d/%m/%Y").date()
+    except (ValueError, TypeError):
+        pass
+    # d/m sin año: se completa con el año actual, PERO una fecha d/m no puede ser
+    # futura → si cae en el futuro (frontera dic/ene: cargar el 2-ene un movimiento
+    # del 31-dic), es del año anterior (Kimi M-01). El fix definitivo es leer el año
+    # del encabezado del extracto; se hará al congelar los fixtures reales (S1-01).
+    hoy = today_bogota()
+    try:
+        dt = datetime.strptime(f"{s}/{hoy.year}", "%d/%m/%Y").date()
+    except (ValueError, TypeError):
+        raise _FilaError("fecha inválida", s) from None
+    if dt > hoy:
         try:
-            return datetime.strptime(candidato, "%d/%m/%Y").date()
-        except (ValueError, TypeError):
-            continue
-    raise _FilaError("fecha inválida", s) from None
+            dt = dt.replace(year=dt.year - 1)
+        except ValueError:  # 29-feb en año no bisiesto
+            dt = dt.replace(year=dt.year - 1, day=28)
+    return dt
 
 
 def _fecha_iso(raw) -> date:
diff --git a/backend/tests/test_bank_parsers.py b/backend/tests/test_bank_parsers.py
index e6974e9..4ccfe91 100644
--- a/backend/tests/test_bank_parsers.py
+++ b/backend/tests/test_bank_parsers.py
@@ -265,6 +265,25 @@ class TestGlobal66:
 # ── Dispatcher ───────────────────────────────────────────────────────────
 
 
+class TestFronteraAnio:
+    def test_diciembre_leido_en_enero_no_salta_al_futuro(self, tmp_path, monkeypatch):
+        # M-01 (Kimi): cargar el 2-ene-2027 un movimiento "31/12" → 2026-12-31.
+        import app.parsers.bank_parsers as bp
+        monkeypatch.setattr(bp, "today_bogota", lambda: date(2027, 1, 2))
+        p = tmp_path / "b.xlsx"
+        _crear_bancolombia(p, [("31/12", "PAGO", -5000)])
+        m = parse_bancolombia(str(p)).movimientos[0]
+        assert m.fecha == date(2026, 12, 31)
+
+    def test_fecha_del_anio_actual_se_mantiene(self, tmp_path, monkeypatch):
+        import app.parsers.bank_parsers as bp
+        monkeypatch.setattr(bp, "today_bogota", lambda: date(2027, 1, 2))
+        p = tmp_path / "b.xlsx"
+        _crear_bancolombia(p, [("01/01", "PAGO", -5000)])
+        m = parse_bancolombia(str(p)).movimientos[0]
+        assert m.fecha == date(2027, 1, 1)
+
+
 class TestParseExtracto:
     def test_autodetecta_y_rutea(self, tmp_path):
         p = tmp_path / "g.xlsx"
diff --git a/backend/tests/test_carga.py b/backend/tests/test_carga.py
index b37d72a..527dc2a 100644
--- a/backend/tests/test_carga.py
+++ b/backend/tests/test_carga.py
@@ -117,6 +117,7 @@ class TestServicioCarga:
             archivo_path=str(p),
             archivo_nombre=nombre,
             usuario_id=PydanticObjectId(),
+            dir_originales=str(tmp_path / "orig"),
         )
 
     async def test_completada_inserta_transacciones(self, entorno, tmp_path):
@@ -145,7 +146,7 @@ class TestServicioCarga:
         p = tmp_path / "dup.xlsx"
         _crear_bbva(p, [("15-03-2026", "COMPRA", -50000)])
         kw = dict(banco=Banco.BBVA, archivo_path=str(p), archivo_nombre="dup.xlsx",
-                  usuario_id=PydanticObjectId())
+                  usuario_id=PydanticObjectId(), dir_originales=str(tmp_path / "orig"))
         await procesar_carga(**kw)
         with pytest.raises(CargaDuplicadaError):
             await procesar_carga(**kw)  # mismo hash, ya completada → F-02
@@ -166,3 +167,54 @@ class TestServicioCarga:
         doc = await col.find_one({"evento": AuditEvento.carga_completada.value})
         assert doc is not None
         assert doc["entidad_id"] == str(carga.id)
+
+    async def test_identicos_en_un_archivo_no_colapsan(self, entorno, tmp_path):
+        # A-01: dos cuotas legítimas idénticas el mismo día → AMBAS entran.
+        carga = await self._procesar(tmp_path, [
+            ("15-03-2026", "ABONO", -50000),
+            ("15-03-2026", "ABONO", -50000),
+        ])
+        assert carga.nuevas == 2
+        assert carga.duplicadas == 0
+
+    async def test_solape_dedup_conserva_identicos(self, entorno, tmp_path):
+        # A-01 + dedup: archivo A [X,X]; archivo B (otro hash) [X,X,Z] → solo Z nuevo.
+        await self._procesar(tmp_path, [
+            ("15-03-2026", "ABONO", -50000),
+            ("15-03-2026", "ABONO", -50000),
+        ], "a.xlsx")
+        carga2 = await self._procesar(tmp_path, [
+            ("15-03-2026", "ABONO", -50000),
+            ("15-03-2026", "ABONO", -50000),
+            ("17-03-2026", "OTRO", -3000),
+        ], "b.xlsx")
+        assert carga2.nuevas == 1
+        assert carga2.duplicadas == 2
+
+    async def test_valor_crudo_se_propaga(self, entorno, tmp_path):
+        # Regla 7 / Kimi: el texto crudo ambiguo llega al Financiero.
+        carga = await self._procesar(tmp_path, [
+            ("15-03-2026", "OK", -1000),
+            ("15-03-2026", "RARO", "N/A"),
+        ])
+        assert carga.errores == 1
+        assert carga.errores_detalle[0].valor_crudo == "N/A"
+
+    async def test_sin_preservacion_rechaza(self, entorno, tmp_path):
+        # M-04 (regla dura): sin S3 ni dir_originales, no se carga.
+        from app.cargas.service import OriginalNoPreservableError, procesar_carga
+
+        p = tmp_path / "np.xlsx"
+        _crear_bbva(p, [("15-03-2026", "X", -1000)])
+        with pytest.raises(OriginalNoPreservableError):
+            await procesar_carga(
+                banco=Banco.BBVA, archivo_path=str(p),
+                archivo_nombre="np.xlsx", usuario_id=PydanticObjectId(),
+            )
+
+    async def test_preserva_original_local(self, entorno, tmp_path):
+        from anyio import Path as AsyncPath
+
+        carga = await self._procesar(tmp_path, [("15-03-2026", "X", -1000)])
+        assert carga.archivo_s3_key.startswith("local://")
+        assert await AsyncPath(carga.archivo_s3_key.removeprefix("local://")).exists()
diff --git a/backend/tests/test_real_mongo_marker.py b/backend/tests/test_real_mongo_marker.py
deleted file mode 100644
index 201bb67..0000000
--- a/backend/tests/test_real_mongo_marker.py
+++ /dev/null
@@ -1,16 +0,0 @@
-# backend/tests/test_real_mongo_marker.py
-"""Verifica que el contrato del marker `requires_real_mongo` funciona:
-los tests marcados se saltan por defecto (mongomock no sirve para ellos) y
-solo corren con `pytest -m requires_real_mongo` contra un Mongo real.
-
-Ver el comentario extenso en conftest.py."""
-
-import pytest
-
-
-@pytest.mark.requires_real_mongo
-def test_placeholder_dedup_indice_unico_parcial():
-    # Dedup parcial (banco, id_banco) con partialFilterExpression: IMPLEMENTADO al
-    # portar los parsers (Sprint 1). La cobertura real vive en
-    # tests/test_transaccion_dedup.py (solape no duplica + coexistencia de 2 manuales).
-    pytest.skip("Cubierto en test_transaccion_dedup.py (Transaccion, Sprint 1).")
diff --git a/backend/tests/test_transaccion.py b/backend/tests/test_transaccion.py
index 94d2fd3..be02b82 100644
--- a/backend/tests/test_transaccion.py
+++ b/backend/tests/test_transaccion.py
@@ -113,7 +113,18 @@ class TestDerivarIdBanco:
         a = derivar_id_banco(**args)
         b = derivar_id_banco(**args)
         assert a == b  # determinista → dedup de solape
-        assert len(a) <= 40 and a.isalnum()
+        assert len(a) <= 40
+        assert a.endswith("|1")  # huella MD5 + ordinal de ocurrencia (A-01)
+
+    def test_ordinal_distingue_identicos(self):
+        # A-01: misma huella, distinta ocurrencia → id distinto (no colapsan).
+        base = dict(
+            banco=Banco.BANCOLOMBIA, fecha="2026-03-15", descripcion="ABONO",
+            valor=Decimal("50000"), tipo_flujo=TipoFlujo.EGRESO,
+        )
+        assert derivar_id_banco(**base, ocurrencia=1) != derivar_id_banco(
+            **base, ocurrencia=2
+        )
 
     def test_huella_cambia_con_el_monto(self):
         base = dict(
```
