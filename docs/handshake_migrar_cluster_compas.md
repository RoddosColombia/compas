# Handshake · Migrar COMPAS a su propio cluster MongoDB

Status: grilled · 2026-09-14

## La idea en palabras planas

COMPAS hoy no abre porque su base de datos vive dentro de un edificio grande que se llama "cluster de SISMO", y una parte de ese edificio (el nodo 01) lleva mas de un mes rota. Cada vez que COMPAS intenta despertarse, se queda esperando a que esa parte responda y nunca lo hace, asi que la app nunca termina de arrancar.

La solucion es que COMPAS deje ese edificio y se mude a uno propio. Se crea un cluster nuevo en MongoDB Atlas (misma plataforma), tamano free (M0), dentro de la misma cuenta `info@roddos.com` y, muy importante, en la misma region donde vive SISMO hoy: `mx-central-1` (Mexico). El cluster nuevo se llama `compas-prod` y es totalmente autonomo del de SISMO.

Por que la region tiene que ser la misma que SISMO, sin negociar: COMPAS lleva meses hablando con MongoDB en `mx-central-1`, y todos sus tiempos (arranque, timeouts, health checks) estan calibrados a esa latencia. Si se mueve el cluster a otra region, cada llamada al MongoDB tarda decenas de milisegundos mas; el `init_beanie` del arranque hace decenas de esas llamadas, asi que el backend puede volver a colgarse al despertar, pero ahora por causa nueva (la latencia), no por la que se esta curando. Seria cambiar dos cosas a la vez en una migracion critica. Si Atlas Free no ofrece M0 en `mx-central-1`, en vez de cambiar la region se sube a M10 (aproximadamente 60 USD al mes) en `mx-central-1`.

Despues se copia toda la base de datos vieja al cluster nuevo con `mongodump` (una foto binaria) y `mongorestore` (pegar la foto en el destino). Se lleva todo, incluida la caja curada mar-jul que el CEO trabajo a mano y no se puede volver a generar automaticamente.

Cuando la copia esta completa y verificada, se cambia una sola variable en Render (`MONGODB_URI_COMPAS`) para que apunte al cluster nuevo. Se guarda la variable vieja como respaldo (`MONGODB_URI_COMPAS_OLD`) por 48 horas por si algo sale mal y hay que devolverse.

El resultado: el CEO entra a compas.roddos.com, la app carga, y COMPAS ya nunca depende de que SISMO este sano.

## Por que importa

COMPAS no abre. El backend cuelga en el arranque porque `init_beanie` no logra descubrir la topologia del replica set: el nodo `sismo-v3-shard-00-01` del cluster compartido con SISMO lleva 30+ dias en rollback loop (ticket abierto por el CEO con MongoDB Support, sin ETA). Mientras eso siga asi, cualquier deploy de COMPAS falla en el arranque aunque el codigo este perfecto. La unica salida limpia y bajo nuestro control es que COMPAS deje de depender de la salud del cluster de SISMO.

## Para quien es

- CEO (Andres) · desbloquear el uso de COMPAS ya, y quitarnos la dependencia operativa de un cluster que no controlamos.
- Cualquier desarrollo futuro de COMPAS · el cluster propio se vuelve el sustrato estable sobre el que se construye.

## Que existe hoy

- Backend en Render Free (`compas-api`), auto-deploy desde `main`.
- Cluster actual: `sismo-v3` en Atlas, region `mx-central-1` (M40, compartido con SISMO).
- Base de datos en ese cluster: `compas` (colecciones sembradas idempotentes: `configuracion`, `users`, etc., mas colecciones que la app usa: `parametros_proyeccion`, `modelos_moto`, `movimientos`, `caja`, ...).
- Caja curada mar-jul: data hecha a mano por el CEO desde el Excel (aproximadamente 704.7 millones COP), no re-sembrable automaticamente.
- URI en env var `MONGODB_URI_COMPAS` en Render.
- Migraciones idempotentes en `migrations/` (patron: `MONGODB_URI_COMPAS=... python migrations/xxx.py`; ver `20260901_seed_configuracion.py` como referencia).
- `backend/app/db/mongo.py` centraliza el cliente y `init_beanie_for(client, db_name)`.

