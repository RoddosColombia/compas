# AUDIT - Dossier de research de migracion de cluster

Auditor: Claude (Arquitecto y auditor) - 2026-09-14
Objeto auditado: `docs/equipo/entregas/RESEARCH-migracion-cluster.md` (Jose, Researcher 1)
Handshake de referencia: `docs/handshake_migrar_cluster_compas.md` (status grilled)

---

## VEREDICTO: NO-GO

**Importante leer el motivo antes que el veredicto.** El NO-GO **no es por la calidad del dossier de Jose**, que es alta: citas con file:line, gaps marcados honestamente, y una distincion limpia entre lo que verifico y lo que no pudo. Si el dossier se juzga como pieza de research, pasa.

El NO-GO es porque **el dossier descansa sobre una premisa que yo introduje en el handshake y que es falsa**. Si Andres (planner) arranca ahora, va a producir un plan de migracion a M10 en `mx-central-1` que probablemente sea el destino equivocado, y ese trabajo se tira.

**Condicion para pasar a GO:** que el CEO resuelva la decision de region con la informacion corregida (ver seccion 2, hallazgo C-2). Resuelta esa, el dossier se corrige en tres puntos concretos y habilita el planning.

---

## Metodo

Cruce el dossier contra cuatro fuentes independientes de lo que Jose uso:

1. **Recon en vivo de la consola de Atlas** (ejecutado via navegador el 2026-09-14, solo lectura). Esta es la fuente que Jose no tenia: el marco un tercio de sus gaps como REQUIERE EJECUCION EXTERNA precisamente por no tener acceso a consola.
2. **Lectura directa de `render.yaml`** completo.
3. **Memoria del proyecto** (`~/.claude/projects/...compas/memory/`).
4. **Grep de codigo** para las dos colecciones en disputa.

---

## 1. Hechos que confirmo de forma independiente

| Claim de Jose | Mi verificacion | Veredicto |
|---|---|---|
| A2: Atlas no ofrece M0 ni Flex en `mx-central-1` | Recon en consola: el tab Free aparece deshabilitado con tooltip "The limit for free tier clusters in this project has been reached"; ademas `mx-central-1` figura con icono de "Dedicated tier region" y al elegir Flex la region salto sola a `us-east-1` | **CONFIRMADO por metodo independiente.** Jose lo saco de la tabla oficial de regiones AWS; yo lo vi en la consola en vivo. Dos caminos distintos, misma conclusion. Es el hallazgo mas solido del dossier. |
| B4: `healthCheckPath` es `/health`, no `/api/v1/health/ready` | `render.yaml:38` literal `healthCheckPath: /health`, mas el bloque de comentario `render.yaml:26-38` que documenta la regresion del 2026-09-03 y la regla "el health check de Render es LIVENESS" | **CONFIRMADO.** |
| B3: el worker `compas-jobs` esta comentado en el blueprint | `render.yaml:72-108`, bloque completo comentado con la nota "DIFERIDO a Sprint 5-6" | **CONFIRMADO** en el blueprint. El gap que Jose deja abierto (que el dashboard tenga algo creado a mano) sigue valido y no lo pude cerrar: mi recon fue de Atlas, no de Render. |
| B1: el sistema usa dos usuarios, no uno | `render.yaml:57-58` declara `MONGODB_URI_AUDIT` con el comentario literal "usuario compas_audit (audit_writer); fail-fast C-01 sin el" | **CONFIRMADO por fuente independiente del RUNBOOK que cito Jose.** Que exista la env var separada en el blueprint es prueba fuerte: no es documentacion aspiracional, es configuracion viva. |
| A3: M10 cuesta del orden de 57-60 USD/mes | Recon en consola, flujo Create con region `mx-central-1`: M10 desde 0.08 USD/hora, que da unos 58 USD/mes | **CONFIRMADO**, y ademas cierra el gap 5 de Jose para este caso concreto. |
| A3: Flex existe hoy y reemplazo a M2/M5 | Recon: Flex aparece en el flujo de creacion desde 0.011 USD/hora con tope de 30 USD/mes. M2 y M5 no aparecen en ninguna parte del selector | **CONFIRMADO.** |

---

## 2. Contradicciones

Las dos primeras **son errores mios, no de Jose**. El las heredo de mi handshake, que era su fuente de verdad por contrato.

