# Handshake · Migrar COMPAS a su propio cluster MongoDB

Status: corregido post-auditoria · 2026-09-14 (antes: grilled · 2026-09-14)

## Correcciones aplicadas el 2026-09-14

Este doc tuvo tres errores de fondo, detectados por la auditoria en `docs/equipo/entregas/AUDIT-migracion-cluster.md`. Se dejan registrados en vez de reescribir la historia en silencio, porque el razonamiento equivocado explica por que el plan era otro hasta hace unas horas.

1. **La region `mx-central-1` NO era innegociable.** El doc argumentaba que habia que conservarla para no introducir latencia cross-region nueva. `render.yaml:12` dice `region: ohio`: Render ya corre en Ohio y Atlas en Queretaro, o sea que el sistema **ya es cross-region hoy**, y el propio repo lo documenta como problema (`render.yaml:36`, y el fix del 2026-09-03 en `backend/app/db/mongo.py`). El argumento estaba invertido: mudarse a `us-east-1` reduce la latencia en vez de aumentarla. **Region corregida a `us-east-1`.**
2. **El nodo enfermo es el `-02`, no el `-01`.** El doc afirmaba que `sismo-v3-shard-00-01` estaba en rollback loop. Recon en vivo del 2026-09-14: `-00` SECONDARY sano, `-01` **PRIMARY sano**, `-02` con estado anomalo. El plan B del dump apuntaba a esquivar justamente al primario sano.
3. **El arbol de decision de tier era innecesario.** Se construyo sobre el supuesto de que el tamano de la base era desconocido y podia forzar un tier caro. Medicion real: **2.44 MB**. Contra el tope de 512 MB de M0 hay margen de unas 200 veces. El arbol se elimina; M0 alcanza de sobra.

---

## La idea en palabras planas

COMPAS hoy no abre porque su base de datos vive dentro de un edificio grande que se llama "cluster de SISMO", y una parte de ese edificio esta rota. Cada vez que COMPAS intenta despertarse, se queda esperando a que esa parte responda y nunca lo hace, asi que la app nunca termina de arrancar.

La solucion es que COMPAS deje ese edificio y se mude a uno propio. Se crea un cluster nuevo en MongoDB Atlas, tamano free (M0), en la region `us-east-1` (Virginia), dentro de la cuenta `info@roddos.com`. El cluster se llama `compas-prod` y es totalmente autonomo del de SISMO.

Por que Virginia y no Mexico, que es donde esta el cluster viejo: el servidor que consume esta base corre en Ohio, no en Mexico. Hoy la base esta lejos del servidor y eso ya causa problemas documentados de lentitud al arrancar. Virginia esta al lado de Ohio, asi que mudarse ahi **acerca** la base a quien la usa. Ademas, Atlas no ofrece el tamano gratuito en Mexico y si en Virginia, asi que la mudanza resuelve la latencia y el costo de una sola vez.

Despues se copia toda la base vieja al cluster nuevo con `mongodump`, que saca una foto, y `mongorestore`, que pega esa foto en el destino. Se lleva todo. La base entera pesa 2.44 MB, asi que la copia es rapida y liviana.

Cuando la copia esta completa y verificada, se cambian dos variables en Render para que apunten al cluster nuevo. Se guarda la configuracion vieja como respaldo por si hay que devolverse.

El resultado: el CEO entra a compas.roddos.com, la app carga, y COMPAS ya nunca depende de que SISMO este sano.

## Por que importa

COMPAS no abre. El backend cuelga en el arranque porque no logra completar la conexion contra el cluster compartido `sismo-v3`, que tiene un nodo en estado anomalo. Mientras eso siga asi, cualquier deploy falla aunque el codigo este perfecto. La unica salida bajo nuestro control es que COMPAS deje de depender de la salud de un cluster que no controlamos.

Hay un segundo motivo, descubierto en la auditoria: **la configuracion del motor ya esta cargada** (`parametros_proyeccion` con 14 documentos, `modelos_moto` con 3). Hasta ahora se creia que las pantallas en blanco eran una brecha de configuracion. No lo son. Eso significa que **esta migracion puede ser lo unico que falta para que COMPAS vuelva a funcionar**, sin trabajo de configuracion adicional.

## Para quien es

- CEO (Andres) · desbloquear el uso de COMPAS ya, y quitarnos la dependencia de un cluster que no controlamos.
- Cualquier desarrollo futuro de COMPAS · el cluster propio se vuelve el sustrato estable.

## Que existe hoy

