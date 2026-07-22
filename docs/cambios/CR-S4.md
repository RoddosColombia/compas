# CR-S4 — Categorías administrables: 2 eventos de auditoría + permiso RBAC

**Origen:** C1 (Sprint 4) — el CEO pidió **crear/administrar categorías desde la app**
(2026-07-22). Cambiar categorías moldea todo el presupuesto → crear/editar deben quedar
auditados. Toca dos innegociables (regla 11 catálogo, regla 9 RBAC) → se declara por CR
ANTES de construir.

## Decisión que se formaliza

### (a) Catálogo de auditoría (regla 11): 31 → 33 eventos
Se agregan al catálogo CERRADO dos eventos:
- `rubro.creado` — al crear una categoría (actor + grupo + nombre + tipo_flujo).
- `rubro.editado` — al editar una categoría (actor + campos cambiados: valor anterior→nuevo).

`rubro.desactivado` YA existe (v1.1). Con esto la baja lógica y el alta/edición quedan
todas con rastro. Se actualiza el test de completitud del catálogo en CI (31→33).

### (b) RBAC (regla 9 / Spec §4.1): permiso nuevo
- `rubros:gestionar` = **{Financiero, Admin}**. Habilita `POST /rubros`, `PATCH /rubros/{id}`,
  `POST /rubros/{id}/desactivar`. El listado (`GET /rubros`) queda en `dashboard:leer`
  (todos los roles). El Financiero administra la estructura presupuestal a diario; Admin también.

## Semántica y guardas (no cambian las reglas de dinero)
- Rubros de **sistema** ('Por clasificar', 'Ajuste de conciliación', 'Recaudo') **inmutables**
  (409 al editar/desactivar) — Spec §2.2.
- **No se borra** un rubro (Spec §2.2): solo baja lógica (`activo=false`).
- Único (grupo, nombre) — índice existente.
- Re-seed de la taxonomía real (31 categorías del `Base real egresos`, agrupadas en los 5
  grupos) mediante migración idempotente `$setOnInsert` — no pisa ediciones ni duplica.
  Seguro hoy: prod solo tiene la semilla (aún no hay transacciones reales migradas).

## Alcance NO incluido (para que quede claro)
- Reglas de auto-clasificación (ReglaClasificacion) = **C3**, CR/PLAN aparte.
- Este CR solo habilita **C1** (categorías administrables).

---
**Firma CEO:** ☐ Pendiente — aprobación explícita en sesión (como CR-S2/CR-S3). El CEO
seleccionó "CR corto: auditar crear+editar" y "rubros:gestionar = Financiero+Admin"
(2026-07-22). Se confirma al aprobar el gate PLAN de C1.
