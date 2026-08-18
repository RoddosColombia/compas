# CR-CFO-2 — Eventos de auditoría del vínculo Telegram (allowlist)

- **Fecha:** 2026-08-17 · **GO:** CEO (diseño con gate Kimi 9.3 GO — B-1/B-2/B-3
  aplicados; el código de esta pieza es gate crítico aparte, ver abajo).
- **Regla 11:** el catálogo de eventos es cerrado; este CR lo amplía 64 → 66.
- **Contexto:** FABS inc3 Pieza B — canal Telegram (`docs/superpowers/specs/2026-08-17-fabs-inc3b-telegram-design.md`).
  Precedente directo: CR-CFO-1 (`planning/phases/fabs-inc2/CR-CFO-1.md`, catálogo 62→64).

## Eventos nuevos

- `cfo.vinculo_creado` — se emite cuando un admin vincula un `telegram_id` a un
  `user_id` (alta en la allowlist del canal Telegram de FABS). `entidad="cfo"`,
  `actor_id`=admin autenticado real, `metadata={telegram_id, user_id}`.
- `cfo.vinculo_eliminado` — se emite al desvincular (baja del allowlist,
  `repositorio.eliminar_vinculo`). `actor_id`=admin, `metadata={telegram_id}`.

Ambos se emiten desde el endpoint admin (`POST` / `DELETE /api/v1/cfo/telegram/vinculos`),
protegido con `require_role(Role.admin)`. El vínculo es **uno-a-uno** (único en
`telegram_id` Y en `user_id` — decisión B-3 del spec): no existe un estado
activo/inactivo que "reactivar", así que no hay evento espejo tipo
`.editado {activo: false→true}` como en rubro/regla/obligación — vincular de
nuevo tras una baja es simplemente un `cfo.vinculo_creado` nuevo.

## Qué NO cubre este CR (por qué son solo 2 eventos)

El Q&A por Telegram (recibir la pregunta del usuario, responder) **reusa**
`cfo.consulta` / `cfo.respuesta` — ya en el catálogo desde CR-CFO-1 — con
`metadata.canal="telegram"` agregado. No se crean eventos nuevos para eso.
Este CR cubre exclusivamente el ciclo de vida del vínculo identidad↔canal, que
es la única superficie *nueva* de auditoría que introduce la Pieza B.

## Política de fallo

Vincular/desvincular es una operación administrativa de identidad, no un
movimiento de dinero, pero a diferencia de una consulta de solo lectura
decide **quién puede usar FABS por este canal**. El control de acceso real lo
hace el documento `VinculoTelegram` (la allowlist en `cfo_vinculos_telegram`,
resuelta en cada webhook antes de llamar al servicio); el evento de auditoría
es el rastro forense de ese alta/baja, no el mecanismo de control — mismo
patrón que `user.creado` / `user.desactivado`.

## Por qué es gate crítico

1. **Toca el catálogo cerrado** (regla 11): cualquier cambio al catálogo es,
   por definición, un CR con gate Kimi — sin excepción por tamaño.
2. **Es un binding de identidad, no solo un registro:** el vínculo
   `telegram_id↔user_id` determina qué `actor_id` real queda detrás de cada
   mensaje de Telegram que llega a FABS, y por tanto qué RBAC y qué rastro
   (`cfo.consulta` / `cfo.respuesta` con ese `actor_id`) aplican después. Un
   alta/baja mal auditada deja un hueco forense sobre quién tuvo acceso a
   FABS por este canal y desde cuándo — el mismo tipo de superficie que
   `user.creado` / `user.rol_cambiado`, pero para un canal externo nuevo.
3. Endpoint expuesto solo a `Role.admin`, en un módulo (`app/cfo/telegram/`)
   que además es webhook público (verificado por secret token) — exactamente
   la superficie que el spec (§5/§6) marca para auditar con lupa en el gate
   de código de esta pieza (Kimi, PLAN ya GO 9.3; código pendiente).

## Implementación

- `backend/app/audit/events.py` — bloque `CR-CFO-2 (2)` al final de
  `AuditEvento`: `cfo_vinculo_creado = "cfo.vinculo_creado"`,
  `cfo_vinculo_eliminado = "cfo.vinculo_eliminado"`.
- `backend/tests/test_audit_events.py` — `test_catalogo_tiene_exactamente_66_eventos`
  (antes `..._64_eventos`): `len(AuditEvento) == 66`, `len(CATALOGO_EVENTOS) == 66`,
  y ambos eventos nuevos presentes en `CATALOGO_EVENTOS`.
- Quién emite los eventos (`vinculos.py` / `router.py` del módulo
  `app/cfo/telegram/`) es trabajo de una tarea posterior de esta misma pieza
  (B3/B5 del roadmap de inc3b); este CR solo abre el catálogo.

---
*Ante conflicto de alcance mandan `COMPAS_NORTE.md`, `CLAUDE.md` y el spec de
diseño de esta pieza. El flag `CFO_ENABLED` sigue apagado; esto no habilita
nada en producción por sí solo.*
