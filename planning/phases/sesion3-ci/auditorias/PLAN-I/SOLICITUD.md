# SOLICITUD DE AUDITORÍA — sesion3-ci · PLAN-I

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-19
**Base:** `main` (Sprint 0b completo: PR-1/2/3 GO, DoD #11/#12 cerrados).
**Plan padre:** `planning/phases/sesion3-ci/PLAN.md`
**Docs:** DoD #8 · CLAUDE.md (gitleaks bloquea; `@requires_real_mongo`) · RUNBOOK §9 · STACK §2/§7
**Nivel:** PLAN (pre-código). Es **prerrequisito duro del Gate G1**.

## Qué se propone
CI en GitHub Actions que **corre de verdad** lo que hoy se saltea y bloquea lo inseguro:
1. `ci.yml`: jobs **backend** (ruff + pytest mongomock + cobertura), **backend-real-mongo**
   (servicio `mongo:7` con auth → crea rol `audit_writer`/usuario `compas_audit` + índices →
   `pytest -m requires_real_mongo`: índices únicos, **inmutabilidad de audit_log**, concurrencia),
   **frontend** (biome + `tsc`+`vite build` + vitest), **pip-audit**, **gitleaks**.
2. `dependabot.yml`: pip + npm + github-actions.
3. Soporte: `pip-audit` en dev-deps; branch protection documentado en RUNBOOK §9.

## Puntos a auditar con lupa
1. **Inmutabilidad real de `audit_log` en CI (DoD #6):** ¿el enfoque de levantar mongod con
   auth + `create_audit_role.py` + correr el test con el usuario restringido `compas_audit`
   (update/remove FALLA) es correcto y reproducible en Actions? ¿O hay un camino más simple?
2. **`@requires_real_mongo` completos:** ¿el job cubre los 12 (rubros/config/auth únicos, dedup
   parcial, concurrencia de rotación) con un mongod de servicio?
3. **gitleaks bloqueante** con allowlist SOLO para fixtures anonimizados: ¿bien acotado (regla 12)?
4. **Alcance:** ¿es correcto dejar k6 (DoD #9) y Playwright para después, o algo de eso es
   prerrequisito de G1?

## Decisiones declaradas
- **C-1** Un solo PR crítico para toda la CI (con su propio gate Kimi de código), en vez de
  fragmentar. ¿Aceptable?
- **C-2** mongod de CI con **auth** (no anónimo) para poder probar la restricción de privilegios
  del canal de auditoría; el usuario admin del servicio solo existe dentro del runner efímero.
- **C-3** El deploy real (Render/Vercel) NO se toca aquí; solo se documenta el branch protection.

## Evidencia
Sin código aún (auditoría de plan). Estado base: Sprint 0b en `main`, **172 tests** verdes
(9 `@requires_real_mongo` hoy en skip — justo lo que esta sesión pone a correr de verdad),
ruff limpio.

## Pregunta al auditor
¿El plan de CI cubre lo que el Gate G1 exige (suite real + escáneres bloqueantes) y el enfoque
de la inmutabilidad de audit en CI es sólido, o hay un riesgo a resolver antes de construir?
