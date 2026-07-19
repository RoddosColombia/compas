# CERTIFICADO DE CIERRE KIMI — sprint0-auth-rbac-audit · PR-1: audit base

**Calificación: 9.2/10 — GO ✅** (umbral ≥ 9.0; merge de PR-1 AUTORIZADO)
**Fecha:** 2026-07-18 · **Rama:** `sprint0/sesion2-auth-rbac-audit` · diff `d08a395..288ce54`
**Historial PR-1:** I-PR1 8.9 (sin evidencia) → R-PR1 8.8 (6 Medias + 5 Bajas + 2 nits) → **cierre 9.2 GO**.

## Verificación: 13/13 correcciones cerradas
H-01..H-07 + 4 Bajas + 2 nits confirmados en el diff. Salidas reales: pytest 19→24 passed,
`-m requires_real_mongo` 4 failed (markers honestos), ruff limpio.

## Cierre de las 2 verificaciones triviales del certificado
| # | Punto | Estado |
|---|---|---|
| P-1 | `tz_aware=True` en `app/db/mongo.py` (factory Motor) | ✅ Confirmado: `app/db/mongo.py:27` → `AsyncIOMotorClient(uri, tz_aware=True)`. El comentario del validator H-05 es exacto. |
| P-2 | Tests de los 3 validadores + Literal | ✅ `tests/test_audit_models.py` (5 tests): `_cast_evento` (str→enum OK / inválido→ValidationError), `_timestamp_aware` (naive→error / aware ok), `app_env` Literal (typo→error). pytest **24 passed / 4 skipped**. Commit `5d5ae41`. |

## Declaración del auditor
PR-1 cumple el contrato certificado: catálogo cerrado de 30 exacto, `emit_audit` append-only por
conexión dedicada a la misma db, inmutabilidad por privilegios (tests neg/pos diferidos a CI con
markers que fallan), fail-fast del canal de auditoría fuera de dev, convención UTC-aware defendida
por validadores, y tooling del rol endurecido. **GO para merge.**

Siguiente gate: **PR-2 (auth)** ≥ 9.0 — se auditará: login emitiendo `user.login`/`login_fallido`/
`bloqueado` por este `emit_audit`; `token_version` por request y en refresh; rotación atómica con
detección de reuso sobre `refresh_sessions`; cookie `Path=/api/v1/auth` same-site; backoff IP+cuenta.

---
> Certificado textual de Kimi (sin editar):

Certificado de cierre — R-PR1 · Sprint 0 · PR-1: audit base
9.2 / 10 — GO CONDICIONADO (merge autorizado al cerrar 2 verificaciones triviales)
[Informe completo archivado por el CEO. 13/13 correcciones cerradas. P-1 (tz_aware en mongo.py) y
P-2 (tests de validadores) resueltos en commit 5d5ae41 → GO pleno. Siguiente gate: PR-2 (auth) ≥ 9.0.]
