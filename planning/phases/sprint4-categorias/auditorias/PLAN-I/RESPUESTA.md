# RESPUESTA — Kimi · I-PLAN Sprint 4: C1 Categorías administrables

> Pegada por el CEO el 2026-07-22. Veredicto: **APROBADO — 9.2/10. GO para construir con TDD.**

---

COMPAS — Auditoría I-PLAN Sprint 4: C1 Categorías administrables (rubros CRUD + re-seed)
Auditor: Kimi (auditor técnico senior independiente) · Fecha: 2026-07-22
Objeto: SOLICITUD(22).md + PAQUETE(22).pdf — sprint4-categorias · I-PLAN C1 (PLAN, pre-código)
Base: main con Vista Control mergeada (I-PR1 GO 9.4). Contrato: COMPAS_NORTE, PROJECT (C1), MODELO (taxonomía real), CR-S4 (catálogo 31→33 + rubros:gestionar), Spec §1.2/§2.2/§4.1. Umbral ≥ 9.0.

Veredicto: APROBADO — 9.2 / 10. GO para construir con TDD.

Diseño limpio y bien acotado (C1 solo; C3 en PLAN aparte — buena disciplina), gobernanza correcta vía CR-S4 para los 2 eventos y el nuevo permiso, y las tres decisiones consultadas (D1/D2/D3) van en la dirección correcta. Sin hallazgos Medios/Altos. 5 Bajas de precisión/declaración para incorporar en TDD (se verifican en el gate de código, sin re-auditoría de plan) + 2 observaciones de gobernanza.

## 1. Respuesta a las preguntas del equipo

**D1 — ¿Congelar tipo_flujo si el rubro ya tiene transacciones? SÍ, correcto ✔ — con una extensión (B-1).**
Primero, un hecho que desdramatiza: verifiqué el código certificado y ningún cálculo de dinero toma el signo del rubro — _signo(t) (caja/conciliación) y E(i) del motor usan t.tipo_flujo de la transacción. Voltear rubro.tipo_flujo no cambia retroactivamente ningún número. Aun así, el congelamiento es la guarda correcta para la integridad semántica (clasificación, C3 futuro, coherencia del histórico — regla 4 en espíritu).
B-1: la guarda debe ser "tiene referencias", no solo "tiene transacciones": un rubro con líneas de presupuesto pero aún sin movimientos (p.ej. creado vía C1 e incluido en una generación de sugerido) quedaría editable en tipo_flujo, y el flip lo dejaría con una línea calculada como egreso siendo ingreso. Extender el congelamiento a ∃ Transaccion(rubro_id) ∨ ∃ PresupuestoLinea(rubro_id). Una línea de código y un test.

**D2 — ¿Desactivar con movimientos? De acuerdo ✔** — la baja lógica es la única opción coherente con histórico inmutable; las transacciones permanecen en la categoría inactiva y visibles. Falta declarar el alcance completo de la baja (B-2).

**D3 — ¿Categorías viejas genéricas: dejarlas activas o desactivarlas? ✔** Dejarlas activas y que el CEO las depure desde la app — la respuesta correcta precisamente porque la desactivación viaja en esta misma pieza: sin pérdida de datos, sin adivinar (regla 7), y prod aún no tiene transacciones reales. Con el reporte de colisiones del re-seed (B-4), el riesgo residual queda cubierto.

## 2. Verificación de los puntos "con lupa"

- Inmutabilidad de sistema (409 en editar/desactivar) ✔ — los 3 rubros (Por clasificar, Ajuste de conciliación, Recaudo) protegidos por es_sistema; correcto que el 409 aplique a PATCH y a desactivar (y, por consistencia, también debe aplicar a cualquier intento de cambiarles es_sistema — no expuesto en la API, bien). Tests negativos esperados.
- CR-S4 (catálogo 31→33 + rubros:gestionar) ✔ gobernanza correcta — el catálogo es cerrado y los permisos son §4.1: ambos cambian por CR. El test de completitud de CI (E-9) y el guardian de require_permission atrapan cualquier desviación automáticamente. Punto de verificación para el gate de código (no es hallazgo): confirmar que rubro.desactivado existe en el catálogo de 31 (el plan lo afirma; si no existiera, CR-S4 sería +3, no +2) y que rubros:gestionar={financiero,admin} queda en el config con sus tests negativos (consulta/directivo → 403).
- Congelar tipo_flujo (D1) ✔ con la extensión B-1.
- Re-seed idempotente ($setOnInsert por (grupo,nombre)) ✔ — no duplica, no pisa ediciones, apoyado en el índice único existente; re-ejecutable. B-4 añade el reporte de colisiones.
- Único (grupo,nombre) → 409 ✔ — vía DuplicateKeyError del índice, con manejo explícito a 409 (no 500) y test.

