# PLAN · Migracion de COMPAS a su propio cluster MongoDB (`compas-prod`)

Autor: Andres (Planner 1) · 2026-09-14
Insumos, en orden de autoridad: (1) `docs/handshake_migrar_cluster_compas.md` (status corregido post-auditoria), (2) `docs/equipo/entregas/RESEARCH-migracion-cluster.md` (Jose), (3) `docs/equipo/entregas/AUDIT-migracion-cluster.md` (Claude, posterior y con acceso a consola; donde difiera del dossier, manda la auditoria).
Ejecutores: Jorge (Builder 1) y Sergio (Builder 2). Aprobador: CEO.
Bitacora de ejecucion: `docs/equipo/entregas/BUILD-migracion-cluster.md` (la abren los builders, cada uno en su seccion).

---

## 0. Avisos al CEO antes de ejecutar (leer primero)

Ninguna decision cerrada del handshake descansa sobre un hecho falso. Revise region (`us-east-1` contra Render en Ohio, que es AWS `us-east-2`), tier (M0, 2.44 MB contra 512 MB), nodo sano (`-01`), 28 colecciones y las dos env vars: todo consistente con el codigo y con la auditoria. Hay cuatro avisos que no bloquean pero cambian pasos concretos:

**Aviso 1 · Los usuarios y el rol de Atlas viven a nivel de PROYECTO, no de cluster. Eso ramifica el paso de usuarios.**
En Atlas, Database Users, Custom Roles y la IP Access List pertenecen al proyecto y aplican a todos los clusters del proyecto (salvo que un usuario tenga marcado "Restrict Access to Specific Clusters"). La auditoria reporta 4 clusters en la cuenta y un cupo free "del proyecto" agotado, lo que sugiere que `compas-prod` puede estar en el MISMO proyecto que `sismo-v3`. Si es asi, `compas_app`, `compas_audit` y `audit_writer` ya existen y ya aplican a `compas-prod` con las passwords de hoy; Atlas ni siquiera permite crear un segundo usuario con el mismo nombre en el proyecto. Si `compas-prod` esta en OTRO proyecto, aplica el click-path B1 del dossier tal cual. El paso A4 ramifica segun lo que muestre la consola. La advertencia 2 de la auditoria (verificar que la garantia append-only quede enforced) se cumple en AMBAS ramas con el paso C3, que la prueba contra el cluster nuevo.

**Aviso 2 · El test de CI NO va a detectar un rol faltante en `compas-prod`.**
El handshake dice que si el rol no viaja "hay un test de CI que deberia empezar a fallar". `backend/tests/test_audit_immutable.py:1-12,38-41` corre contra `COMPAS_TEST_AUDIT_URI` (cluster de pruebas), y sin esa env var se salta, no falla. No mira produccion. Por eso la unica verificacion valida del enforcement es manual, contra `compas-prod`, y esta en el paso C3 como criterio de "hecho" bloqueante antes del switch.

**Aviso 3 · `compas_app` tiene `readWrite` sobre `compas`, y `readWrite` incluye update y remove sobre `audit_log`.**
La frase del RUNBOOK §2 "el usuario general `compas_app` NO tiene update/remove sobre `audit_log`" solo seria cierta con un rol custom acotado, que no es lo que describe el mismo RUNBOOK ni el dossier. Hoy la garantia real es que el codigo escribe auditoria SOLO por la conexion de `compas_audit`. Este plan replica la configuracion actual tal cual (paso A4 exige copiar lo que muestra la consola de hoy, no lo que dice un doc). Endurecer `compas_app` es otra tarea y requiere CR; no se hace aqui.

**Aviso 4 · Hechos que yo no pude verificar y que Jose deberia confirmar si el CEO quiere certeza antes de la ventana.** Ninguno bloquea; todos tienen ruta alternativa dentro del plan.
- Sintaxis exacta de la URI de conexion directa a un nodo de Atlas (paso B5, escalon 2): `mongodb://` sin SRV exige `tls=true` y `authSource=admin` explicitos porque sin SRV no llega el registro TXT que los aporta. Es conocimiento estandar del driver, no verificado por Jose.
- Identificadores de winget para instalar las herramientas si faltan (`MongoDB.DatabaseTools`, `MongoDB.Shell`). Alternativa: descarga manual desde mongodb.com.
- Plazo de auto-pausa de M0. El dossier dice 30 dias citando docs oficiales; mi recuerdo es 60. No cambia nada del plan.

---

## 1. Objetivo

Que `compas.roddos.com` vuelva a abrir con toda su data, leyendo y escribiendo unicamente en un cluster Atlas propio (`compas-prod`, M0, `us-east-1`, cuenta `info@roddos.com`), sin que ninguna linea del backend dependa de la salud de `sismo-v3`, y con un dump permanente en disco del CEO como unica copia de seguridad.

## 2. Alcance

**Si:** preparar `compas-prod`; dump completo de la db `compas` del cluster viejo; restore en el nuevo; recrear o confirmar rol y usuarios; cambiar `MONGODB_URI_COMPAS` y `MONGODB_URI_AUDIT` en el dashboard de Render; verificar; checkpoint de no-retorno; registrar secretos, RUNBOOK, tracker y bitacora.

**No:** tocar `render.yaml` ni `backend/app/db/mongo.py`; bumpear timeouts; cambiar codigo de la app; pinear `pymongo`; borrar la db `compas` de `sismo-v3` (queda intacta, ver §8); endurecer roles; restringir el allowlist (tarea de go-live); activar el worker `compas-jobs`.

## 3. Precondiciones (todas verificadas antes del paso A1 / B1)

