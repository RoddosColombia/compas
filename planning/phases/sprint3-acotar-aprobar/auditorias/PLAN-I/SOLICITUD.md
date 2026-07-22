# SOLICITUD DE AUDITORÍA — sprint3-acotar-aprobar · I-PLAN: acotamiento + aprobación del presupuesto

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-21
**Docs contrato:** Spec §1.4 (PresupuestoLinea), §2.2 (integridad: multi-doc F-09, versionado nit-12), §2.4 (tabla única de autoridad, prevalece), §1.11/§1.12 (audit + Idempotency-Key); CLAUDE.md reglas 1, 2, 3, 4, 8, 9, 11
**Base:** `main` con el motor del sugerido mergeado (GO I-PR1 9.2, commit `7f835be`). **Nivel:** PLAN (pre-código).
**Antecedente:** este PR consume las 5 Bajas del certificado del motor.

> Anunciaste que en este incremento auditarías **la tabla de autoridad §2.4 en acción** (Directivo/Financiero acota, Admin aprueba) y el **flip atómico de vigente** dentro de la transacción multi-doc (regla 8). El PLAN se diseñó alrededor de esos dos puntos.

## Qué se propone (1 PR, alcance decidido por el CEO: Acotar + Aprobar)

1. **Acotar** — `PATCH /api/v1/meses/{mes}/presupuesto/{rubro_id}`, RBAC `presupuesto:acotar` (Financiero/Directivo/Admin, §2.4 "Proponer/acotar líneas"). Body `{monto_definido: str, comentario?: str}` (monto string, regla 1). Fija `monto_definido` en la línea vigente **no aprobada** y registra un `Ajuste` append-only (valor_anterior, valor_nuevo, por, at, **comentario**). Emite `presupuesto.acotado`. Permitido solo con mes en `sugerido`/`propuesto`.

2. **Aprobar** — `POST /api/v1/meses/{mes}/presupuesto/aprobar`, RBAC `ciclo:aprobar` (**solo Admin**, aprobador formal único §2.4), header **Idempotency-Key** (§1.12). **Transacción multi-doc (regla 8/F-09)** en la conexión principal: fija `monto_definido` en las ~30 líneas vigentes (las no acotadas toman su `monto_sugerido`) **+** MesControl → `definido` (+`definido_por`/`definido_at`), atómico, con **reintento ante `TransientTransactionError`**. Emite `presupuesto.definido`.

