# SOLICITUD DE AUDITORÍA — sprint4-vista-control · I-PR1: Vista Control

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-22
**Docs contrato:** Spec §0.1, §1.4, §17 (cálculo en backend), §4.1 (RBAC); PRD M2; CLAUDE.md reglas 1, 2, 3, 9. DoD #3.
**Rama / PR:** `feat/vista-control` / **#23** · commit `37426e4` · **SIN mergear — gate pre-merge**
**Antecedente:** GO PLAN I 9.3 (sin hallazgos M/A). Este es el gate de CÓDIGO con los 8 tests + las 3 Bajas.

## Qué hace (implementado)
**`GET /meses/{mes}/control`** (`app/control/service.py::control` + router, RBAC `dashboard:leer`, solo `en_ejecucion`/`cerrado` → si no, 409). READ-ONLY (sin escrituras/transacciones/eventos).
- Por rubro (línea `PresupuestoLinea` vigente), agrupado en los 5 grupos (orden del enum, rubros por `orden`): `definido`, `ejecutado` (Σ egresos del rubro, vía `$group`), `disponible` (=definido−ejecutado), `pct_ejecutado` (Decimal 2dec HALF_EVEN, **string**, B-2; `null` si definido==0), `semaforo`.
- **Semáforo (B-1):** calculado sobre el pct CUANTIZADO — verde `≤90`, amarillo `90<pct≤100`, rojo `>100`. `definido==0`: gasto→rojo, sin gasto→verde.
- Subtotal por grupo + total (Σ). `caja_disponible` = `saldo_inicial + Σ signo(tx)` excluyendo SOLO 'Ajuste de conciliación' (reusa `_caja_libro` del cierre; 'Por clasificar' cuenta).
- `sin_presupuesto` (B-3): egresos en rubros NO de sistema sin línea vigente (informativo, regla 7).

## Las 3 Bajas del PLAN — resueltas
- **B-1** semáforo sobre pct cuantizado — test de bordes 90.00→verde, 90.01→amarillo, 100.00→amarillo, 100.01→rojo.
- **B-2** `pct_ejecutado` string — test de serialización.
- **B-3** fila `sin_presupuesto` informativa — test dedicado (aparece rubro sin línea; 'Por clasificar' de sistema NO aparece).

## Semántica preservada
Solo se agrega un router de lectura; nada existente cambia. Motor/acotar/aprobar/cierre intactos. Dinero Decimal/string; Pydantic strict; sin eventos (lectura). Ejecutado = misma E(i) del motor §1.4.1 (comparable celda a celda, DoD #3).

## Puntos a auditar con lupa (los 8 tests)
1. Dorado de celda (definido 1M / ejec 900k → disp 100k, pct 90.00, verde) · 2. bordes del semáforo · 3. caja con el ajuste presente (excluido) y 'Por clasificar' incluido · 4. guardas (409 no-en_ejecucion, 404 inexistente) · 5. RBAC 4 roles (200) · 6. equivalencia $group (suma de varias tx) · 7. linealidad de subtotales (Σ disp = Σ def − Σ ejec) · 8. serialización (strings).

## Evidencia (ver EVIDENCIA.md)
- **Local:** 309 passed / 34 skipped. ruff limpio. Greps del protocolo en 0.
- **CI (PR #23):** ver EVIDENCIA (conclusión de los jobs).

## Pregunta al auditor
¿El cálculo de Vista Control (% ejecutado, disponible, semáforo con bordes cuantizados, caja con exclusión del ajuste, sin_presupuesto) es correcto y está probado para merge?