| # | Precondicion | Como se verifica | Owner |
|---|---|---|---|
| P1 | Ventana acordada con el CEO: minimo 3 horas continuas (2 de ejecucion + 1 de observacion), CEO disponible para 4 gates | Mensaje del CEO con fecha y hora en `BUILD-migracion-cluster.md` | CEO |
| P2 | Acceso a Atlas (`info@roddos.com`, con MFA a mano) y a Render Dashboard | Login exitoso en ambos, sin tocar nada | Sergio (Atlas), Jorge (Render) |
| P3 | Acceso a `docs/INVENTARIO-SECRETOS.xlsx` con las dos URIs actuales (`MONGODB_URI_COMPAS`, `MONGODB_URI_AUDIT`) | Abrir el archivo y ubicar las filas; NO copiar valores a ningun doc | Jorge |
| P4 | Herramientas instaladas en la maquina del CEO | `mongodump --version`, `mongorestore --version`, `mongosh --version` responden. Si falta: `winget install MongoDB.DatabaseTools` y `winget install MongoDB.Shell` (ver Aviso 4) | Jorge |
| P5 | Carpeta de respaldo FUERA del repo, creada y vacia: `C:\Users\AndresSanJuan\roddos-backups\compas\<YYYY-MM-DD>_pre-migracion\` | `ls` de la carpeta. Nunca dentro de `roddos-workspace/COMPAS` (contiene datos financieros y no hay `.gitignore` para dumps) | Jorge |
| P6 | Nadie va a mergear a `main` durante la ventana (auto-deploy ensuciaria la lectura de los deploys) | Aviso del CEO en el BUILD | CEO |
| P7 | Regla de secretos entendida por ambos builders: ninguna URI ni password entra en `BUILD-*.md`, en commits, en capturas ni en el chat. Solo en `INVENTARIO-SECRETOS.xlsx` | Ambos lo anotan como primera linea de su seccion del BUILD | Jorge, Sergio |
| P8 | Fila de la tarea en el tracker `docs/COMPAS_Control_Desarrollo.xlsx`, hoja Tareas, estado "En curso" (regla de cierre del CLAUDE.md: no construir sin registro) | ID de fila anotado en el BUILD | Sergio |

## 4. Reparto y dependencias

La migracion tiene un tramo intrinsecamente secuencial (dump, restore, switch, verificacion, no-retorno) y UN tramo que si conviene paralelizar: preparar el cluster nuevo mientras se saca el dump del viejo. Son dos clusters distintos, asi que no hay dos personas tocando el mismo sistema a la vez.

```
Fase A · Preparar compas-prod (Atlas)        Sergio   ─┐
                                                        ├─> Fase C · Restore + switch + verificacion   Jorge
Fase B · Congelar + dump del cluster viejo    Jorge    ─┘
                                                            Fase D · Cierre documental                 Sergio
```

- **A y B corren en paralelo.** A toca solo Atlas `compas-prod` (y el proyecto que lo contiene). B toca Render Dashboard (lectura), el cluster viejo (solo lectura por `mongodump`) y el disco del CEO.
- **C arranca solo cuando A6 y B6 estan en "hecho".** C es de un solo owner (Jorge) de punta a punta: quien hace el restore hace el switch y la verificacion, para que la evidencia de conteos y la decision de rollback esten en una sola cabeza.
- **D arranca al cierre del no-retorno (C8).** Sergio queda sin trabajo entre A6 y C8; se dice explicito en vez de inventarle pasos.
- **Archivo compartido con riesgo de clobber:** `docs/INVENTARIO-SECRETOS.xlsx` (binario). Lo edita SOLO Sergio en A5 y SOLO Jorge en C9, en momentos distintos, cada uno con commit inmediato. Antes de abrirlo, verificar en el BUILD que el otro no lo tiene abierto.
- **Pasos de consola (Atlas, Render):** el owner los ejecuta con la herramienta de navegador de Claude Code o los dicta al CEO click por click. La evidencia es texto en el BUILD (nombres, conteos, estados) y capturas guardadas en la carpeta de respaldo de P5, no en el repo.

## 5. Pasos

Formato de cada paso: owner · que hace · comando o click-path · evidencia esperada · criterio de "hecho". Los comandos son para la herramienta Bash (Git Bash) de Claude Code, en una sola invocacion cada uno porque las variables de entorno no persisten entre invocaciones. Reemplazar `<...>` con valores reales tomados de la consola o del INVENTARIO.

### Fase A · Preparar `compas-prod` (owner: Sergio)

**A1 · Identificar el proyecto y el estado real de `compas-prod`.**
Click-path: Atlas, selector de organizacion y proyecto (arriba a la izquierda), recorrer los proyectos hasta ubicar el cluster `compas-prod`. En su tarjeta leer: tier, proveedor y region, version, estado (activo o paused), y si el proyecto es el mismo donde vive `sismo-v3`.
Evidencia: en el BUILD, cuatro lineas: proyecto de `compas-prod`, tier, region, estado; y una quinta: mismo proyecto que `sismo-v3` si o no.
Hecho: las cinco lineas escritas sin ambiguedad.

**A2 · Decidir reutilizar, borrar y recrear, o proyecto nuevo (ramifica).**
- **Rama A2.1 · `compas-prod` es M0 en AWS `us-east-1`.** Reutilizar. Si esta paused: tarjeta del cluster, boton Resume, esperar estado activo. Verificar que este vacio: Browse Collections debe mostrar "no databases" (o solo `admin`/`local`). Si muestra una db `compas` con colecciones: PARAR, Gate G1, el CEO decide (el handshake dice que no tiene trabajo adentro; si lo tiene, ese hecho era falso y se escala).
- **Rama A2.2 · `compas-prod` existe pero NO es M0 en `us-east-1`.** Gate G1 antes de borrar (accion destructiva). Con GO del CEO: tarjeta del cluster, menu de tres puntos, Terminate, escribir el nombre `compas-prod`, confirmar. Esperar a que desaparezca de la lista (minutos). Luego: Create, pestana Free (debe estar habilitada ahora que se libero el cupo; si sigue deshabilitada, ir a A2.3), proveedor AWS, region N. Virginia (`us-east-1`), nombre `compas-prod`, crear. Si el formulario ofrece crear un usuario o allowlist en el asistente de bienvenida, cerrarlo sin crear nada: eso se hace en A3 y A4 con criterio.
- **Rama A2.3 · El cupo free del proyecto lo ocupa OTRO cluster que no se puede borrar.** Gate G1. Opcion a proponer al CEO: crear un proyecto nuevo `COMPAS` dentro de la misma organizacion (el cupo M0 es por proyecto), y crear ahi `compas-prod` M0 `us-east-1`. En esa rama, A3 y A4 aplican completos (proyecto nuevo, sin usuarios ni allowlist).
Evidencia: tarjeta del cluster con `compas-prod`, `M0`, `AWS us-east-1`, estado activo; captura en la carpeta de P5.
Hecho: existe exactamente UN cluster llamado `compas-prod`, M0, `us-east-1`, activo y sin base `compas`.

**A3 · Allowlist del proyecto de `compas-prod`.**
Click-path: Security, Network Access, IP Access List. Si ya figura `0.0.0.0/0` (rama mismo proyecto que `sismo-v3`, precedente `docs/RUNBOOK-INFRA.md:50`), no tocar. Si no figura: Add IP Address, Allow access from anywhere (`0.0.0.0/0`), comentario `dev - cerrar en go-live (RUNBOOK §2)`, Confirm. Esperar estado Active.
Motivo (dossier B3): Render Free no tiene IP de salida estatica y sus rangos rotaron en nov-2025; allowlistear rangos daria el mismo sintoma que se esta arreglando. Esta es la politica vigente del proyecto para desarrollo; restringir es tarea de go-live.
Evidencia: fila `0.0.0.0/0` en estado Active.
Hecho: la fila existe y esta Active.

**A4 · Rol `audit_writer` y usuarios `compas_app` y `compas_audit` (ramifica por Aviso 1). SIEMPRE por Atlas UI, nunca por driver ni `mongosh`, sin importar el tier (`docs/RUNBOOK-INFRA.md:47`, AtlasError 8000).**
Primero, en el proyecto donde vive `sismo-v3`: Security, Database Access, pestana Database Users, abrir `compas_app` y `compas_audit` con Edit (sin guardar) y anotar EXACTAMENTE sus roles, scope de base, y si tienen "Restrict Access to Specific Clusters" marcado. Pestana Custom Roles, abrir `audit_writer` y anotar sus acciones y su scope. Esto es la fuente de verdad de "como esta hoy"; el RUNBOOK y el dossier son la referencia, la consola manda.
- **Rama A4.1 · `compas-prod` esta en el mismo proyecto que `sismo-v3`.** Los tres ya existen y aplican a `compas-prod`. Unica accion: si alguno de los dos usuarios tiene "Restrict Access to Specific Clusters" activo, editarlo para incluir `compas-prod` (o quitar la restriccion) y Update User. Las passwords siguen siendo las de hoy; NO regenerarlas (regenerar rompe el cluster viejo, que es el rollback).
- **Rama A4.2 · `compas-prod` esta en otro proyecto.** Click-path exacto del dossier B1, en este orden:
  1. Database Access, Custom Roles, Add New Custom Role. Role Name `audit_writer`. Add Privilege: Database `compas`, Collection `audit_log`, Actions `insert` y `find`. Nada mas. Save. Esperar a que aplique (unos 30 s).
  2. Database Access, Database Users, Add New Database User. Password. Username `compas_app`. Password autogenerada (copiar de inmediato; Atlas no la vuelve a mostrar). Database User Privileges: Grant Database Access, rol `readWrite`, database `compas` (no "any database"). Add User.
  3. Add New Database User. Username `compas_audit`. Password autogenerada (copiar). Privileges: Add custom role, `audit_writer`. Ningun otro rol. Add User.
  Las passwords autogeneradas de Atlas son alfanumericas y no requieren URL-encoding en la URI. Si el CEO prefiere una propia, evitar `@ : / ? # & %`.
