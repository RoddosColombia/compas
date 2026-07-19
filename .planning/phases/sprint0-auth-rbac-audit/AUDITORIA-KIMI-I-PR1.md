# AUDITORÍA KIMI — sprint0-auth-rbac-audit · I-PR1: audit base

**Calificación: 8.9/10 provisional — NO-GO POR EVIDENCIA** (umbral ≥ 9.0)
**Fecha:** 2026-07-18 · **Rama:** `sprint0/sesion2-auth-rbac-audit` · **Nivel:** PR (código)
**Motivo del NO-GO:** solo se envió la SOLICITUD (descripción), no el diff/archivos. "La
evidencia manda sobre la descripción." El diseño se dio por CONFORME; nota final estimada ≥ 9.2
si el código sostiene los claims y se aplica C-01.

## Cambios exigidos / observaciones — ESTADO
| Ítem | Sev | Estado |
|---|---|---|
| **C-01** Fail-fast fuera de dev (no warning) si falta `MONGODB_URI_AUDIT` | Media | ✅ Aplicado en `app/main.py` + tests `test_audit_failfast.py` |
| **O1** Política de fallo de `emit_audit` ante error de BD | Baja | ✅ Documentada (fail-closed; ciclo → rollback; no críticos → try/except+Sentry) |
| **O2** Tipo de `entidad_id` (str vs ObjectId) | Baja | ✅ Fijado **str** (forma canónica) + comentario |
| **O3** Creación del índice forense (quién/cuándo) | Baja | ✅ En `scripts/create_audit_role.py` (setup admin, idempotente) |
| **Evidencia** Adjuntar código + salidas de pytest | — | ✅ `EVIDENCIA-I-PR1.md` + `docs/audits/PAQUETE-AUDITORIA-I-PR1.pdf` |

## Verificaciones que Kimi hará contra el código (todas cubiertas)
- enum ≡ lista canónica §4 (30, sin typos, formato dominio.acción) — `test_audit_events.py`.
- `emit_audit` inserta solo por el cliente dedicado y rechaza eventos fuera del catálogo (ValueError) — `test_audit_emit.py`.
- modelo strict + `extra="forbid"`, timestamp aware, `entidad_id` str — `models.py`.
- lifespan con fail-fast fuera de dev (C-01) — `main.py` + `test_audit_failfast.py`.
- script de rol idempotente (rol+usuario insert+find; índice forense) — `create_audit_role.py`.
- markers **fallan, no skip** — salida `pytest -m requires_real_mongo` (4 failed) en la evidencia.

## Veredicto
NO-GO por evidencia → re-presentar con el **PAQUETE-AUDITORIA-I-PR1.pdf** (SOLICITUD + EVIDENCIA con
el código y las salidas) + C-01/O1/O2/O3 aplicados. Verificación el mismo día; estimación ≥ 9.2.

---
> Respuesta textual de Kimi (sin editar):

Auditoría I-PR1 — Sprint 0 · PR-1: audit base
Veredicto: NO-GO por evidencia — 8.9/10 provisional (umbral ≥ 9.0)
[Informe completo archivado por el CEO. Objeto recibido: solo la SOLICITUD (descripción), no el
diff/archivos. Diseño conforme (inmutabilidad, A-04, respuestas a los 5 puntos de lupa). Exigido:
C-01 fail-fast fuera de dev. Observaciones O1 (política de fallo de emit_audit), O2 (tipo entidad_id),
O3 (creación del índice). Lista canónica de 30 eventos entregada para el diff. Paquete de evidencia a
adjuntar: los 3 módulos + core/time + main + script de rol + los 4 tests + conftest + .env.example +
RUNBOOK §2/§8 + salida de pytest -m requires_real_mongo con los 4 fallos. Estimación ≥ 9.2 con C-01.]
