# CERTIFICADO KIMI — sprint3-motor PR1-I: motor del sugerido (§1.4.1, F-07)

**Resultado:** **9.2 / 10 — ✅ GO (merge autorizado)** · **Fecha:** 2026-07-21
**Ronda:** I (inicial) · **Umbral:** ≥ 9.0 · **Aprobador:** Kimi (auditor adversarial externo)
**PDF fuente:** `COMPAS_Certificado_I-PR1_Sprint3_MotorSugerido_2026-07-21.pdf`
**Merge:** commit `7f835be` a `main` (fast-forward desde `feat/motor-sugerido`).

## Veredicto

El corazón del ciclo es correcto y está verificado dos veces. La fórmula §1.4.1 como
función PURA de Decimal (HALF_EVEN) con el test dorado reproduciendo el ejemplo del
Spec celda a celda — E=48/61/75M, crec 15% → prom_3m=61.333.333,33,
tendencia=13.500.000,00, sugerido=84.033.333,33 — tanto en el motor puro como
end-to-end por la API (3 meses cerrados con transacciones que suman 48M, 61M, 75M →
la línea sale idéntica). La nota CEO #1 ya tiene su demostración técnica antes de la demo.

También fiel al resto del contrato: componentes persistidos para verificación celda a
celda, versionado F-06 con índice único parcial {vigente:true}, monto_definido null
hasta aprobar, compromisos_programados fuera de la fórmula (regla 10), modo_calculo
default historico, exclusión de rubros de sistema (test), no-regeneración 409 (test),
E(i) solo meses 'cerrado' (test: en_ejecucion no cuenta), RBAC fiel a §2.4, crec_pct
Decimal exacto con 422 en negativos.

## Respuesta a las 4 decisiones declaradas

1. **Generalización n<3:** aceptada — se reduce exactamente a la oficial en n=3, honesta
   (marca historia_incompleta, no adivina), con tests en los 4 escenarios.
2. **Generación sin evento:** aceptada, con precisión: el §2.2.5 exige que el recálculo
   "quede auditado" cuando exista.
3. **Alcance:** correcto — el crec_pct global de este PR ES literalmente la acción
   "Aplicar % global del mes" del Spec.
4. **D-4 (sugerido negativo):** **clamp a 0** — un presupuesto negativo leería como bug a
   los directivos; la tendencia decreciente queda visible en tendencia_mes sin clamp.
   → APLICADO en commit `97af7a7` (+2 tests).

## 5 Bajas a incorporar (ninguna bloquea el merge)

1. `creada_por` en la línea (el actor de la generación hoy se descarta).
2. Ruta de recálculo antes de las tardías de Sprint 4 (§2.2.5: líneas nunca aprobadas +
   evento — recomienda el flag `forzar_recalculo`).
3. `Ajuste.comentario` antes del acotamiento (US-02: "renegociado").
4. Agregación `$group` para `_ejecutado` (1 query vs 90; importa para el RNF del dashboard).
5. Nit de fechas incoherentes en el helper de tests.

## Siguiente

Acotamiento (monto_definido + ajustes) y aprobación (→definido, transacción multi-doc
regla 8) — ahí Kimi auditará la tabla de autoridad §2.4 en acción (Directivo acota, Admin
aprueba, flip atómico de vigente) y la demo nota CEO #1 celda a celda contra el Excel
congelado.