Evidencia: en el BUILD, tabla de tres filas (`audit_writer`, `compas_app`, `compas_audit`) con roles y scope tal como quedaron en `compas-prod`, y la rama tomada. Sin passwords.
Hecho: los tres existen en el proyecto de `compas-prod` con los mismos privilegios que hoy en `sismo-v3`, y ningun usuario quedo restringido a un cluster que excluya a `compas-prod`.

**A5 · Construir las dos URIs nuevas y registrarlas en el INVENTARIO.**
Click-path: tarjeta de `compas-prod`, Connect, Drivers, copiar el host (`compas-prod.<sufijo>.mongodb.net`). Construir, en formato SRV obligatorio (handshake, "Formato de URI"; `dnspython` es dependencia dura de `pymongo`, sin cambios en `requirements.txt`):
```
mongodb+srv://compas_app:<PASSWORD_APP>@compas-prod.<sufijo>.mongodb.net/compas?retryWrites=true&w=majority&appName=compas-prod
mongodb+srv://compas_audit:<PASSWORD_AUDIT>@compas-prod.<sufijo>.mongodb.net/compas?retryWrites=true&w=majority&appName=compas-prod
```
Sin `authSource` (los usuarios de UI autentican contra `admin` y SRV lo resuelve, `docs/RUNBOOK-INFRA.md:48`). Abrir `docs/INVENTARIO-SECRETOS.xlsx` (verificar antes en el BUILD que Jorge no lo tiene abierto), agregar dos filas nuevas `MONGODB_URI_COMPAS (compas-prod)` y `MONGODB_URI_AUDIT (compas-prod)` con fecha; NO tocar todavia las filas viejas (las deprecara Jorge en C9). Guardar, `git add docs/INVENTARIO-SECRETOS.xlsx`, commit `chore(secretos): URIs de compas-prod (migracion cluster)`, push.
Evidencia: hash del commit en el BUILD.
Hecho: las dos filas existen en el INVENTARIO y el commit esta en `main`.

**A6 · Prueba de conexion en frio contra `compas-prod` (solo lectura, base vacia).**
```
export URI_NEW_APP='<MONGODB_URI_COMPAS (compas-prod) copiada del INVENTARIO>'; \
mongosh "$URI_NEW_APP" --quiet --eval 'printjson({ok: db.runCommand({ping:1}).ok, dbs: db.getMongo().getDBNames()})'
```
Evidencia esperada: `{ ok: 1, dbs: [ 'admin', 'local' ] }` o lista sin `compas`. En M0 `getDBNames` puede negar `listDatabases`; en ese caso basta `ok: 1` y que `db.getCollectionNames()` sobre `compas` devuelva `[]`.
Y lo mismo con la URI de `compas_audit`: `ok: 1`.
Hecho: ambas URIs autentican contra `compas-prod` y la db `compas` no existe o esta vacia. **Fin de Fase A. Sergio anota "A6 hecho" en el BUILD y avisa al CEO.**

