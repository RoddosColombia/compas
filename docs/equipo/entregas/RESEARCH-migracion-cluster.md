# RESEARCH - Migracion de COMPAS a cluster MongoDB propio

Autor: Jose (Researcher 1) - 2026-09-14
Fuente de la tarea: handshake `docs/handshake_migrar_cluster_compas.md` (grilled, 2026-09-14)
Alcance: responder las 9 preguntas abiertas del handshake, en los 3 bloques pedidos. Sin ejecucion, sin conexion a ninguna base, sin plan de pasos (eso es tarea del planner).

## Contexto

COMPAS no abre porque `init_beanie` no logra completar el arranque contra el cluster compartido `sismo-v3` (nodo `sismo-v3-shard-00-01` en rollback loop 30+ dias). La salida acordada es sacar `compas` a un cluster Atlas propio, `compas-prod`, en la cuenta `info@roddos.com`, region `mx-central-1` (innegociable), tier M0 firme salvo que no quepa o no exista, caso en el cual la ruta ya decidida es subir a M10 en la misma region (nunca cambiar de region). Esas decisiones no se tocan aqui; este documento solo aporta hechos para ejecutarlas.

**Hallazgo que atraviesa todo el dossier (Bloque A):** Atlas NO ofrece M0 ni Flex en `mx-central-1`, solo M10+. Esto no es una opinion, es la tabla oficial de MongoDB (evidencia en A2). Por texto explicito del propio handshake ("Si Atlas Free no da M0 en mx-central-1, la ruta correcta es subir a M10 en mx-central-1, NO cambiar de region"), esto activa el fallback ya acordado: **M10 en mx-central-1**. No estoy reabriendo la decision de tier ni de region, estoy reportando el hecho que el propio handshake preveia y ya resolvio de antemano. Ver seccion de gaps para el unico punto que si amerita una alerta al CEO (el driver de costo del M0 no se cumple).

---

## Bloque A - bloquea crear el cluster

### A2 (pregunta 1) - Existe M0 en mx-central-1?

**Hecho verificado: NO.**

Tabla oficial de regiones AWS de Atlas (`https://www.mongodb.com/docs/atlas/reference/amazon-aws/`, consultado 2026-09-14):

| AWS Region | Ubicacion | Atlas Region | Free cluster / Atlas Flex | M10+ |
|---|---|---|---|---|
| `mx-central-1` | Queretaro, Mexico | `MX_CENTRAL_1` | NO soportado | Soportado |

La columna de la fuente combina Free y Flex en una sola casilla ("Free cluster/Atlas Flex Support"), y para `mx-central-1` esa casilla es NO. Es decir, ni M0 ni Flex existen en esta region hoy; solo clusters dedicados M10 en adelante.

**Consecuencia directa para A3:** la escalera de tiers economicos que pide el handshake (M0 -> tier intermedio barato -> M10) no aplica geograficamente. En `mx-central-1` no hay escalera: es M10 o nada.

**Consecuencia directa para el driver de costo del CEO:** la decision del CEO fue M0 con el driver explicito de "costo cero". Esa decision, tal como esta escrita, es fisicamente imposible en `mx-central-1`. El handshake ya preveia este escenario exacto y ya fijo la salida (M10, sin cambiar de region), asi que no hay decision nueva que tomar - pero SI hay un dato nuevo que el CEO debe conocer antes de que el planner arranque: el costo real minimo es ~USD 57-60/mes, no cero. Marco esto en gaps, no lo decido yo.

### A3 (pregunta 7) - Tiers economicos entre M0 y M10 hoy, y precio en mx-central-1

**Hecho verificado:** Atlas reemplazo los viejos tiers compartidos M2/M5 (y Serverless) por un tier unico llamado **Flex**, GA desde febrero de 2025; M2/M5/Serverless quedaron end-of-life el 22-ene-2026 (fuente: busqueda web sobre el anuncio de MongoDB, consultada 2026-09-14; recomiendo verificar contra el post oficial de MongoDB antes de citarlo en un documento externo, yo no pude abrir el blog post original, solo agregadores).

Specs de Flex (`https://www.mongodb.com/docs/atlas/reference/flex-limitations/`, consultado 2026-09-14):
- Storage maximo: 5 GB
- Throughput: hasta 500 operaciones/seg
- Backup: 1 snapshot diario (24h), sin point-in-time recovery, sin snapshots on-demand
- Precio (de fuentes secundarias, no pude confirmar en la pagina oficial de pricing que devolvio 404 en mi fetch): base ~USD 8/mes que cubre 5 GB y 100 ops/seg, con cargo variable por uso adicional, tope duro de ~USD 30/mes.

