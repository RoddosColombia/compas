# PLAN — Sprint 1: Datos (esquema canónico, dedup, parser Bancolombia, ciclo de cargas)

**Fase:** `sprint1-parsers` · **Fecha:** 2026-07-20 · **Base:** `main` (Sprint 0 cerrado tras Gate G1)
**Contrato:** Spec §1.5 (Transaccion), §1.6/§1.6.1 (CargaBancaria + parsers), §2.2 (integridad), §2.3 (índices) · PRD M2/M3 · PLAN_TRABAJO F2/Sprint 1 · DoD #4 (dedup), #7 (transacción multi-doc), #8 (CI) · CR-001 (fuera de alcance aquí)
**Fuente a portar:** `../SISMO-V2/backend/services/bank_parsers.py` (parser Bancolombia) — **adaptar, no copiar** (float→Decimal, silencioso→reportado, 5 bancos→1).

> **Alcance del Sprint 1 (PLAN_TRABAJO, F2 · Sprint 1 — NO ampliar sin CR):**
> congelar layouts (fixtures Día 0) + **parser Bancolombia** + **esquema canónico** (Transaccion/CargaBancaria) +
> **dedup** (índice único parcial + manuales `MAN-`) + **pantalla de cargas con ciclo de vida completo**
> (fallida/reaper/reproceso, F-02) + **POST manual**.
> **BBVA y Global66 son Sprint 2** (con moneda original, F-03) — este plan NO los construye. Reglas de
> clasificación, 'Por clasificar' y mini-migración también son Sprint 2.

---

## Objetivo
Poner en pie la ingesta de movimientos bancarios de RODDOS de punta a punta para **un** banco
(Bancolombia), con el esquema canónico y las garantías de integridad que el resto de bancos
reutilizarán en Sprint 2: dinero en Decimal, deduplicación en la base, parsers que **transforman y
jamás interpretan** (fila ambigua = error reportado, carga 'fallida'), y un ciclo de vida de cargas
idempotente y reprocesable.

---

## Brainstorming (obligatorio antes de código — CLAUDE.md)

**Problema en una oración:** ingerir extractos de Bancolombia como `Transaccion` inmutables y
deduplicadas, sin adivinar nunca una fila ambigua, con dinero exacto (Decimal) y un ciclo de carga
reprocesable.

### Decisión A — ¿de dónde sale `id_banco` para Bancolombia? *(el riesgo #1 del sprint)*
El Spec exige `id_banco String(40)` "de extracto si banco ≠ manual" (§1.5) y la dedup es por índice
único `(banco, id_banco)` (§2.3). **El parser de SISMO NO produce ningún `id_banco`.** Si el layout
real de Bancolombia (Día 0) no trae un identificador de transacción nativo y estable, tenemos:
- **A1 — Usar el ID nativo del extracto** si existe (columna tipo "referencia"/"documento"). ✅ cumple
  "transforman, no interpretan"; dedup trivial. *Depende de que el layout lo traiga.*
- **A2 — Clave determinista de campos inmutables** (`fecha|valor|descripcion|secuencia_en_archivo`).
  ⚠️ es *derivación*, roza la regla 7 y fija semántica de dedup e inmutabilidad → **requiere CR y
  bendición del CEO**; riesgo de colisión de dos movimientos idénticos legítimos el mismo día.
- **A3 — Bloquear** hasta congelar el layout real y decidir con evidencia.
- **Elección: A3 → luego A1 si el layout lo permite; si no, A2 documentado en un CR.** El
  congelamiento de layouts (F-51) es el PRIMER entregable y **precondición** del parser. **No se
  escribe el parser adivinando el `id_banco`.**

### Decisión B — Decimal al leer celdas .xlsx
`openpyxl` devuelve números como `float`/`int`; pasar por `float` viola la regla 1 y pierde precisión.
- **B1 — `Decimal(str(cell.value))`** por celda; para celdas texto, parsear locale **es-CO**
  explícito (punto=miles, coma=decimales — al revés que SISMO, que asumía formato US). ✅
- **B2 — pandas** (`read_excel`): reintroduce float64 en el camino. ❌ (lo usaba SISMO para Nequi).
- **Elección: B1.** Reutiliza `app/core/money.py` (`Money`, `money_str`); nunca `float()` sobre montos.

### Decisión C — modelo de "fila ambigua = error reportado"
- **C1 — Acumular errores por fila** (`fila`, `motivo`, `valor_crudo`) y, si hay ≥1 error,
  marcar la carga `fallida` con `motivo_fallo` visible; NADA se inserta (todo-o-nada por carga). ✅
  cumple regla 7 y el escenario Spec §300 (BBVA falla por fila ambigua → 'fallida').