### Fase B · Congelar escrituras y sacar el dump del cluster viejo (owner: Jorge)

**B1 · Abrir la bitacora y confirmar precondiciones.**
Crear `docs/equipo/entregas/BUILD-migracion-cluster.md` con dos secciones (Jorge, Sergio), la primera linea de cada una es la regla P7. Pegar el resultado de P4 (versiones) y la ruta de P5.
Hecho: archivo creado, versiones y ruta escritas.

**B2 · Chequear si existe un worker `compas-jobs` creado a mano en Render (ramifica; punto abierto del handshake).**
Click-path: Render Dashboard, lista de Services del workspace. Buscar cualquier servicio de tipo Background Worker (o cron) cuyo nombre o `startCommand` mencione `compas`, `jobs` o `scheduler`.
- **Rama B2.1 · No existe.** Anotar "sin worker; blueprint `render.yaml:72-108` coincide con el dashboard". Dejar en el BUILD la nota para Sprint 5-6: cuando se active `compas-jobs`, el Paso 0 de cualquier migracion futura vuelve a incluir detenerlo, y sus env vars `MONGODB_URI_*` deben apuntar a `compas-prod`.
- **Rama B2.2 · Existe.** Abrirlo, Settings, Suspend Service. Anotar nombre, tipo y hora de suspension. Este servicio se reconfigura en C4b y se reanuda en C8b.
Evidencia: lista de servicios (nombres y tipos) en el BUILD.
Hecho: la rama esta escrita y, si aplica, el worker esta Suspended.

**B3 · Congelar escrituras al cluster viejo (Paso 0 del CRITICO 2).**
Checklist en el BUILD, cada item con hora:
1. Worker: segun B2.
2. Ningun script o migracion corriendo en la maquina del CEO: en PowerShell `Get-Process python* | Select-Object Id,ProcessName,StartTime` debe devolver solo procesos ajenos a `migrations/` (o nada). Cerrar cualquier terminal con `MONGODB_URI_COMPAS` exportada.
3. El CEO confirma por escrito que nadie va a usar `compas.roddos.com` hasta que Jorge avise (hoy la app no abre, asi que el costo es cero).
4. Nadie mergea a `main` (P6).
Hecho: los cuatro items con hora y confirmacion del CEO.

**B4 · Reconfirmar en la consola cual nodo de `sismo-v3` esta sano, el mismo dia (advertencia 3 de la auditoria).**
Click-path: Atlas, proyecto de `sismo-v3`, tarjeta del cluster, ver los tres nodos (`sismo-v3-shard-00-00/-01/-02.onh5xm.mongodb.net`) con su rol (PRIMARY / SECONDARY) y su estado. Anotar tambien el nombre del replica set que muestra Connect, Drivers, opcion de conexion estandar (`replicaSet=...`).
Evidencia: tabla de tres filas en el BUILD: host, rol, estado, hora.
Hecho: hay al menos un nodo PRIMARY sano identificado por hostname. Al 2026-09-14 era `-01`; si cambio, el plan usa el que diga la consola HOY.

**B5 · `mongodump` de la db `compas` (escalera del CRITICO 1, en orden; pasar al siguiente escalon solo si el anterior se cuelga mas de 5 minutos sin imprimir `done dumping`).**
Variables comunes (misma invocacion que el comando):
```
export DUMP="/c/Users/AndresSanJuan/roddos-backups/compas/<YYYY-MM-DD>_pre-migracion"; mkdir -p "$DUMP"
export URI_OLD_APP='<MONGODB_URI_COMPAS actual, del INVENTARIO>'
```
Escalon 1, SRV normal con tope de seleccion de servidor para que falle rapido en vez de colgarse (agregar con `&` si la URI ya tiene `?`, con `?` si no):
```
mongodump --uri "${URI_OLD_APP}&serverSelectionTimeoutMS=20000" --nsInclude 'compas.*' --out "$DUMP" 2>&1 | tee "$DUMP/mongodump.log"
```
Escalon 2, conexion directa al PRIMARY sano de B4, saltando el descubrimiento de topologia (sintaxis no verificada por Jose, ver Aviso 4; `tls=true` y `authSource=admin` son obligatorios sin SRV):
```
mongodump --uri 'mongodb://compas_app:<PASSWORD_APP_ACTUAL>@<host-primary-sano>:27017/?tls=true&authSource=admin&directConnection=true&serverSelectionTimeoutMS=20000' --nsInclude 'compas.*' --out "$DUMP" 2>&1 | tee "$DUMP/mongodump.log"
```
Escalon 3, lista manual de los nodos sanos con lectura en secundario preferido:
```
mongodump --uri 'mongodb://compas_app:<PASSWORD_APP_ACTUAL>@<host-sano-1>:27017,<host-sano-2>:27017/?tls=true&authSource=admin&replicaSet=<nombre-rs-de-B4>&readPreference=secondaryPreferred&serverSelectionTimeoutMS=20000' --nsInclude 'compas.*' --out "$DUMP" 2>&1 | tee "$DUMP/mongodump.log"
```
Escalon 4, plan B de ultimo recurso (re-sembrar con migraciones idempotentes y reconstruir a mano la caja curada mar-jul): **NO se ejecuta en esta ventana.** PARAR y abrir Gate G2. El handshake lo acepta de antemano como decision, pero su ejecucion es otra tarea con su propio plan.
Antes de reintentar un escalon, vaciar la carpeta: `rm -rf "$DUMP"/compas` (solo la subcarpeta del dump, nunca la carpeta de respaldo entera).
Evidencia: `mongodump.log` con 28 lineas `done dumping compas.<coleccion> (N documents)` y sin `Failed`. Anotar en el BUILD que escalon funciono.
Hecho: el log muestra 28 `done dumping`, cero errores, y el escalon usado esta anotado.

