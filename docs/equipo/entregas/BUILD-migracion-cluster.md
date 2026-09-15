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

### Escalacion P6: CERRADA

Se encontro en local el commit `d51b7e0` (sesion de Jorge, sin push): explica que `7747f01` lo hizo una sesion que todavia no tenia el aviso de congelamiento, agrega regla nueva de equipo (verificar el BUILD antes de cualquier push a main) y deja ese commit sin pushear hasta que Jorge levante P6. P6 sigue vigente. Sergio no pushea nada mas hasta que Jorge confirme el descongelamiento en este archivo.

### A1 - Identificar el proyecto y el estado real de `compas-prod`. HECHO

Confirmado por el CEO en la consola, 2026-09-14:
- Proyecto: SISMO-V3 (id `6a14574dacf958ad8dd73c4f`)
- Tier: M0 (Free)
- Proveedor y region: AWS, us-east-1 (N. Virginia)
- Version: 8.0.32
- Estado: activo ("Monitoring is Paused" es normal en M0 tras dias sin conexion, no es pausa del cluster)
- Mismo proyecto que `sismo-v3`: SI (tambien comparte con `sismo-v3-recovery` y `sismo-v3-ci`)

Rama tomada: **A2.1** (reutilizar, ya es M0 en us-east-1). Rama de A4: **A4.1** (mismo proyecto, usuarios y rol ya existen).

### A2 - HECHO

`compas-prod` vacio: Browse Collections muestra solo `admin`/`local`, 0 colecciones (verificado por el arquitecto en Data Explorer). Sin Terminate, sin Gate G1.

### A3 - HECHO

`0.0.0.0/0` ya figura Active en el IP Access List del proyecto SISMO-V3 (comentario "CI/CD + dev local. SCRAM auth + TLS forzado"). No se toca nada.

### A4 - HECHO

Rama A4.1 confirmada por el CEO/arquitecto:
- `compas_app`: `readWrite@compas`, sin "Restrict Access to Specific Clusters".
- `compas_audit`: rol custom `audit_writer`, sin restriccion de cluster.
- `audit_writer` (Custom Role): exactamente `find` + `insert` sobre `compas.audit_log`, nada mas.
Sin restriccion de cluster en ninguno de los dos: van a funcionar en `compas-prod` automaticamente. Sin editar nada, sin regenerar passwords.

Nota de proceso: el CEO senalo que con A1-A4 hechos "mi parte de Fase A esta completa" y que seguia Fase D. Es incorrecto contra el plan: A5 y A6 siguen siendo parte de Fase A (ver texto de A5/A6 y §4 "Sergio queda sin trabajo entre A6 y C8", no entre A4 y C8). Se lo senale y seguimos con A5.

### A5 - HECHO

Host de `compas-prod` confirmado por el CEO via Connect > Drivers: `compas-prod.kd5v5rr.mongodb.net`.

Formato del INVENTARIO revisado antes de escribir (hoja `Secretos`, columnas: Secreto/Clave, Servicio, Para que, Donde vive, Formato SIN valor, Como se obtiene, Rotacion, Cargado?, VALOR). Nota menor sin impacto: la columna "Formato (SIN valor)" de `MONGODB_URI_AUDIT (prod)` dice `authSource=compas`, pero el VALOR real no lo tiene (verificado sin exponer el valor, solo comprobando la presencia de la subcadena); esa columna de documentacion quedo desactualizada, no cambia nada de lo que se ejecuta. Se sigue el template exacto del plan (con `appName=compas-prod`, sin `authSource`).

Dos filas nuevas agregadas en `docs/INVENTARIO-SECRETOS.xlsx` (filas 14 y 15): `MONGODB_URI_COMPAS (compas-prod)` y `MONGODB_URI_AUDIT (compas-prod)`. Mismo usuario/password que hoy en `sismo-v3` (rama A4.1), host nuevo, sin regenerar nada. Filas viejas sin tocar (las deprecara Jorge en C9).

Commit local `0183a4e` en la rama `session/sergio-migracion` de este worktree. **Sin push: P6 sigue congelado.**

### A6 - HECHO

Intento inicial: extraer la URI nueva del INVENTARIO dentro de la misma invocacion de Bash (sustitucion de comando, `$(...)`) y pasarla directo a `mongosh --eval` contra `compas-prod`, sin que el valor apareciera nunca como texto plano en la salida ni en el chat. El clasificador de modo automatico de Claude Code bloqueo la accion (motivo reportado: "Auto-Mode Bypass"). No se intento una forma alternativa de sortear el bloqueo (tampoco la alternativa de Jorge con Python/openpyxl, descartada por la misma razon). Se escalo al CEO.

El CEO corrio la prueba de conexion el mismo, en su propia terminal, fuera de cualquier sesion de Claude Code. Resultado confirmado por el CEO en el chat, 2026-09-15:
- `compas_app` autentico OK contra `compas-prod`: `{ ok: 1 }`
- `compas_audit` autentico OK contra `compas-prod`: `{ ok: 1 }`

Nota tecnica del CEO, guardada en memoria para Fase C: la conexion con `mongodb+srv://` fallo dos veces desde su maquina (`querySrv ECONNREFUSED`), aunque el DNS del sistema resuelve bien. Uso una connection string estandar (sin SRV, con los 3 hosts directos + `replicaSet=atlas-myw4u7-shard-0`) y esa si funciono. Si a Jorge le pasa lo mismo en el `mongorestore` real de Fase C, ese es el fallback ya verificado.

**Fase A completa (A1-A6).** Fase D (cierre de docs) sigue esperando a que Jorge cierre C9.
