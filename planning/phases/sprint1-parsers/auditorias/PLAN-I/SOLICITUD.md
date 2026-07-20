# SOLICITUD DE AUDITORÍA — sprint1-parsers · PLAN-I: Datos (parser Bancolombia + esquema + dedup)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-20
**Plan padre:** `planning/phases/sprint1-parsers/PLAN.md`
**Docs contrato:** Spec §1.5 (Transaccion), §1.6/§1.6.1 (CargaBancaria + parsers), §2.2/§2.3
(integridad e índices) · PRD M2/M3 · PLAN_TRABAJO F2/Sprint 1 · DoD #4/#7/#8 · CLAUDE.md (reglas 1,4,5,6,7,8,11)
**Nivel:** PLAN (aún no hay código). Fuente a portar: `../SISMO-V2/backend/services/bank_parsers.py`.

## Qué se somete
El plan del Sprint 1 (Datos), scopeado al alcance oficial del PLAN_TRABAJO: **solo parser
Bancolombia** + esquema canónico (Transaccion/CargaBancaria) + dedup (índice único parcial + manuales
`MAN-`) + ciclo de vida de cargas (fallida/reaper/reproceso, F-02) + POST manual. **BBVA y Global66
quedan explícitamente para Sprint 2.** Desglose en 4 PRs (3 críticos con gate Kimi).

## Decisiones declaradas (brainstorming en el PLAN)
- **A — `id_banco` de Bancolombia:** el parser de SISMO NO produce `id_banco`; el Spec lo exige "de
  extracto". Se trata como **precondición**: congelar el layout real (F-51) primero; si hay ID nativo
  se usa (A1); si no, CR aprobado por el CEO para una clave determinista (A2). **No se adivina.**
- **B — Decimal al leer .xlsx:** `Decimal(str(cell))`, locale es-CO explícito (SISMO asumía formato
  US y `float`); nunca `float()` sobre montos (regla 1).
- **C — fila ambigua:** todo-o-nada por carga; ≥1 error ⇒ `fallida` + `motivo_fallo`, nada insertado
  (regla 7 + escenario Spec §300). SISMO hacía `continue` silencioso.
- **D — orden de PRs:** esquema+dedup → parser (transform puro, TDD) → ciclo de cargas
  (transacción multi-doc) → pantalla.

## Semántica preservada (no cambia)
Histórico inmutable; `audit_log` append-only; catálogo cerrado de eventos (usa `carga.completada`/
`carga.fallida`, no inventa); Decimal; TZ Bogotá; Pydantic strict; `RUN_SCHEDULER=false` en web
(reaper solo en worker).

## Puntos a auditar con lupa
1. **Decisión A (`id_banco`)** — ¿es correcto tratarlo como precondición/CR en vez de derivarlo a
   ciegas? ¿La opción A2 (clave determinista) tiene riesgo de colisión de dos movimientos legítimos
   idénticos el mismo día, y está bien exigir CR + CEO para ella?
2. **Dedup (DoD #4)** — índice único parcial `(banco, id_banco)` con
   `partialFilterExpression {id_banco:{$type:'string'}}` + `MAN-`+ULID: ¿garantiza coexistencia de
   manuales y 0 duplicados en solape sin colisión?
3. **Transacción multi-documento (DoD #7)** en finalización de carga — ¿el todo-o-nada + `insertMany
   ordered=False` con conteo de `DuplicateKeyError` es consistente y idempotente?
4. **Alcance** — ¿el plan evita sobre-alcance (BBVA/Global66/clasificación/mini-migración son Sprint
   2) y no deja huecos del Sprint 1?
5. **Fixtures/secretos** — anonimización determinista + verificación + gitleaks; reales solo en S3
   (reglas 12/§1.6.1): ¿suficiente?

## Evidencia local
- Nivel PLAN: sin código aún. Fuente real de referencia adjunta: `bank_parsers.py` de SISMO-V2
  (parser Bancolombia a adaptar) + data dictionary del Spec (§1.5/§1.6) citado al peso.
- Dependencias duras declaradas: Gate G1 GO, fixtures Día 0 anonimizados, Atlas aprovisionado,
  Decisión A resuelta antes de PR-2.

## Cumplimiento del DoD / reglas de CLAUDE.md
Cubre DoD #4 (dedup), #7 (transacción multi-doc) y aporta al #8 (tests real-mongo en CI). Respeta
reglas 1 (Decimal), 4 (histórico inmutable), 5 (dedup en BD), 6 (scheduler solo worker), 7 (parsers
transforman), 8 (transacción multi-doc), 11 (catálogo cerrado de eventos).

## Pregunta al auditor
¿El plan del Sprint 1 es apto para construir (GO ≥ 9.0), con la Decisión A como precondición y sin
sobre-alcance, listo para arrancar por PR-1 apenas cierre el Gate G1?
