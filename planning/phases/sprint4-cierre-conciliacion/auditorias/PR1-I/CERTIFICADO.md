# CERTIFICADO KIMI — sprint4-cierre-conciliacion · I-PR1 (gate de código, PR #22)

**Resultado:** **9.4 / 10 — ✅ GO para merge** · **Fecha:** 2026-07-21
**Rama:** `feat/cierre-conciliacion` · commit `6f57c9a` · **CI PR #22: 6/6 jobs verdes**
**PDF fuente:** `COMPAS_Certificado_I-PR1_Sprint4_Cierre_2026-07-21.footnote.docx`

## Los 8 tests exigidos: 8/8 verdes contra el replica set real (backend-real-mongo 34 passed)
1-2. Dorado cuadra a 118 por ambas vías + exclusión del rubro ✔ (dif −2, ajuste egreso 2 en jul día-1, ancla=118, disponible=118).
3. Contra-asiento + ancla restaurada ✔ (original intacto §2.2.2, contra con revierte_id invertido valor 2).
4-5. Doble cierre 409 · replay sin duplicar ✔ (1 solo evento en ambos).
6-7. Convergencia en ambos puntos de fallo ✔ (abort datos → rollback total; emit caído → compensación; ambos convergen).
8. Ajuste omitido si dif==0 ✔.

## Nota del auditor (refutación aceptada, B-1 del R-PLAN)
Kimi sugirió `R_M := Σ reportado(b)`; el equipo implementó `R_M := Σ calculado(b)` (ancla
bancaria + movimientos posteriores a fecha_reporte) y **su lectura es la correcta** —
verificado con el caso de reporte a mitad de mes (−35 correcto vs −5 con la fórmula de
Kimi). Refutación aceptada. El `continue` antes de `bancos_con_mov.add` (el ajuste nunca
contamina `sin_dato` en meses siguientes) está bien ordenado.

## 3 Bajas no bloqueantes
- **B-1 (operativa, previa a G3):** el rubro 'Ajuste de conciliación' debe quedar en la
  semilla de código (33→34) y sembrado en base viva; cargar `UMBRAL_DIF_BANCO_CIERRE`.
  Los guardas son fail-loud (500 explícito, cero riesgo silencioso) → no bloquea el merge;
  aplicar el precedente S0B-05 antes de la demo G3 con julio real.
- **B-2 (hardening, ~3 líneas):** guardas de estado fuera de la transacción (TOCTOU) —
  releer `mc.estado` dentro de la sesión. Backport opcional junto a S4-00.
- **B-3 (test nit):** fijar con un test que `POST /reabrir` exige step-up (admin sin
  `mfa_at` reciente → 401).

**Veredicto:** "Autorizo el merge de PR #22." Siguiente: S4-00 (higiene), Vista Control,
tardías F-08 y CR-001 — cada una con su gate.
