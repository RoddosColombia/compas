# CERTIFICADO KIMI — sprint3-acotar-aprobar · I-PR1 (gate de código, PR #21)

**Resultado:** **9.5 / 10 — ✅ GO (merge autorizado)** · **Fecha:** 2026-07-21
**Rama:** `feat/acotar-aprobar` · commit `2277d32` (SIN mergear al certificar)
**CI:** PR #21 run 29883289498 — 6 jobs verdes (incl. `backend-real-mongo` 27 passed).

## Verificación contra lo exigido en el I-PLAN (todo probado)
- **Transacción multi-doc real (regla 8):** `with_transaction` fija monto_definido (null→sugerido) + MesControl→definido, atómico, reintento automático. `test_convergencia_abort_datos`: fallo dentro de la sesión → rollback total → reintento converge.
- **Convergencia en AMBOS puntos de fallo:** `test_convergencia_falla_emit_compensa`: commit OK + emit caído → compensación (mes→propuesto, null→null, la acotada 1.200.000 intacta, 0 eventos) → converge.
- **M-1 (flip en acotar):** sugerido→propuesto en el primer acotamiento; la compensación revierte el flip.
- **M-2 (saga O1 en acotar):** compensa ajuste + monto + estado si el emit falla.
- **Idempotency-Key:** payload distinto→422, en curso→409, replay sin re-ejecutar (un solo evento), key fallida no se quema.
- **RBAC §2.4:** acotar Directivo OK / Consulta 403; aprobar solo Admin (Financiero/Directivo/Consulta→403).
- **$group (Baja #4):** mismo E(i) que el loop; dorado 48/61/75M→84.033.333,33 pasa contra la agregación.
- **Modelo:** Ajuste.comentario ("renegociado"), creada_por, Baja #5.
- **D1** in-place implementada como se auditó (flip nit-12 → Sprint 4).

## Única Baja (HIGIENE, NO bloquea — recomendación explícita de Kimi)
`acotar` escribe línea + mes SIN transacción Mongo. La saga cubre el fallo del audit,
pero un crash ENTRE `ln.save()` y `mc.save()` dejaría el ajuste persistido y el mes sin
flip (inconsistencia benigna y **auto-sanable**: el siguiente acotar/aprobar la repara).
~4 líneas para darle a `acotar` la misma transacción que `aprobar` (y dividir sus tests:
guardas en mongomock, transacción en real-mongo). **Recomendado como higiene, no como
condición.**

## Declaración del auditor
La tabla §2.4 queda implementada y probada en acción (Directivo/Financiero acotan con saga
y flip a propuesto; Admin aprueba, solo él, con transacción multi-doc atómica e idempotencia
con replay). Regla 8 demostrada contra el replica set real; saga de auditoría en dos
conexiones demostrada en sus dos puntos de fallo. **GO — merge del PR #21 autorizado.**

Ciclo presupuestal completo en su columna: sugerido → propuesto → definido. Siguiente:
ejecución del mes (Sprint 4 — % ejecutado, conciliación por banco, tardías F-08).