## Como se ve el exito

El CEO abre `compas.roddos.com`, la app carga, puede navegar y editar configuracion, y ni una sola linea del backend habla con el cluster `sismo-v3`. Comprobable con:

- El navegador entra.
- `/api/v1/health/ready` responde 200.
- `MONGODB_URI_COMPAS` en Render apunta al cluster nuevo.
- La caja curada mar-jul sigue visible con los mismos valores.

## Decisiones ya tomadas

- COMPAS se saca del cluster `sismo-v3` y va a un cluster MongoDB propio.
- **Proveedor:** MongoDB Atlas (mismo proveedor de hoy).
- **Tier: M0 (free). Decision firme del CEO, 2026-09-14, tras leer el grill.** El driver de esta decision es costo: esta base tiene que ser supremamente economica. El CEO **declaro explicitamente que no se requiere backup** y **acepto el riesgo** que eso implica (ver "Riesgo aceptado" abajo). No se arranca en M10.
- **Region:** la misma que SISMO (`mx-central-1`), innegociable. Motivos, en orden de peso:
  1. **Latencia conocida y validada.** Render `compas-api` ya lleva meses hablando con MongoDB en `mx-central-1`; los tiempos de respuesta, el `init_beanie` al arranque y todos los timeouts internos estan calibrados a esa latencia. Mudarse a otra region (aunque sea "mas cerca de Render") mete un perfil de red nuevo y no verificado.
  2. **Cross-region multiplica los timeouts en el arranque.** `init_beanie` hace decenas de roundtrips al MongoDB (descubre topologia, crea indices, valida schemas). Cada roundtrip a otra region suma decenas de ms; el arranque total puede pasarse del timeout de 15s de Render y **re-introducir exactamente el mismo sintoma que se esta tratando de curar** (backend colgado al despertar), pero por otra causa (latencia, no salud del nodo).
  3. **Predictibilidad.** COMPAS funcionaba cuando el cluster estaba sano en `mx-central-1`. Cualquier otra region es una variable nueva; en una migracion critica, cambiar dos cosas a la vez (cluster mas region) es debuggear dos hipotesis mezcladas.
  4. **Consistencia operativa.** Reglas de compliance, limites de datos y latencias que ya se conocen.

  Si Atlas Free no da M0 en `mx-central-1`, la ruta correcta es **subir a M10 en `mx-central-1`** (aproximadamente 60 USD al mes), NO cambiar de region para conservar el tier Free.
- **Cuenta Atlas:** la misma de hoy (`info@roddos.com`), pero cluster nuevo, autonomo, sin dependencias con `sismo-v3`.
- **Nombre del cluster nuevo:** `compas-prod`.
- **Data a migrar:** dump completo de la db `compas` (`mongodump` mas `mongorestore`). Se lleva todo tal como esta y se limpia despues si aparece algo sucio.
- **Downtime aceptable:** ventana corta (5-15 min). Sin impacto marginal porque COMPAS ya no abre.
- **Rollback plan:** guardar la URI vieja en Render como env var alterno `MONGODB_URI_COMPAS_OLD` por 48h. Si el cluster nuevo falla, se revierte con un cambio de env var mas redeploy en 2 min.

## Decisiones aun abiertas

Ninguna decision propiamente abierta. La sesion de grill del 2026-09-14 abrio 4 riesgos criticos con mitigacion (seccion nueva abajo) y 4 puntos que Jose (researcher) resuelve en su dossier (ver "Preguntas abiertas para investigacion").

## Riesgos criticos con mitigacion (grill 2026-09-14)