**Infraestructura**
- Backend en Render Free (`compas-api`), **region Ohio**, auto-deploy desde `main` (`render.yaml:8-16`).
- Worker `compas-jobs`: **NO existe como servicio activo.** Esta comentado en `render.yaml:72-108`, diferido a Sprint 5-6.
- Cluster actual: `sismo-v3` en Atlas, region `mx-central-1`, M40, compartido con SISMO, MongoDB 8.0.30.
- Estado de sus nodos al 2026-09-14: `-00` SECONDARY sano, `-01` PRIMARY sano, `-02` anomalo.
- Ya existe un cluster llamado `compas-prod` en la cuenta, **creado por el CEO, sin trabajo hecho adentro**. Es descartable o reutilizable segun su region y tier.
- El cupo de tier gratuito del proyecto Atlas esta ocupado, probablemente por ese `compas-prod`.

**Datos**
- Base `compas`: 2.44 MB de data, 1.08 MB de storage, **28 colecciones**, 71 indices.
- El codigo espera 30 colecciones; faltan `escenarios_impacto` y `cfo_goldens`, que existen en codigo pero nunca se escribieron. Esperar 28 post-restore, no 30.
- Colecciones con data: `audit_log` 2.4K, `transacciones` 2.2K (incluye la caja curada mar-jul), `facturas` 482, `reglas_clasificacion` 159, `presupuesto_lineas` 130, `refresh_sessions` 99, `cartera_previa_recaudo` 82, `rubros` 54, `parametros_proyeccion` 14, `configuracion` 11, `facturas_obligacion` 9, `meses_control` 7, `cargas` 6, `modelos_moto` 3, `metas_ingreso` 2, `cfo_hilos` 1, `cfo_vinculos_telegram` 1, `obligaciones` 1, `users` 1.

**Configuracion de conexion**
- Dos env vars, no una: `MONGODB_URI_COMPAS` (usuario `compas_app`) y `MONGODB_URI_AUDIT` (usuario `compas_audit`), ambas en `render.yaml:55-58`.
- `healthCheckPath` es `/health`, liveness pura sin Mongo (`render.yaml:38`). **No hay que tocar `render.yaml` para esta migracion.**
- `ensure_beanie` tiene timeout de 30s y es no-fatal; si falla, el servicio sigue vivo y reintenta en el siguiente request.

## Como se ve el exito

El CEO abre `compas.roddos.com`, la app carga, puede navegar y editar, y ni una linea del backend habla con `sismo-v3`. Comprobable con:

- El navegador entra y las pantallas muestran data.
- `/api/v1/health/ready` responde 200.
- `MONGODB_URI_COMPAS` y `MONGODB_URI_AUDIT` en Render apuntan al cluster nuevo.
- La caja curada mar-jul sigue visible con los mismos valores (`transacciones`, 2.2K documentos).
- `parametros_proyeccion` sigue con 14 documentos y `modelos_moto` con 3.

## Decisiones ya tomadas

- COMPAS se saca del cluster `sismo-v3` y va a un cluster propio.
- **Proveedor:** MongoDB Atlas.
- **Region: `us-east-1` (Virginia).** Decision del CEO del 2026-09-14, tras corregirse la premisa falsa. Motivos:
  1. **Acerca la base al servidor.** Render corre en Ohio. Virginia es la region AWS contigua; Queretaro esta mucho mas lejos en terminos de red.
  2. **Corrige un problema documentado.** El repo ya registra la latencia cross-region como causa de fallas de arranque. Esta mudanza la ataca en vez de conservarla.
  3. **Habilita el tier gratuito.** Atlas no ofrece M0 ni Flex en `mx-central-1`; en `us-east-1` si.
- **Tier: M0 (free).** Decision firme del CEO. Driver: costo. La base pesa 2.44 MB contra un tope de 512 MB, margen de 200 veces.
- **Sin backup, riesgo aceptado.** Ver "Riesgo aceptado" abajo.
- **Cuenta Atlas:** la misma de hoy (`info@roddos.com`), cluster autonomo sin dependencias con `sismo-v3`.
- **Nombre del cluster:** `compas-prod`.
- **Data a migrar:** dump completo de la db `compas`.
- **Downtime aceptable:** ventana corta. Sin impacto marginal porque COMPAS ya no abre.
- **Rollback:** guardar las URIs viejas en Render como env vars alternas hasta el checkpoint de no-retorno.
- **No se toca `render.yaml`.** El `healthCheckPath` ya esta desacoplado de Mongo y `ensure_beanie` ya es no-fatal con timeout de 30s. Solo cambian valores de env vars en el dashboard.

### Riesgo aceptado (decision trazable del CEO)

El CEO acepta operar COMPAS en un cluster **sin backup automatico y sin point-in-time recovery**. Consecuencia concreta y entendida: si el cluster se corrompe, se borra por error, o Atlas lo suspende, **la data de COMPAS se pierde y no hay restore**. La unica red de seguridad es el dump que se saque durante esta migracion, que **debe conservarse en disco del CEO de forma permanente**, y cualquier dump manual futuro. Driver: costo.

