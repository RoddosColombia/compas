# SOLICITUD DE AUDITORÍA — iva-c11 PR1-I: E2 backend (captura de facturas + IVA)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-30
**Plan padre:** Spec de ejecución E2/E1 v1.3 — aval de Kimi 9.4/10 con 3 condiciones cerradas (M-1/M-2/M-3)
**Docs contrato:** `docs/COMPAS_SPEC_EJECUCION_E2_E1.md` (§3 alcance E2, §8 criterios A1–A18), `docs/COMPAS_CR-E2_Compuerta_IVA_Proyeccion.md`; CLAUDE.md reglas 1, 3, 4, 5, 7, 9, 11; R0 (motor intocable), R6, R8
**Rama:** `feat/e2-facturas-iva` → `main` · **PR #46** (NO mergeado; este gate es PRE-merge)

> **PR crítico:** parsers/cargas (PDF DIAN) + RBAC/PII (Ley 1581) + migración de datos reales corrida en PROD. No hay merge sin este gate ≥ 9.0 (o gate-waiver del CEO + auditoría retroactiva, registrado en 'Gates').

## Qué hace (piezas 4–6 + 2 rondas de GO del CEO)

1. **Ingesta `POST /api/v1/facturas/cargar`** (`facturas/ingesta.py`): lote de PDFs DIAN → resultado POR ARCHIVO con estados distinguibles `creada | duplicada | rechazada_no_dian | rechazada_tipo_no_soportado | requiere_confirmacion | error` + resumen. Parseo FUERA del event loop (`anyio.to_thread`; pdfplumber es CPU-bound, A16); tope 20 archivos / 10 MB. Resultado PARCIAL (una excepción no frena al lote → estado `error`). Dedup por CUFE: pre-check en el servicio (NO atómico) + índice único `cufe_unico` (garantía dura). RBAC `iva:gestionar`.
2. **Mapeo** emitida→venta / recibida→compra; origen auteco (NIT desde Configuracion) / sin_clasificar. `FacturaDian.inc → Factura.inc_valor` (rename anti-shadow de beanie.Document, con candado en test INC>0: nunca 0.00 en silencio). Auditoría `factura.creada` fail-closed (saga O1: si el emit falla, compensar el insert). Sin PII en logs.
3. **Precedencia `iva_valor`** (D-13/§3.2): el IVA del bloque de totales se guarda tal cual; NO se recalcula base×tarifa. **Hallazgo R6** (ver lupa 1).
4. **`total_bruto` vs `base_gravable`** (GO CEO 1): la DIAN guarda `total_bruto` (Total Bruto Factura) y deja `base_gravable=None` (base gravada real desconocida sin parsear líneas; R5). La captura manual sigue exigiendo `base_gravable`.
5. **Endurecer `tarifa_iva`** (pieza 6) a `{0, 0.05, 0.19}` SOLO en captura manual (endurecer, no cambiar el cálculo → R6 sin CR). La ingesta guarda `tarifa_iva=None`.
6. **PII / Ley 1581** (GO CEO 4 + 2ª ronda): permiso propio `facturas:ver_detalle` = {financiero, admin}; `GET /facturas/{id}` restringido. Captura `tipo_contribuyente` de la CONTRAPARTE (sección emisor si recibida / adquiriente si emitida). El **listado** enmascara `tercero_nombre`/`tercero_nit` SOLO si la contraparte es persona natural o desconocida y el usuario no tiene `ver_detalle`; persona jurídica (razón social ≠ PII) queda visible. `/liquidacion` sigue en `dashboard:leer`.
7. **Compuerta IVA→proyección** (CR-E2-COMPUERTA): `IVA_ALIMENTA_PROYECCION` sembrada en `false`; `_iva_plan` devuelve `({}, [])` con la compuerta apagada → `GET /proyeccion` idéntico bit a bit con cualquier número de facturas (D-12).
8. **Modelo Factura DIAN + migración idempotente** (`cufe` único sparse, campos nuevos, NITs y compuerta en Configuracion). Migración **corrida en PROD** (evidencia).

## Cambios de valores esperados
**Ninguno.** `motor.py` cero diffs; golden master verde SIN regenerar; `GET /proyeccion` idéntico bit a bit (compuerta apagada). El único cambio en `proyeccion/` es `_iva_plan` (autorizado por CR-E2-COMPUERTA).