- **C2 — Insertar lo válido y reportar lo demás.** ❌ deja el histórico a medias; contradice el
  escenario del Spec.
- **Elección: C1** (todo-o-nada; el humano corrige el archivo y re-sube — el hash previo no bloquea
  porque la carga anterior no quedó 'completada', §1.6).

### Decisión D — orden de construcción (PRs, cada crítico con gate Kimi ≥ 9.0)
Esquema+dedup primero (todo lo demás depende de él), luego parser (aislado, TDD contra fixture),
luego ciclo de cargas (orquesta parser+dedup+transacción), luego pantalla. Ver desglose.

---

## Desglose en PRs (4 · los 3 primeros son críticos → gate Kimi obligatorio)

### PR-1 — Esquema canónico + dedup + POST manual  *(crítico)*
Modelos de dominio y la integridad que todo lo demás reutiliza.
- **`app/domain/transaccion.py`** — `Transaccion` (Beanie Document) según Spec §1.5: `fecha`,
  `descripcion(300)`, `valor: Money` (>0, COP), `tipo_flujo: ingreso|egreso`, `rubro_id`
  (default 'Por clasificar'), `mes_id` (derivado de fecha, día 1), `banco: Banco|manual`,
  `id_banco(40)`, `tardia: bool`, campos opcionales de origen/conciliación. Campos de moneda
  original (`moneda_original/valor_original/tasa_cambio/tasa_fuente`) **se declaran** en el schema
  (los usará Global66 en Sprint 2) pero quedan `None` para Bancolombia/manual. Pydantic `strict=True`.
- **`app/domain/carga_bancaria.py`** — `CargaBancaria` (Spec §1.6): `banco`, `archivo_nombre/hash/s3_key`,
  contadores `total_filas/nuevas/duplicadas/errores`, `estado: procesando|completada|fallida`,
  `motivo_fallo`, `usuario_id`, `created_at`.
