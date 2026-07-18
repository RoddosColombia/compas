# PLAN — Sprint 0 · Sesión 2: portar auth + RBAC + audit log desde SISMO-V3

**Fase:** `sprint0-auth-rbac-audit` · **Fecha:** 2026-07-18
**Base:** rama `sprint0/sesion2-auth-rbac-audit` (apilada sobre el esqueleto de Sesión 1)
**Contrato:** Spec §1.1 (User), §1.11 (AuditLog, catálogo de 30), §2.4 (autoridad), §4.1 (matriz permiso×endpoint), §5 DoD (#1 RBAC, #6 audit, #11 auth endurecida)
**Fuente a portar:** `../SISMO-V3/backend/app/` → `core/security.py`, `models/user.py`, `models/audit_log.py`, `routers/auth.py`, `schemas/auth.py`, `services/audit/`

## Objetivo
Traer de SISMO-V3 la estructura de autenticación JWT, RBAC por dependencia y audit log append-only, **adaptándola al Spec de COMPAS**, y **construir lo que SISMO no tiene** (token_version, denylist de refresh, rotación con detección de reuso). Documentar lo portado en `docs/PORTADO_DE_SISMO.md` (entregable para Iván).

## Qué se PORTA vs. qué se CONSTRUYE (hallazgo del escaneo de ../SISMO-V3)
- **Se porta (existe en SISMO):** patrón `get_current_user` + `require_role(*roles)` como dependencies FastAPI; `AuditLog` model append-only + router/service de auditoría; hashing bcrypt; estructura de `routers/auth.py`.
- **Se construye (NO existe en SISMO — nuevo del Spec COMPAS):** `token_version` en el claim y su validación por request; `jwt_denylist` (jti, TTL 30 días); rotación de refresh con **detección de reuso** (refresh ya rotado → revoca la familia); `require_permission` + config único de permisos derivado de la matriz §4.1; roles COMPAS `admin|directivo|financiero|consulta` (SISMO usa otros).

## Desglose en PRs (cada uno = gate de auditoría Kimi ≥ 9.0)

### PR-1 — Núcleo de auth (JWT + endurecimiento)
- `User` (Beanie Document): `email` único, `password_hash` (bcrypt), `rol`, `token_version` (default 1), `activo`, timestamps `now_bogota()`.
- Password: bcrypt; política de longitud mínima (12 admin/directivo, 10 resto); backoff por cuenta (5 fallos → 15 min). **HIBP y MFA TOTP quedan para Sprint 0b** (fuera de esta sesión).
- JWT: access 15 min (memoria SPA), refresh en cookie HttpOnly/Secure/SameSite=Strict path `/auth`; `token_version` en el claim, validado en cada request → desactivar usuario o cambiar contraseña revoca todo.
- Endpoints: `POST /api/v1/auth/login`, `/auth/refresh` (rotación + detección de reuso → revoca familia), `/auth/logout` (jti a `jwt_denylist`).
- `jwt_denylist`: índice `(jti)` único + TTL 30 días.
- **TDD:** tests de login OK/fallido, token_version revoca, logout revoca, rotación detecta reuso. Los que dependen del índice TTL/único → `@requires_real_mongo` (mongomock no soporta TTL ni unicidad real).

### PR-2 — RBAC por dependencia (matriz §4.1)
- `Role(StrEnum)`: `admin | directivo | financiero | consulta`.
- `get_current_user`, `require_role(*roles)`, `require_permission("<cap>")`.
- **Config único de permisos** derivado de la matriz §4.1 (una sola fuente; el navbar del frontend se derivará de aquí en su momento).
- **DoD #1:** tests NEGATIVOS por rol (incl. export de Consulta denegado).

### PR-3 — Audit log append-only (catálogo de 30) + inmutabilidad en CI
- `AuditLog` (append-only), catálogo **cerrado de 30 eventos** (§1.11: 29 + `extracto.cargado` de CR-001) como enum; helper `emit_audit(...)`.
- Rol Mongo custom `audit_writer` (insert+find, sin update/remove) — documentado en RUNBOOK §2.
- **DoD #6:** test automatizado en CI de que `update`/`remove` sobre `audit_log` **FALLA** → `@requires_real_mongo` (permisos de BD reales; correr contra mongod en CI del Sprint 0/0b).

## Reglas innegociables aplicables
- Pydantic `strict=True` en todos los schemas nuevos (regla 3).
- `now_bogota()` en toda marca temporal (regla 2).
- Sin secretos en el repo: `JWT_SECRET` por env (regla 12).
- Audit append-only (regla 4); catálogo cerrado de 30 (regla 11) — no inventar eventos.
- Nada de localStorage para tokens (access en memoria, refresh cookie HttpOnly).

## Fuera de alcance (para no violar el "no scope creep")
MFA TOTP + códigos de respaldo + step-up (Sprint 0b) · HIBP k-anonymity (0b) · cabeceras de seguridad/CSP (0b) · workflows de CI (Sesión 3) · aplicación de `require_permission` a endpoints de negocio que aún no existen.

## DoD cubierto por esta sesión
- Parcial #1 (RBAC + tests negativos), parcial #6 (audit inmutable + test CI), parcial #11 (auth endurecida: logout revoca, token_version, backoff). MFA de #11 queda en 0b.

## Riesgos
1. **Deriva de semántica al portar** (SISMO usa otros roles y no tiene token_version) → mitigación: construir el endurecimiento fresco con TDD, no adaptar a ciegas; documentar en PORTADO_DE_SISMO.md.
2. **Tests que mongomock no cubre** (TTL, unicidad, permisos de BD) → marcados `@requires_real_mongo`; el CI del Sprint 0/0b debe levantar un mongod real.
3. **Orden de branch:** esta rama se apila sobre Sesión 1 (aún no mergeada a main).

## Gate
Auditoría Kimi del PLAN (esta) ≥ 9.0 → construir. Luego PR-1, PR-2, PR-3, cada uno con su gate Kimi ≥ 9.0 antes de merge.
