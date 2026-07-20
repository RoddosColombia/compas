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

### 1.b Implementar (no solo ejecutar) los `@requires_real_mongo` (Kimi P-1)
Hoy son `raise AssertionError("Pendiente CI Sesión 3")` a propósito (fallan, no skip). Esta
sesión **los implementa de verdad**, o el job `-m requires_real_mongo` nace ROJO. Lista exacta:
- **Inmutabilidad de `audit_log` (3, `test_audit_immutable.py`)**: como app user, `update`/`remove`
  FALLAN (code 13); como `compas_audit`, `insert`/`find` OK (el positivo es imprescindible: un rol
  roto sin `insert` pasaría el negativo y el audit moriría en silencio).
- **Existencia de índices auth (1, `test_auth_indexes.py`)**: tras `create_auth_indexes.py`, los
  índices únicos/TTL existen.
- **Concurrencia de rotación (1, `test_auth_concurrency.py`)**: dos refresh simultáneos → EXACTAMENTE
  una rotación gana (los demás → reuso → familia revocada).
- **Unicidad de dominio (3, `test_domain_indexes.py`)**: ya IMPLEMENTADOS y reales desde PR-1
  (rubro `(grupo,nombre)`, config `(clave,vigente_desde)`) — el job solo los corre.
- **Dedup parcial `(banco,id_banco)` (`test_real_mongo_marker.py`)**: es de **Sprint 1** (necesita
  `Transaccion`). Decisión: se **EXCLUYE explícitamente** del job de la Sesión 3 (el placeholder se
  convierte en `skip` marcado "Sprint 1", NO en fallo) y se implementa con `Transaccion` en Sprint 1.
  Así la CI de esta sesión queda verde sin construir dominio de Sprint 1.

### 2. `.github/dependabot.yml`
Ecosistemas: `pip` (`/backend`), `npm` (`/frontend`), `github-actions`. Cadencia semanal.

### 3. Branch protection con required checks EXPLÍCITOS (Kimi P-2)
En RUNBOOK §9, la lista nombrada de **required status checks** de `main` (no "documentado" a secas):
`backend`, **`backend-real-mongo`** (bloqueante — sin él, DoD #6 se saltaría con un admin merge),
`frontend`, `pip-audit`, `gitleaks`. Más: CI verde obligatorio antes de merge; producción solo por
tag `v*` + reviewer (F-32) — verificar el bloqueo.

### 4. Ajustes menores de soporte
- Añadir `pip-audit` a `requirements-dev.txt`.
- **Actions pineadas a SHA completo** (`actions/checkout@<sha>`) — higiene de supply chain.
- **pip-audit**: proceso de excepciones (lista de ignores pineada y revisada por PR), bloqueante
  pero con criterio ante una vuln transitiva de baja severidad.
- **Cobertura**: solo reporte, SIN umbral (el DoD no pide meta de cobertura — no inventarla).
- `COMPAS_TEST_MONGO_URI` se **construye en el job** (no es secreto de repo), como ya lo lee
  `test_domain_indexes.py`.
- Paso **`wait-for-mongo`** (loop de ping / `health-cmd` del servicio) antes del script de rol:
  los servicios de Actions arrancan asíncronos.

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
