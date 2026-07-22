# RESPUESTA KIMI — sprint3-acotar-aprobar · I-PLAN

**Resultado:** **9.2 / 10 — ✅ GO** (umbral superado, con 2 incorporaciones requeridas) · **Fecha:** 2026-07-21
**PDF fuente:** `COMPAS_Auditoria_I-PLAN_Sprint3_AcotarAprobar_2026-07-21.pdf`
**Camino:** M-1 + M-2 al plan (2 párrafos, **sin re-auditoría del plan**) → construir con TDD.

## Veredicto de las 4 decisiones declaradas

1. **D1 — Primera aprobación in-place, sin flip:** CORRECTO. US-02 "versión 1 vigente congelada" + §2.2.5 "cambiar un presupuesto definido crea versión nueva". El flip (nit-12) se ejerce al modificar una línea YA aprobada (Sprint 4). No se exige versión "aprobada" al nacer.
2. **D2 — Sin acotar → monto_definido = monto_sugerido:** CORRECTO. "Sugerir, no decidir": aprobar la propuesta ES la decisión humana (registrada con definido_por/at). Exigir acotar las ~30 haría inútil el motor.
3. **D3 — Saga de auditoría por conexiones separadas:** CORRECTA (con extensión M-2). Compensación que preserva acotados legítimos + reconciliación por Idempotency-Key + job referencial. Patrón correcto y simétrico con la apertura certificada.
4. **D4 — Sin verbo `proponer`:** aceptable CON la corrección M-1.

## Incorporaciones requeridas (al plan, sin re-auditoría)

**M-1 — `PATCH acotar` transiciona `sugerido → propuesto` al primer acotamiento.**
El estado `propuesto` ES "los directivos ajustan cifra por cifra" (M2). Sin la transición, un mes con ajustes seguiría mostrando `sugerido` → inconsistencia de estado. Una línea en el servicio + test (mes `sugerido` → tras PATCH queda `propuesto`); el verbo explícito queda innecesario.

**M-2 — `acotar` también es O1 fail-closed (saga), no solo `aprobar`.**
`presupuesto.acotado` es una decisión financiera con autor (la vara de medición del mes) — clase F-21, no puede perderse en silencio. Compensación trivial (1 documento): revertir el ajuste añadido y restaurar el `monto_definido` previo si el emit falla.

## Notas sobre las Bajas / tests
- La equivalencia del `$group` se prueba con el **mismo test dorado end-to-end** (48/61/75M → 84.033.333,33).
- El test **"aprobación interrumpida converge"** debe cubrir los **dos puntos de fallo distintos**: (a) abort de la transacción de datos, (b) fallo del emit → compensación.

## En el gate de código Kimi auditará
La transacción real contra el replica set (regla 8), el test de convergencia en ambos puntos de fallo, el flip de estado en acotar (M-1), y la saga completa (M-2 incluida).