- **Dedup en BD (DoD #4):** índice **único parcial** `(banco, id_banco)` con
  `partialFilterExpression {id_banco: {$type: 'string'}}`; migración fechada idempotente
  (`migrations/2026…_transaccion_indexes.py`). Manuales: `id_banco = 'MAN-' + ULID`.
- **`POST /api/v1/transacciones` (manual):** genera `MAN-`+ULID, `banco='manual'`, Idempotency-Key
  (scope usuario+endpoint+key). RBAC: Financiero/Admin (§4.1).
- **Tests (TDD, real-mongo):** dos manuales del mismo día **coexisten** (no DuplicateKeyError) —
  cierra el `skip` "Sprint 1" que dejó la Sesión 3 en `test_real_mongo_marker.py`; solape de
  `id_banco` iguales → exactamente 1 gana, el 2º cuenta como duplicado; `valor` rechaza float;
  `mes_id` normalizado a día 1; mes cerrado rechaza manual (salvo carga tardía — PR-3).

### PR-2 — Congelamiento de layouts (F-51) + parser Bancolombia  *(crítico)*
- **Congelar layout Bancolombia** contra el fixture real Día 0: documento
  `docs/layouts/bancolombia_v1.md` (hoja, fila de encabezados, columnas, formato de fecha y de
  monto, y **de dónde sale `id_banco`** — Decisión A resuelta con evidencia). Los 3 layouts se
  congelan; solo Bancolombia se implementa ahora.
- **Anonimización de fixtures (F-25/§1.6.1):** `scripts/anonimizar_extracto.py` determinista +
  verificación automática (0 datos reales) antes de entrar al repo. **Repo solo sintéticos/anonimizados**;
  reales en S3 privado; gitleaks en CI. Fixture sintético en `backend/tests/fixtures/bancolombia/`.
- **`app/parsers/bancolombia.py`** (adaptado de SISMO):
  - Streaming `openpyxl read_only=True, data_only=True`.
  - **Decimal** por celda (Decisión B); mapeo `credito→ingreso`, `debito→egreso`, `valor>0`.
  - **Transforman, no interpretan** (Decisión C): devuelve `(movimientos, errores[])`; fecha/monto
    inválidos, columnas faltantes, o fila que no case el layout congelado → **error con nº de fila y
    motivo**, jamás `continue` silencioso (a diferencia de SISMO).
  - **Parser versionado** (`LAYOUT_VERSION`) — cambio de layout ⇒ versión nueva.
- **Tests (TDD):** parser es transform puro (sin Mongo/Alegra) — casos: fila válida, monto
  Decimal exacto es-CO, fecha sin año → año en curso, fila ambigua ⇒ error reportado (no adivina),
  archivo sin hoja/columna ⇒ error, 0 movimientos válidos ⇒ error.

### PR-3 — Ciclo de vida de cargas (F-02) + reaper  *(crítico)*
Orquesta parser + dedup + transacción, idempotente y reprocesable.
- **`POST /api/v1/cargas`**: recibe archivo, calcula **SHA-256**, **rechaza por hash SOLO si existe
  carga previa `completada`** con ese hash (si la previa está `fallida`, permite re-carga, §1.6);
  Idempotency-Key. Límites **F-22**: ≤10 MB, ~20.000 filas, ratio de descompresión acotado,
  `.xlsm` rechazado; parseo en **threadpool** (`anyio.to_thread`) para no bloquear el event loop.
- **Finalización de carga = transacción multi-documento (DoD #7):** parsea → si hay errores,
  `fallida` + `motivo_fallo` (nada insertado, Decisión C); si OK, `insertMany(ordered=False)`,
  `duplicadas` = `DuplicateKeyError` contados, `nuevas` = resto, estado `completada`. Todo bajo una
  transacción de Mongo (carga + movimientos consistentes).
- **Reaper (job worker, F-02):** `procesando` > `UMBRAL_CARGA_STALE` → `fallida` con motivo.
  **`RUN_SCHEDULER=false` en web** (regla 6); job **idempotente**, solo en `compas-jobs`.
- **Reproceso:** re-subir el archivo corregido de una carga `fallida` funciona (hash no bloquea).
- **Eventos de auditoría:** `carga.completada` / `carga.fallida` (del catálogo cerrado — sin
  inventar eventos, regla 11).
- **Tests (TDD, real-mongo):** solape de 2 cargas → 0 duplicados; carga fallida → reproceso OK;
  hash de `completada` bloquea, hash de `fallida` no; reaper marca stale; `.xlsm`/>10 MB rechazados.

### PR-4 — Pantalla de cargas (frontend)  *(no crítico)*
Vista de cargas con estado del ciclo de vida (procesando/completada/fallida + motivo), subida con
Idempotency-Key, contadores (nuevas/duplicadas/errores), descarga del original
(`Content-Disposition: attachment` + `nosniff`). Rutas `/:mes/cargas`; TanStack Query keys
`['mes', 'YYYY-MM', 'cargas']`, invalidación tras mutación. Dinero solo con `Intl.NumberFormat('es-CO')`,
nunca `Number` sobre montos.

---

## Dependencias y precondiciones (duras)
1. **Gate G1 GO** (cierre de Sprint 0) — este sprint arranca *después*. Hoy bloqueado por el run
   verde de Actions (incidente GitHub) + bloque C operacional del CEO.
2. **Fixtures reales Día 0** (Bancolombia como mínimo) entregados y anonimizados — **precondición de
   PR-2** (sin el layout real no se congela ni se escribe el parser). Operacional del CEO.
3. **Atlas aprovisionado** (C7) para que los tests real-mongo de dedup/carga corran en CI.
4. **Decisión A (`id_banco`)** resuelta en el congelamiento de layouts *antes* de PR-2; si el layout
   no trae ID nativo → CR aprobado por el CEO para la clave determinista.

## Semántica preservada (no cambia aquí)
Histórico inmutable (meses cerrados; solo tardías por carga con `tardia=true`); `audit_log`
append-only; catálogo cerrado de eventos (no se inventan); Decimal en todo el dinero; TZ
América/Bogotá; Pydantic strict; `RUN_SCHEDULER=false` en web.

## Riesgos
| # | Riesgo | Mitigación |
|---|---|---|
| 1 | `id_banco` de Bancolombia no nativo → dedup/inmutabilidad frágiles | Decisión A: congelar layout primero; A1 si hay ID nativo, si no CR para A2 |
| 2 | Pérdida de precisión float al leer .xlsx | Decisión B: `Decimal(str(...))`, nunca `float()`; locale es-CO explícito |
| 3 | Fixture real filtrado al repo | Anonimización determinista + verificación + gitleaks; reales solo en S3 |
| 4 | Sobre-escopar a BBVA/Global66 | Este plan los excluye explícitamente (Sprint 2) |

## Definición de hecho del sprint
- Parser Bancolombia con **fixture real anonimizado**, **0 duplicados en solape**, coexistencia de
  **2 manuales** (F-04) y **reproceso de carga fallida** (F-02) — DoD del PLAN_TRABAJO Sprint 1.
- Todos los tests que tocan Mongo bajo `@requires_real_mongo` verdes en CI (job `backend-real-mongo`).
- Ninguna fila ambigua adivinada (regla 7 verificada con test).

## Pregunta al auditor (gate del PLAN)
¿Este plan cierra el alcance del Sprint 1 sin huecos ni sobre-alcance, con la integridad correcta
(dedup en BD, Decimal, transforman-no-interpretan, transacción multi-doc), y la Decisión A
(`id_banco`) tratada como precondición y no como algo a adivinar?
