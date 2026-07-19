# SOLICITUD DE AUDITORÍA — sprint0-auth-rbac-audit · I-PR1: audit base

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-18
**Plan padre:** `planning/phases/sprint0-auth-rbac-audit/PLAN.md` (v3, R-PLAN 9.1 GO)
**Docs contrato:** Spec §1.11 (catálogo), §2.3 (índice audit_log), §2.2.6 · DoD #6 · CR-001
**Rama:** `sprint0/sesion2-auth-rbac-audit` (sobre `61048ac`) · **Nivel:** PR (código)

## Qué hace (PR-1 — audit base, primero por A-05)
1. **Catálogo cerrado de 30 eventos** (`app/audit/events.py`, `AuditEvento` StrEnum): 29 del Spec §1.11 + `extracto.cargado` (CR-001). `CATALOGO_EVENTOS` (frozenset) para tests de completitud.
2. **`AuditLog`** (`app/audit/models.py`): Pydantic **strict**, `extra="forbid"` — `evento, entidad, entidad_id, actor_id, metadata, timestamp`. `timestamp` UTC-aware por `now_utc()`. Constantes `AUDIT_COLLECTION` + `AUDIT_INDEXES` (índice forense Spec §2.3).
3. **`emit_audit`** (`app/audit/service.py`): valida el evento contra el catálogo (`AuditEvento(evento)` → `ValueError` si no existe, regla 11) e inserta por la **conexión dedicada** `configure_audit(client)`.
4. **Inmutabilidad por privilegios (DoD #6):** conexión `compas_audit` (rol `audit_writer` insert+find) = 2ª cadena `MONGODB_URI_AUDIT` a la **misma** db `compas`; cableada en el lifespan (`app/main.py`) con fallback a la conexión general SOLO en dev + `logger.warning` fuera de dev. Script idempotente `scripts/create_audit_role.py`. RUNBOOK §2/§8 y `.env.example` actualizados.
5. **`now_utc()`** (`app/core/time.py`): convención A-04 (persistencia/TTL/claims UTC-aware; `now_bogota()` solo presentación).

## Semántica preservada
- Catálogo **cerrado**: `emit_audit` rechaza cualquier evento fuera de los 30 (regla 11).
- Audit **append-only**: `emit_audit` solo hace `insert_one`; no hay update/remove en el código. La inmutabilidad dura la imponen los privilegios de BD (test @requires_real_mongo, CI S3).
- `extracto.cargado` ≠ `carga.completada` (CR-001); emisor real `POST /extractos` en Sprint 4.
- Pydantic strict (regla 3); UTC-aware (regla A-04); sin secretos en repo (regla 12).

## Puntos a auditar con lupa
1. **Separación de privilegios:** ¿el diseño `configure_audit(audit_client)` + fallback en dev es correcto? ¿El `logger.warning` fuera de dev es suficiente, o debería **fallar** el arranque si falta `MONGODB_URI_AUDIT` en staging/producción?
2. **Serialización para BSON:** `emit_audit` inserta `payload["evento"]=doc.evento.value` (str) y `timestamp` como `datetime` aware. ¿Correcto para Mongo real (no el enum de Python, fecha como BSON date)?
3. **Catálogo:** ¿los 30 valores coinciden EXACTO con Spec §1.11 (29) + CR-001? ¿algún nombre mal escrito?
4. **Diferimiento a CI:** los 3 tests de inmutabilidad son `@requires_real_mongo` y **fallan (no skip)** si se piden sin mongod con auth. ¿Aceptas el diferimiento a la Sesión 3 (decisión CEO) con el script de rol entregado?
5. **`AuditLog` Pydantic vs Beanie:** se hizo Pydantic plano (Beanie 2.0 no deja instanciar Document sin `init_beanie`); las lecturas por Beanie se difieren. ¿Correcto para el alcance de PR-1?

## Evidencia local
- **pytest: 17 passed, 4 skipped** (3 inmutabilidad + 1 dedup placeholder, todos `@requires_real_mongo`). Con `-m requires_real_mongo` esos 4 **fallan** (no skip), como exige Kimi Baja-2.
- **ruff: All checks passed** (incl. UP017 `datetime.UTC`, import order).
- Tests nuevos: `test_audit_events.py` (catálogo = 30, `extracto.cargado`≠`carga.completada`, formato dominio.acción), `test_audit_emit.py` (doc bien formado, timestamp UTC-aware, evento inválido → ValueError, sin configurar → RuntimeError), `test_audit_immutable.py` (@requires_real_mongo, CI S3).
- Reglas verificadas: strict=True, UTC-aware, append-only en código, catálogo cerrado, `JWT_SECRET`/`MONGODB_URI_AUDIT` por env.

## DoD / CLAUDE.md
Avanza DoD #6 (audit + inmutabilidad; el test real corre en CI S3). Respeta reglas 2, 3, 4, 11, 12.

## Pregunta al auditor
¿El diseño de inmutabilidad (privilegios + test diferido + script de rol) y el emit por conexión dedicada son suficientes para aprobar PR-1, o exiges que el arranque **falle** sin `MONGODB_URI_AUDIT` fuera de dev?