Los 4 riesgos siguientes son huecos del plan original detectados en la sesion de stress-testing. NINGUNO se puede ignorar; cada uno tiene mitigacion obligatoria antes de ejecutar la migracion.

### CRITICO 1 · `mongodump` contra el cluster viejo puede colgarse igual que `init_beanie`

**Riesgo:** `mongodump` no usa Beanie, pero usa el mismo protocolo de descubrimiento de topologia (SDAM) que Beanie. El nodo `sismo-v3-shard-00-01` en rollback loop puede colgar el descubrimiento igual. Si el dump se cuelga, no hay data para restaurar y toda la migracion se cae.

**Mitigacion obligatoria:**

1. **Primer intento:** `mongodump` con URI SRV normal. Si funciona en menos de 5 min, se procede.
2. **Segundo intento (si el primero cuelga):** conectar por URI directo a un nodo sano identificado, saltando SDAM: `mongodb://<host-sano>:27017/?directConnection=true&tls=true&authSource=admin`. Requiere identificar cual nodo esta sano ANTES (Atlas UI muestra estado por nodo).
3. **Tercer intento (si el segundo tambien cuelga):** `mongodump` con `--readPreference=secondaryPreferred` explicito y `--host` apuntando a la lista de nodos sanos manualmente.
4. **Plan B ultimo recurso (si los 3 intentos fallan):** re-sembrar el cluster nuevo desde cero con las migraciones idempotentes existentes y reconstruir a mano la caja curada mar-jul desde `docs/Global66_MovimientosCuentaCOP_*.xlsx` del CEO. Costo estimado: varias horas del CEO. **Este plan B debe estar aceptado ANTES de arrancar, no se decide sobre la marcha.**

### CRITICO 2 · Perdida silenciosa de writes durante la ventana de migracion

**Riesgo:** el snapshot de `mongodump` toma la data en un instante t; todo write al cluster viejo entre t y el switch de URI se pierde. Aunque el CEO no puede escribir (COMPAS no abre desde el front), procesos automatizados podrian estar escribiendo: worker `compas-jobs` (FABS, vigilante, cierre mensual), cron de keep-alive, cualquier script del CEO.

**Mitigacion obligatoria (Paso 0 de la ejecucion, antes de cualquier otra cosa):**

1. **Detener el worker `compas-jobs` en Render** (Suspend). Confirmar en la consola que quedo en estado detenido.
2. **Verificar que no hay ninguna migracion ni script del CEO corriendo** contra el cluster viejo.
3. **Anunciar ventana de migracion.** Aunque el CEO sea el unico usuario, dejar constancia del inicio.
4. Solo entonces arrancar `mongodump`.

Al terminar el switch de URI, re-encender `compas-jobs` apuntado al cluster nuevo.

### CRITICO 3 · M0 tiene 512 MB de storage y CERO backup automatico

**Riesgo:** Atlas Free tier real: 512 MB de storage, sin backup automatico, sin point-in-time recovery, auto-pausa tras inactividad prolongada. Consecuencias: (a) si la db actual supera 512 MB, el restore falla sin remedio; (b) aunque quepa hoy, la caja curada + movimientos + FABS + cartera crece con el uso; (c) un cluster sin backup en produccion no es aceptable ni un solo dia.

**Resolucion del CEO (2026-09-14):** M0 confirmado. No se requiere backup. Riesgo aceptado. El arbol de decision por tamano se mantiene, porque el cap de 512 MB no es una preferencia sino un limite fisico: si la data no entra, M0 es imposible independientemente del presupuesto.

**Riesgo aceptado (decision trazable del CEO):**

El CEO acepta operar COMPAS en un cluster **sin backup automatico y sin point-in-time recovery**. Consecuencia concreta y entendida: si el cluster se corrompe, se borra por error, o Atlas lo suspende, **la data de COMPAS se pierde y no hay restore**. La unica red de seguridad es el dump manual que se saque durante esta migracion (que debe conservarse en disco del CEO, no borrarse tras el restore) y cualquier dump manual futuro que se decida sacar. Driver de la decision: costo. El CEO prioriza costo cero sobre red de seguridad automatica en esta etapa.

