# SOLICITUD DE AUDITORÍA — sprint1-parsers PR1-I: parsers 3 bancos + Transaccion + carga §1.6

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-20
**Plan padre:** gate `Kimi PLAN (Sprint 1)` = **Aprobado** · **Docs contrato:** Spec §1.5 (Transaccion), §1.6 (CargaBancaria), §2.3 (índices), PRD M7; CLAUDE.md reglas 1, 3, 5, 7, 8, 11
**Rama / merge:** `feat/parsers-transaccion-carga` → `main` (`0a3f1fa`; commits `7285c34` código + `b23a2ee` tracker)

> **Desviación declarada (auditar):** el CEO ordenó **mergear a `main` ANTES de este gate** (CLAUDE.md exige Kimi ≥9.0 pre-merge en flujos críticos). Merge a `main` = solo **staging** (producción sigue gated por tag `v*` + reviewer). Esta auditoría es **post-merge (ronda I)**; si baja de 9.0 se corrige hacia adelante.

## Qué hace
1. **Parsers de los 3 bancos** (`backend/app/parsers/bank_parsers.py`): Bancolombia (hoja 'Extracto', fila 15), BBVA (fila 14), Global66 (hoja 'Movimientos de cuenta COP', fila 4). Auto-detección + dispatcher `parse_extracto`. Portados en espíritu de SISMO v2, **reescritos** para las reglas de COMPAS. Salida: `ResultadoParseo{movimientos, errores}`.
2. **Regla 1 (Decimal):** los montos se construyen como `Decimal` vía el tipo `Money` (rechaza `float`); los números de openpyxl (float) se convierten con `Decimal(str(v))`.
3. **Regla 7 (transforma, no interpreta):** fila con fecha/monto no parseables → `ErrorFila` acumulado (nº de fila), **jamás** adivinado ni tragado. Solo filas vacías / valor 0 se omiten sin error.
4. **Global66 (regla 7):** conserva `moneda_original`/`tasa_cambio` (hoy hoja COP → 'COP'/1; el mapeo FX multi-moneda real espera un export .xlsx de muestra).
5. **`Transaccion` (§1.5)** (`backend/app/domain/transaccion.py`): Document Beanie strict + `derivar_id_banco` (Global66 → referencia nativa; Bancolombia/BBVA → huella MD5 determinista `banco|fecha|tipo|desc|valor`, precedente V2, cabe en String(40)) + índice **único parcial** `(banco, id_banco)` con `partialFilterExpression {id_banco:{$type:'string'}}` (regla 5).
6. **`CargaBancaria` (§1.6)** + **servicio `procesar_carga`** (`app/cargas/`): parseo en threadpool → mapeo → `insertMany(ordered=False)` contando duplicados por `DuplicateKeyError` → estado `procesando`→`completada`/`fallida` con conteos; **F-02** (rechazo solo si hay carga previa 'completada' con el mismo hash; si la previa está 'fallida', re-carga permitida); eventos `carga.completada`/`carga.fallida`.
7. **`Banco` += `MANUAL`** (solo el campo `banco` de Transaccion; `SaldoBanco` sigue con los 3 reales).

## Cambios de valores esperados
N/A — código nuevo, no altera valores/semántica de módulos existentes.

## Semántica preservada (NO cambia en este PR)
- Histórico inmutable y `audit_log` append-only: intactos (la carga solo inserta transacciones nuevas; no edita meses cerrados).
- Reglas de dinero (Money/Decimal), zona horaria, Pydantic strict: aplicadas a los nuevos modelos.
- Catálogo cerrado de eventos: se usan `carga.completada`/`carga.fallida` YA existentes (regla 11), no se inventan.
- `SaldoBanco` no admite 'manual' (el enum se amplió pero su uso en §1.3 no cambia).

## Puntos a auditar con lupa
1. **§1.6 vs regla 8 (EL punto central):** el §1.6 manda `insertMany ordered=False` con conteo de duplicados — **no transaccional**. La regla 8 lista "finalización de carga" como transacción multi-doc, PERO abortaría en el 1er duplicado, rompiendo el conteo-y-continúa. Seguí el §1.6 (data dictionary manda). ¿Se acepta, o exiges rediseño + CR de la regla 8?
2. **`id_banco` por huella (Bancolombia/BBVA):** dos transacciones **legítimas idénticas** el mismo día (misma fecha/desc/monto/tipo) colisionan en la huella → la 2ª se rechaza como duplicado (posible pérdida). ¿Aceptable dado el diseño del índice único, o hace falta un discriminador (p. ej. secuencia por fila)?
3. **Índice único parcial:** ¿`partialFilterExpression {id_banco:{$type:'string'}}` bien construido y verificado? (test real-mongo: solape no duplica + 2 manuales coexisten).
4. **`archivo_s3_key` opcional:** el §1.6 lo marca Req; lo hice opcional porque **S3 está diferido** (RUNBOOK §6). Desviación documentada.
5. **Merge pre-gate** (arriba): riesgo de proceso.
6. **Fail-loud (regla 7):** ¿cobertura suficiente de filas ambiguas → `errores` sin adivinar? ¿Algún camino que trague en silencio?
7. **Dependencia de ciclo mensual:** la carga exige `MesControl` del mes; movimientos de meses no abiertos van a `errores` (el ciclo mensual aún no existe). ¿Es la degradación correcta?

## Evidencia local (ver EVIDENCIA.md — código + salidas reales)
- **pytest:** 209 passed / 19 skipped (local) · **8 passed** @requires_real_mongo (carga + dedup, contra Mongo real).
- **ruff:** All checks passed.
- **Protocolo de commit:** `app.alegra r1: 0 · journal-entries: 0 · estado.*pending: 0`.
- **Reglas innegociables verificadas:** Decimal (Money rechaza float, test), dedup en BD (índice único parcial, test real-mongo), fail-loud (tests de fila ambigua), audit append-only intacto, Pydantic strict + extra=forbid en todos los modelos.

## Cumplimiento del DoD / reglas de CLAUDE.md
- **DoD #2** (parsers de los 3 bancos, 0 duplicados en solape, coexistencia de 2 manuales): cubierto por código + tests real-mongo. Pendiente: **fixtures reales anonimizados** (S1-01) y export Global66 .xlsx para FX.
- **Reglas 1, 3, 5, 7, 11:** cubiertas. **Regla 8:** en tensión (punto 1). **G2** (parsers+dedup+mini-migración): parsers+dedup listos; mini-migración (S2-02) pendiente.
