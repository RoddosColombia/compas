# SOLICITUD DE AUDITORÍA — sprint0-auth-rbac-audit · R-PR2: auth (re-presentación)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-19
**Ronda:** R-PR2 · **Previa:** I-PR2 7.8/10 NO-GO (1 Crítica + 2 Altas + 6 Medias + 5 Bajas)
**Rama:** `sprint0/sesion2-auth-rbac-audit` · **Evidencia:** `EVIDENCIA-R-PR2.md` (diff `ce2cfab..f103a2d` + salidas)
**Nivel:** PR (código) — se adjunta el **diff de líneas cambiadas**.

## Resolución de los hallazgos (todos aplicados)
| # | Sev | Corrección |
|---|---|---|
| L4 | Crítica | `scripts/create_auth_indexes.py` idempotente (itera `AUTH_INDEXES`) + test `@requires_real_mongo` de existencia. TTL de `login_throttle`/refresh/denylist con `expireAfterSeconds:0`. |
| L2 | Alta | `client_ip()` lee `CF-Connecting-IP` (Cloudflare) + `--proxy-headers` en render.yaml + nota RUNBOOK (restringir origen a Cloudflare). |
| L6 | Alta | Al expirar `locked_until`, `reset_failed_login` **antes** de evaluar → no re-bloquea con 1 intento/15 min. |
| L1 | Media | `verify_password` SIEMPRE una vez (sin cortocircuito del `or`) → sin oráculo de timing. |
| L3 | Media | Fail-fast de `JWT_SECRET` (≥32 B) fuera de dev en el lifespan (patrón C-01). |
| L5 | Media | Normalización de email en **escritura** (`field_validator` del modelo). |
| H1 | Media | `reset_ip_attempts` en login exitoso → una ráfaga legítima no se auto-bloquea. |
| H3 | Baja | `_init_sentry` (guardado, `send_default_pii=False` + scrubbing) + `capture_exception` en `_safe_emit`. |
| H2 | Baja | `ip` en metadata de `user.login_fallido` / `user.bloqueado`. |
| H5 | Baja | `user.bloqueado` solo en la transición exacta (`== max`); `revoke_family` devuelve count → evento de reuso solo en transición. |
| L7 | Media (no bloqueaba) | Reuso **estricto** sin replay server-side: registrado en errata **E-8** con compromiso (Sprint 0b/1). |

## Tests nuevos (Kimi H4)
idle 12 h, máx 30 d, expiración de lock (L6), `verify_origin` 403 fuera de dev, `tv`⇒refresh 401, logout con access expirado, atributo Secure, fail-fast de JWT (L3), reset del cupo IP (H1), existencia de índices (`@requires_real_mongo`, L4).

## Autoauditoría (antes de enviar)
Revisé explícitamente las realidades de producción que Kimi señaló como clase: IP tras proxy, fail-fast de secretos, creadores de índices, timing, y cobertura TDD de bordes/defensas. Todo cerrado o registrado.

## Evidencia local
- `pytest`: **63 passed, 6 skipped**; `-m requires_real_mongo` → **6 failed** (concurrencia/inmutabilidad/dedup/índices → CI S3); `ruff`: limpio.

## Pregunta al auditor
¿El diff cierra la Crítica + 2 Altas + Medias + Bajas para autorizar el merge de PR-2 y habilitar el gate de PR-3 (RBAC)?
