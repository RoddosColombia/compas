# SOLICITUD DE AUDITORÍA — sprint0-auth-rbac-audit · I-PLAN: portar auth + RBAC + audit log

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-18
**Plan padre:** `planning/phases/sprint0-auth-rbac-audit/PLAN.md`
**Docs contrato:** Spec §1.1, §1.11, §2.4, §4.1, §5 (DoD #1/#6/#11) · PRD M2
**Rama:** `sprint0/sesion2-auth-rbac-audit` (apilada sobre `sprint0/sesion1-esqueleto`)
**Nivel:** auditoría de PLAN (antes de construir). No hay código aún.

## Qué se propone construir
Portar de `../SISMO-V3/backend/app/` la estructura de auth JWT, RBAC por dependencia y
audit log append-only, adaptada al Spec de COMPAS, y **construir** lo que SISMO no tiene.
Desglose en 3 PRs, cada uno con su propio gate Kimi:

1. **PR-1 Auth:** `User` (token_version, bcrypt, activo), JWT access 15m + refresh cookie
   HttpOnly, `token_version` validado por request, login/refresh/logout, **rotación de
   refresh con detección de reuso** (revoca familia), `jwt_denylist` (jti, TTL 30 días),
   backoff 5 fallos → 15 min.
2. **PR-2 RBAC:** roles `admin|directivo|financiero|consulta`, `get_current_user`,
   `require_role`, `require_permission` + **config único** derivado de la matriz §4.1;
   tests negativos por rol (DoD #1).
3. **PR-3 Audit:** `AuditLog` append-only, **catálogo cerrado de 30 eventos** (§1.11),
   `emit_audit`, rol Mongo `audit_writer`, **test CI de que update/remove FALLA** (DoD #6).

## Hallazgo del escaneo de la fuente (verificado, no asumido)
- SISMO **SÍ** tiene: `core/security.py` con `get_current_user`/`require_role`, `AuditLog`
  model + router/service, bcrypt. Se porta el patrón.
- SISMO **NO** tiene: `token_version`, `jwt_denylist`/`jti`, rotación con detección de reuso
  (grep sobre `token_version|denylist|jti|reuse|rotation` → 0 en auth). Esto se **construye**
  fresco con TDD, no se adapta a ciegas.

## Semántica preservada (invariantes del proyecto)
- Pydantic `strict=True` en todo schema nuevo; `now_bogota()` en toda marca temporal.
- Audit **append-only** (regla 4); catálogo **cerrado de 30** (regla 11) — no inventar eventos.
- Access token solo en memoria de la SPA; refresh en cookie HttpOnly (nada en localStorage).
- `JWT_SECRET` por env; ningún secreto en el repo.
- La tabla de autoridad §2.4 manda sobre cualquier otra redacción para las capacidades del ciclo.

## Puntos a auditar con lupa
1. **Rotación + detección de reuso:** ¿el modelo de "familia" de refresh y la revocación al
   detectar reuso es correcto y sin condición de carrera? ¿TTL de denylist = 30 días (vida máx
   del refresh) es coherente?
2. **token_version:** validarlo en cada request, ¿es suficiente para revocación inmediata al
   desactivar usuario / cambiar contraseña? ¿algún camino que lo salte?
3. **Matriz §4.1 como fuente única:** ¿el diseño de `require_permission` + config evita drift
   entre backend y navbar? ¿cubre "export:*" y la denegación a Consulta (DoD #1)?
4. **Inmutabilidad del audit:** ¿el test de que update/remove FALLA debe correr contra Mongo
   real (permisos de BD)? ¿basta el rol `audit_writer` o hace falta también $jsonSchema?
5. **Alcance:** ¿es correcto diferir MFA/HIBP a Sprint 0b, o algún punto del DoD #11 exige
   MFA ya en esta sesión?
6. **Frontera mongomock/real:** ¿los tests marcados `@requires_real_mongo` (TTL, unicidad,
   permisos) están bien identificados? ¿algún otro que mongomock falsee?

## Evidencia local
- Aún no hay código (auditoría de PLAN). El esqueleto base (Sesión 1) está verde:
  pytest 9 passed/1 skipped, ruff limpio, build frontend OK, npm audit 0 vulnerabilidades
  (commit `61048ac`).
- El marker `@requires_real_mongo` ya existe en `backend/tests/conftest.py` para exactamente
  estos casos.

## Cumplimiento del DoD / reglas de CLAUDE.md
Cubre parcialmente DoD #1 (RBAC + negativos), #6 (audit inmutable + CI), #11 (auth endurecida
sin MFA). Respeta reglas 2, 3, 4, 11, 12 y la prohibición de localStorage para tokens.

## Pregunta explícita al auditor
¿El desglose en PR-1/2/3 y la línea porta-vs-construye son correctos y seguros para arrancar,
o hay un riesgo de seguridad/semántica que deba resolverse en el PLAN antes de escribir código?
