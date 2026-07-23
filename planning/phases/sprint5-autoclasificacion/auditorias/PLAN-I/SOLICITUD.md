# SOLICITUD DE AUDITORÍA — sprint5-autoclasificacion · I-PLAN: C3 auto-clasificación de movimientos

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-22
**Docs contrato:** `docs/COMPAS_NORTE.md`, `.planning/PROJECT.md` (C3), `docs/modelo/MODELO.md` (§C3), **Spec §1.9 (ReglaClasificacion), §1.5 (`regla_id`), §319 (API /reglas-clasificacion)**; CR-S5 (declarado abajo); CLAUDE.md reglas 3, 4, 7, 9, 11.
**Base:** `main` con C1 mergeada (tu GO I-PR1 9.4) y re-seed corrido en prod (39 rubros, solo difs de orden). **Nivel:** PLAN (pre-código).
**Alcance:** SOLO C3 backend (reglas + aplicación en carga + reclasificación manual + semilla). La pantalla frontend va aparte sin gate. C4 (ajuste de caja) en PLAN aparte.

> Contexto de norte: sin clasificación, todo egreso cae en 'Por clasificar' y ni la
> Vista Control ni el motor del sugerido ni la capa predictiva (C7) tienen insumo por
> categoría. Es el bloqueador funcional más caro después de C7 (CONCERNS C3).
> En tu certificado de C1 anunciaste auditar aquí: **coherencia tipo_transacción↔
> tipo_rubro** y **guarda de inactivos en reglas automáticas** — ambas están diseñadas
> abajo (D1, D2).

## Qué se propone

**1. Entidad `ReglaClasificacion`** (Spec §1.9, fiel): `patron` String(120) — match
**contains case-insensitive y sin tildes** sobre `descripcion` (normalización única
compartida) — `rubro_id`, `tipo_flujo`, `prioridad` int (primera que matchea por
prioridad ascendente gana; empate → `_id` como desempate estable), `origen`
manual|aprendida, `activa`, `creada_por`. Índices: `(prioridad)`, único parcial
`(patron_normalizado, tipo_flujo)` con `activa=true` — dos reglas activas idénticas
son ambigüedad (regla 7). `patron` mínimo 3 caracteres (una letra matchearía todo).

**2. CRUD `/api/v1/reglas-clasificacion`** (Spec §319):
- `GET` (`dashboard:leer`) — filtros `activa`/`tipo_flujo`.
- `POST` (`reglas:gestionar`, CR-S5) — valida: rubro existe, **activo** y **su
  `tipo_flujo` == el de la regla** (D1, coherencia por construcción). Emite `regla.creada`.
- `PATCH /{id}` — patron/prioridad/rubro_id (misma validación D1); reactivar =
  `activa:true` (patrón B-3 de C1: emite `regla.editada`, sin evento extra).
- `POST /{id}/desactivar` — baja lógica. Emite `regla.desactivada`.
- `POST /{id}/aprobar` (Spec §319; **Financiero/Admin**) — solo `origen=aprendida`
  con `activa=false` → `activa=true`. Emite `regla.editada` {activa: false→true,
  via: 'aprobacion'} (economía B-3: sin evento `regla.aprobada` extra).
- Auditoría **fail-closed O1** con compensación (estándar fijado en C1/B-5).

**3. Aplicación al cargar** (`procesar_carga`): para cada fila del extracto se
evalúan las reglas activas de su `tipo_flujo` en orden de prioridad; primera que
matchea → `rubro_id` + **`regla_id`** en la Transaccion (rastro forense §1.5/F-05);
ninguna → 'Por clasificar' (regla 7: no se adivina).
- **D2 (guarda de inactivos):** una regla activa cuyo **rubro esté inactivo NO
  clasifica** (se salta; la fila cae a 'Por clasificar') y el resultado de la carga
  reporta `reglas_con_rubro_inactivo` (fail-loud informativo, patrón B-4).
- **D3 (auditoría de la clasificación automática):** NO se emite un evento por
  transacción clasificada en carga masiva (ruido: cientos por carga); el rastro es
  `regla_id` persistido + `carga.completada` con contadores `{clasificadas,
  por_clasificar}`. La clasificación MANUAL sí emite `transaccion.clasificada`
  (catálogo v1.0, sin CR). ¿De acuerdo?

**4. Reclasificación manual** — `PATCH /api/v1/transacciones/{id}/clasificar`
(`cargas:gestionar`, como el POST manual): mueve una transacción a un rubro
**existente, activo y coherente en tipo** (D1); **mes cerrado → 409** (regla 4 — la
reclasificación NO toca histórico congelado); emite `transaccion.clasificada` con
{rubro_anterior→nuevo}. Solo muta `rubro_id`/`clasificada_por/at` — fecha, valor,
banco, id_banco inmutables (Spec §2.2).
- Con flag opcional `proponer_regla:true` → crea `ReglaClasificacion`
  `origen=aprendida, activa=false` con el texto que el usuario marque (flujo Spec
  §1.9: "propuesta desde reclasificaciones, requiere aprobación, nunca auto-activada").

