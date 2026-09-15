# Estado - Chat de Jose (Researcher 1)

**Ultima actualizacion:** 2026-09-15 (diagnostico de CI en rojo cerrado).

## Tarea en curso

Ninguna. Ultima tarea cerrada: diagnostico de por que el CI del repositorio esta en rojo permanente.

## Contexto abierto

- Dossier entregado en `docs/equipo/entregas/RESEARCH-ci-rojo.md`.
- Sin archivos de codigo tocados (solo lectura y ejecucion local de tests/lint/build para reproducir, sin commitear ningun cambio del repo).
- Sin branch propia todavia para este dossier (se crea al cerrar).

## Ultimo hito

Diagnostico de CI en rojo cerrado (2026-09-15). Hallazgos clave en 3 lineas:

1. Los 3 checks que fallan tienen causas distintas y no relacionadas entre si: `reglas inviolables (CLAUDE.md)` (semgrep) esta roto de fabrica desde que se creo (78/78 runs en failure, un patron invalido mas un falso positivo nunca excluido), `frontend` es deuda de formato/lint acumulada desde el PR #119 (build y tests estan sanos, 100% reproducible y facil de arreglar), y `backend` es un test real de la proyeccion (particion de un modelo en dos planes, PLAN-52) roto de forma determinista desde al menos el 2026-09-04, que toca el motor y por eso no lo investigue mas alla de reportarlo.
2. La memoria `ci-actions-billing-bloqueado` describe un incidente real pero ya cerrado (2026-08-17); usarla para explicar el rojo actual es un error, y ademas su afirmacion de que los required checks son imposibles en plan Free quedo contradicha por evidencia de hoy (la org sigue en Free y los 8 checks obligatorios funcionan). Queda marcado para que el arquitecto lo revise.
3. Los tres se pueden reproducir localmente: semgrep con el comando del propio workflow, frontend con `npm run lint`/`build`/`test`, backend con `pytest tests/test_modelos_planes.py` en aislamiento total (mismo numero exacto que en CI).

## Pendiente inmediato

Ninguno de mi lado. El dossier deja 4 gaps marcados (el mas importante: no se aislo el commit exacto que rompio el test de backend, porque eso exige entender la logica de particion de planes, fuera de mi alcance en esta tarea). Sigue Andres (planner) o el arquitecto, segun decida el CEO.

## Como retomar

Pegar el boilerplate de arranque de `docs/equipo/roles/jose-researcher.md`. El dossier esta cerrado; si aparece una tarea nueva, arrancar desde ahi.

## Historial reciente

- 2026-09-14: RESEARCH-migracion-cluster.md (migracion de COMPAS a cluster Atlas propio).
- 2026-09-15: RESEARCH-ci-rojo.md (diagnostico de los 3 checks de CI en rojo permanente).