**Pero (hecho de A2): Flex tampoco esta disponible en `mx-central-1`.** La misma columna de la tabla de regiones que excluye M0 excluye Flex. Entonces la respuesta correcta a la pregunta 7 para esta migracion especifica es: **no existe ningun tier economico intermedio disponible en `mx-central-1`. Las unicas dos opciones reales en esta region son M0 (no disponible) y M10+ (disponible).**

### A1 (pregunta 8) - Tamano real de la db `compas` hoy

**REQUIERE EJECUCION EXTERNA.** No tengo acceso a la consola de Atlas ni al cluster. No puedo correr `db.stats()` (ademas, conectar al cluster viejo arriesga colgarse por el mismo problema de SDAM que motiva toda esta migracion - ver CRITICO 1 del handshake).

Dado el hallazgo de A2, esta medicion **ya no es bloqueante para elegir tier** (el tier ya esta forzado a M10 por region, no por tamano). Sigue siendo util para: (a) confirmar que el dump cabe comodo en el piso de 10 GB de M10, (b) dimensionar cuanto va a pesar el archivo que el CEO va a guardar en su disco como unica copia de seguridad, (c) tener una linea base de crecimiento.

Como obtenerlo sin dumpear (mas seguro dado CRITICO 1):

1. Atlas UI -> proyecto -> cluster `sismo-v3` -> pestana **Metrics** -> metrica **Data Size** o **Storage Size**, filtrada a la base `compas` si el dashboard lo permite por base; si el metrics es por cluster completo, restar el tamano de las demas bases del mismo cluster (SISMO usa el mismo cluster).
2. Alternativa si el dashboard no discrimina por base: Atlas UI -> **Data Explorer** en el cluster -> lista de bases -> `compas` suele mostrar tamano total y por coleccion en esa vista, sin necesidad de abrir un shell ni de que el driver haga SDAM completo (Data Explorer usa la capa de administracion de Atlas, no la ruta de conexion normal del cliente).
3. Si ninguna de las dos responde (cluster degradado tambien para el panel), la unica alternativa es medir con el dump mismo, siguiendo la escalera del CRITICO 1 del handshake (SRV normal -> directConnection al nodo sano -> readPreference forzado).

**Lo que necesito de vuelta:** el numero en MB/GB de la metrica Data Size de la base `compas` (screenshot o el valor exacto sirve).

---

## Bloque B - bloquea el switch de URI

### B1 (pregunta 4) - Creacion de usuarios en el cluster nuevo

**Hecho verificado, mas importante de lo que pedia la pregunta original:** no es un solo usuario. El sistema actual usa DOS usuarios y UN rol custom, y esto esta enforced por la regla 4 de CLAUDE.md (audit_log append-only, verificado por un test de CI):

Evidencia en `docs/RUNBOOK-INFRA.md:44-48`:
- Usuario `compas_app`: `readWrite` SOLO sobre la db `compas` (usuario general de la app).
- Rol custom `audit_writer`: `insert` + `find` sobre `compas.audit_log`, SIN `update`/`remove`.
- Usuario `compas_audit`: tiene SOLO el rol `audit_writer`. Es la identidad que usa `MONGODB_URI_AUDIT` (env var separada, ver `render.yaml:57-58`).
- Nota operativa citada literal del RUNBOOK: "Los usuarios creados por la UI autentican contra `admin` (las URIs NO llevan `authSource=compas`)."

Confirmado tambien en codigo: `backend/app/db/mongo.py:1-8` dice explicitamente que `AuditLog`, `User` y `RefreshSession` van por Motor crudo con conexion propia, separada del ODM general - esa separacion de identidades (`compas_app` vs `compas_audit`) es arquitectura, no un detalle de conveniencia.

**Como se crean (hecho verificado, con una contradiccion interna en el repo que dejo marcada):**

`docs/RUNBOOK-INFRA.md:47` trae una correccion explicita fechada 20-jul-2026: *"Atlas NO permite `createUser`/`createRole` por driver/mongosh en NINGUN tier (`CMD_NOT_ALLOWED`, AtlasError 8000) - los usuarios/roles se gestionan SOLO por Atlas UI o Admin API."* Esto esta marcado como "verificado en vivo" contra el cluster real M40 de SISMO.