**5. Aplicar reglas a pendientes** — `POST /api/v1/reglas-clasificacion/aplicar-pendientes`
(`reglas:gestionar`): re-corre las reglas SOLO sobre transacciones en 'Por
clasificar' de **meses NO cerrados**. Idempotente (lo ya clasificado no se toca).
Devuelve contadores. **D4:** ¿evento? Propongo `regla.editada` NO aplica; emitir
`transaccion.clasificada` agregado no existe → propongo **una entrada
`carga.completada`-like NO**: mejor devolver el resumen en la respuesta y que cada
transacción quede con su `regla_id` (mismo criterio D3). Necesario para clasificar
lo ya cargado sin esperar la próxima carga (p. ej. la migración abr–jul).

**6. Semilla de reglas** (migración idempotente, patrón B-1 de C1: URI por entorno):
del mapeo descripción→categoría de `Base real egresos` (Global66). **Solo patrones
de comercios/servicios — NUNCA nombres de personas (Ley 1581; los abonos de
clientes se cubren con las genéricas de ingreso)**. Ingresos: `'Abono'`, `'Recibido
de'` → rubro de sistema 'Recaudo' (MODELO §C3), prioridad alta. `$setOnInsert` por
(patron_normalizado, tipo_flujo) + reporte de colisiones (B-4).

**CR-S5 (declarado):** catálogo 33→**36** (`regla.creada`, `regla.editada`,
`regla.desactivada`) + permiso **`reglas:gestionar`** = {financiero, admin} (§4.1
por CR; simetría con `rubros:gestionar` de CR-S4). Tests de completitud y guardián
actualizados.

## Decisiones declaradas (auditar)

- **D1 — coherencia tipo_tx↔tipo_rubro por construcción:** la regla exige
  `regla.tipo_flujo == rubro.tipo_flujo` al crear/editar, y solo se evalúa contra
  transacciones de su mismo `tipo_flujo`. Así es IMPOSIBLE clasificar un egreso en
  un rubro de ingreso, ni por regla ni por carrera (si el rubro cambió de tipo, está
  congelado por B-1 de C1 al tener referencias).
- **D2 — rubro inactivo en regla:** saltar y reportar (no desactivar la regla en
  cascada: si el CEO reactiva el rubro, la regla vuelve a operar sola). ¿De acuerdo?
- **D3 — sin evento por transacción en clasificación automática** (rastro =
  `regla_id`; contadores en `carga.completada`). ¿Suficiente para el forense?
- **D4 — `aplicar-pendientes` sin evento propio** (respuesta con contadores +
  `regla_id` por doc). Alternativa: nuevo evento `reglas.aplicadas` (CR-S5 sería +4).
- **D5 — reglas aprendidas en esta fase** solo como PROPUESTA manual explícita
  (`proponer_regla:true` al reclasificar) + `/aprobar`. La detección automática de
  "reclasificaciones repetidas" (minería) queda para después — no es predicción de
  caja (norte) y añade complejidad sin datos aún.

## Semántica preservada

Dinero/tiempo intactos: la clasificación solo asigna `rubro_id`/`regla_id` — nunca
toca valor, fecha, signo ni dedup. El motor §1.4.1, cierre, conciliación y Vista
Control no cambian (solo RECIBEN mejor insumo). Histórico inmutable: mes cerrado no
se reclasifica (409). Pydantic strict en todo. Catálogo cerrado: solo CR-S5.

## Puntos a auditar con lupa

1. D1 — coherencia de tipos por construcción (tu anuncio en el certificado de C1).
2. D2 — guarda de inactivos en reglas automáticas (ídem).
3. Precedencia determinista (prioridad + desempate estable) y unicidad de patrón activo.
4. Regla 4: reclasificación bloqueada en meses cerrados; inmutabilidad §2.2 del resto de campos.
5. Semilla sin PII (Ley 1581) + reporte de colisiones.
6. CR-S5: +3 eventos y permiso — ¿o exiges evento para aplicar-pendientes (D4)?

## Evidencia

Sin código aún (PLAN). Base: C1 en prod (GO 9.2/9.4, merge 126ac29, re-seed corrido:
39 rubros). CI verde en main. La guarda B-2a de C1 (clasificar hacia inactivo → 422)
ya existe y este diseño la extiende a las reglas automáticas (D2).

## Pregunta al auditor

¿El diseño de C3 (reglas administrables Spec §1.9 con coherencia de tipos por
construcción, guarda de inactivos, aplicación determinista al cargar, reclasificación
manual auditada con regla 4, aprendidas solo-propuesta, semilla sin PII, CR-S5) es
correcto para construir con TDD? En particular D2, D3 y D4.
