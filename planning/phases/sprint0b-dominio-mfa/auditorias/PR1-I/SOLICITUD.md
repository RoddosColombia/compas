# SOLICITUD DE AUDITORÍA — sprint0b-dominio-mfa · I-PR1 (código)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-19
**Base:** `main` + rama `sprint0b-dominio-mfa` · **Commit:** `203e23f`
**Plan padre:** `planning/phases/sprint0b-dominio-mfa/PLAN.md` (I-PLAN 8.7 GO CONDICIONADO)
**Docs contrato:** Spec §1.2/§1.3/§1.10/§0.1/§2.2.6 · PRD M1 · reglas 1/2/3/4 de CLAUDE.md
**Nivel:** PR (código) — evidencia con diff + tests en `EVIDENCIA.md` (misma carpeta).

## Qué hace PR-1 (dominio base)
Modelos de dominio como **Beanie Documents** (decisión del CEO: PLAN literal) + `init_beanie`
cableado sin romper "arranca sin BD":
1. **`app/core/money.py`** — tipo `Money`: Decimal end-to-end; coerciona `Decimal128→Decimal`
   al leer de Mongo y **rechaza float/bool** (regla 1). `money_str` para la API.
2. **`Rubro`** + **semilla REAL** (32 rubros): 31 categorías del Excel congelado
   (`Flujo de pagos deudas.xlsx`, hoja 'Presupuesto', PRD M1) + `Ajuste de conciliación`
   (Spec §2.2.6). 2 de sistema (`Por clasificar`, `Ajuste de conciliación`). Índice único
   `(grupo, nombre)` (Kimi M-02).
3. **`MesControl`** — `mes` 'YYYY-MM-01' string único, estados, saldos `Decimal`, `saldos_banco`;
   `assert_editable()` bloquea meses cerrados (regla 4).
4. **`Configuracion`** — valor **tipado por clave** (`valor_decimal`/`valor_fecha`/`valor_json`),
   exactamente-uno-del-tipo-correcto (Kimi M-03); semilla UMBRAL `$50.000` + CALENDARIO_DIAN
   real (13-may-26/10-sep-26/14-ene-27) + DIAS_CREDITO (vacío, lo puebla Financiero).
5. **`seed.py` + migrations** — idempotentes (`$setOnInsert`); `Decimal→Decimal128` al escribir.
6. **`init_beanie`** — `DOCUMENT_MODELS = [Rubro, MesControl, Configuracion]`; AuditLog/User/
   RefreshSession FUERA (Motor crudo, Kimi M-04). `ensure_beanie` NO fatal + reintento en readiness.

## Puntos a auditar con lupa
1. **Money/Decimal128:** ¿la coerción `Decimal128→Decimal` + rechazo de float/bool es correcta y
   suficiente? ¿El seed por Motor crudo (`Decimal→Decimal128`) preserva el valor exacto?
2. **Semilla real:** ¿los 32 rubros y su clasificación por grupo son fieles al Excel? ¿es
   correcto añadir `Ajuste de conciliación` (no está en el Excel) por Spec §2.2.6?
3. **init_beanie sin romper 'arranca sin BD':** ¿el patrón no-fatal + reintento en readiness es
   sólido? ¿AuditLog correctamente FUERA del ODM?
4. **Inmutabilidad de meses cerrados** (regla 4) y unicidad de índices (probada con `@requires_real_mongo`).

## Autoauditoría — desviaciones que declaro (para que las cierres)
- **D-1 `mes`/fechas como STRING 'YYYY-MM-DD', no `Date`:** el Spec §1.3 dice "Date (YYYY-MM-01)".
  BSON no tiene fecha-sin-hora → un `date` se persiste como `datetime` y al releer rompe el
  schema strict y arrastra zona horaria. La regla 2 de CLAUDE.md pide 'YYYY-MM-DD, mes al día 1'.
  Elegí string ISO (representación fiel, inequívoca). ¿Aceptable o exiges `Date`?
- **D-2 `Configuracion` índice `(clave, vigente_desde)` único:** el Spec §1.10 no fija el índice;
  inferí versionado temporal (el valor vigente = mayor `vigente_desde` ≤ hoy). Sin flag `vigente`
  (a diferencia de PresupuestoLinea). ¿De acuerdo?
- **D-3 `Ajuste de conciliación` en grupo `otros`:** el Spec no dice a qué grupo pertenece;
  lo puse en `otros` (es de sistema). Es una decisión, la señalo.
- **D-4 `Money` rechaza `int`/`str`:** fuerza a pasar `Decimal` explícito; la API parseará el
  string→Decimal antes de construir. ¿Muy estricto o correcto?

## Evidencia (en EVIDENCIA.md)
Código fuente completo de los módulos nuevos + diffs de `mongo.py`/`main.py`/`health.py`,
salida de `pytest` (129 passed, 9 skipped @requires_real_mongo) y `ruff` limpio, y self-check
de la semilla "al peso".

## Pregunta al auditor
¿El dominio base (modelos strict + Decimal end-to-end + semilla real + init_beanie no-fatal) es
correcto y fiel al contrato para GO, o hay un riesgo a resolver antes de mergear?
