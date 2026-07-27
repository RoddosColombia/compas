# CR-D2 — Obligaciones, facturas y metas de ingreso auditadas (extensión del catálogo)

**Fecha:** 2026-07-27 · **Sprint:** D2 · **GO CEO:** 2026-07-27
**Regla que lo exige:** regla 11 (CLAUDE.md) — catálogo CERRADO de eventos; no inventar sin CR. Patrón idéntico a CR-D1.

## Contexto
D2 introduce tres entidades administrables con CRUD **auditado** (spec §2 y §6):
**Obligación** (deudas/cuentas por pagar de dos naturalezas), **FacturaObligación**
(registro factura a factura) y **MetaIngreso** (meta de ingreso por mes). Cada mutación
—por la regla 4 (rastro append-only) y las specs— debe quedar auditada, y ninguno de los
eventos actuales las cubre.

## Cambio
Se añaden **8 eventos** al catálogo cerrado `AuditEvento` (50 → **58**):

| Miembro (enum) | Valor | Cuándo |
|---|---|---|
| `obligacion_creada` | `obligacion.creada` | POST /obligaciones |
| `obligacion_editada` | `obligacion.editada` | PATCH (incl. reactivación) |
| `obligacion_eliminada` | `obligacion.eliminada` | DELETE (baja lógica) |
| `factura_obligacion_registrada` | `factura_obligacion.registrada` | POST factura |
| `factura_obligacion_anulada` | `factura_obligacion.anulada` | DELETE factura (baja lógica) |
| `meta_ingreso_creada` | `meta_ingreso.creada` | POST /metas-ingreso |
| `meta_ingreso_editada` | `meta_ingreso.editada` | PATCH |
| `meta_ingreso_eliminada` | `meta_ingreso.eliminada` | DELETE (baja lógica) |

Convención: miembro con `_`, valor `<dominio>.<acción>`. Emisión **fail-closed** estilo
O1 (mutar → emitir → compensar), idéntica a `modelo_moto.*` / `escenario_impacto.*`.

## Impacto
- `backend/app/audit/events.py`: +8 miembros; docstring actualizado (total 58).
- `backend/tests/test_audit_events.py`: conteo 50 → 58; eventos clave añadidos.
- Colecciones nuevas `obligaciones`, `facturas_obligacion`, `metas_ingreso`.
- **`motor.py` y golden-master:** sin cambios (capa POSTERIOR).

## Fuera de alcance
No se emiten eventos al *simular* (política de plazos §5 es compute-only). La deuda de
inversores NO se migra al modelo (sigue dentro del motor; decisión CEO post-D2).
