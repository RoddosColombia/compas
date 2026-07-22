# SOLICITUD DE AUDITORÍA — sprint4-cierre-conciliacion · I-PR1: cierre + conciliación + reapertura

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-21
**Docs contrato:** Spec §1.3, §1.10, §2.2 (F-09, inmutabilidad §2.2.2, nit-9), §2.4; CLAUDE.md reglas 1,2,3,4,5,8,9,11
**Rama / PR:** `feat/cierre-conciliacion` / **#22** · commit `6f57c9a` · **SIN mergear — gate pre-merge**
**Antecedente:** GO PLAN R 9.4 (M-1..M-4). Este es el gate de CÓDIGO con los 8 tests exigidos.

> En el R-PLAN condicionaste el merge a los 8 tests contra el replica set real + la saga O1 en ambos puntos de fallo. La EVIDENCIA trae el diff real + las salidas (incl. CI real-mongo).

## Qué hace (implementado)

1. **M-1** — `aprobar_presupuesto` deja el mes en `en_ejecucion` (no `definido`); `definido_por/at` + `presupuesto.definido` siguen siendo el registro. Test de Sprint 3 actualizado.
2. **Conciliación** (`app/cierre/service.py::conciliacion`, `POST /meses/{mes}/cierre/conciliacion`, `ciclo:cierre_operativo`) — compute-only. Por banco (M-3): `calculado(b) = reportado(b) + Σ signo(movimientos de b con fecha > fecha_reporte(b))`; banco con movimientos y SIN saldo reportado → `sin_dato` (regla 7). `C_M` = caja del libro = `saldo_inicial + Σ signo(tx)` EXCLUYENDO el rubro de sistema 'Ajuste de conciliación' (M-2/B-2). `diferencia = R_M − C_M`.
3. **Confirmar cierre** (`confirmar_cierre`, `POST …/cierre/confirmar`, `ciclo:confirmar_cierre` **solo Admin**, **Idempotency-Key**) — **TRANSACCIÓN MULTI-DOC (regla 8)**: re-ancla `saldo_inicial(M+1) := R_M` (guardando el previo en `MesControl.cierre_info`), crea el 'Ajuste de conciliación' en M+1 (fecha día-1, `MAN-`+ULID, **omitido si diferencia==0**, B-2), congela M `→cerrado`. `mes.cerrado` post-commit con **saga O1** (compensa borrando los artefactos del cierre FALLIDO — mismo patrón que la apertura certificada). Guardas: M+1 debe estar abierto (D2), diferencia ≤ umbral y sin `sin_dato` (D3), reintento `TransientTransactionError`.
4. **Reapertura** (`reabrir_mes`, `POST …/reabrir`, `ciclo:reabrir` **Admin + step-up MFA**) — **CONTRA-ASIENTO** (M-4, §2.2.2: la Transaccion NUNCA se borra) con `tipo_flujo` invertido + `revierte_id`, restaura `saldo_inicial(M+1)` al previo de `cierre_info`, M `→en_ejecucion`, `mes.reabierto`. LIFO: M+1 debe seguir editable.
5. **Modelo:** `MesControl.cierre_info {ancla_anterior_siguiente, diferencia, ajuste_tx_id}`; `Transaccion.revierte_id`.

## Fórmulas (para verificación, B-1)
- `reportado(b)` = `saldos_banco[b].saldo`. `calculado(b)` = reportado(b) + Σ signo(tx de b con fecha > fecha_reporte(b), excl. rubro ajuste).
- **R_M** = Σ_b calculado(b) (bancos con dato). En el dorado (fecha_reporte = fin de mes, sin movimientos posteriores) se reduce a Σ reportado(b) = 118.
- **C_M** = `saldo_inicial_caja + Σ signo(tx del mes, excl. rubro ajuste)` = 120 en el dorado. `diferencia = R_M − C_M = −2`.
- **Anti-doble-conteo:** la disponible de un mes = `saldo_inicial` (ya = R del cierre previo) + flujos EXCLUYENDO el rubro ajuste. Dorado: disponible(M+1) arranca en 118. Ambas vías = 118.

## Semántica preservada
Motor/acotar/aprobar intactos (salvo M-1: definido→en_ejecucion, con test actualizado). Índice `{vigente:true}` intacto. Histórico inmutable (regla 4): el ajuste/contra-asiento se crean en M+1 (editable), nunca en M cerrado; reapertura por contra-asiento, no delete. Dinero Decimal/string; `MAN-`+ULID (regla 5). Catálogo de eventos cerrado (mes.cerrado/mes.reabierto; sin inventar).

## Puntos a auditar con lupa (los 8 tests exigidos)
1. Dorado numérico (real-mongo): cuadra a 118 por ambas vías · 2. exclusión del rubro en la disponible · 3. contra-asiento + ancla restaurada · 4. doble cierre abortado (distinta key → 409) · 5. replay Idempotency-Key sin duplicar (1 solo evento) · 6-7. convergencia en abort de datos y en fallo de emit · 8. ajuste omitido si dif==0. Todos contra el replica set (regla 8) + saga O1.

## Evidencia (ver EVIDENCIA.md)
- **Local:** 298 passed / 34 skipped (los skipped = real-mongo). ruff limpio. Greps del protocolo en 0.
- **CI (PR #22):** ver EVIDENCIA (conclusión de todos los jobs, incl. `backend-real-mongo`).

## Pregunta al auditor
¿La transacción multi-doc del cierre (con el re-anclaje + ajuste en M+1), la conciliación por banco (M-3), el contra-asiento en reapertura (M-4) y la aprobación→en_ejecucion (M-1) están correctas y probadas para merge?