**B6 · Verificar el dump y guardar la copia permanente (advertencia 5: es la unica copia de seguridad que va a existir).**
```
export DUMP="/c/Users/AndresSanJuan/roddos-backups/compas/<YYYY-MM-DD>_pre-migracion"; \
echo "bson: $(ls "$DUMP/compas"/*.bson | wc -l)  metadata: $(ls "$DUMP/compas"/*.metadata.json | wc -l)"; \
grep 'done dumping' "$DUMP/mongodump.log" | sed -E 's/.*done dumping compas\.([^ ]+) \(([0-9]+) documents?\).*/\1 \2/' | sort > "$DUMP/conteo-origen.txt"; \
cat "$DUMP/conteo-origen.txt"; du -sh "$DUMP"
```
Evidencia esperada: `bson: 28  metadata: 28`; `conteo-origen.txt` con 28 filas; ordenes de magnitud del handshake: `audit_log` ~2400, `transacciones` ~2200, `facturas` 482, `reglas_clasificacion` 159, `presupuesto_lineas` 130, `refresh_sessions` 99, `cartera_previa_recaudo` 82, `rubros` 54, `parametros_proyeccion` 14, `configuracion` 11, `facturas_obligacion` 9, `meses_control` 7, `cargas` 6, `modelos_moto` 3, `metas_ingreso` 2, `cfo_hilos` 1, `cfo_vinculos_telegram` 1, `obligaciones` 1, `users` 1; nueve en 0 (`cfo_avisos_vigilante`, `colocacion_mes`, `gastos_recurrentes`, `idempotency_keys`, `jwt_denylist`, `loantape_creditos`, `login_throttle`, `pagos_planeados`, `proyeccion_versiones`). Tamano total de unos pocos MB. Si una coleccion con data esperada aparece en 0 (por ejemplo `transacciones`), el dump esta malo: repetir B5, no seguir.
Copia permanente, en PowerShell:
```
$d = "C:\Users\AndresSanJuan\roddos-backups\compas\<YYYY-MM-DD>_pre-migracion"
Compress-Archive -Path $d -DestinationPath "$d.zip"
Get-FileHash "$d.zip" -Algorithm SHA256
Copy-Item "$d.zip" "<segunda ubicacion que indique el CEO: OneDrive, disco externo o USB>"
```
Evidencia: ruta de la carpeta, ruta del zip, SHA256 y segunda ubicacion en el BUILD (el hash no es secreto). Los `.bson` contienen datos financieros y el hash de la password del CEO: no van al repo ni a ningun chat.
Hecho: 28 y 28, conteos plausibles, zip con hash, y dos copias en ubicaciones distintas. **Fin de Fase B. Jorge anota "B6 hecho" y avisa al CEO.**

Si B5 requirio el escalon 3 o llego al 4: **Gate G2** antes de seguir.

### Fase C · Restore, verificacion, switch y no-retorno (owner: Jorge; requiere A6 y B6 en "hecho")

**C1 · `mongorestore` contra `compas-prod`.**
```
export DUMP="/c/Users/AndresSanJuan/roddos-backups/compas/<YYYY-MM-DD>_pre-migracion"; \
export URI_NEW_APP='<MONGODB_URI_COMPAS (compas-prod)>'; \
mongorestore --uri "$URI_NEW_APP" --nsInclude 'compas.*' --drop --dir "$DUMP" 2>&1 | tee "$DUMP/mongorestore.log"
```
`--drop` hace el paso idempotente: un reintento borra lo parcial y vuelve a cargar. Los indices viajan en los `.metadata.json` y `mongorestore` los construye al final de cada coleccion.
Evidencia: ultimas lineas del log con `N document(s) restored successfully. 0 document(s) failed to restore.` donde N es la suma de `conteo-origen.txt`. Sin lineas `error` ni `Failed`.
Hecho: `0 document(s) failed` y N coincide con la suma del origen.

**C2 · Verificar 28 colecciones (NO 30), conteos identicos e indices (advertencia 1; gap 4 del dossier).**
```
export DUMP="/c/Users/AndresSanJuan/roddos-backups/compas/<YYYY-MM-DD>_pre-migracion"; \
export URI_NEW_APP='<MONGODB_URI_COMPAS (compas-prod)>'; \
mongosh "$URI_NEW_APP" --quiet --eval '
  const cols = db.getCollectionNames().sort();
  cols.forEach(c => print(c, db.getCollection(c).countDocuments()));
' > "$DUMP/conteo-destino.txt"; \
echo "colecciones destino: $(wc -l < "$DUMP/conteo-destino.txt")"; \
diff <(sort "$DUMP/conteo-origen.txt") <(sort "$DUMP/conteo-destino.txt") && echo "CONTEOS IDENTICOS"; \
mongosh "$URI_NEW_APP" --quiet --eval '
  printjson(db.audit_log.getIndexes().map(i => i.name));
  printjson(db.transacciones.getIndexes().filter(i => i.unique).map(i => ({name: i.name, key: i.key, partial: i.partialFilterExpression})));
  printjson({dataMB: (db.stats().dataSize/1048576).toFixed(2)});
'
```
Evidencia esperada:
- `colecciones destino: 28`. Las dos que faltan respecto del codigo (`escenarios_impacto`, `cfo_goldens`) nunca se escribieron y Mongo no materializa colecciones vacias (`backend/app/domain/escenario_impacto.py:43`, `backend/app/cfo/goldens/modelo.py:14`). 28 es completo. 30 no es una meta.
- `CONTEOS IDENTICOS`.
- Indices de `audit_log` incluyen `forense_entidad_ts` (`backend/app/audit/models.py:23-28`).
- `transacciones` tiene un indice unico con `key {banco:1, id_banco:1}` y `partial {id_banco:{$type:'string'}}` (regla 5 del CLAUDE.md).
- `dataMB` cercano a 2.44.
Si falta el indice forense: crearlo con `compas_app` desde `mongosh` con la misma definicion (`db.audit_log.createIndex({entidad:1, entidad_id:1, timestamp:1}, {name:"forense_entidad_ts"})`), que es lo que hace `scripts/create_audit_role.py:111-118`, y anotar la anomalia. Si falta el indice unico parcial de `transacciones`: PARAR y avisar al CEO, no inventar la definicion.
Hecho: 28, conteos identicos, los dos indices presentes.