**Mitigacion obligatoria (Paso 0.5 de la ejecucion, antes de crear el cluster):**

1. **Medir el tamano real del dump ANTES de crear el cluster nuevo.** Correr el dump completo a disco y medir el directorio resultante. Si el dump supera **400 MB** (80% del cap de M0), M0 no es viable y aplica la escalera de tier de abajo.
2. **Escalera de tier, de mas barato a mas caro (solo se sube si el anterior no entra):**
   - **M0** (free, 512 MB, sin backup) · la eleccion del CEO. Se usa si el dump entra con margen.
   - **Tier intermedio compartido** (historicamente M2/M5, hoy posiblemente reemplazados por el tier "Flex" de Atlas; precio del orden de unas pocas decenas de USD al mes) · **Jose debe verificar que ofrece Atlas hoy y a que precio en `mx-central-1`** (ver pregunta abierta 7). Esta es la escalacion correcta si M0 no alcanza, NO M10.
   - **M10** (aproximadamente 60 USD al mes) · ultimo recurso, solo si ni M0 ni el tier intermedio sirven.
   - **Alternativa antes de subir de tier:** podar data antes de migrar (archivar colecciones historicas que no se consultan, limpiar data de pruebas). Se evalua solo si el dump esta apenas por encima del cap.
3. **Conservar el dump de la migracion en disco del CEO de forma permanente.** Con M0 sin backup, ese dump es la unica copia de seguridad existente del estado previo. No borrarlo tras el restore.
4. **Senal de alerta para revisar la decision (no escalacion automatica, solo aviso al CEO):** cuando el uso de storage supere 350 MB (70% del cap), avisar al CEO para que decida si poda data o sube de tier. El CEO decide, no se escala solo.

### CRITICO 4 · El rollback plan tiene una trampa silenciosa de data loss

**Riesgo:** El plan dice "guardar `MONGODB_URI_COMPAS_OLD` por 48h, si algo falla revertir". Pero si en esas 48h se escribio al cluster nuevo (CEO configurando, FABS narrando, jobs corriendo) y despues volvemos al viejo, esos writes se pierden.

**Mitigacion obligatoria:**

1. **Aclarar en la ejecucion:** el rollback es "seguro sin data loss" **solo antes del primer write al cluster nuevo**. Despues del primer write, rollback significa perder esos writes.
2. **Definir checkpoint de no-retorno explicito.** Propuesta: tras 1 hora de operacion sana con al menos un write confirmado, se marca el punto de no-retorno; a partir de ese momento, un rollback deja de estar sobre la mesa y el fix es hacia adelante (patch al cluster nuevo, no vuelta al viejo).
3. **Al llegar al no-retorno:** borrar `MONGODB_URI_COMPAS_OLD` de Render para eliminar la tentacion de rollback silencioso.
4. **Documentar el checkpoint en el commit de cierre de la migracion**, para trazabilidad.

## Constraints y guardarrailes

- No debe romperse ni tocarse el cluster de SISMO (es de otro producto en produccion).
- Los secretos del cluster nuevo NUNCA en el repo. Solo en Render env vars y en `docs/INVENTARIO-SECRETOS.xlsx` (allowlisted por CLAUDE.md).
- Todo movimiento con evidencia (ping, logs de deploy, prints de `[lifespan]`). No especular.
- Reglas innegociables del CLAUDE.md siguen vigentes (Decimal, TZ Bogota, RBAC, motor intocable, etc.).
- Migraciones prod: URI por env var, nunca argv; `PYTHONUTF8=1` en Windows.

## Fuera de alcance