### C-1 · El nodo roto es el `-02`, no el `-01`

Mi handshake afirma en multiples lugares que `sismo-v3-shard-00-01` esta en rollback loop hace 30+ dias. Jose lo reprodujo en la linea 8 de su dossier porque el handshake es su input autoritativo.

Recon en vivo del replica set:

```
sismo-v3-shard-00-00.onh5xm.mongodb.net:27017  SECONDARY  sano
sismo-v3-shard-00-01.onh5xm.mongodb.net:27017  PRIMARY    sano
sismo-v3-shard-00-02.onh5xm.mongodb.net:27017  badge naranja, anomalo
```

Banner del cluster: "deploying your changes: 2 of 3 servers complete, waiting for 1 server to be healthy".

**Por que importa:** el CRITICO 1 del handshake define un plan B que consiste en conectarse con `directConnection` a un nodo sano para sacar el dump esquivando el nodo enfermo. Con el dato malo, ese plan apuntaba a esquivar justamente al primario sano. Si alguien ejecuta el plan B tal como esta escrito hoy, se conecta al nodo equivocado.

**Caveat honesto:** el recon es una foto de un instante, y el banner indica una operacion de deploy en curso. Es posible que los nodos hayan rotado roles o que el problema se haya movido de nodo con el tiempo. Lo que es seguro es que **hoy** el `-01` esta sano y es primario, y el `-02` es el anomalo. El hostname exacto del nodo sano hay que reconfirmarlo el dia del dump, no darlo por fijo.

### C-2 · La premisa de "region innegociable" es falsa

Esta es la grave, y es enteramente mia.

En el handshake escribi que `mx-central-1` es innegociable, con cuatro razones. La principal: "Render `compas-api` ya lleva meses hablando con MongoDB en `mx-central-1`; los tiempos de respuesta y todos los timeouts internos estan calibrados a esa latencia. Mudarnos a otra region mete un perfil de red nuevo y no verificado."

`render.yaml:12` dice: **`region: ohio`**.

Render corre en Ohio. Atlas esta en Queretaro. **El sistema ya es cross-region hoy**, y el propio repositorio lo documenta como problema, no como estado calibrado:

- `render.yaml:36`, literal: "el health check de Render es LIVENESS. Nunca puede depender de una BD cross-region: si Atlas tarda, Render mata el deploy y el arranque nunca puede completarse, deadlock."
- El fix del 2026-09-03 en `backend/app/db/mongo.py` (citado por Jose en su B4) explica que el timeout viejo de 15s no lo agotaba el ping sino la creacion en serie de indices **contra Atlas cross-region**.

Mi razon numero 2 del handshake era literalmente "cross-region multiplica los timeouts en el arranque". Eso es un argumento **en contra** de `mx-central-1`, y lo use para defenderla.

**Consecuencia:** mover Atlas a `us-east-1` no introduce latencia nueva. La reduce, porque acerca la base al servidor que la consume. Y en `us-east-1` si existen M0 y Flex, con lo cual el conflicto entre la region y el driver de costo del CEO se disuelve por completo.

**Fallo de proceso que hay que registrar:** Jose vio este hecho. Su linea 129 dice textual "notese que la region de RENDER es Ohio, distinta de la region de ATLAS `mx-central-1`; son dos nubes distintas, el handshake ya lo asume". Lo vio y no lo escalo, porque mi mensaje de tarea le decia explicitamente "No reabras decisiones ya cerradas del handshake, en particular la region y el tier M0". **Le puse una mordaza justo en el punto donde tenia la evidencia para corregirme.** El error de la instruccion es mio; la conducta de Jose fue la correcta dada la instruccion.

### C-3 · Una memoria del proyecto esta obsoleta y contradice la realidad

La memoria `compas-desplegado-estado` (fechada 2026-07-26, hace 50 dias) afirma: "el motor no esta configurado, `parametros_proyeccion=0`, `modelos_moto=0`".

Recon de hoy en la base `compas`: **`parametros_proyeccion` tiene 14 documentos y `modelos_moto` tiene 3.**

La memoria quedo vieja. Ver hallazgo N-1 abajo, porque las consecuencias exceden a este dossier.

---

## 3. Gaps de Jose que cierro con el recon

