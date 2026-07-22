# CERTIFICADO KIMI — sprint4-cierre-conciliacion · R-PLAN

**Resultado:** **9.4 / 10 — ✅ GO para construir con TDD** · **Fecha:** 2026-07-21
**PDF fuente:** `COMPAS_Certificado_R-PLAN_Sprint4_Cierre_2026-07-21.footnote.docx`
Los 4 hallazgos de la ronda I (8.5) cerrados correctamente, sin re-diseño.

## Verificación
- **M-1** ✔ aprobación → en_ejecucion (definido_por/at + `presupuesto.definido`, sin evento nuevo; `definido` transitorio).
- **M-2 (núcleo)** ✔ Kimi reprodujo el cálculo: ledger `100+(50−30)+(−2)=118=R_M` y disponible arranca en 118 sin doble conteo. Contrapruebas: ajuste en disponible → 116≠R_M; sin re-ancla → 117≠118. Re-ancla sancionada §1.3/F-14, previo guardado.
- **M-3** ✔ ancla por banco (reportado @ fecha + movimientos posteriores), "sin dato" = regla 7.
- **M-4** ✔ contra-asiento (§2.2.2), neto del rubro = 0 por ciclo, ancla restaurada, LIFO por "M+1 editable", Admin + step-up.

## 2 Bajas no bloqueantes (a incorporar en el código, verificadas en el gate I-PR1)
- **B-1:** fijar en código `R_M := Σ reportado(b)`, `C_M := Σ calculado(b)` (la frase "Σ de esos saldos" era ambigua).
- **B-2:** rubro de sistema 'Ajuste de conciliación' declarado en la semilla (excluido de la disponible por `rubro_id`) y **omitir el ajuste si diferencia == 0**.

## Condición para el merge (gate de código I-PR1)
Los 8 tests listados contra el **replica set real** (regla 8) + saga O1 en ambos puntos de fallo (como PR #21):
1. Ejemplo numérico como **test dorado** (cuadra a 118 por ambas vías).
2. Exclusión del rubro 'Ajuste de conciliación' en la disponible.
3. Contra-asiento + ancla restaurada al reabrir.
4. Doble cierre abortado (idempotencia).
5. Replay Idempotency-Key sin duplicar.
6. Transacción multi-doc atómica contra replica set.
7. Saga O1 — fallo de emit → compensación.
8. Convergencia tras interrupción.

**Veredicto:** "la matemática está correcta — construyan."
