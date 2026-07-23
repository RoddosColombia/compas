# RESPUESTA KIMI — sprint4-deuda · I-PR1: cierre de deuda S4-00 + S4-06 (código, PR #26)

**Veredicto: APROBADO — 9.5 / 10. GO para merge.** · Fecha: 2026-07-22

---

COMPAS — Certificado I-PR1 Sprint 4: Cierre de deuda S4-00 + S4-06 (gate de código, PR #26)
Auditor: Kimi (auditor técnico senior independiente) · Fecha: 2026-07-22
Objeto: SOLICITUD(26).md + EVIDENCIA(16).md + PAQUETE(26).pdf — rama fix/deuda-s4-transacciones, PR #26, pre-merge
Objeto del PR: mis propias Bajas diferidas, con mi prescripción exacta — S4-00 (acotar transaccional, de I-PR1 PR #21 9.5) y S4-06 B-2/B-3 (TOCTOU + test step-up, de I-PR1 PR #22 9.4). Umbral ≥ 9.0.

Veredicto: APROBADO — 9.5 / 10. GO para merge.

Las tres piezas de deuda quedan cerradas exactamente como fueron prescritas, con los tests decisivos corriendo contra el replica set real (incluido el caso exacto que motivó S4-00) y cero cambios de semántica financiera (motor §1.4.1, _conciliar, montos, catálogo de 36 eventos y permisos intactos — verificado en el diff). 1 nit cosmético pre-existente (§3).

## 1. S4-00 — acotar_linea transaccional ✔ CERRADO

Mi prescripción: "envolver ln.save + mc.save en with_transaction como ya hacen aprobar_presupuesto y confirmar_cierre". Implementación [HECHO: diff]:
- cambio_mes se evalúa antes de la transacción (mc.estado is SUGERIDO) y se usa consistentemente en aplicar y en revertir ✔ (mi punto "con lupa" #1).
- _acotar(session): ln.save(session) + mc.save(session) si cambio_mes — atómico; la ventana "ajuste sin transición" desaparece ✔.
- La compensación O1 (emit falla) también es transaccional, simétrica a la reversión de aprobar ✔; estado previo capturado antes de mutar (prev_ajustes/prev_monto/prev_estado, sin cambio) ✔.
- Tests (real-mongo, patrón certificado): los 2 happy-path migrados (mongomock no soporta sesiones — declarado y correcto) + test_acotar_abort_datos_rollback_total: el caso exacto que motivó la Baja — la escritura del MES falla tras la línea → rollback TOTAL (ni ajuste, ni monto, ni transición) ✔ + test_acotar_compensa_si_falla_auditoria (commit OK + emit caído → compensación → converge al reintentar) ✔. Guardas (403/409/404/422) permanecen en mongomock — retornan antes de la transacción ✔.

## 2. S4-06/B-2 — TOCTOU ✔ CERRADO

Mi prescripción: "releer mc/siguiente con session= dentro de _cerrar y revalidar estado ahí, abortar si cambió". Implementación [HECHO]:
- _cerrar: re-lee mc_fresco y sig_fresco con session= (dentro del snapshot de la transacción); si mc ya no está en_ejecucion o siguiente quedó cerrado → CierreError 409 ✔. CierreError no es TransientTransactionError → with_transaction no reintenta, propaga al router (409, key no quemada) ✔ (mi punto "con lupa" #2).
- _reabrir: extensión simétrica declarada (mc debe seguir cerrado; siguiente no puede haberse cerrado — LIFO) ✔ — mismo riesgo, mismo patrón, bien justificada.
- Tests TOCTOU (real-mongo): simulan el proceso concurrente con un hook en _conciliar — la costura exacta entre las guardas y la transacción — que muta el estado por colección cruda. test_toctou_estado_cambiado_aborta_cierre y test_toctou_siguiente_cerrado_aborta_cierre verifican 409 + NO-mutación: sin ajuste, ancla intacta, 0 eventos mes.cerrado ✔ (mi punto "con lupa" #4). El doble ajuste que motivó la Baja es ahora imposible.

## 3. S4-06/B-3 — step-up blindado ✔ CERRADO

test_reabrir_admin_sin_step_up_403: admin autenticado sin MFA reciente → 403 con "Step-up" en el detalle y el mes intacto (CERRADO). El require_step_up del router queda blindado contra regresión ✔ — mi prescripción literal, corriendo en mongomock (verde local).

**Nit cosmético (pre-existente, no de este PR):** el docstring del módulo presupuesto/service.py sigue diciendo que aprobar_presupuesto deja el mes en "definido" — quedó desactualizado desde M-1 (PR #22: el código fija en_ejecucion). Una línea, cuando hagan el próximo pase.

## 4. Consistencia de la suite y polizontes

Conteo cuadrado [HECHO]: 412 → 411 passed local (−3 tests de acotar que migraron a real-mongo, +1 B-3 mongomock) y 40 → 46 skipped (los 6 que corren en CI: 4 acotar + 2 TOCTOU) — la aritmética de la suite es exactamente la esperada por la migración de tests declarada.
Cero polizontes: el diff toca solo cierre/service.py (2 bloques de re-lectura), presupuesto/service.py (transacción de acotar) y tests. ruff/format limpios, greps del protocolo en 0.

## 5. Respuesta a la pregunta del equipo

Sí — S4-00 y S4-06 implementan fielmente mis prescripciones (atomicidad del acotar, revalidación en sesión del cierre/reapertura, step-up blindado) sin tocar semántica financiera. **Autorizo el merge de PR #26** con los 6/6 jobs verdes (los decisivos corren en backend-real-mongo).

Estado de la deuda registrada tras este merge: S4-00 ✔, S4-06 (B-2 TOCTOU + B-3 step-up) ✔, B-1 C1 (URI por entorno — adoptada como patrón en la migración de C3) ✔, B-1 Vista Control (fail-loud caja) ✔ pre-merge, B-1 C3 (reglas_con_rubro_inactivo en respuesta de aplicar-pendientes) — única Baja abierta, sin gate. Deuda de auditoría prácticamente saldada. Quedan en el programa: tardías (F-08), CR-001 ExtractoMensual, pantalla de reglas (sin gate), semilla de egresos cuando el CEO comparta el mapeo, C4 (ajuste de caja, PLAN aparte) y el camino a G3.

Kimi — auditor técnico senior independiente. Veredicto: GO para merge — 9.5/10.