Nota operativa sobre M0: Atlas pausa automaticamente los clusters Free tras **30 dias sin ninguna conexion**, avisando por email 7 dias antes. No es pausa diaria. El keep-alive actual de GitHub Actions **no cuenta** como actividad para Atlas, porque solo hace un GET HTTP contra `/health` de Render y nunca abre conexion a Mongo. En uso normal esto no es un riesgo; si COMPAS queda un mes sin usarse, el cluster se pausa y hay que reanudarlo a mano.

## Decisiones aun abiertas

Ninguna que bloquee. Una se resuelve en el momento de ejecutar:

**Reutilizar o descartar el `compas-prod` que ya existe.** El CEO confirmo que lo creo el y que no tiene trabajo adentro. En la consola, al ejecutar: si ya es M0 en `us-east-1`, se reutiliza tal cual y no hay que crear nada. Si esta en otra region o con otro tier, se borra y se crea de nuevo en `us-east-1`. Borrarlo ademas libera el cupo de tier gratuito del proyecto, que hoy esta agotado.

## Riesgos criticos con mitigacion

### CRITICO 1 · `mongodump` contra el cluster viejo puede colgarse

**Riesgo:** `mongodump` no usa Beanie, pero usa el mismo protocolo de descubrimiento de topologia que cuelga al backend. Si el dump se cuelga, no hay data para restaurar.

**Mitigacion, escalera en orden:**

1. `mongodump` con la URI SRV normal. Si responde en pocos minutos, seguir.
2. Si cuelga: conectar directo al **nodo `-01`, que es el PRIMARY sano**, saltando el descubrimiento de topologia, con `directConnection=true`. **Reconfirmar en la consola cual es el nodo sano el mismo dia**, porque el estado por nodo puede haber cambiado desde el 2026-09-14.
3. Si tambien cuelga: `mongodump` con `--readPreference=secondaryPreferred` y `--host` apuntando manualmente a los nodos sanos.
4. **Plan B ultimo recurso:** re-sembrar desde cero con las migraciones idempotentes y reconstruir a mano la caja curada mar-jul. Costo: varias horas del CEO. **Aceptado de antemano, no se decide sobre la marcha.**

Atenuante nuevo: la base pesa 2.44 MB. Si el dump arranca, termina en segundos.

### CRITICO 2 · Que nadie escriba al cluster viejo durante la ventana

**Riesgo:** todo write al cluster viejo entre el snapshot y el switch de URI se pierde.

**Estado real, corregido:** el worker `compas-jobs` **no existe como servicio activo** (`render.yaml:72-108`, comentado y diferido). El paso original "detener el worker" no aplica tal como estaba escrito.

**Mitigacion, Paso 0:**

1. **Confirmar en el dashboard de Render** que no existe un servicio worker creado a mano fuera del blueprint. Si existe, detenerlo.
2. Verificar que no hay migraciones ni scripts del CEO corriendo contra el cluster viejo.
3. No usar la app durante la ventana.
4. Dejar nota: cuando `compas-jobs` se active en Sprint 5-6, este paso vuelve a aplicar.

### CRITICO 3 · M0 sin backup

**Resuelto en cuanto a capacidad.** La base pesa 2.44 MB contra 512 MB de tope. El arbol de decision por tamano se elimina.

**Mitigacion de la falta de backup:** conservar el dump de la migracion en disco del CEO de forma permanente. Con M0 sin backup, ese archivo es la unica copia de seguridad que existe. No borrarlo tras el restore.

**Senal de alerta, no escalacion automatica:** si el uso de storage llegara a 350 MB (70% del tope), avisar al CEO para que decida si poda data o sube de tier. El CEO decide.

### CRITICO 4 · El rollback tiene una trampa silenciosa de perdida de datos

**Riesgo:** si se escribe al cluster nuevo y despues se vuelve al viejo, esos writes se pierden.

**Mitigacion:**

1. El rollback es seguro **solo antes del primer write al cluster nuevo**. Despues, revertir significa perder esos writes.
2. **Checkpoint de no-retorno:** tras 1 hora de operacion sana con al menos un write confirmado, el rollback deja de estar sobre la mesa y el fix es hacia adelante.
3. Al llegar al no-retorno, borrar de Render las env vars de respaldo con las URIs viejas.
4. Documentar el checkpoint en el commit de cierre.

### CRITICO 5 · La garantia de append-only del log de auditoria no viaja en el dump

**Riesgo nuevo, elevado por la auditoria.** La regla 4 de CLAUDE.md exige que `audit_log` sea append-only, y eso hoy esta enforced a nivel de base de datos por un rol custom. **`mongorestore` copia datos e indices, pero NO copia usuarios ni roles de Atlas.** Si el cluster nuevo queda sin el rol `audit_writer` y sin el usuario `compas_audit`, la garantia desaparece en silencio y hay un test de CI que deberia empezar a fallar.