Contradice el comentario del propio script `scripts/create_audit_role.py:19-21`, que dice *"createRole/createUser estan disponibles en M10+ ... En clusters Free/Flex estan BLOQUEADOS"* - esta nota del script quedo desactualizada; el RUNBOOK la reemplaza explicitamente ("CORRECCION ... reemplaza la nota Kimi H-01"). **Recomiendo al planner no confiar en el docstring del script y seguir el RUNBOOK: crear por Atlas UI, no por driver, sin importar que el tier nuevo sea M10.**

Click-path exacto en Atlas UI (cluster `compas-prod`, proyecto de la cuenta `info@roddos.com`):

1. **Database Access** (menu izquierdo, bajo Security) -> pestana **Custom Roles** -> **Add New Custom Role**.
   - Role Name: `audit_writer`
   - Add Privilege: Database `compas`, Collection `audit_log`, Actions: `insert`, `find` (nada mas).
   - Save.
2. **Database Access** -> pestana **Database Users** -> **Add New Database User**.
   - Authentication Method: Password.
   - Username: `compas_app`.
   - Password: autogenerada (guardarla de inmediato, Atlas no la vuelve a mostrar).
   - Database User Privileges: "Grant Database Access" -> role `readWrite` -> scope solo a la database `compas` (no "any database").
   - Save.
3. **Database Access** -> **Add New Database User** otra vez.
   - Username: `compas_audit`.
   - Password: autogenerada.
   - Database User Privileges: "Add custom role" -> `audit_writer` (scope: la db `compas`, que es donde vive `audit_log`).
   - Save.
4. Registrar ambas credenciales en `docs/INVENTARIO-SECRETOS.xlsx` de inmediato (regla de CLAUDE.md, es el unico lugar permitido para secretos en texto plano en este repo).

URI resultante de ejemplo (formato que ya usa el proyecto, sin `authSource` explicito porque Atlas lo resuelve solo, confirmado por la nota del RUNBOOK citada arriba):

```
MONGODB_URI_COMPAS=mongodb+srv://compas_app:<PASSWORD_APP>@compas-prod.xxxxx.mongodb.net/compas?retryWrites=true&w=majority&appName=compas-prod

MONGODB_URI_AUDIT=mongodb+srv://compas_audit:<PASSWORD_AUDIT>@compas-prod.xxxxx.mongodb.net/compas?retryWrites=true&w=majority&appName=compas-prod
```

(`xxxxx` es el sufijo que Atlas asigna al crear el cluster, visible en el boton "Connect" de la consola; ambas URIs apuntan a la MISMA base `compas`, solo cambia el usuario - igual que hoy.)

**Gap:** no pude confirmar si Atlas exige tambien recrear el indice forense de `audit_log` (`entidad, entidad_id, timestamp`, ver `scripts/create_audit_role.py:111-118`) o si eso lo cubre el `mongorestore` (los indices SI viajan en un dump completo con `mongodump`/`mongorestore` estandar, a diferencia de usuarios/roles). Mi lectura del codigo dice que el indice deberia venir con el restore; el planner deberia confirmarlo verificando `db.audit_log.getIndexes()` despues del restore, no asumirlo.

### B2 (pregunta 6) - URI en formato SRV, pymongo y dnspython

**Hecho verificado:** `backend/requirements.txt` fija `beanie==2.0.0` y `motor==3.7.1`, y NO fija `pymongo` ni `dnspython` de forma explicita (no hay pin directo, no hay lockfile en el repo - busque `.lock`/`poetry.lock`/`uv.lock` en `backend/` y no existe ninguno).

Cadena de dependencias verificada (via metadata de paquetes instalados, `pip show`):
- `motor==3.7.1` exige `pymongo>=4.9,<5.0` (dependencia declarada, no una suposicion).
- `pymongo` exige `dnspython>=2.6.1,<3.0.0` como dependencia **incondicional** (no es el extra `pymongo[srv]`; desde pymongo 4.3 dnspython es dependencia dura del paquete, confirmado por la documentacion/changelog de pymongo consultada 2026-09-14). Esto significa que la pregunta original ("verificar que `pymongo[srv]` esta instalado") esta un poco desactualizada: no hace falta el extra `[srv]`, dnspython viaja siempre con pymongo moderno.
- En el ambiente donde corri esta verificacion (no es el venv de Render, es un Python global de esta maquina con paquetes de varios proyectos) resolvio `pymongo==4.16.0` y `dnspython==2.8.0`, ambos dentro del rango que motor exige. Deberia ser representativo de lo que Render resuelve en build, pero no es prueba directa del build real de Render.