**C3 · Verificar que la garantia append-only del `audit_log` esta ENFORCED en `compas-prod` (advertencia 2; Aviso 2). Bloqueante para el switch.**
Se prueba con el usuario `compas_audit`. Solo operaciones que deben ser rechazadas o que son de lectura. NO se inserta ningun documento de prueba: `audit_log` es append-only y un evento falso quedaria para siempre.
```
export URI_NEW_AUDIT='<MONGODB_URI_AUDIT (compas-prod)>'; \
mongosh "$URI_NEW_AUDIT" --quiet --eval '
  function esperaRechazo(nombre, fn) { try { const r = fn(); print("FALLO " + nombre + ": permitido -> " + JSON.stringify(r)); } catch (e) { print("OK " + nombre + " rechazado: " + e.codeName); } }
  esperaRechazo("update audit_log", () => db.audit_log.updateOne({_id: "no-existe"}, {$set: {x: 1}}));
  esperaRechazo("delete audit_log", () => db.audit_log.deleteOne({_id: "no-existe"}));
  esperaRechazo("find rubros",      () => db.rubros.findOne());
  print("find audit_log permitido, docs: " + db.audit_log.countDocuments());
'
```
Evidencia esperada, cuatro lineas: `OK update audit_log rechazado: Unauthorized`, `OK delete audit_log rechazado: Unauthorized`, `OK find rubros rechazado: Unauthorized`, `find audit_log permitido, docs: <mismo numero que conteo-origen>`.
Cualquier linea que empiece con `FALLO`: el rol no esta bien configurado. PARAR, volver a A4, no hacer el switch.
Hecho: las cuatro lineas exactamente como se esperan.

**>>> Gate G3 (CEO): autorizar el switch.** Jorge presenta en el BUILD: escalon del dump, B6, C1, C2, C3. El CEO responde GO por escrito. Sin GO, Fase C no continua.

**C4 · Cambiar las DOS env vars en Render, en un solo guardado, con respaldo de las viejas (advertencia 4: no se toca `render.yaml`, no se bumpea ningun timeout).**
Click-path: Render Dashboard, servicio `compas-api`, pestana Environment. En una sola edicion:
1. Add Environment Variable: `MONGODB_URI_COMPAS_OLD` = valor ACTUAL de `MONGODB_URI_COMPAS` (usar el ojo de "reveal" y copiar exacto).
2. Add Environment Variable: `MONGODB_URI_AUDIT_OLD` = valor ACTUAL de `MONGODB_URI_AUDIT`.
3. Editar `MONGODB_URI_COMPAS` = URI nueva de `compas_app` (del INVENTARIO, fila `compas-prod`).
4. Editar `MONGODB_URI_AUDIT` = URI nueva de `compas_audit`.
5. Un solo "Save, rebuild, and deploy". Render dispara un deploy automaticamente al guardar env vars; hacerlo en un solo guardado evita dos deploys encadenados.
Anotar la hora exacta del guardado: es T0 del switch.
**C4b (solo rama B2.2):** repetir 1 a 5 en el worker suspendido, sin reanudarlo todavia.
Evidencia: pestana Events de `compas-api` muestra un deploy iniciado por cambio de env vars a la hora T0; la pestana Environment muestra 4 variables `MONGODB_URI_*` (dos nuevas, dos `_OLD`).
Hecho: deploy en curso y 4 variables visibles.

**C5 · Observar el deploy y la readiness.**
Click-path: `compas-api`, Logs. Esperar la linea `[ensure_beanie] init_beanie OK` (`backend/app/main.py:95`). Si aparece `[ensure_beanie] TIMEOUT tras 30.0s`, el propio mensaje lista las tres causas a revisar: allowlist (A3), cluster Free pausado (A2), DNS SRV (A5). Como `/health` es liveness pura (`render.yaml:38`), el deploy se promueve igual y el servicio sigue vivo mientras reintenta.
```
curl -s -o /dev/null -w '%{http_code}\n' https://api.compas.roddos.com/health
curl -s https://api.compas.roddos.com/api/v1/health/ready
```
Evidencia esperada: `200` en `/health`; en `/health/ready`, `{"status":"ready","mongo":"up","beanie":"ready"}`. Es normal ver `{"status":"not_ready","mongo":"up","beanie":"pending"}` con 503 durante los primeros segundos: readiness solo lee estado y el middleware lazy despierta Beanie en el primer request real (`backend/app/api/v1/health.py:35-67`). Si a los 5 minutos sigue `pending`, hacer un request real (abrir `compas.roddos.com` sin loguearse) y volver a consultar. Si dice `"mongo":"down"` pasados 5 minutos: ir a §6, rollback RB-1.
Hecho: `ready` en 200 y `init_beanie OK` en el log. Anotar la hora.

**C6 · Smoke del CEO (define el fin de la ventana de rollback sin perdida, ver §6).**
Antes de que el CEO haga login, Jorge anota la hora: hasta aqui NO hubo escrituras en `compas-prod` (RB-1 vigente). El login escribe `refresh_sessions`, `login_throttle` y un evento `user.login` en `audit_log`: es la primera escritura y ademas sirve como "write confirmado" sin tocar data de negocio.
El CEO, en `compas.roddos.com`:
1. Login con MFA (el secreto TOTP viaja cifrado con `MFA_ENC_KEY`, que no cambia).
2. Inicio: el tile de caja muestra saldo; la caja curada mar-jul es visible con los mismos valores que antes de la caida.
3. Datos o Transacciones: se ven movimientos de mar-jul (2.2K en total).
4. Configuracion del motor: los 3 modelos de moto y los parametros de proyeccion cargados (14 filas; si la pantalla no los lista, se verifica en el punto 5).
Jorge confirma la escritura en Atlas: `compas-prod`, Browse Collections, `compas.audit_log`, el conteo debe ser el de origen mas 1 (o mas, uno por login), y `parametros_proyeccion` sigue en 14 y `modelos_moto` en 3. Alternativa por `mongosh` con `URI_NEW_APP`: `db.audit_log.countDocuments()`.
Evidencia: las cuatro pantallas confirmadas por el CEO por escrito en el BUILD; conteo de `audit_log` origen+1 anotado con hora.
Hecho: el CEO ve data y `audit_log` crecio en `compas-prod`. **Desde aqui rige RB-2, no RB-1.**

