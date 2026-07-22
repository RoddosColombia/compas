# CERTIFICADO KIMI — sprint4-vista-control · I-PR1 (gate de código, PR #23)

**Resultado:** **9.4 / 10 — ✅ GO para merge** · **Fecha:** 2026-07-22
**Rama:** `feat/vista-control` · commit `37426e4` · **CI PR #23 run 29950896107: 6/6 verde**

## Los 8 tests exigidos + 3 Bajas del plan: cerrados
1. Dorado de celda ✔ · 2. Bordes del semáforo (sobre pct cuantizado) ✔ · 3. Caja: ajuste excluido / 'Por clasificar' incluido ✔ · 4. Guardas ✔ · 5. RBAC 4 roles ✔ · 6. Equivalencia $group ✔ · 7. Linealidad de subtotales ✔ · 8. Serialización strings ✔.
Bajas del plan: B-1 semáforo sobre pct cuantizado (garantía estructural) ✔ · B-2 pct string ✔ · B-3 sin_presupuesto informativo ✔.

Verificación adversarial: `_pct` (Decimal, HALF_EVEN, None si definido==0), `_semaforo` (sobre el cuantizado — 90.005→90.00→verde por construcción), `_egresos_por_rubro` ($group = E(i) del motor, DoD #3), subtotales lineales, solo-lectura real (cero escrituras/transacciones/eventos), diff puramente aditivo.

## Baja NUEVA (no bloqueante — camino del dinero, fix 1-2 líneas)
**B-1 (sentinela None):** `control.py` localiza el rubro de ajuste con `next(..., None)` y pasa `None` a `_caja_libro`. Con `rubro_ajuste_id=None`, el predicado `t.rubro_id == rubro_ajuste_id` puede excluir silenciosamente transacciones equivocadas si el rubro 'Ajuste de conciliación' no está sembrado → número de dinero equivocado y silencioso (regla 7). En el cierre no ocurre porque `_rubro_ajuste()` es fail-loud (500). **Fix:** reutilizar `_rubro_ajuste()` en `control.py` (mismo fail-loud). → APLICADO antes del merge.

## Observación (no puntúa)
`_caja_libro` recorre todas las transacciones del mes por streaming (~20k/carga). Correcto pero candidato a `$group` cuando llegue la prueba de carga DoD #9 (p95 < 2 s). Anotado para ese sprint.

## Veredicto
"Autorizo el merge de PR #23 con la B-1 registrada." → El fix fail-loud se incorpora antes del merge (prescrito por Kimi, sin re-auditoría). Post-merge Sprint 4: S4-00, tardías F-08, CR-001, frontend Vista Control (sin gate), luego G3.