**Conclusion:** SRV esta soportado, sin cambios de codigo ni de `requirements.txt`. `mongodb+srv://` va a funcionar con la version de pymongo que se resuelva hoy en un `pip install -r requirements.txt` limpio.

**Gap (riesgo menor, no bloqueante):** como `pymongo` y `dnspython` no estan pineados, dos builds de Render en fechas distintas pueden resolver versiones de pymongo distintas (mientras se mantengan `>=4.9,<5.0`). No hay evidencia de que esto rompa nada hoy, pero es una fuente de no-reproducibilidad que el planner podria decidir cerrar (pinear `pymongo` explicito) - no lo hago yo porque es un cambio de codigo, fuera de mi alcance como researcher.

### B3 (pregunta 3) - Consumidores y allowlist

**Hecho verificado sobre quien existe hoy como consumidor real:**

1. **Render `compas-api` (servicio web).** Existe y esta vivo (`render.yaml:8-16`, plan `free`, region Render `ohio` - notese que la region de RENDER es Ohio, distinta de la region de ATLAS `mx-central-1`; son dos nubes distintas, el handshake ya lo asume). Este es el unico consumidor de produccion confirmado hoy.

2. **Worker `compas-jobs`.** **Hecho verificado, contradice un supuesto del handshake:** en `render.yaml:72-108` este servicio esta COMENTADO por completo, con la nota explicita "DIFERIDO a Sprint 5-6 ... Se RE-HABILITA (Starter) cuando existan los jobs." No hay bloque `type: worker` activo en el blueprint. Esto es consistente con la memoria de sesiones previas ("Go-live vigilante pendiente (ops CEO): worker compas-jobs ... pendiente"). **El CRITICO 2 del handshake pide "detener el worker compas-jobs en Render" como Paso 0 - si el worker no existe como servicio de Render, ese paso no aplica hoy tal como esta escrito.**
   - **REQUIERE EJECUCION EXTERNA para cerrar esto con certeza:** `render.yaml` puede estar desincronizado de lo que el CEO haya creado a mano en el dashboard (el principio rector del proyecto es "un solo entorno, minimizar pasos manuales", pero no puedo descartar que exista un worker creado manualmente sin reflejarse en el blueprint). Pido: entrar a Render Dashboard -> lista de Services del proyecto -> confirmar si aparece o no un servicio tipo Background Worker llamado `compas-jobs`. Si existe, si aplica el Paso 0 del CRITICO 1; si no existe, ese paso se salta y hay que anotarlo para cuando se active en el futuro.

3. **Cron de GitHub Actions (`keep-alive.yml`).** Existe y corre cada 10 min. **Hecho verificado: este cron NO necesita entrar al allowlist de Atlas.** Lee `.github/workflows/keep-alive.yml:53-60`: hace `curl -fsS https://api.compas.roddos.com/health`, un GET HTTP contra el dominio publico de Render, nunca abre una conexion Mongo directa. No es un consumidor de Atlas.

4. **La maquina del CEO cuando corre migraciones.** Consumidor real e intermitente (patron documentado en `docs/RUNBOOK-INFRA.md` y en los scripts de `migrations/`: `MONGODB_URI_COMPAS=... python migrations/xxx.py`). IP dinamica de home/oficina, no fija.

**Decision-ready por consumidor (dato, no decision mia):**

- Render `compas-api`: **Hecho verificado - Render Free NO ofrece IP de salida estatica nativa.** Confirmado en la documentacion oficial de Render sobre IPs de salida (`https://render.com/docs/static-outbound-ip-addresses`, consultado 2026-09-14): los rangos de IP de salida son compartidos, dependen de la region del servicio, se consultan por servicio en el Dashboard (Connect -> pestana Outbound), Y la propia documentacion de Render recomienda comprar "dedicated outbound IPs" (add-on de pago) para casos donde la estabilidad del IP importa para un allowlist de terceros. Ademas hay evidencia externa (busqueda web) de que esos rangos compartidos de Render **cambiaron en noviembre de 2025** sin que el allowlisting previo siguiera funcionando. Esto significa que meter rangos especificos de Render hoy en el allowlist de Atlas es fragil: si Render vuelve a rotar esos rangos, el `compas-api` se cae del allowlist sin aviso y el sintoma se ve identico al bug que se esta arreglando (backend que no conecta a Mongo).
- La maquina del CEO: IP dinamica, no allowlisteable de forma estable sin un servicio de IP fija.
- Precedente directo del propio proyecto: `docs/RUNBOOK-INFRA.md:50` documenta que el cluster COMPARTIDO de SISMO-V3 (el que hoy aloja `compas`, tier M40, el mas critico de los dos) tiene `0.0.0.0/0` en su IP Access List HOY, marcado como "pendiente de seguridad ... restringir antes del go-live". Es decir, el patron ya establecido y vigente en este proyecto para la fase de desarrollo es abrir el allowlist y cerrarlo en go-live, exactamente lo que dice el principio rector de CLAUDE.md ("un solo entorno... minimizar fricicion... endurecer en go-live").

