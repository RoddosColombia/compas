# EVIDENCIA — FIX-I-2 (dedup F-02 linearizable)

Rama `fix/i2-dedup-linearizable` sobre `main`. commit `ba18d79`.

## 1. Regresión mongomock (job `backend` de CI)

```
$ cd backend && python -m pytest -q
910 passed, 95 skipped, 5304 warnings in 475.51s
```

0 fallos. Los 95 skipped son `@requires_real_mongo` (incl. `test_s3_dedup_no_re_sube`), que
corren en el job `backend-real-mongo` de CI.

## 2. ruff + greps del protocolo

```
$ python -m ruff check app/cargas/service.py         → All checks passed!
$ python -m ruff format --check app/cargas/service.py → 1 file already formatted
$ grep -rn "app.alegra.com/api/r1" backend/app        → 0
$ grep -rn "journal-entries" backend/app              → 0
$ grep -rn "estado.*pending" backend/app/cargas       → 0
```

## 3. Validación del cambio (fuera del harness)

```
$ python -c "from pymongo.read_concern import ReadConcern; print(ReadConcern('linearizable').level)"
linearizable
$ python -c "import app.cargas.service"   → import OK
```

Cargas mongomock puras: `6 passed, 18 skipped` (los 18 real-mongo se saltan local).

**Limitación declarada:** el flake es de timing y no se pudo reproducir localmente (Docker
apagado, sin `mongod`). Decisión CEO: fix directo + validar en CI (`backend-real-mongo`). Un run
verde no prueba al 100% la ausencia del flake; la confianza viene de que `linearizable` es la
garantía documentada correcta para read-after-write cross-client (supera a `majority`, que era la
mitad del contrato que dejó FIX-I).

## 4. Diff (1 archivo — solo la lectura de dedup)

```diff
diff --git a/backend/app/cargas/service.py b/backend/app/cargas/service.py
@@ async def procesar_carga(
     archivo_hash = await to_thread.run_sync(_hash_archivo, archivo_path)

-    # F-02 ... read concern 'majority' (FIX-I) ...
+    # F-02 ... FIX-I-2: 'majority' garantiza majority-committed, NO el último commit;
+    # sin consistencia causal la lectura podía leer un snapshot anterior al COMPLETADA
+    # de la carga previa (read-after-write causal gap del RS). 'linearizable' refleja
+    # todos los writes majority-ack completados antes de iniciar la lectura → determinista.
     _dedup_col = CargaBancaria.get_pymongo_collection().with_options(
-        read_concern=ReadConcern("majority")
+        read_concern=ReadConcern("linearizable")
     )
     previa = await _dedup_col.find_one(
         {
             "archivo_hash": archivo_hash,
             "estado": EstadoCarga.COMPLETADA.value,
-        }
+        },
+        max_time_ms=5000,
     )
```

Escritura (`session.with_transaction` → `carga.save`) y lógica de dedup por transacción: **intactas**.

## 5. TDD / systematic-debugging

Fase 1 (causa raíz): errores leídos, cambio previo (FIX-I) revisado, contrato read/write trazado,
topología CI confirmada (RS 1 nodo). Fase 2/3: `majority` vs `linearizable` — `linearizable` es la
garantía que faltaba. Fase 4: fix mínimo en la causa raíz; sin test RED nuevo determinista posible
(flake de timing no reproducible localmente — excepción documentada); el test de comportamiento
existente valida en CI real-mongo.
