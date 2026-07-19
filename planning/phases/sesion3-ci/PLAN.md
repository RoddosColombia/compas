# PLAN — Sesión 3: CI/CD (prerrequisito duro del Gate G1)

**Fase:** `sesion3-ci` · **Fecha:** 2026-07-19 · **Base:** `main` (Sprint 0b completo, `8aed406`)
**Contrato:** DoD #8 (suite verde en CI con pip-audit/gitleaks/Dependabot) · CLAUDE.md (gitleaks bloquea; `@requires_real_mongo`) · Spec §2.3/§2.2.6 · RUNBOOK §9 · STACK §2/§7
**Fuente a portar:** CI de `../SISMO-V3` si existe (verificar con grep; adaptar, no copiar).

## Objetivo
Montar la CI que **corre de verdad** lo que hoy se saltea y bloquea lo inseguro, para
habilitar el **Gate G1**: (1) suite backend completa **incluyendo los 12 `@requires_real_mongo`**
contra un mongod real con auth; (2) `pip-audit` + `gitleaks` + `Dependabot`; (3) lint+build+test
del frontend. Todo verde y bloqueante en cada PR a `main`.

## Desglose (un PR crítico, gate Kimi ≥ 9.0)

### 1. `.github/workflows/ci.yml` — disparado en PR y push a `main`
- **job `backend`** (ubuntu, Python 3.12): `pip install -r backend/requirements-dev.txt`;
  `ruff check` + `ruff format --check`; `pytest` (rápidos, mongomock) con cobertura.
- **job `backend-real-mongo`** (servicio `mongo:7` con auth):
  - Levanta mongod con usuario admin; corre `scripts/create_audit_role.py` (rol `audit_writer`
    + usuario `compas_audit`) y `scripts/create_auth_indexes.py` + (nuevo) creación de índices
    de dominio; exporta `COMPAS_TEST_MONGO_URI`.
  - `pytest -m requires_real_mongo`: valida **índices únicos** (rubros, configuracion, auth,
    dedup parcial), **inmutabilidad de `audit_log`** (update/remove FALLA con el usuario
    `compas_audit` — DoD #6) y **concurrencia** de rotación de refresh.
  - *Punto a auditar con lupa:* cómo se prueba la inmutabilidad real (usuario restringido) en CI.
- **job `frontend`** (node 20): `npm ci` (usa `package-lock.json`); `biome check`;
  `tsc -b && vite build`; `vitest run`.
- **job `pip-audit`**: falla ante CVE conocido en dependencias de runtime.
- **job `gitleaks`**: `gitleaks/gitleaks-action`; bloquea si hay secreto. `.gitleaks.toml` con
  allowlist SOLO para fixtures bancarios anonimizados (regla 12).

### 2. `.github/dependabot.yml`
Ecosistemas: `pip` (`/backend`), `npm` (`/frontend`), `github-actions`. Cadencia semanal.

### 3. Ajustes menores de soporte
- Añadir `pip-audit` a `requirements-dev.txt`.
- Documentar en RUNBOOK §9 el **branch protection** de `main` (CI verde obligatorio antes de
  merge; producción solo por tag `v*` + reviewer — verificar el bloqueo).

## Fuera de alcance (declarado, con destino)
- **k6 de carga** (DoD #9): Sprint posterior. · **Playwright e2e** (flujo crítico): Sprint posterior.
- **Deploy real** a Render/Vercel: ya definido en `render.yaml`; aquí solo se verifica el gate de
  branch protection, no se toca el pipeline de deploy.

## Reglas / DoD
Cierra **DoD #8**. Habilita los controles de CI que exige el **Gate G1**. No relaja ninguna
regla innegociable; gitleaks y pip-audit son bloqueantes. mongod de CI con auth (no anónimo).

## Gate
Auditoría Kimi de **este PLAN** ≥ 9.0 → construir el PR de CI → gate Kimi del PR ≥ 9.0 →
queda listo el prerrequisito de CI para el **Gate G1** (junto con §9 del RUNBOOK y A-01/CR-003).