**Mitigacion:** crear el rol y los dos usuarios a mano en el cluster nuevo antes del switch, por Atlas UI, y verificar `db.audit_log.getIndexes()` despues del restore. Detalle completo en el dossier de research, seccion B1.

## Preguntas abiertas

Casi todas cerradas por el research de Jose (`docs/equipo/entregas/RESEARCH-migracion-cluster.md`) y el recon de consola. Quedan cuatro, ninguna bloqueante:

1. **Existe un worker creado a mano en el dashboard de Render?** El blueprint dice que no. Verificar en Render Dashboard, Services. Afecta al Paso 0 del CRITICO 2.
2. **Rango de IPs de salida de `compas-api`.** Render Dashboard, servicio `compas-api`, Connect, pestana Outbound. Solo para documentar; no se recomienda como estrategia de allowlist porque los rangos de Render son compartidos y rotan sin aviso. El precedente del proyecto es abrir `0.0.0.0/0` en desarrollo y cerrar en go-live.
3. **Sobrevive el indice forense de `audit_log` al restore?** Verificar con `getIndexes()` despues, no asumir.
4. **Que hay en las 14 filas de `parametros_proyeccion`?** Es configuracion financiera viva que alguien cargo entre julio y hoy sin que quedara registro. No bloquea la migracion (el dump se la lleva igual), pero conviene saberlo.

## Notas de traspaso

**Secuencia sugerida:**

1. **Paso 0.** Confirmar en Render Dashboard que no hay worker activo. Verificar que no hay scripts corriendo. No usar la app durante la ventana.
2. Mirar el `compas-prod` existente en Atlas. Si es M0 en `us-east-1`, reutilizarlo. Si no, borrarlo (libera el cupo free) y crear uno nuevo: M0, `us-east-1`, nombre `compas-prod`.
3. Configurar el allowlist. Recomendado `0.0.0.0/0` durante la ventana, con el mismo criterio que ya usa el cluster de SISMO en desarrollo.
4. **Crear el rol custom y los dos usuarios por Atlas UI** (nunca por driver, en ningun tier): rol `audit_writer` con `insert` y `find` sobre `compas.audit_log`; usuario `compas_app` con `readWrite` sobre `compas`; usuario `compas_audit` solo con `audit_writer`. Guardar ambas passwords en `docs/INVENTARIO-SECRETOS.xlsx` de inmediato. Click-path exacto en el dossier, seccion B1.
5. **Reconfirmar en la consola cual nodo del cluster viejo esta sano**, antes de dumpear.
6. `mongodump` de la db `compas`. Si cuelga, aplicar la escalera del CRITICO 1.
7. **Guardar el dump en disco del CEO de forma permanente.** Es la unica copia de seguridad que va a existir.
8. `mongorestore` contra el cluster nuevo.
9. Verificar: **28 colecciones**, no 30. Contar documentos por coleccion y comparar contra la tabla de "Que existe hoy". Confirmar `db.audit_log.getIndexes()`.
10. En Render: guardar las URIs viejas como env vars de respaldo y cambiar `MONGODB_URI_COMPAS` y `MONGODB_URI_AUDIT` a las nuevas, en formato `mongodb+srv://`.
11. Redeploy manual. **No hace falta tocar `render.yaml` ni bumpear ningun timeout.**
12. Verificar `/api/v1/health/ready` en 200 y que el CEO entra y ve data.
13. **Checkpoint de no-retorno** tras 1 hora sana: borrar las env vars de respaldo.
14. Registrar commit o PR en `docs/COMPAS_Control_Desarrollo.xlsx`.

**Archivos a NO tocar:** `backend/app/db/mongo.py`, `render.yaml`. Solo cambian valores de env vars en el dashboard de Render.

**Archivos a tocar:** `docs/INVENTARIO-SECRETOS.xlsx` (URIs y credenciales nuevas; marcar las viejas como deprecadas con fecha).

**Formato de URI:** obligatoriamente `mongodb+srv://`. Verificado que `pymongo` trae `dnspython` como dependencia dura, no hace falta el extra `[srv]` ni cambios en `requirements.txt`.

## Related

- `docs/equipo/entregas/RESEARCH-migracion-cluster.md` · dossier de research de Jose, con click-paths y evidencia con file:line.
- `docs/equipo/entregas/AUDIT-migracion-cluster.md` · auditoria que detecto las tres correcciones de arriba.
- `docs/RUNBOOK-INFRA.md` §2 · usuarios y roles existentes, precedente de `0.0.0.0/0` en desarrollo.
- `render.yaml` · region Ohio, healthCheckPath, dos env vars de Mongo, worker diferido.
- `docs/INVENTARIO-SECRETOS.xlsx` · donde viven las URIs.