**C7 · Ventana de observacion: 1 hora de operacion sana con al menos un write confirmado (CRITICO 4).**
Durante 60 minutos desde C6: el CEO usa la app con normalidad; Jorge consulta `/api/v1/health/ready` cada 15 minutos (4 lecturas, todas `ready`), revisa que en Logs de Render no aparezca `[ensure_beanie]` con error, y mira en Atlas `compas-prod`, Metrics, que Connections sea mayor que 0 y Opcounters muestre actividad. Si el CEO hace una escritura de negocio (editar, clasificar, aprobar), anotarla con hora: desde ese momento el rollback implica perder esa escritura (RB-3).
Evidencia: tabla de 4 lecturas de readiness con hora, y las escrituras conocidas.
Hecho: 60 minutos, 4 de 4 `ready`, sin errores de conexion, al menos el write de C6 confirmado.

**>>> Gate G4 (CEO): declarar el checkpoint de no-retorno.** Con la evidencia de C7, el CEO autoriza por escrito cerrar el rollback. A partir de aqui, cualquier problema se arregla hacia adelante sobre `compas-prod`.

**C8 · Cerrar el rollback: borrar las env vars de respaldo.**
Click-path: `compas-api`, Environment, eliminar `MONGODB_URI_COMPAS_OLD` y `MONGODB_URI_AUDIT_OLD`, un solo guardado (dispara un deploy mas; esperar `ready` otra vez con el curl de C5).
**C8b (solo rama B2.2):** eliminar tambien las `_OLD` del worker y reanudarlo (Settings, Resume Service). Confirmar en sus Logs que arranca contra `compas-prod`.
Evidencia: Environment de `compas-api` con exactamente dos `MONGODB_URI_*`; `ready` en 200 despues del redeploy.
Hecho: dos variables, `ready` 200, hora anotada.

**C9 · Deprecar las URIs viejas en el INVENTARIO.**
Verificar en el BUILD que Sergio ya commiteo A5 y no tiene el archivo abierto. En `docs/INVENTARIO-SECRETOS.xlsx`, marcar las filas viejas de `MONGODB_URI_COMPAS` y `MONGODB_URI_AUDIT` (host `sismo-v3`) como `DEPRECADA <YYYY-MM-DD> - migrado a compas-prod`. NO borrar las filas, NO regenerar passwords (en la rama A4.1 son los mismos usuarios que usa `compas-prod`). Commit `chore(secretos): deprecar URIs de sismo-v3 tras migracion` y push.
Evidencia: hash del commit.
Hecho: filas marcadas y commit en `main`. **Fin de Fase C. Jorge avisa al CEO.**

### Fase D · Cierre documental (owner: Sergio; arranca tras C9)

**D1 · Correccion fechada en `docs/RUNBOOK-INFRA.md` §2.** Debajo de la linea "Ejecutado (20-jul-2026)", agregar una nota `CORRECCION <YYYY-MM-DD>: compas migrada al cluster propio compas-prod (M0, AWS us-east-1, proyecto <nombre>). sismo-v3 ya no aloja compas en produccion. Rol y usuarios: <rama A4.1 o A4.2>. Dump pre-migracion en disco del CEO (ruta y SHA256 en BUILD-migracion-cluster.md). Sin backup automatico: riesgo aceptado por el CEO (handshake).` Mismo patron de correccion fechada que ya usa el RUNBOOK. No reescribir la historia.
Hecho: nota agregada, sin tocar el resto del archivo.

**D2 · Tracker.** `docs/COMPAS_Control_Desarrollo.xlsx`, hoja Tareas, fila de P8: Estado `Hecha`, Fecha cierre, Evidencia = hash del commit de D3. Con openpyxl, sin tocar encabezados, formulas del Dashboard ni validaciones. Verificar antes que no haya otra sesion con el archivo abierto.
Hecho: fila actualizada.

**D3 · Commit de cierre.** `git add docs/RUNBOOK-INFRA.md docs/COMPAS_Control_Desarrollo.xlsx docs/equipo/entregas/BUILD-migracion-cluster.md` y commit `docs(infra): migracion de compas a compas-prod cerrada; checkpoint de no-retorno <YYYY-MM-DD HH:MM>`, con el cuerpo del mensaje indicando: escalon de dump usado, rama de A2 y A4, rama de B2, hora del switch (T0), hora del no-retorno, ruta y SHA256 del dump. Push.
Hecho: commit en `main`.

**D4 · Recomendaciones que quedan registradas para decision del CEO (no son pasos).**
- Rutina de dump manual mensual con el mismo comando de B5 escalon 1 contra `compas-prod`, guardado en la misma carpeta. Con M0 no hay otra red.
- Alerta de storage al 70% (350 MB) segun CRITICO 3: en Atlas, Alerts, se puede configurar sobre `compas-prod`; hoy esta a 2.44 MB.
- Auto-pausa de M0 por inactividad: el keep-alive de GitHub Actions no cuenta porque nunca abre conexion a Mongo (`.github/workflows/keep-alive.yml:53-60`). En uso normal no aplica.
- Borrado de la db `compas` en `sismo-v3`: fuera de este plan, ver §8.

## 6. Puntos de rollback y donde deja de ser posible

