# AUDITORÍA KIMI — sprint0-auth-rbac-audit · I-PLAN: portar auth + RBAC + audit log

**Calificación: 7.8/10 — NO-GO condicionado ❌** (umbral ≥ 9.0)
**Fecha:** 2026-07-18 · **PR:** — · **Rama:** `sprint0/sesion2-auth-rbac-audit`
**Autorización de merge:** N/A (auditoría de plan; sin código)
**Método Kimi:** 2 verificadores (seguridad auth 8.2/10; coherencia/proceso 7.0/10), contra baseline v1.1.2 y OWASP/RFC 6265/7519/MongoDB.

## Alcance auditado
PLAN.md + SOLICITUD-AUDITORIA-I-PLAN.md de la fase (nivel plan, pre-código).

## Resultado
6 Altas + 11 Medias + 6 Bajas. Todas son ediciones de texto al PLAN (2–4 h); lo único
nuevo de diseño es especificar la colección `refresh_sessions` y reordenar los PRs.
Estimación de Kimi con las correcciones aplicadas: **≥ 9.2/10**.

## Hallazgos Altos (bloquean el GO)
| # | Hallazgo | Estado |
|---|---|---|
| A-01 | Cookie `Path=/auth` no matchea `/api/v1/auth` (RFC 6265) → refresh roto 100% | RESUELTO en PLAN v2 (Path=/api/v1/auth) + errata Spec §4 |
| A-02 | Rotación sin atomicidad → la carrera anula la detección de reuso | RESUELTO (findOneAndUpdate atómico + single-flight + leeway + test de concurrencia) |
| A-03 | Sin estado server-side del refresh (familia, idle 12h, máx 30d) | RESUELTO (colección `refresh_sessions`) |
| A-04 | Datetimes naive → TTL/exp desfasados −5h (access 15m → ~5h) | RESUELTO (convención UTC-aware; naive prohibido por lint) |
| A-05 | Orden PR-1↔PR-3: login necesita `emit_audit` 2 PRs después | RESUELTO (reorden: PR-1 audit → PR-2 auth → PR-3 RBAC) |
| A-06 | Catálogo 29 vs 30 sin reconciliar en el .docx certificado | RESUELTO (30 es normativo por CR-001 + CLAUDE.md + tracker DoD#6; errata .docx registrada en CR-002) |

## Medias / Bajas
Incorporadas todas al PLAN v2 (ver tabla de resolución en `SOLICITUD-AUDITORIA-R-PLAN.md`):
capabilities endpoint, test de completitud del config de permisos, normalización/anti-enumeración
de email, rate limit IP+cuenta, conexión `compas_audit` dedicada + test positivo, `require_permission`
único en negocio, checklist cripto (HS256 explícito, leeway, jti uuid4, bcrypt rounds=12), etc.

## Veredicto
NO-GO condicionado. Aplicar correcciones al PLAN + tramitar errata documental (CR-002) →
re-presentar en ronda R (verificación de cierre puntual).

---
> Respuesta textual de Kimi (sin editar):

Auditoría I-PLAN — Sprint 0 · Sesión 2: portar auth + RBAC + audit log
Veredicto: NO-GO condicionado — 7.8 / 10 (umbral ≥ 9.0)
RODDOS S.A.S. · 18 de julio de 2026 · Nivel: auditoría de PLAN (pre-código)

[Informe completo archivado por el CEO. Resumen de ejes: Seguridad 8.2/10 (4 Altas, 6 Medias,
4 Bajas); Coherencia/Proceso 7.0/10 (2 Altas, 5 Medias, 2 Bajas); Global 7.8/10.
Hallazgos estructurales: A-01 (cookie Path), A-02 (atomicidad rotación), A-03 (refresh_sessions),
A-04 (datetimes UTC), A-05 (orden de PRs), A-06 (catálogo 29/30 + errata baseline).
Camino al GO: aplicar 6 Altas + 11 Medias, tramitar errata documental, re-presentar (≥9.2 estimado).
Lo que está BIEN y se preserva: línea porta-vs-construye verificada con grep, endurecimiento
fresco con TDD, disciplina de scope, frontera mongomock/real, dirección de inmutabilidad,
reglas innegociables citadas.]