## 3. Bajas (incorporar en TDD; las verifico en I-PR1)

- **B-1 (D1):** congelar tipo_flujo si el rubro tiene transacciones O líneas de presupuesto (ver §1). Nombre/orden editables siempre — correcto (no afectan cómputo).
- **B-2 (alcance de la baja lógica):** declarar y probar los 3 puntos de contacto de activo=false: (a) la clasificación (manual y la futura C3) rechaza rubros inactivos — dónde vive esa guarda; (b) el motor del sugerido omite rubros inactivos en generaciones futuras (si no, la baja "gotea": la categoría desactivada volvería a recibir línea el próximo mes); (c) Vista Control sigue mostrando las líneas ya existentes del rubro inactivo (histórico del ciclo en curso) — que es el comportamiento natural al iterar por líneas y conviene fijarlo con un test. Nota asociada: una categoría operativa de tipo ingreso creada vía C1 no recibe línea de presupuesto (el presupuesto §1.4 es de egresos) — declararlo para que nadie la espere en Vista Control.
- **B-3 (reactivación):** fijar la vía antes de código. Recomendación: PATCH con activo:true emitiendo rubro.editado {activo: false→true} — rastro completo sin un 34.º evento (CR-S4 queda en +2). La alternativa (endpoint simétrico /activar con rubro.activado) costaría otro evento de catálogo; la primera opción es suficiente y más barata.
- **B-4 (re-seed):** emitir un reporte de colisiones: los (grupo,nombre) donde $setOnInsert omitió porque ya existía un doc viejo. Hoy, sin transacciones reales, un doc viejo coincidente podría tener tipo_flujo/orden distintos del mapeo de MODELO.md y nadie se enteraría (silencioso). Con el reporte, el equipo verifica los coincidentes (o hace upsert de tipo_flujo solo en docs sin referencias — seguro hoy).
- **B-5 (política de auditoría de las mutaciones):** declarar la política de emisión para rubro.creado/editado/desactivado. Recomendación: fail-closed estilo O1 (son cambios estructurales del sistema presupuestal — Ley 1581): insertar/actualizar → emitir → si la emisión falla, compensar (borrar el rubro creado / revertir el campo). Es un solo documento, la compensación es trivial, y queda consistente con el estándar del ciclo. Si eligen fire-and-forget, que quede declarado con justificación.

## 4. Observaciones de gobernanza (no puntúan)

- Alcance: C1 es una adición de alcance respecto al baseline v1.1.2 (Sprint 4 original: Vista Control + tardías + cierre). Llega con la gobernanza correcta (COMPAS_NORTE + CR-S4 declarado, decisión CEO) y los criterios de G3 no cambian (ciclo + control con julio real). Registrar C1 en el tracker con ID propio (no aparece como fila S4-xx aún) y vigilar la capacidad del sprint: quedan en vuelo S4-00, S4-06, tardías (F-08) — que no aparece como tarea separada en el tracker desde que S4-01 se cerró como Vista Control —, CR-001 y C3.
- Deuda documental conocida: DoD #6 sigue diciendo "30 eventos"; la errata v1.1.3 / CR-002 pendiente debe absorber CR-S2 (31) y ahora CR-S4 (33) + rubros:gestionar en §4.1.

## 5. Tests que el gate de código (I-PR1) esperará ver

- POST crea con orden = máx(grupo)+1 y emite rubro.creado (1 evento); duplicado (grupo,nombre) → 409.
- PATCH edita nombre/orden → rubro.editado con {campo: anterior→nuevo}; nombre duplicado → 409.
- D1/B-1: PATCH tipo_flujo en rubro con transacciones → 409; en rubro con línea de presupuesto sin transacciones → 409; en rubro nuevo sin referencias → 200.
- Sistema: PATCH y desactivar sobre los 3 rubros de sistema → 409 (parametrizado).
- Desactivar con movimientos → 200, histórico intacto; clasificar hacia rubro inactivo → 409/422 (B-2a); sugerido omite inactivo (B-2b); Vista Control conserva línea existente de inactivo (B-2c).
- RBAC exacto: GET 200 los 4 roles; POST/PATCH/desactivar → 403 consulta y directivo, 200 financiero y admin.
- Re-seed: 1.ª corrida siembra las 31 reales; 2.ª corrida no duplica ni pisa (idempotente); reporte de colisiones presente (B-4).
- Reactivación por la vía elegida (B-3) con su evento; test de completitud del catálogo en 33 + guardian con rubros:gestionar.
- Política de emisión declarada (B-5): si fail-closed, test de compensación al fallar la emisión (patrón ya probado en ciclo).

**Camino: construir con TDD incorporando B-1..B-5 → I-PR1 con esos tests → merge. Sin re-auditoría de plan.**
