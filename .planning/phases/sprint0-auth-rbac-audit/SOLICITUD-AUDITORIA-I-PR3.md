# SOLICITUD DE AUDITORÍA — sprint0-auth-rbac-audit · I-PR3: RBAC

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-19
**Plan padre:** `PLAN.md` v3 · **Base:** PR-1 (9.2) + PR-2 (9.3), ambos GO
**Docs contrato:** Spec §4.1 (matriz permiso×endpoint), §2.4 (autoridad del ciclo), DoD #1
**Rama:** `sprint0/sesion2-auth-rbac-audit` · **Nivel:** PR (código) — `EVIDENCIA-I-PR3.md` adjunta fuentes + salidas.

## Qué hace (PR-3 — último de la Sesión 2)
1. **`permissions.py`** — `PERMISSIONS`: **config único** (fuente de verdad) que codifica la matriz **§4.1** + la autoridad **§2.4** como capacidades `ciclo:*` (que manda sobre §4.1). `has_permission(rol, cap)`, `capabilities_for(rol)`, `CAPABILITIES`.
2. **`deps.py`** — `require_permission(cap)` para endpoints de negocio; `require_role(*roles)` **solo** para administración de identidad (/users) — prohibido en negocio (Kimi H-1, sin 5º rol).
3. **`router.py`** — `GET /api/v1/auth/capabilities` → `{rol, capabilities}` del usuario; el navbar del frontend renderiza desde aquí (M13.1 #6: prohibido mapear rol→ítems en el front).

## Puntos a auditar con lupa (los que anunciaste)
1. **Config ≡ §4.1/§2.4:** ¿la matriz codificada coincide EXACTO? (test la congela). ¿`ciclo:aprobar` solo Admin, `ciclo:cierre_operativo` Fin+Admin, `confirmar_cierre`/`reabrir`/`config` solo Admin?
2. **Capacidades `ciclo:*`:** ¿reflejan §2.4 (que prevalece sobre §4.1)? `reabrir`/`config` llevan nota de step-up MFA (Sprint 0b).
3. **`GET /auth/capabilities`:** ¿es la única fuente para el navbar? ¿filtra bien por rol?
4. **Routers solo-test:** los endpoints `/_test/*` se montan SOLO en el test, nunca en `create_app` (no llegan a prod).
5. **Completitud triple + guardián:** (a) guardián que escanea `require_permission("X")` en `app/` y exige `X∈config`; (b) config ≡ canónica congelada; (c) sin huérfanas y todos los roles cubiertos.
6. **`require_role` restringido:** solo para /users; negocio usa `require_permission`.

## Evidencia local (en `EVIDENCIA-I-PR3.md`)
- **pytest: 80 passed, 6 skipped**; `-m requires_real_mongo` → **6 failed** (CI S3); `ruff`: limpio.
- Negativos por rol (DoD #1): Consulta 403 en export; solo-admin 403 para consulta/financiero, 200 admin; sin token 401; capabilities de Consulta = `["dashboard:leer"]`.

## Autoauditoría (antes de enviar)
Revisé: fuente única sin drift (guardián de decoradores), §2.4 prevalece, routers de prueba no llegan a prod, negativos por rol reales, `require_role` acotado. Sin business endpoints aún → `require_permission` se aplicará a ellos en sus sprints (el guardián los cubrirá).

## Pregunta al auditor
¿El config único + `require_permission` + capabilities + la completitud triple cierran el RBAC de la matriz §4.1/§2.4 para GO, cerrando así la Sesión 2 completa?