Jose dejo 7 gaps. Cierro tres.

**Gap 1 (A1, tamano real de `compas`) - CERRADO.**

```
Storage size: 1.08 MB
Data size:    2.44 MB
Colecciones:  28
Indices:      71
```

El tamano deja de ser una variable del problema: contra el tope de 512 MB de M0 hay un margen de aproximadamente 200 veces. Cualquier tier sirve por capacidad. El dump que el CEO va a guardar en disco va a pesar unos pocos MB, no gigabytes.

**Gap 6 (C2, que colecciones tienen documentos hoy) - CERRADO.**

Con documentos, 19:

```
audit_log 2.4K · transacciones 2.2K · facturas 482 · reglas_clasificacion 159
presupuesto_lineas 130 · refresh_sessions 99 · cartera_previa_recaudo 82
rubros 54 · parametros_proyeccion 14 · configuracion 11 · facturas_obligacion 9
meses_control 7 · cargas 6 · modelos_moto 3 · metas_ingreso 2 · cfo_hilos 1
cfo_vinculos_telegram 1 · obligaciones 1 · users 1
```

Vacias, 9: `cfo_avisos_vigilante`, `colocacion_mes`, `gastos_recurrentes`, `idempotency_keys`, `jwt_denylist`, `loantape_creditos`, `login_throttle`, `pagos_planeados`, `proyeccion_versiones`.

**Gap 5 (precios exactos) - CERRADO para lo que importa.** M10 en `mx-central-1`: 0.08 USD/hora. Flex: 0.011 USD/hora con tope de 30 USD/mes, pero no disponible en `mx-central-1`.

---

## 4. Gaps que siguen abiertos

- **Gap 2 - existencia real del worker `compas-jobs` en el dashboard de Render.** Mi recon fue de Atlas, no de Render. Sigue requiriendo que alguien mire Render Dashboard, Services.
- **Gap 3 - rango de IPs de salida de Render.** Idem. Coincido con Jose en que no conviene usarlo como estrategia primaria de allowlist.
- **Gap 4 - si el indice forense de `audit_log` sobrevive al restore.** Solo verificable despues del restore. Coincido con su recomendacion de confirmarlo con `getIndexes()` y no asumirlo.
- **Gap 7 - version exacta de pymongo en el build real de Render.** Solo sale de un log de build real.

---

## 5. Hallazgos nuevos, que ni el dossier ni el handshake tenian

### N-1 · El config gap del motor YA ESTA CERRADO. Esto cambia el diagnostico de fondo.

`parametros_proyeccion` tiene 14 documentos. `modelos_moto` tiene 3. La configuracion del motor **existe y esta cargada**.

Esto tiene tres consecuencias que exceden a esta migracion:

1. **La hipotesis de "paginas en blanco por falta de configuracion" cae.** Esa era la explicacion vigente desde julio. La configuracion esta. Lo que falta es que el backend pueda conectarse a Mongo. Es decir: **esta migracion puede ser la unica cosa que hace falta para que COMPAS vuelva a funcionar**, sin ningun trabajo de configuracion adicional.

2. **La migracion de semilla que yo propuse esta manana habria escrito encima de configuracion viva.** Mi propuesta era insertar 3 modelos y 1 fila de parametros con valores sacados del Excel. Habrian aterrizado sobre 3 modelos y 14 filas de parametros que ya existen. En el mejor caso duplicados; en el peor, configuracion contradictoria en una coleccion versionada por `vigente_desde`. El CEO corto eso con "no vas a poblar nada" por una razon de principio, y resulta que ademas evito un dano concreto.

3. **Alguien cargo esa configuracion entre el 2026-07-26 y hoy, y no quedo registrado.** Vale la pena saber que hay en esas 14 filas de `parametros_proyeccion` antes de migrar, porque es configuracion financiera viva que va a viajar en el dump.

### N-2 · Ya existe un cluster llamado `compas-prod`

El recon reporta 4 clusters en la cuenta, uno de ellos llamado `compas-prod`, mostrando "Monitoring Paused". Ademas el cupo de tier gratuito del proyecto esta agotado, lo que sugiere que ese `compas-prod` podria ser el M0 que lo ocupa.