- Migrar SISMO fuera de su cluster (es otro producto, otro equipo).
- Cambiar de proveedor de deploy (Render sigue).
- Reescribir codigo de `backend/app/db/mongo.py`, solo se cambia la URI.
- El bug de UX de "pagina en blanco" en `DatosPage` (bug real, pero desligado de este handshake).

## Preguntas abiertas para investigacion

Estas preguntas son tarea del researcher (Jose) antes de que se pueda ejecutar la migracion. El dossier que entregue Jose debe responderlas todas con evidencia.

**Del handshake original:**

1. **Atlas M0 disponible en `mx-central-1`?** Atlas Free tiene disponibilidad limitada por region. **Si `mx-central-1` no ofrece M0, la ruta acordada es M10 en `mx-central-1`** (aproximadamente 60 USD al mes), la region no se cambia. Bloqueante ANTES de crear el cluster.
2. Cual es la lista real de colecciones con data escrita hoy en la db `compas` del cluster viejo? Determina que hay que dumpear vs que basta con re-sembrar. Nota: el dump completo cubre esto por definicion, pero saber la lista ayuda a verificar la copia despues.

**Anadidas por grill 2026-09-14 (SIGNIFICATIVOS):**

3. **Enumerar consumidores que necesitan acceso al cluster nuevo (allowlist).** Al menos: Render `compas-api`, worker `compas-jobs`, cron GH Actions de keep-alive, maquina del CEO cuando corre migraciones. Decidir por cada uno si va con `0.0.0.0/0` durante la ventana y se endurece despues, o si desde el dia 1 va con rangos especificos.
4. **Creacion de usuarios de Atlas en el cluster nuevo.** `mongorestore` NO copia usuarios. El usuario `compas-app` con rol `readWrite` sobre db `compas` debe crearse manualmente en el cluster nuevo, con password nuevo, y guardarse en `INVENTARIO-SECRETOS.xlsx`. Jose debe entregar el paso exacto (comando o click-path en Atlas UI) y la URI resultante ejemplo.
5. **Timeout de arranque en Render tras el switch.** Primer arranque contra cluster nuevo paga DNS SRV, TLS handshake, SDAM discovery inicial, `init_beanie` con re-validacion de indices. Puede exceder los 15s calibrados a la latencia actual. Jose debe: (a) confirmar el timeout de startup actual en la config de Render, (b) proponer bump temporal (60s) para el deploy del switch y vuelta al normal despues.
6. **URI en formato SRV explicito y dependencias.** El driver descubre topologia desde el SRV; propuse una vez URI non-SRV y me corrigieron. Jose debe: (a) verificar que `pymongo[srv]` con `dnspython` esta instalado en `backend/pyproject.toml` o `requirements.txt`; (b) anclar en el plan que la URI del cluster nuevo va obligatoriamente en formato `mongodb+srv://`; (c) confirmar la version de pymongo instalada soporta SRV con Atlas actual.

7. **Que tiers economicos ofrece Atlas hoy entre M0 y M10, y a que precio en `mx-central-1`?** Historicamente existian M2 (2 GB) y M5 (5 GB) como tiers compartidos baratos, pero Atlas los reemplazo en algun momento por un tier llamado "Flex" con precio por uso. No tengo certeza de que ofrece Atlas hoy ni del precio exacto, y esto importa porque **es la escalacion correcta si el dump no entra en M0** (el CEO descarto M10 por costo). Jose debe entregar: nombre del tier, storage incluido, precio mensual en `mx-central-1`, y si incluye backup.

8. **Cual es el tamano real de la db `compas` hoy?** Bloqueante para el Paso 0.5. Jose puede obtenerlo sin dumpear: desde la consola de Atlas (metrica de storage por db) o con `db.stats()` si logra conectar. Si el cluster viejo no responde ni para esto, el tamano se mide con el dump mismo.

