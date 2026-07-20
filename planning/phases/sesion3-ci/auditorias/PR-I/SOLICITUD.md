# SOLICITUD DE AUDITORÍA — sesion3-ci · PR-I (código)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-19
**Base:** `main` + rama `sesion3-ci` · **PR:** #6
**Plan padre:** `planning/phases/sesion3-ci/PLAN.md` (PLAN-I 9.1 GO; P-1/P-2 incorporadas)
**Docs:** DoD #8 · CLAUDE.md (gitleaks/`@requires_real_mongo`) · RUNBOOK §9
**Nivel:** PR (código). Evidencia (código + verificación local + **run real de Actions**) en `EVIDENCIA.md`.

## Qué hace el PR
1. **`.github/workflows/ci.yml`** (jobs, en PR y push a main):
   - `backend`: `ruff check` + `ruff format --check` + `pytest` (mongomock) + cobertura (solo reporte).
   - `backend-real-mongo`: servicio `mongo:7` con auth → `wait-for-mongo` → `create_audit_role.py`
     (rol `audit_writer`/usuario `compas_audit`) → **`pytest -m requires_real_mongo`**.
   - `frontend`: `npm ci` + `biome check` + `tsc`+`vite build` + `vitest run`.
   - `pip-audit --strict` (bloqueante) · `gitleaks` (binario pineado + `.gitleaks.toml` allowlist estrecha).
   - Actions **pineadas a SHA** (supply chain, Kimi §4).
2. **`@requires_real_mongo` implementados de verdad** (Kimi P-1), ya NO placeholders:
   - `test_audit_immutable.py`: como `compas_audit`, `update`/`delete` → `OperationFailure 13`;
     `insert`/`find` → OK (positivo, DoD #6).
   - `test_auth_indexes.py`: índices auth existen + `email` único se aplica + TTL configurado.
   - `test_auth_concurrency.py`: dos rotaciones simultáneas → exactamente UNA gana.
   - Dominio (rubro/config únicos) ya reales desde PR-1. Dedup parcial → `skip` (Sprint 1).
3. `.github/dependabot.yml` (pip/npm/actions) · `.gitattributes` (LF determinista) · `pip-audit` en dev-deps.

## Puntos a auditar con lupa
1. **Inmutabilidad de audit en CI real**: ¿el job `backend-real-mongo` prueba de verdad DoD #6
   (negativo update/remove + positivo insert/find con el usuario restringido)?
2. **required checks / branch protection** (P-2): documentados en RUNBOOK §9 con la lista explícita.
3. **gitleaks**: allowlist estrecha (solo credenciales efímeras de CI), no rutas amplias (regla 12).
4. **Supply chain**: actions pineadas a SHA; pip-audit `--strict` con proceso de excepciones.

## Decisiones declaradas
- **G-1** El job de real-mongo usa `mongo:7` con auth + `create_audit_role.py` (mismo script del
  operador); el usuario admin es efímero del runner (sin secreto en el repo).
- **G-2** gitleaks se instala como **binario pineado** (v8.18.4) en vez de la action, para evitar el
  requisito de licencia de `gitleaks-action` en repos de organización.
- **G-3** Cobertura solo-reporte (sin umbral): el DoD no pide meta de cobertura.

## Evidencia (en EVIDENCIA.md)
Código de `ci.yml`/`dependabot.yml`/`.gitleaks.toml` + los tests real-mongo implementados;
**verificación local** contra `mongo:7` docker con auth (**10 passed, 1 skipped**); y el **run
real de GitHub Actions del PR #6 verde** (todos los jobs) — adjuntado cuando GitHub se recupere
del incidente en curso.

## Pregunta al auditor
¿La CI (real-mongo bloqueante + escáneres + Dependabot + supply-chain) cierra DoD #8 y satisface
el prerrequisito de CI del Gate G1?
