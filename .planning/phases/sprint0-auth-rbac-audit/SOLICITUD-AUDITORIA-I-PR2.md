# SOLICITUD DE AUDITORÍA — sprint0-auth-rbac-audit · I-PR2: auth (JWT endurecido)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-19
**Plan padre:** `PLAN.md` v3 (R-PLAN 9.1 GO) · **Base:** PR-1 audit base (cerrado 9.2 GO)
**Docs contrato:** Spec §1.1, §2.3, §4, §8.1 · **Rama:** `sprint0/sesion2-auth-rbac-audit`
**Nivel:** PR (código) — se adjunta `EVIDENCIA-I-PR2.md` (fuentes íntegras + salidas pytest/ruff).

## Qué hace (PR-2)
1. **`roles.py`** — `Role` (admin|directivo|financiero|consulta), cerrado (sin superadmin, Kimi H-1).
2. **`passwords.py`** — bcrypt `rounds=12`; política de longitud por rol (12 admin/directivo, 10 resto); `DUMMY_HASH` para anti-enumeración.
3. **`tokens.py`** — JWT `HS256` explícito, `leeway=30s`, `jti` uuid4 en access **y** refresh; claims `tv`/`type`/`family_id`; `decode_token(verify_exp=False)` para logout (H-6).
4. **`models.py`** — `User` + `RefreshSession` (Pydantic **strict**, validadores str→Role y anti-naive); índices: `email` único, `jti` único, `family_id`, TTL familia + denylist con `expireAfterSeconds:0`.
5. **`repository.py`** — Motor crudo (users/refresh_sessions/jwt_denylist/login_throttle); **rotación atómica** `findOneAndUpdate({jti,rotado:false,revocado:false}→rotado:true)`; `revoke_family`; denylist; rate limit por IP; normaliza datetimes a UTC al leer (mongomock).
6. **`service.py`** — login (backoff por cuenta + rate limit IP + anti-enumeración + eventos **fire-and-forget** O1); refresh (checks exp/idle 12h/máx 30d/tv/activo → rotación → reuso ⇒ `revoke_family` + `user.bloqueado{motivo:'reuso_refresh'}`); logout (deniega jti de access **y** refresh + revoca familia); authenticate (firma/denylist/activo/token_version por request).
7. **`router.py`** — `POST /api/v1/auth/login|refresh|logout`; cookie `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`; verificación de Origin fuera de dev.
8. **`deps.py`** — `get_current_user` (base del RBAC de PR-3). **`main.py`**: `configure_auth` en lifespan + CORS (origen exacto + `allow_credentials`).

## Semántica preservada / invariantes
- Respuesta de login **uniforme** (mismo 401 `_INVALID` para email desconocido, contraseña mala, bloqueado o inactivo) — sin oráculo de enumeración.
- Eventos de auth por el `emit_audit` **ya aprobado** (PR-1): `user.login`/`user.login_fallido`/`user.bloqueado`; **fire-and-forget** (O1: auth no cae si el canal de audit falla).
- Tiempos UTC-aware (A-04); Pydantic strict (r3); sin secretos en repo (r12); access en memoria, refresh en cookie (no localStorage).

## Puntos a auditar con lupa
1. **Rotación + reuso:** ¿`findOneAndUpdate` atómico + `revoke_family` cubre el reuso? Nota honesta: el **replay dentro del leeway NO está implementado en el servidor** — el reuso (incluido el doble-submit de 2 pestañas) revoca la familia; la mitigación es el single-flight del SPA. ¿Aceptable, o exiges replay server-side ya?
2. **token_version:** validado en `authenticate` (por request) **y** en `refresh`. ¿Algún camino que lo salte?
3. **Anti-enumeración:** ¿el path de email inexistente (verify contra `DUMMY_HASH`) iguala tiempo/forma? ¿El rate limit IP (429) antes de credenciales rompe la uniformidad de forma explotable?
4. **Backoff:** cuenta (5→15min, en `User`) + IP (`login_throttle`, ventana). ¿El desbloqueo por reactivación/tiempo y el reset en éxito están bien?
5. **Cookie/CSRF:** `Path=/api/v1/auth` + `SameSite=Strict` + verificación de Origin + CORS con origen exacto. ¿Suficiente para Fase 0–1?
6. **strict + reads:** `_awaken` normaliza naive→UTC al leer (mongomock ignora tz_aware); el validator sigue rechazando naive en construcción. ¿Correcto?

## Evidencia local (en `EVIDENCIA-I-PR2.md`)
- **pytest: 54 passed, 5 skipped**; `-m requires_real_mongo` → **5 failed** (concurrencia de rotación + inmutabilidad + dedup, para CI S3); `ruff`: limpio.
- Fuentes íntegras de `app/auth/*` + `main.py`/`config.py` (deltas) + los 5 `test_auth_*.py`.

## Pregunta al auditor
¿El diseño de sesiones de refresh (rotación atómica + reuso, sin replay server-side) y la uniformidad del login son suficientes para GO, o hay un hueco de seguridad que resolver antes del merge de PR-2?