9. **Atlas M0 se auto-pausa por inactividad?** Si M0 pausa el cluster tras dias sin uso y Render Free tambien hace spin-down, un cold start podria encadenar ambas latencias y superar cualquier timeout razonable. Jose debe confirmar la politica actual de auto-pausa de M0 y, si existe, si el keep-alive de GitHub Actions que ya tenemos la previene.

## Notas de traspaso

Punteros para el planner cuando llegue el momento:

- **Secuencia sugerida (incorporando mitigaciones del grill):**
  1. **Paso 0 (CRITICO 2):** parar worker `compas-jobs` en Render. Verificar que no hay migraciones ni scripts del CEO corriendo. Anunciar ventana.
  2. **Paso 0.5 (CRITICO 3):** medir el tamano real del dump del cluster viejo. Si supera 400 MB, aplicar la escalera de tier (M0, luego tier intermedio economico, M10 solo como ultimo recurso). **Conservar el dump en disco del CEO de forma permanente: con M0 sin backup, es la unica copia de seguridad.**
  3. Verificar disponibilidad de M0 en `mx-central-1` en la consola de Atlas.
  4. Crear cluster `compas-prod` en la cuenta `info@roddos.com`, region `mx-central-1`.
  5. Configurar allowlist inicial (probablemente `0.0.0.0/0`; ver pregunta abierta 3 del research).
  6. Crear usuario de base de datos `compas-app` en el cluster nuevo (ver pregunta abierta 4 del research). Guardar credenciales en `docs/INVENTARIO-SECRETOS.xlsx`.
  7. Sacar `mongodump` de la db `compas` del cluster viejo. Si cuelga, aplicar la escalera del CRITICO 1 (directConnection al nodo sano, luego readPreference forzado, luego plan B de re-siembra manual).
  8. Correr `mongorestore` contra el cluster nuevo.
  9. Verificar que la copia esta completa: contar documentos por coleccion, comparar contra el viejo, y revisar que la caja curada mar-jul aparece con los mismos valores.
  10. **Bumpear temporalmente el timeout de startup en Render** a 60s para el deploy del switch (ver pregunta abierta 5 del research).
  11. En Render: guardar la URI vieja como `MONGODB_URI_COMPAS_OLD` (respaldo hasta checkpoint de no-retorno) y cambiar `MONGODB_URI_COMPAS` al cluster nuevo (formato SRV, ver pregunta abierta 6).
  12. Redeploy manual.
  13. Verificar `/api/v1/health/ready` responde 200.
  14. Verificar que el CEO entra a `compas.roddos.com` y ve la app, y que la caja curada esta visible con valores correctos.
  15. Re-encender worker `compas-jobs` apuntado al cluster nuevo.
  16. **Checkpoint de no-retorno (CRITICO 4):** tras 1 hora de operacion sana con al menos un write confirmado, borrar `MONGODB_URI_COMPAS_OLD` de Render y bajar el timeout de startup al valor original.
  17. Documentar el commit hash o PR en `docs/COMPAS_Control_Desarrollo.xlsx` con el checkpoint marcado.
- **Archivo a NO tocar:** `backend/app/db/mongo.py` (el driver es el que ya vive; solo cambia la URI en env var).
- **Archivos a tocar:** `docs/INVENTARIO-SECRETOS.xlsx` (registrar URI nueva, credenciales del cluster nuevo, y guardar la vieja marcada `DEPRECATED-<fecha>`), env vars en Render, migraciones nuevas idempotentes si aparece data faltante despues del restore.

## Related

- Ticket MongoDB Support del CEO por `sismo-v3-shard-00-01` (rollback loop 30+ dias).
- CLAUDE.md · principio rector "facil para el CEO" y reglas innegociables.
- `docs/RUNBOOK-INFRA.md` · punto de referencia de aprovisionamiento.
- `docs/INVENTARIO-SECRETOS.xlsx` · donde vive la URI actual y donde ira la nueva.
- Memoria `feedback-espanol-neutro-sin-acentos` · estilo de comunicacion aplicado desde este doc en adelante.