**REQUIERE EJECUCION EXTERNA:** el rango exacto de IPs de salida de Render para `compas-api` (Render Dashboard -> servicio `compas-api` -> boton **Connect** -> pestana **Outbound**). Lo pido solo para que quede documentado en `INVENTARIO-SECRETOS.xlsx`, no porque lo recomiende como estrategia primaria dado el punto anterior.

No decido la politica final; dejo los datos para que el planner y el CEO decidan con el precedente ya sentado por el propio proyecto.

### B4 (pregunta 5) - Timeout de arranque en Render

**Hecho verificado, y es una buena noticia que cambia el marco de la pregunta:** el `healthCheckPath` de `render.yaml:38` es `/health`, NO `/api/v1/health/ready`. Este es un cambio deliberado documentado en el propio `render.yaml:26-38` (comentario "REGRESION 2026-09-03") y en `backend/app/api/v1/health.py:1-16`: `/health` es liveness pura, **no depende de Mongo en absoluto** (confirmado leyendo el codigo del endpoint en `backend/app/main.py` - no hay ninguna llamada a Mongo antes de que `/health` pueda responder). El endpoint que SI depende de Mongo/Beanie es `/api/v1/health/ready` (`backend/app/api/v1/health.py:35-67`), y ese ya NO es el que usa Render para decidir si promociona un deploy.

Esto importa porque el riesgo que describe la pregunta 5 (DNS SRV + TLS handshake + descubrimiento SDAM + `init_beanie` revalidando indices, todo antes de que Render considere el deploy exitoso) **ya no puede pasar por el health check de promocion de Render**, porque ese health check no toca Mongo. El primer arranque contra el cluster nuevo puede tardar lo que tarde en conectar a Mongo sin que eso bloquee que Render marque el deploy como sano.

