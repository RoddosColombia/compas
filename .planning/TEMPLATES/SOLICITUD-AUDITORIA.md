# SOLICITUD DE AUDITORÍA — <FASE> <RONDA>[-PR<N>]: <título corto>

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** YYYY-MM-DD
**Plan padre:** `.planning/phases/<fase>/PLAN.md` · **Docs contrato:** Spec §X, PRD MX
**Rama / PR:** `<rama>` / #<n> (si aplica)

## Qué hace
<Descripción precisa de lo entregado. Numerar los cambios. Referenciar archivos.>

## Cambios de valores esperados (verificados al peso)
<Solo si aplica: tabla caso → valor viejo → valor nuevo, ya verificados en tests.>

| Caso | Antes | Después |
|---|---|---|
|  |  |  |

## Semántica preservada (NO cambia en este PR)
<Qué se mantiene intacto: histórico inmutable, reglas de dinero, contratos existentes.>

## Puntos a auditar con lupa
1. <El punto más riesgoso — pedir escrutinio explícito.>
2. <Casos borde, migraciones de semántica, seguridad.>

## Evidencia local
- pytest: <N passed / N skipped>
- ruff: <estado> · build frontend: <estado> · (mypy si aplica)
- Reglas innegociables verificadas: <Decimal, TZ, Pydantic strict, RUN_SCHEDULER, audit append-only…>

## Cumplimiento del DoD / reglas de CLAUDE.md
<Qué puntos del DoD (Spec §5) o reglas innegociables cubre este entregable.>