## Semántica preservada (NO cambia en este PR)
- **R0:** `motor.py` intocable (0 diffs en `main..HEAD`).
- **D-12 (A14):** IVA no alimenta la proyección (compuerta apagada; candado `test_a14_..._identica_bit_a_bit`).
- **Catálogo de eventos (regla 11):** usa `factura.creada`/`factura.anulada` YA existentes; no inventa eventos.
- **Audit append-only, Pydantic strict + extra=forbid, Money/Decimal, América/Bogotá:** aplicados.

## Puntos a auditar con lupa
1. **R6 — validación base×tarifa DESCARTADA para la ruta DIAN.** El §3.1 pedía `iva_desde_base` como validación (>1 centavo → requiere_confirmacion). No aplica: `base_gravable` de la DIAN es el **Total Bruto** (incluye líneas sin IVA) y el doc mezcla tarifas → la tasa implícita ≠ nominal. En el A1 real `base×0.19 = 5.974,94` vs IVA `1.452,94` (tasa 4,62%): un gate base×tarifa marcaría la propia muestra de oro. La validación de integridad es la **coherencia A6** (`base+iva+inc+bolsas+otros==total`), ya implementada. ¿Se acepta descartar el gate?
2. **Enmascaramiento por `tipo_contribuyente`.** ¿Correcto que persona jurídica sea visible bajo `dashboard:leer` y solo se enmascare natural/desconocido? ¿El `None` (manual / PDF sin dato) → enmascarar es la degradación segura? El endpoint de DETALLE NO depende del registro (siempre {financiero, admin}).
3. **`total_bruto`/`base_gravable=None`.** ¿Correcto fiscalmente NO inventar la base gravada (R5) y exponer `null`→"—" en la UI? ¿Rompe algún consumidor que yo no vea? (Verifiqué liquidación, serializador, crear manual.)
4. **Dedup CUFE no atómico + índice.** Pre-check `find_one(cufe)` + `cufe_unico` (sparse, `{cufe:{$type:string}}`) + captura de `DuplicateKeyError`. ¿Suficiente contra carrera? El índice se crea en la MIGRACIÓN (no en Settings; mongomock no honra el partial). Verificado `@requires_real_mongo` + corrida en PROD.
5. **A16 — parseo fuera del event loop + topes.** ¿`anyio.to_thread.run_sync(_extraer_bytes, ...)` bien aplicado? ¿Los topes (20/10MB) y el resultado PARCIAL (estado `error`) cubren el DoS de PDF gigante / PDF corrupto?
6. **Migración idempotente en PROD.** foto antes/después (0→0 facturas), `cufe_unico` presente, 2ª corrida 0 claves. ¿Reversa correcta ($unset incl. `inc_valor`, `total_bruto`, `tipo_contribuyente`)?
7. **M-1 intacto** (orden de detección de tipo): no reordenado; `TITULOS_A8` + regresión verdes.
8. **Archivo original (decisión CEO):** NO se guardan bytes; el CUFE es el puntero (re-descarga DIAN) y el sha256 solo verifica. ¿Aceptable para trazabilidad/auditoría fiscal, o exiges persistir el original?

## Evidencia local (ver EVIDENCIA.md — diff real + salidas)
- **pytest:** **728 passed / 62 skipped** (suite completa, mongomock). `@requires_real_mongo` (índice cufe_unico) verificado aparte.
- **ruff:** All checks passed.
- **`motor.py`:** `git diff main..HEAD` VACÍO. **golden master** verde SIN regenerar.
- **Migración en PROD:** `índices: ['_id_','cufe_unico','nit_numero_unico','por_fecha']`, facturas 0→0, 2ª corrida 0 claves.
- **Protocolo de commit:** `app.alegra r1: 0 · journal-entries: 0 · estado.*pending: 0`.

## Cumplimiento A1–A18
A1–A8, A11, A12, A13, A14, A16 cubiertos con test (ver EVIDENCIA). A10 end-to-end con las cifras exactas del §6 (arrastre 11.001.452,94 / pago 1.998.547,06). A17: listado minimizado + detalle restringido + sin PII en logs (nota: `archivos:descargar` fuera de alcance por la decisión del original). A9/A15 → PR2 (frontend). A18 verde.