Ademas, el propio codigo ya fue endurecido especificamente para el escenario de latencia cross-region (comentario en `backend/app/db/mongo.py:9-13,44-45` y `backend/app/main.py` funcion `ensure_beanie`, `_BEANIE_TIMEOUT_S = 30.0`, fix fechado 2026-09-03):
- `init_beanie_for` registra los modelos con `skip_indexes=True` por defecto - NO toca la red para crear indices durante el arranque critico.
- `ensure_beanie` envuelve el registro en un `asyncio.wait_for(..., timeout=30.0)` y es explicitamente NO fatal: si falla o da timeout, deja `beanie_ready=False`, loguea la causa por stderr, y el servicio sigue vivo. `/api/v1/health/ready` reportara 503 hasta que conecte; el middleware lazy (mencionado en `health.py:14`, PR #152) reintenta en el siguiente request real.
- El comentario del propio fix explica la causa raiz historica: el timeout viejo de 15s no lo agotaba el ping (~0.1s) sino la creacion en serie de indices de los 25 Documents contra Atlas cross-region - ese problema ya esta resuelto de raiz, independientemente de esta migracion.

**Sobre el limite de plataforma de Render (no configurable en `render.yaml`):** segun la documentacion oficial de Render (`https://render.com/docs/health-checks`, consultada 2026-09-14), un check HTTP se considera exitoso con 2xx/3xx dentro de 5 segundos, y **para un deploy nuevo Render espera hasta 15 minutos** a que la nueva instancia responda sano antes de cancelar el deploy y seguir sirviendo la version vieja. Ese valor de 15 minutos aparece como comportamiento fijo de la plataforma, no encontre un campo en `render.yaml` para configurarlo (el unico campo relacionado con salud del servicio en el blueprint es `healthCheckPath`).

**Recomendacion basada en esta evidencia (no una decision, un dato para el planner):** dado que `/health` no depende de Mongo, no hace falta ningun bump de timeout en Render para el switch de URI. El riesgo real no es que el deploy falle en promocionarse, es que las primeras requests reales a la API devuelvan 503 por unos segundos (o hasta 30s por el safety net) mientras `ensure_beanie` conecta por primera vez al cluster nuevo - eso es exactamente el "patron autocurativo" que el propio codigo ya documenta como diseño esperado, no un bug a mitigar con configuracion de Render.

**Gap:** no pude confirmar si existe algun timeout adicional a nivel de Render que no este documentado publicamente (por ejemplo, algun limite interno de arranque del proceso antes de que el puerto quede escuchando). Si el planner quiere blindarse del todo, la unica forma de confirmarlo es observar el log de deploy real el dia del switch (`[ensure_beanie]` en stderr, mencionado en el propio codigo) - no hay forma de simularlo sin cortar sobre el cluster real.

---

## Bloque C - operacion y verificacion

### C1 (pregunta 9) - Auto-pausa de M0 y el keep-alive

**Hecho verificado sobre la politica de Atlas (aplica igual a Free y, con matices, a Flex):** Atlas pausa automaticamente un cluster Free tras **30 dias sin ninguna conexion**, avisando por email 7 dias antes y de nuevo al pausar; el cluster se puede reanudar en cualquier momento salvo que haya quedado en una version que Atlas ya no soporte restaurar (fuente: documentacion oficial + foro de la comunidad de MongoDB, consultada 2026-09-14). Esto es distinto al "duerme por inactividad" de Render Free, que es cuestion de minutos, no dias.

**Hecho verificado sobre si el keep-alive actual previene esto:** **NO, y esto es cierto sin importar el tier.** Lei `.github/workflows/keep-alive.yml:53-60` completo: hace un `curl` HTTP contra `https://api.compas.roddos.com/health`. Ese endpoint, confirmado en B4, es liveness pura y no abre ninguna conexion a Mongo. El cron mantiene despierto a Render, pero nunca toca Atlas. Si el cluster fuera Free/Flex, este cron no cuenta como "actividad" para efectos de la politica de auto-pausa de Atlas.

**Pero, por el hallazgo de A2, esto queda sin efecto practico para esta migracion:** con el fallback ya acordado a M10, la pregunta deja de aplicar - **los clusters dedicados (M10 en adelante) no tienen auto-pausa por inactividad**, esa politica es exclusiva de Free y Flex. Documento la respuesta completa por si en algun momento futuro se reconsiderara un tier compartido en otra region, pero para el plan actual (M10 en `mx-central-1`) no hay riesgo de auto-pausa que mitigar.

### C2 (pregunta 2) - Colecciones esperadas en `compas`

**Hecho verificado, lista completa por lectura de codigo (no supuesta):**

Documents registrados en Beanie, fuente unica `backend/app/domain/__init__.py:32-58` (`DOMAIN_DOCUMENTS`, 25 modelos). Nombre real de coleccion (constante `_COLLECTION`, verificado con grep, no el nombre de archivo ni de clase):

| Coleccion (nombre real en Mongo) | Fuente (file:line) |
|---|---|
| `rubros` | `backend/app/domain/rubro.py:22` |
| `meses_control` | `backend/app/domain/mes_control.py:22` |
| `configuracion` | `backend/app/domain/configuracion.py:22` |
| `transacciones` | `backend/app/domain/transaccion.py:33` |
| `cargas` | `backend/app/domain/carga.py:25` |
| `idempotency_keys` | `backend/app/domain/idempotency.py:17` |
| `presupuesto_lineas` | `backend/app/domain/presupuesto.py:23` |
| `reglas_clasificacion` | `backend/app/domain/regla_clasificacion.py:31` |
| `pagos_planeados` | `backend/app/domain/pago_planeado.py:24` |
| `modelos_moto` | `backend/app/domain/modelo_moto.py:21` |
| `parametros_proyeccion` | `backend/app/domain/parametros_proyeccion.py:29` |
| `cartera_previa_recaudo` | `backend/app/domain/cartera_previa.py:18` |
| `colocacion_mes` | `backend/app/domain/cartera_previa.py:19` |
| `facturas` | `backend/app/domain/factura.py:28` |
| `loantape_creditos` | `backend/app/domain/loantape.py:23` |
| `gastos_recurrentes` | `backend/app/domain/gasto_recurrente.py:24` |
| `escenarios_impacto` | `backend/app/domain/escenario_impacto.py:43` |
| `obligaciones` | `backend/app/domain/obligacion.py:53` |
| `facturas_obligacion` | `backend/app/domain/obligacion.py:117` |
| `metas_ingreso` | `backend/app/domain/obligacion.py:146` |
| `proyeccion_versiones` | `backend/app/domain/proyeccion_version.py:25` |
| `cfo_goldens` | `backend/app/cfo/goldens/modelo.py:14` |
| `cfo_vinculos_telegram` | `backend/app/cfo/telegram/modelos.py:12` |
| `cfo_hilos` | `backend/app/cfo/telegram/modelos.py:13` |
| `cfo_avisos_vigilante` | `backend/app/cfo/vigilante/modelos.py:13` |

Colecciones que NO son Documents de Beanie, van por Motor crudo (`backend/app/db/mongo.py:5-7`, `backend/app/audit/models.py:19`, `backend/app/auth/models.py:14-17`):

| Coleccion | Fuente |
|---|---|
| `audit_log` | `backend/app/audit/models.py:19` |
| `users` | `backend/app/auth/models.py:14` |
| `refresh_sessions` | `backend/app/auth/models.py:15` |
| `jwt_denylist` | `backend/app/auth/models.py:16` |
| `login_throttle` | `backend/app/auth/models.py:17` |

**Total: 30 colecciones esperadas.**

**Cuales deberian tener data real (evidencia por migracion, no adivinado):** hice grep de los 24 scripts en `migrations/*.py` buscando los nombres reales de coleccion de la tabla de arriba. 20 de los 24 scripts referencian al menos una de: `rubros`, `reglas_clasificacion`, `cartera_previa_recaudo`, `transacciones`, `facturas`, `presupuesto_lineas`, `configuracion`. Estas son las colecciones con **evidencia directa de siembra/carga real** (incluye `transacciones`, donde vive la caja curada mar-jul del CEO segun `migrations/20260726_carga_inicial_global66.py`, el nombre del archivo coincide con lo que describe el handshake).

Las 4 migraciones que no matchearon esos nombres y el resto de colecciones (`idempotency_keys`, `modelos_moto`, `colocacion_mes`, `loantape_creditos`, `obligaciones`, `facturas_obligacion`, `metas_ingreso`, `proyeccion_versiones`, `cfo_goldens`, `cfo_vinculos_telegram`, `cfo_hilos`, `cfo_avisos_vigilante`, `users`, `refresh_sessions`, `jwt_denylist`, `login_throttle`, `audit_log`) son de escritura en tiempo de ejecucion (login, uso del chat FABS/Telegram, aprobaciones, jobs del vigilante) - **no tengo forma de saber sin conectar si ya tienen documentos o estan vacias**, y no lo voy a adivinar. El dump completo se las lleva a todas igual (por definicion, es todo el `compas`), asi que esto no bloquea nada; sirve solo para que despues del restore el planner sepa que un conteo en cero en, por ejemplo, `cfo_hilos` no es necesariamente un restore roto - puede ser que nunca hubo data ahi.

**Gap:** no pude correr un conteo real por coleccion contra el cluster viejo (mismo problema de conexion del CRITICO 1). El paso de verificacion post-restore del handshake ("contar documentos por coleccion, comparar contra el viejo") va a necesitar un conteo ANTES tambien, idealmente sacado en el mismo momento del dump (`mongodump` ya lo hace de forma implicita: el numero de documentos exportados por coleccion queda en su log de salida).

---

## Opciones evaluadas

Solo hubo una decision real con opciones (la escalera de tier); documentada en A2/A3 arriba. Para el resto de preguntas, la respuesta fue un hecho verificable, no una eleccion entre alternativas.

| Opcion | Storage | Backup | Disponible en mx-central-1 | Precio aprox/mes |
|---|---|---|---|---|
| M0 (Free) | 0.5 GB | Ninguno | NO | 0 |
| Flex | 5 GB | 1 snapshot diario, sin PITR | NO | ~USD 8-30 (variable, tope 30) |
| M10 | 10-128 GB | Segun se configure (fuera de alcance de este research verificar el default exacto) | SI | ~USD 57-60 |

Con la columna 4 en NO/NO/SI, no hay una eleccion real que evaluar para esta migracion: M10 es la unica opcion que existe en la region ya decidida.

## Recomendacion

No me corresponde recomendar plan de ejecucion (eso es tarea de Andres, planner). Lo que si puedo recomendar, como researcher, es sobre la calidad de la informacion para que el planner no arranque con supuestos rotos:

1. **Avisar al CEO antes de que el planner arranque** que el driver de costo detras de M0 ("supremamente economica", "no se arranca en M10") no se puede cumplir en `mx-central-1` - la unica ruta tecnica es M10 (~USD 57-60/mes). El handshake ya preveia y resolvio este escenario exacto, pero el CEO tomo la decision original de M0 pensando que existia margen para elegirlo; ese margen no existe. Esto no es mio para decidir, es mio para señalar con evidencia antes de que se gaste tiempo de ejecucion sobre un supuesto que la propia documentacion de Atlas descarta.
2. Verificar el estado real del worker `compas-jobs` en el Render Dashboard (B3) ANTES de que el planner escriba el Paso 0 del CRITICO 1 - si el worker no existe, ese paso del plan cambia de "detener servicio X" a "no aplica, dejar nota para cuando se active".
3. Seguir el RUNBOOK (Atlas UI/Admin API) para crear usuarios y rol, no el comentario desactualizado del script `create_audit_role.py` (B1).
4. No agregar rangos de IP de Render al allowlist de Atlas como estrategia primaria (B3) - son compartidos, rotan sin aviso (ya rotaron en nov-2025), y el propio proyecto ya tiene precedente de abrir `0.0.0.0/0` en desarrollo y cerrar en go-live.
5. No tocar `render.yaml` para el switch (B4) - `/health` ya esta desacoplado de Mongo, el riesgo de timeout de arranque contra un cluster nuevo ya fue resuelto en el fix de 2026-09-03, independiente de esta migracion.

## Gaps (lo que no pude verificar, y por que)

1. **A1 - tamano real de `compas`.** Requiere consola de Atlas (Metrics o Data Explorer del cluster `sismo-v3`). Ya no es bloqueante para el tier (forzado a M10 por region), pero si util para dimensionar el dump. Pido el numero de la metrica Data Size.
2. **B3 - existencia real del worker `compas-jobs` en Render.** `render.yaml` lo muestra comentado/diferido, pero el blueprint puede estar desincronizado de lo creado a mano en el dashboard. Pido confirmar en Render Dashboard -> Services.
3. **B3 - rango exacto de IPs de salida de `compas-api`.** Render Dashboard -> servicio `compas-api` -> Connect -> pestana Outbound. Lo pido solo para dejarlo documentado, no lo recomiendo como estrategia de allowlist primaria (ver razones arriba).
4. **B1 - si el indice forense de `audit_log` sobrevive al `mongorestore`.** Mi lectura de como funciona `mongodump`/`mongorestore` dice que si (los indices viajan en un dump completo), pero no lo tengo verificado contra este caso especifico. Pido al planner confirmarlo con `db.audit_log.getIndexes()` despues del restore, no asumirlo.
5. **A3 - precio exacto de Flex y de M10 en dolares, de la pagina oficial de pricing de MongoDB.** La pagina de pricing detallada me devolvio 404 en el fetch directo; los numeros que doy vienen de fuentes secundarias (agregadores) mas la referencia rapida de la propia calculadora citada por MongoDB. Como Flex no aplica a esta region, el impacto de este gap es bajo, pero si el CEO quiere el numero exacto de M10 en `mx-central-1` especificamente (puede variar vs. us-east-1), la unica fuente confiable es la calculadora oficial (`https://www.mongodb.com/pricing/calculator`), que no pude usar de forma interactiva.
6. **C2 - cuales colecciones de "escritura en tiempo de ejecucion" tienen documentos hoy.** No puedo saberlo sin conectar (ver lista completa en C2). El dump se las lleva a todas de todas formas; el gap solo afecta la interpretacion de la verificacion post-restore (un conteo en cero no es necesariamente un error).
7. **B2 - version exacta de pymongo que resuelve el build real de Render.** No pineada en `requirements.txt`, no hay lockfile. Lo que reporto (`pymongo==4.16.0`) es de un ambiente Python local con paquetes de varios proyectos, representativo pero no una prueba directa del build de Render.

## Related

- `docs/handshake_migrar_cluster_compas.md` - decisiones cerradas y las 9 preguntas originales.
- `docs/RUNBOOK-INFRA.md` §2 - usuarios/roles existentes, precedente de `0.0.0.0/0` en dev.
- `backend/app/db/mongo.py`, `backend/app/main.py`, `backend/app/api/v1/health.py` - evidencia de codigo del fix de arranque 2026-09-03.
- `render.yaml` - estado real de los servicios (worker diferido, healthCheckPath).
- `scripts/create_audit_role.py`, `scripts/create_auth_indexes.py` - scripts de provisioning existentes, uno con un comentario desactualizado (ver B1).