| Punto | Cuando | Que se hace | Que se pierde |
|---|---|---|---|
| RB-0 | Cualquier momento antes de C4 | Nada que deshacer. La app sigue apuntando a `sismo-v3`. `compas-prod` queda con una copia inerte que se puede borrar o dejar. | Nada |
| RB-1 | Entre C4 y el login del CEO en C6 | En Render, Environment: copiar los valores de `MONGODB_URI_COMPAS_OLD` y `MONGODB_URI_AUDIT_OLD` de vuelta a `MONGODB_URI_COMPAS` y `MONGODB_URI_AUDIT`, un solo guardado, esperar el deploy. Si el worker existia (B2.2), idem y NO reanudarlo. | Nada: `compas-prod` no recibio escrituras |
| RB-2 | Despues del login de C6 y antes de cualquier escritura de negocio | Mismo procedimiento que RB-1. Requiere decision del CEO por escrito. | Las sesiones de login y los eventos `user.login` del smoke, que quedan solo en `compas-prod`. El `audit_log` de `sismo-v3` no tendra esos eventos; se anota en el BUILD como brecha conocida. Nada de negocio |
| RB-3 | Despues de la primera escritura de negocio en `compas-prod` y antes de G4 | Solo con decision explicita del CEO y entendiendo la perdida. | Toda escritura hecha en `compas-prod` desde C4. No se intenta "copiar de vuelta" al cluster viejo: es exactamente la trampa silenciosa del CRITICO 4 |
| No-retorno | Gate G4 aprobado y C8 ejecutado | No hay rollback. Todo problema se arregla hacia adelante sobre `compas-prod`. | N/A |

Reglas del rollback:
- El rollback devuelve la app al cluster enfermo. Es volver al estado "COMPAS no abre", no a un estado bueno. Se usa solo si `compas-prod` esta peor que eso (data incorrecta, auth rota, `mongo: down` persistente).
- Despues de un rollback, `compas-prod` queda desincronizado. Un segundo intento repite la Fase B completa (nuevo dump) y C1 con `--drop`. Nunca se restaura "encima" sin `--drop` ni se reutiliza el dump anterior si hubo escrituras en `sismo-v3` entre medio.
- Las env vars `_OLD` son la unica llave del rollback. No se borran antes de G4 bajo ninguna circunstancia.

## 7. Gates de aprobacion del CEO

| Gate | Momento | Que decide el CEO | Sin GO |
|---|---|---|---|
| G1 | Fase A, paso A2, solo en ramas A2.2 (borrar cluster) o A2.3 (proyecto nuevo), o si `compas-prod` resulta tener data adentro | Autorizar el Terminate del `compas-prod` actual, o la creacion de un proyecto nuevo, o que hacer con data inesperada | Sergio no borra ni crea nada; Fase B puede seguir |
| G2 | Fase B, paso B5, solo si el dump necesito el escalon 3 o llego al 4 | Escalon 3: aceptar un dump sacado de secundarios como fuente de verdad. Escalon 4: activar el plan B de re-siembra como tarea separada | No hay restore |
| G3 | Fin de C3, antes de C4 | Autorizar el switch de URIs en Render con la evidencia de A6, B6, C1, C2, C3 | La app sigue en `sismo-v3`, RB-0 |
| G4 | Fin de C7 | Declarar el no-retorno y autorizar borrar las `_OLD` | Las `_OLD` se quedan; el CEO puede extender la observacion o pedir rollback RB-2/RB-3 |

Cualquier rollback (RB-2 o RB-3) tambien es decision del CEO, nunca del builder.

## 8. Fuera de alcance y decisiones que este plan NO toma

- **Borrar la db `compas` de `sismo-v3`.** Queda intacta como copia congelada al momento del dump. Borrarla es una accion destructiva sobre un cluster de otro producto; requiere una decision separada del CEO, no antes de 30 dias del no-retorno, y con el dump de B6 verificado otra vez.
- **Restringir el allowlist `0.0.0.0/0`.** Tarea de go-live (RUNBOOK §2).
- **Acotar `compas_app` para que no pueda hacer update/remove sobre `audit_log`** (Aviso 3). Requiere CR.
- **Pinear `pymongo` en `requirements.txt`** (gap 7 del dossier). Cambio de codigo, fuera de esta migracion.
- **Activar el worker `compas-jobs`.** Sprint 5-6. Nota registrada en B2.1.
- **Que hay en las 14 filas de `parametros_proyeccion`** (pregunta 4 del handshake). Viajan en el dump tal cual. Averiguarlo es tarea de research, no de migracion.
- **Actualizar memorias del arquitecto** (`compas-desplegado-estado`, handshake a status "ejecutado"). Tarea de Claude, via CEO, con la evidencia de D3.

## 9. Hechos pendientes para Jose (si el CEO quiere cerrarlos antes de la ventana)

1. Sintaxis exacta de la URI `mongodb://` directa a un nodo de Atlas con `tls=true&authSource=admin&directConnection=true` (paso B5, escalon 2).
2. Identificadores de winget de MongoDB Database Tools y mongosh (P4).
3. Plazo real de auto-pausa de M0 (30 o 60 dias). Solo informativo.
4. Confirmar en la consola si `compas-prod` y `sismo-v3` comparten proyecto (Aviso 1). Si Jose lo cierra antes, A1 y A4 dejan de ramificar y el plan se simplifica.

## Related

- `docs/handshake_migrar_cluster_compas.md` · decisiones cerradas, CRITICOS 1 a 5, secuencia sugerida.
- `docs/equipo/entregas/RESEARCH-migracion-cluster.md` · click-paths (B1), consumidores y allowlist (B3), arranque (B4), colecciones (C2).
- `docs/equipo/entregas/AUDIT-migracion-cluster.md` · nodo sano, 2.44 MB, 28 colecciones, `compas-prod` preexistente, cupo free agotado.
- `docs/RUNBOOK-INFRA.md` §2 · usuarios, rol, `0.0.0.0/0`, "solo por Atlas UI".
- `render.yaml:12,38,55-58,72-108` · region Ohio, `healthCheckPath`, dos env vars, worker diferido.
- `backend/app/main.py:69-115`, `backend/app/api/v1/health.py:35-67` · lo que se observa en C5.
- `backend/app/audit/models.py:23-28`, `scripts/create_audit_role.py:111-118` · indice forense.
- `backend/tests/test_audit_immutable.py` · por que el CI no vigila produccion (Aviso 2).
- `docs/INVENTARIO-SECRETOS.xlsx` · unico lugar para URIs y passwords.