3. **Cambios de modelo (mínimos):** `Ajuste.comentario: str | None` (Baja #3, US-02 "renegociado"); `PresupuestoLinea.creada_por: str | None` (Baja #1, hoy el actor de la generación se descarta). MesControl sin cambios.

4. **Bajas del motor incorporadas:** #1 `creada_por`, #3 `Ajuste.comentario`, #4 `$group` para `_ejecutado` (1 query agregada vs ~90 punto-a-punto; RNF dashboard), #5 fix de fechas incoherentes en el helper de tests. **#2** (ruta de recálculo `forzar_recalculo`) se **difiere** al fast-follow de edición de crec_pct, su hogar natural (ahí vive `presupuesto.crec_modificado`). Se declara, no se pierde.

## Semántica preservada (NO cambia en este PR)
- El motor §1.4.1 y su test dorado (48/61/75M → 84.033.333,33) intactos.
- Índice único parcial `{vigente:true}` (F-06) intacto → invariante "≤1 vigente por mes/rubro".
- Histórico inmutable (regla 4): mes `cerrado` rechaza acotar/aprobar; `audit_log` append-only.
- Reglas de dinero/tiempo (Decimal, string en API, Bogotá) y Pydantic strict.
- Sin eventos nuevos: se usan `presupuesto.acotado` y `presupuesto.definido`, ya en el catálogo cerrado (regla 11).

## Decisiones declaradas (auditar con lupa)

1. **Primera aprobación = in-place** (fija `monto_definido` sobre la versión vigente actual), **NO** crea versión nueva. Lectura del contrato §2.2: *"las aprobadas generan versión nueva"* = al **modificar** una línea ya aprobada (tardías/renegociación, Sprint 4); ahí se ejerce el **flip de vigente** (nit-12: hereda `monto_definido` + apagar anterior/encender nueva en la misma transacción). En la primera aprobación no hay flip porque no nace una versión nueva. ¿De acuerdo, o exiges que la aprobación ya materialice una versión "aprobada" con flip?

2. **Líneas sin acotar → `monto_definido = monto_sugerido`** al aprobar (aceptar la recomendación del motor). ¿Correcto, o la aprobación debe **exigir** acotamiento explícito de cada línea (bloquear si alguna quedó null)?

3. **Auditoría fuera de la transacción (saga fail-closed, O1):** `presupuesto.definido` va por la **conexión dedicada de auditoría** (`compas_audit`), por lo que **no puede** participar en la sesión Mongo de la transacción de datos. Patrón propuesto (igual que la apertura ya certificada): capturar estado previo → transacción de aprobación → emitir audit; si el emit falla, **transacción compensatoria** que revierte (mes→estado previo, limpiar los `monto_definido` que eran null). Convergencia ante caída entre commit y audit vía **Idempotency-Key** (re-ejecución detecta mes ya `definido` y reconcilia el evento) + job nocturno de verificación referencial (§2.2). ¿Aceptas la saga, o exiges otro mecanismo dado que audit es conexión aparte?

4. **No hay verbo `proponer` explícito** en este PR: aprobar admite mes en `sugerido` **o** `propuesto`. El flip `sugerido→propuesto` (permiso `ciclo:proponer`) y la edición de crec_pct por rubro/global son el fast-follow. ¿Aceptable para el gate, o el estado `propuesto` debe entrar ya?

## Puntos a auditar con lupa
1. **Transacción multi-doc (regla 8):** ¿el diseño garantiza atomicidad de las ~30 líneas + MesControl, con reintento `TransientTransactionError` y el test "aprobación interrumpida converge"?
2. **Saga de auditoría** (decisión #3) — el punto más delicado por la conexión dedicada.
3. **RBAC §2.4 exacto:** acotar = Financiero/Directivo/Admin; aprobar = solo Admin (403 para el resto). ¿Bien mapeado a `presupuesto:acotar` / `ciclo:aprobar`?
4. **Guardas de estado:** acotar/aprobar rechazan mes `cerrado` (regla 4) y mes ya `definido`; aprobar es idempotente.
5. **`$group` (Baja #4):** ¿la agregación produce EXACTAMENTE el mismo E(i) que el loop punto-a-punto certificado (solo egresos, solo meses cerrados)?

## Evidencia
- Sin código aún (auditoría de PLAN). `main` con el motor mergeado: 272 tests verdes, ruff limpio, CI verde, deploy sano (`/health` 200, rutas del motor vivas).

## Pregunta al auditor
¿El diseño de acotar + aprobar —en especial la **transacción multi-doc**, la **saga de auditoría** por conexión dedicada, y las 4 decisiones declaradas— es correcto para arrancar a construir con TDD, o hay un riesgo a resolver en el PLAN antes de escribir código?

---

## Incorporaciones post-gate (GO I-PLAN 9.2 — requeridas por Kimi, sin re-auditoría)

**M-1 — `PATCH acotar` transiciona `sugerido → propuesto` en el primer acotamiento.**
El estado `propuesto` ES literalmente "los directivos ajustan cifra por cifra" (M2). Sin la
transición, un mes con ajustes seguiría mostrando `sugerido` → inconsistencia de estado. Se
añade una línea en el servicio (si mes==`sugerido` → `propuesto`) + test dedicado; con esto el
verbo `proponer` explícito queda innecesario en este PR (decisión D4 resuelta).

**M-2 — `acotar` también es O1 fail-closed (saga), igual que `aprobar`.**
`presupuesto.acotado` es una decisión financiera con autor (la vara de medición del mes) —
clase F-21, no puede perderse en silencio. Si el emit de auditoría falla, se **compensa** (1
documento): revertir el `Ajuste` recién añadido y restaurar el `monto_definido` previo (y el
estado del mes si M-1 lo cambió). El acotar deja de ser un `save` suelto y pasa a saga
capturar-previo → escribir → emitir → compensar-si-falla.

**Tests exigidos:** el `$group` (Baja #4) se valida con el mismo test dorado end-to-end
(48/61/75M → 84.033.333,33). El test "aprobación interrumpida converge" cubre los DOS puntos
de fallo: (a) abort de la transacción de datos, (b) fallo del emit → compensación.
