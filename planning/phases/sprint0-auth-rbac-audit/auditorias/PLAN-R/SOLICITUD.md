# SOLICITUD DE AUDITORÍA — sprint0-auth-rbac-audit · R-PLAN: re-presentación del plan corregido

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-18
**Ronda:** R (re-auditoría) · **Previa:** I-PLAN 7.8/10 NO-GO (6 Altas, 11 Medias, 6 Bajas)
**Plan padre:** `planning/phases/sprint0-auth-rbac-audit/PLAN.md` (v2)
**Errata:** `docs/COMPAS_ERRATA_PENDIENTE_v1_1_3.md` (CR-002, pendiente firma CEO)
**Nivel:** auditoría de PLAN (pre-código). Sigue sin haber código.

## Propósito
Re-presentar el PLAN v2 con las 6 Altas + 11 Medias + 6 Bajas resueltas (todas eran texto,
salvo especificar `refresh_sessions` y reordenar los PRs). Estimación previa del auditor con
correcciones: ≥ 9.2/10.

## Resolución de los hallazgos Altos
| # | Hallazgo | Cómo se resolvió en el PLAN v2 |
|---|---|---|
| A-01 | Cookie `Path=/auth` no matchea `/api/v1/auth` | PR-2: `Path=/api/v1/auth` + `Max-Age=2592000` + test del Set-Cookie. Errata E-2. |
| A-02 | Rotación sin atomicidad | PR-2: `findOneAndUpdate({jti,rotado:false}→{rotado:true})`; `null`⇒reuso⇒revoca familia; single-flight + leeway 10s; test de concurrencia @requires_real_mongo. |
| A-03 | Sin estado server-side del refresh | PR-2: colección `refresh_sessions {jti,usuario_id,family_id,family_created_at,ultimo_uso,rotado,revocado}`, TTL +30d; refresh valida exp/idle 12h/máx 30d/tv/activo. |
| A-04 | Datetimes naive → TTL/exp −5h | Convención de fase: persistencia/TTL/claims **UTC aware**; `now_bogota()` solo presentación; naive prohibido por lint. Errata E-4. |
| A-05 | Orden PR-1↔PR-3 (login sin emit_audit) | Reorden: **PR-1 audit base → PR-2 auth (emite eventos) → PR-3 RBAC**. |
| A-06 | Catálogo 29 vs 30 en el .docx | 30 ya normativo (CR-001 + CLAUDE.md + tracker DoD#6); `extracto.cargado` ≠ `carga.completada`; errata .docx en CR-002/E-1. |

## Resolución de las Medias (11)
M-01 refresh valida tv+activo, bump atómico, sin caché de usuario · M-02 logout deniega jti de
access+refresh, identifica sesión por cookie · M-03 `api.compas.roddos.com` + CORS exacto +
Allow-Credentials + Origin en mutaciones (E-3) · M-04 email `strip().lower()` + login uniforme +
bcrypt dummy (anti-enumeración) · M-05 rate limit **IP + cuenta** + reset + desbloqueo admin +
alerta · M-06 conexión `compas_audit` dedicada + app sin update/remove + $jsonSchema + test
positivo · M-07 `GET /api/v1/auth/capabilities` (navbar sin mapa rol→ítems) · M-08 routers de
prueba solo-test para negativos (incl. Consulta sin `export:*`) · M-09 §2.4 como `ciclo:*`;
`require_permission` único en negocio, `require_role` prohibido · M-10 test triple de completitud
del config · M-11 mini-diseño de `refresh_sessions` + TTL denylist por tipo (access 15m / refresh 30d).

## Resolución de las Bajas (6)
Reuso→`user.bloqueado {motivo:'reuso_refresh'}` (sin evento nuevo) · DoD#6 test entregado
`@requires_real_mongo`, CI lo recoge en Sesión 3, mongod de CI con auth, markers **fallan** (no
skip) · bcrypt `rounds=12` + test de latencia <1s · checklist cripto (HS256 explícito, leeway 30s,
jti uuid4 en ambos tokens, JWT_SECRET ≥32B/entorno) · sección de riesgos ampliada · base de rama
fijada en `61048ac` + rebase si se mueve.

## Puntos a auditar con lupa (ronda R)
1. **Atomicidad de la rotación:** ¿el `findOneAndUpdate` + leeway + single-flight cierra de
   verdad la carrera sin auto-revocar familias legítimas (2 pestañas)?
2. **UTC-aware:** ¿la convención cubre TODOS los puntos (TTL, exp/iat, idempotency, denylist) sin
   contradecir la regla 2 (Bogotá para dominio/UI)?
3. **Inmutabilidad del audit:** ¿el par test negativo+positivo con conexión dedicada `compas_audit`
   es suficiente, o falta algo del modelo de privilegios?
4. **Orden de PRs:** ¿PR-1 audit → PR-2 auth → PR-3 RBAC elimina la contaminación de scope?
5. **Errata como CR-002:** ¿es aceptable folder la reconciliación 29→30 y cookie Path en el próximo
   re-baseline (CR-001 ya lo previó como v1.2), construyendo con 30 desde ya, o Kimi exige la
   firma de la errata ANTES del merge de PR-1?

## Evidencia local
- Sin código aún (auditoría de plan). Esqueleto base verde (commit `61048ac`): pytest 9/1skip,
  ruff limpio, build+vitest 3/3, npm audit 0 vulns.
- Marker `@requires_real_mongo` ya en `backend/tests/conftest.py`.

## Cumplimiento del DoD / reglas de CLAUDE.md
Cubre parcial DoD #1/#6/#11 (MFA a 0b). Respeta reglas 2 (precisada UTC/presentación), 3, 4, 11, 12
y la prohibición de localStorage para tokens.
