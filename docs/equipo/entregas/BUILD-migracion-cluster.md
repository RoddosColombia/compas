# BUILD · Migracion de compas a compas-prod

Bitacora compartida. Cada builder escribe solo en su seccion. Plan: `docs/equipo/entregas/PLAN-migracion-cluster.md`.

## Seccion Jorge (Builder 1) · Fase B y Fase C

Regla P7: ninguna URI ni password entra en este archivo, en commits, en capturas ni en el chat. Solo en `docs/INVENTARIO-SECRETOS.xlsx`.

### P1 · Ventana

CEO confirmo la ventana en el chat el 2026-09-14: arranca ahora, disponible para los 4 gates (G1-G4).

### P4 · Herramientas (verificado 2026-09-14)

- `mongodump`: no estaba instalado. Instalado con `winget install MongoDB.DatabaseTools` → version 100.18.0.
- `mongorestore`: idem, version 100.18.0.
- `mongosh`: ya estaba instalado, version 2.8.3.

### P5 · Carpeta de respaldo

`C:\Users\AndresSanJuan\roddos-backups\compas\2026-09-14_pre-migracion` (creada, vacia, fuera del repo).

### P6 · Nadie mergea a main durante la ventana

Confirmado por el CEO en el chat, 2026-09-14: nadie mergea a main durante la ventana.

### P8 · Fila del tracker

Hecho (owner Sergio, ver seccion de abajo).

### B1 · Bitacora

Este archivo. Hecho.

## Seccion Sergio (Builder 2) · Fase A y Fase D

Regla P7: ninguna URI ni password entra en este archivo, en commits, en capturas ni en el chat. Solo en `docs/INVENTARIO-SECRETOS.xlsx`.

P8: fila `INFRA-01` agregada al tracker `docs/COMPAS_Control_Desarrollo.xlsx` (Estado "En curso"), commit `f9c85c9`, push a `main`.

Nota de proceso (clobber): este archivo se sobreescribio entre mi primer `Write` y mi commit porque Jorge lo creo en paralelo con contenido propio; mi primer borrador (con el intento de P2/A1 mas abajo) se perdio antes de llegar a git y quedo commiteado en `4a7501d` el contenido de Jorge tal cual, con mensaje de commit que ya no describe el diff real. No se reescribe la historia; se deja esta nota y de aqui en mas cada edicion a este archivo es con `Edit` (diff dirigido), no `Write` (sobreescritura completa), para no repetir el clobber.

P2 (acceso a Atlas): intente usar la herramienta de navegador de Claude Code (skill `browse` de gstack) para ejecutar A1 sin intervencion manual. El binario no esta compilado para este entorno Windows (`error: server-node.mjs not found. Run 'bun run build' to generate the Windows server bundle.`). Ademas, aunque funcionara, el login a `info@roddos.com` en Atlas requiere MFA que solo el CEO puede completar. Se sigue el camino alternativo previsto en el plan (parrafo "Pasos de consola"): dictar el click-path al CEO y registrar aqui lo que la consola devuelve.

### A1 - Identificar el proyecto y el estado real de `compas-prod`

Estado: EN CURSO. Click-path dictado al CEO, esperando las 5 lineas de evidencia (proyecto, tier, region, estado, mismo proyecto que sismo-v3 si/no).

### Escalacion abierta (P6)

Ver mensaje al CEO en el chat: el commit `7747f01` (`fix(caja): agrega rama isError a CajaPage`) llego a `main` a las 20:32:06 del 2026-09-14, en la misma ventana en la que este archivo registra "P6 confirmado por el CEO: nadie mergea a main". No se toca ese commit ni se revierte nada; se escala para que el CEO aclare si P6 sigue vigente antes de que Sergio haga el proximo push (A5) o Jorge haga C4.
