# CR-D1 — Escenarios de impacto auditados (extensión del catálogo de eventos)

**Fecha:** 2026-07-27 · **Sprint:** D1 (Decisiones sobre el motor) · **GO CEO:** 2026-07-27
**Regla que lo exige:** regla 11 (CLAUDE.md) — *"catálogo cerrado de eventos; no inventar eventos nuevos sin CR."*

## Contexto
La spec de D1 (§2) pide **escenarios de impacto nombrados con CRUD auditado**: el usuario
guarda un conjunto de ajustes ("Sede nueva", "Ventas -10%") como escenario reutilizable.
*Simular nunca escribe*; **guardar sí** — y guardar/editar/eliminar un escenario es una
mutación que, por la regla 4 (rastro append-only) y §2 de la spec, debe quedar auditada.

Guardar un escenario NO encaja en ningún evento del catálogo actual (47): no es
`parametros_proyeccion.actualizado` (eso son los drivers del motor, no un escenario
what-if), ni `config.actualizada`. Se necesitan eventos propios.

## Cambio
Se añaden **3 eventos** al catálogo cerrado `AuditEvento` (47 → **50**):

| Miembro (enum) | Valor | Cuándo |
|---|---|---|
| `escenario_impacto_creado` | `escenario_impacto.creado` | POST /escenarios-impacto |
| `escenario_impacto_editado` | `escenario_impacto.editado` | PATCH (incl. reactivación); metadata = {cambios} |
| `escenario_impacto_eliminado` | `escenario_impacto.eliminado` | DELETE (baja lógica `activo=false`) |

Convención respetada: miembro con `_`, valor `<dominio>.<acción>`. Emisión **fail-closed**
estilo O1 (mutar → emitir → si el emit falla, compensar y propagar), idéntica al patrón
de `modelo_moto.*` auditado por Kimi en C1/COCK.

## Impacto
- `backend/app/audit/events.py`: +3 miembros; docstring actualizado (total 50).
- `backend/tests/test_audit_events.py`: conteo 47 → 50; eventos clave añadidos.
- Colección nueva `escenarios_impacto` (no toca colecciones existentes).
- **motor.py y golden-master:** sin cambios (capa POSTERIOR).

## Fuera de alcance
No se emiten eventos al *simular* impactos (POST /proyeccion/impactos es compute-only) ni
al leerlos. Solo el guardado explícito audita.