No se su region, ni su contenido, ni quien lo creo. **Puede que parte del trabajo de esta migracion ya este hecho.** Hay que averiguarlo antes de crear nada nuevo: crear un segundo `compas-prod` seria un desastre de ambiguedad.

### N-3 · La diferencia entre 30 colecciones esperadas y 28 reales esta explicada

Jose derivo del codigo que deberian existir 30 colecciones. Atlas muestra 28. Las dos ausentes son:

- `escenarios_impacto` (verificado en `backend/app/domain/escenario_impacto.py:43`)
- `cfo_goldens` (verificado en `backend/app/cfo/goldens/modelo.py:14`)

Ambas existen en el codigo pero nunca se les escribio, y MongoDB no materializa una coleccion hasta el primer insert. No es un problema. **Importa para la verificacion post-restore:** quien compare debe esperar 28, no 30, y no leer esa diferencia como restore incompleto.

---

## 6. Riesgos

1. **Riesgo de trabajo tirado (el que motiva el NO-GO).** Si el planner arranca hoy, planifica M10 en `mx-central-1`. Si el CEO decide `us-east-1` tras conocer C-2, ese plan se descarta entero.
2. **Riesgo de ejecutar el plan B del dump contra el nodo equivocado** (C-1). Mitigacion: reconfirmar el estado por nodo en la consola el mismo dia del dump.
3. **Riesgo de duplicar `compas-prod`** (N-2). Mitigacion: identificar el cluster existente antes de crear nada.
4. **Riesgo sobre la regla 4 de CLAUDE.md** (audit_log append-only). `mongorestore` no trae usuarios ni roles. Si el cluster nuevo queda sin el rol `audit_writer` y sin el usuario `compas_audit`, la garantia de append-only del log de auditoria deja de estar enforced a nivel de base de datos. El dossier de Jose cubre bien el como; lo elevo aca a riesgo porque es una regla innegociable del proyecto, no un detalle de setup.
5. **Riesgo de analisis desactualizado si cambia la region.** Los bloques A2, A3 y C1 de Jose son especificos de `mx-central-1`. En `us-east-1` las respuestas son distintas (M0 y Flex si existen, y la auto-pausa de M0 vuelve a ser relevante). Ese pedazo del dossier habria que rehacerlo.

---

## 7. Acciones concretas

**Para el CEO, bloqueantes:**

1. Decidir region con la informacion corregida de C-2. Sin esto no arranca el planner.
2. Averiguar que es el cluster `compas-prod` que ya existe (N-2).

**Para mi (arquitecto), una vez resuelto lo anterior:**

3. Corregir el handshake: el nodo roto, la seccion de region completa (las cuatro razones), y el tier segun lo que decida el CEO. Marcar el cambio como correccion post-auditoria, no reescribir la historia en silencio.
4. Actualizar la memoria `compas-desplegado-estado`, que esta 50 dias vieja y afirma lo contrario de la realidad.
5. Corregir mi propio patron al escribir instrucciones de tarea: la clausula "no reabras decisiones cerradas" tiene que venir siempre con la excepcion "salvo que encuentres evidencia de que la decision se tomo sobre un hecho falso, en cuyo caso escalalo de inmediato".

**Para Jose, cuando se reactive:**

6. Si la region cambia a `us-east-1`, rehacer A2, A3 y C1 para esa region.
7. Ningun reproche por C-1 ni C-2: ambos vinieron de mi handshake y uno de ellos lo detecto igual, aunque la instruccion le impidiera escalarlo.

**Para el planner, cuando arranque:**

8. Esperar 28 colecciones post-restore, no 30 (N-3).
9. Verificar `db.audit_log.getIndexes()` despues del restore (gap 4 de Jose).
10. Crear usuarios y rol por Atlas UI siguiendo el RUNBOOK, no por driver, sin importar el tier (B1 de Jose).

---

## Related

- `docs/equipo/entregas/RESEARCH-migracion-cluster.md` - el dossier auditado.
- `docs/handshake_migrar_cluster_compas.md` - contiene los dos errores C-1 y C-2, pendiente de correccion.
- `render.yaml:12,26-38,57-58,72-108` - evidencia de region Ohio, healthCheckPath, usuario de auditoria y worker diferido.
- Memoria `compas-desplegado-estado` - obsoleta, ver C-3 y N-1.
