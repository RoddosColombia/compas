# Estado - Chat de Jose (Researcher 1)

**Ultima actualizacion:** 2026-09-14 (research de migracion de cluster cerrado).

## Tarea en curso

Ninguna. Ultima tarea cerrada: research de la migracion de COMPAS a cluster MongoDB propio.

## Contexto abierto

- Dossier entregado en `docs/equipo/entregas/RESEARCH-migracion-cluster.md`.
- Sin branch propia (solo se toco `docs/equipo/entregas/` y este archivo de estado).
- Sin archivos WIP.

## Ultimo hito

Research de migracion de cluster cerrado (2026-09-14). Hallazgos clave en 3 lineas:

1. Atlas NO ofrece M0 ni Flex en `mx-central-1` (solo M10+, tabla oficial de regiones AWS de Atlas) - esto activa el fallback que el propio handshake ya preveia (M10, misma region), pero rompe el driver de costo cero de la decision original de M0; hay que avisarle al CEO antes de que el planner arranque.
2. El sistema necesita DOS usuarios de Mongo (`compas_app` readWrite + `compas_audit` con rol custom `audit_writer` insert/find sin update/remove sobre `audit_log`), creados por Atlas UI/Admin API (nunca por driver, en ningun tier, segun `RUNBOOK-INFRA.md` corrigiendo una nota vieja de un script del repo).
3. El riesgo de timeout de arranque de Render contra el cluster nuevo (pregunta 5) ya esta resuelto de raiz por un fix de 2026-09-03: `healthCheckPath` es `/health` (liveness pura, sin Mongo) y `init_beanie` ya no bloquea el arranque - no hace falta tocar `render.yaml`.

## Pendiente inmediato

Ninguno de mi lado. Quedan 7 gaps marcados como REQUIERE EJECUCION EXTERNA en el dossier (tamano real de `compas`, existencia real del worker `compas-jobs` en Render, rango de IPs de salida de Render, y otros de menor peso) - el CEO decide si los resuelve antes de pasarle la tarea a Andres (planner).

## Como retomar

Pegar el boilerplate de arranque de `docs/equipo/roles/jose-researcher.md`. El dossier esta cerrado; si aparece una tarea nueva, arrancar desde ahi.

## Historial reciente

- 2026-09-14: RESEARCH-migracion-cluster.md (dossier completo, 3 bloques, 9 preguntas respondidas o marcadas como ejecucion externa).
