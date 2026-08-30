# FABS · Vigilante — Alerta por umbral de caja (diseño)

**Fecha:** 2026-08-30
**Autor:** Andrés (CEO) + Claude
**Estado:** aprobado para plan (GO CEO 2026-08-30)
**Rama:** `feat/fabs-vigilante-alerta-caja` (desde `main` 73612a1)
**Predecesor:** el vigilante · paquete del lunes (`df3b0b1`) — reusa su patrón borrador→publicar.

---

## 1. Objetivo

Segunda pieza del vigilante: FABS **vigila la caja a diario** y **avisa cuando cruza un umbral**. El paquete del lunes es proactivo pero de cadencia fija; la alerta es **condicional** — solo habla cuando hay algo que decir. Como COMPAS es predictivo, la alerta mira **dos** cajas: la que se **proyecta** (para avisar ANTES) y la **real de hoy** (para avisar cuando ya pasó).

El requisito rector del CEO: **el umbral es editable, no fijo.** Se cumple reusando los umbrales que COMPAS **ya tiene editables y versionados** (no se inventa ninguno hardcodeado).

## 2. Norte y alcance

**Qué SÍ (esta pieza):**
- Un job diario que evalúa **dos disparadores** contra los umbrales vigentes y, si alguno cruza, arma un **borrador de alerta**.
- El borrador llega al **revisor** por Telegram; con **"publicar alerta"** se difunde a todo el comité (flujo idéntico al paquete: un humano libera).
- Umbrales **reusados** (crítico + atención, ya editables desde Supuestos) + **config propia de la alerta** editable por dato (on/off, horizonte).
- Texto **determinista** (plantilla + cifras de COMPAS citadas por token + verificador), **sin LLM por día**.

**Qué NO (fuera de alcance / fast-follows):**
- Narración con LLM de la alerta (se decidió determinista; queda como opción futura).
- UI de encendido/apagado y horizonte de la alerta (editable por dato ahora; el toggle en Supuestos es fast-follow — el editor de umbrales YA existe).
- El cierre mensual comentado (3ª pieza del vigilante, otro CR).
- Cualquier cambio a la matemática del motor o a los umbrales existentes.

## 3. Decisiones del CEO (2026-08-30)

1. **Qué caja vigila:** **ambos** disparadores (piso proyectado + saldo real de hoy).
2. **Cadencia (anti-spam):** **avisa cada día** que la caja esté bajo umbral (sin cooldown; máximo recordatorio). El borrador diario **supersede** al del día anterior → a lo sumo **un** borrador de alerta pendiente.
3. **Destinatario/flujo:** **como el paquete** — borrador al revisor, difusión al comité con "publicar alerta".
4. **Texto:** **determinista** (sin LLM).

## 4. Arquitectura y flujo

```
[cron diario 8:00 Bogotá]  (2º job del scheduler; worker compas-jobs; no-op si CFO_ENABLED off o ALERTA_CAJA_ACTIVA off)
        │
        ▼
evaluar_disparadores()   (cfo/vigilante — orquestación; lee servicios; NO cfo/calc por S1)
   ├─ proyectado: proyeccion.service.proyectar_vigente → 1er mes estado≠ok dentro del horizonte
   │               estado atencion → ÁMBAR ; critico/negativo → ROJO
   └─ real hoy:   cierre.service.conciliacion(mes_en_ejecución).consolidado_reportado vs umbral
                   (sin_dato ⇒ dato incompleto ⇒ ese disparador se abstiene hoy)
        │
        ▼  ¿algún disparador activo?
   NO ──► retirar cualquier borrador de alerta pendiente (estado→'superado'); fin.
   SÍ ──► armar TEXTO DETERMINISTA (plantilla + [[tokens]] de cifras COMPAS)
          → verificar (defensa) → sustituir_tokens
          → supersede el borrador pendiente anterior; UPSERT el de hoy (borrador)
          → soft-audit vigilante.alerta.generada
          → enviar al revisor: "…  Respondé 'publicar alerta' para difundir al comité."
        │
        ▼  [revisor responde "publicar alerta"]  (webhook, match exacto + solo revisor)
   difunde pq.texto (YA verificado) a listar_vinculos() → estado='publicado'
   → soft-audit vigilante.alerta.publicada → confirma al revisor.
```

Reglas heredadas del paquete: solo se difunde **texto ya verificado**; **publicar nunca re-llama al modelo**; **soft-audit** (un proactivo no revienta por fallo de auditoría); scheduler **solo en el worker** (regla 6) y **no-op con flag off**; **dedup por update_id** en el webhook.

## 5. Componentes

### 5.1 Modelo de datos — generalizar el borrador del vigilante

Hoy `PaqueteVigilante` (colección `cfo_paquetes_vigilante`) guarda solo el paquete. Con dos productores de borradores, se **generaliza** (mismos campos + tipo; no es reescritura). No hay datos en producción (el vigilante aún no corre en vivo: worker sin aprovisionar), así que el rename es seguro.

Nuevo `AvisoVigilante` (colección `cfo_avisos_vigilante`):

| Campo | Tipo | Nota |
|---|---|---|
| `tipo` | `str` | `'paquete_lunes'` \| `'alerta_caja'` |
| `periodo` | `str` `'YYYY-MM-DD'` | idempotencia: lunes (paquete) / día (alerta) |
| `texto` | `str` | sustituido (lo que se difunde) |
| `texto_crudo` | `str` | con `[[tokens]]` |
| `estado` | `str` | `'borrador'` \| `'publicado'` \| `'superado'` |
| `generado_at` | `datetime` | TZ-aware |
| `publicado_at` | `datetime \| None` | |
| `conceptos_usados` | `list[str]` | |

- `model_config = ConfigDict(strict=True, extra="forbid")`.
- Índice único `(tipo, periodo)` → `tipo_periodo_unico` (da idempotencia semanal al paquete y diaria a la alerta).
- `estado='superado'` es nuevo (solo lo usa la alerta al retirar/superponer; el paquete no lo usa).
- **Migración de código:** `paquete.py` pasa a usar `AvisoVigilante(tipo='paquete_lunes', periodo=<lunes>)`; comportamiento externo idéntico. Registro en `app/domain/__init__.py::DOMAIN_DOCUMENTS` se actualiza (una sola puerta).

### 5.2 Config editable

**Umbrales — reusados, ya editables (cero nuevo):**
- **Crítico:** `params.caja_minima` (de la proyección vigente). Rojo.
- **Atención:** `configuracion.service.leer_umbral_atencion_activo(caja_minima)` (`ClaveConfig.UMBRAL_ATENCION`, versionado). Ámbar. Ausente → la banda ámbar no se activa (comportamiento actual); el disparador proyectado ámbar simplemente no dispara hasta configurarlo.

**Config propia de la alerta — nueva, mismo patrón `Configuracion` versionado (nada hardcodeado):**
- `ClaveConfig.ALERTA_CAJA_ACTIVA` (tipo `json`, `{"activa": bool}`) — on/off. **Ausente → `False`** (apagada hasta que el CEO la encienda; postura cauta, espeja el flag off del go-live).
- `ClaveConfig.ALERTA_CAJA_HORIZONTE_MESES` (tipo `json`, `{"meses": int}`) — cuántos meses adelante mira el disparador proyectado. **Ausente → `6`.**

Resolvers nuevos en `configuracion/service.py` (patrón de `leer_umbral_atencion_activo`): `leer_alerta_caja_activa() -> bool`, `leer_alerta_horizonte_meses() -> int`, con sus writers `escribir_*` (crean fila nueva; historial por `vigente_desde`). Editable por dato hoy; toggle en Supuestos = fast-follow. Se agregan las dos claves a `ClaveConfig` y a `_TIPO_POR_CLAVE` (`"json"`). **No** se siembran (resolver da el default) — coherente con `UMBRAL_ATENCION`.

### 5.3 Evaluador de disparadores (`cfo/vigilante/`, S1)

Vive en `cfo/vigilante/` (orquestación: lee servicios), **no** en `cfo/calc` (S1: cfo/calc no importa motor/domain). `paquete.py` ya establece este precedente.

`async def evaluar_disparadores() -> ResultadoAlerta | None` — devuelve `None` si ningún disparador cruza (o si la alerta está apagada / sin config de proyección). `ResultadoAlerta` lleva: lista de disparadores activos (`proyectado`/`real`), severidad global (ámbar/rojo — rojo gana), y los `ResultadoCFO` (cifras COMPAS) que alimentan los tokens.

- **Proyectado:** `proyectar_vigente(escenario="base", mes_inicio=(hoy), horizonte_meses=leer_alerta_horizonte_meses())`. Recorre `data["meses"]`; primer mes con `estado != "ok"` = quiebre. Si hay quiebre dentro del horizonte → dispara. Severidad = ámbar si el estado del quiebre es `atencion`, rojo si `critico`/`negativo`. Cifras: `piso_caja`, umbral cruzado, mes de quiebre. Si `proyectar_vigente` lanza `ProyeccionError` (sin config) → este disparador se abstiene (no rompe).
- **Real hoy:** hallar el mes `EN_EJECUCION`; `conciliacion(mes)["consolidado_reportado"]` = disponible real. Comparar contra el crítico (rojo) y, si está configurado, el atención (ámbar). El crítico (`caja_minima`) y el atención se leen de la misma fuente que usa la proyección vigente (params + `leer_umbral_atencion_activo`), para que la alerta y la curva del front hablen del MISMO umbral. Dispara si `disponible ≤ umbral`. **Frescura:** si `conciliacion` lanza `CierreError` (no hay mes en ejecución) o `sin_dato` ≠ [] (bancos sin reportar) → el disparador se abstiene ese día (no falsa alarma con dato incompleto).

Las cifras SIEMPRE las computa COMPAS (los servicios); el evaluador solo compara y arma evidencia (regla 10 / regla 7: dato ambiguo = abstención, no adivinar).

### 5.4 Texto determinista (plantilla + tokens + verificador)

Sin LLM. El texto se arma por plantilla fija según los disparadores activos; cada cifra es un `[[token]]` respaldado por un `ResultadoCFO` (concepto namespaced `alerta_*`). Ejemplos de línea (los `[[…]]` se sustituyen al final):

- Proyectado ámbar: `⚠️ La caja proyectada entra en zona de atención: el piso baja a [[alerta_piso]] y cruza el umbral de atención [[alerta_umbral_atencion]] en [[alerta_mes_quiebre]].`
- Proyectado rojo: `🔴 La caja proyectada cae bajo el mínimo: piso [[alerta_piso]] cruza el crítico [[alerta_umbral_critico]] en [[alerta_mes_quiebre]].`
- Real rojo: `🔴 El disponible real de hoy [[alerta_disponible_hoy]] está bajo el mínimo [[alerta_umbral_critico]].`

Pipeline (idéntico en garantías al paquete): construir texto crudo con tokens → `verificador.verificar(texto_crudo, conceptos)` como **defensa** (pasa trivial: no hay cifras crudas, todo es token) → `sustituir_tokens` estampa los valores → se guarda `texto` (sustituido) y `texto_crudo`. Formateo de dinero por `conceptos.formatear` (Intl es-CO en el front; aquí `money_str`/formato COP existente). El mes de quiebre se cita como token de texto (no es dinero) con su evidencia.

> Nota de diseño: como no interviene el LLM, no hay riesgo de cifra alucinada por construcción. El `verificador` se corre igual (defensa en profundidad y consistencia con el contrato). Si en el futuro se quiere voz narrativa, se cambia esta función por una llamada a `consultar()` sin tocar el resto.

### 5.5 Job diario (scheduler)

Segundo job en `build_scheduler()`:
`scheduler.add_job(_job_alerta_caja, "cron", hour=8, minute=0, id="vigilante_alerta_caja", coalesce=True, misfire_grace_time=3600, replace_existing=True)`.

`_job_alerta_caja()` (wrapper delgado, espeja `_job_paquete_lunes`):
- Import perezoso de `cfo.config`; **no-op si `not cfo_enabled()`**.
- Import perezoso del resolver; **no-op si `not leer_alerta_caja_activa()`**.
- Llama `cfo.vigilante.alerta.generar_y_entregar_alerta()`, envuelto en try/except + logger (un proactivo no revienta el worker). Toda la lógica vive en esa función, no en el wrapper.

`generar_y_entregar_alerta()` (orquestación; espeja `paquete.generar_y_entregar_paquete`, que internamente llama `consultar`):
- `res = await evaluar_disparadores()` (§5.3) — la evalúa AQUÍ, no en el wrapper del job.
- Retirar borradores de alerta pendientes de días previos → `estado='superado'`.
- Si `res is None`: retirar también el de hoy si existía; fin (no envía nada).
- Si `res`: armar texto (§5.4), upsert `AvisoVigilante(tipo='alerta_caja', periodo=hoy, estado='borrador')`, soft-audit `vigilante.alerta.generada`, enviar al `vigilante_revisor_telegram_id()` con la línea "Respondé 'publicar alerta'".

`ensure_worker_context`/`main` sin cambios (docstring del scheduler se actualiza para nombrar el 2º job).

### 5.6 Publicar — desambiguar los dos tipos (webhook)

Se generaliza el publicar por `tipo`:
- Paquete: el borrador se envía con "Respondé **'publicar'**" → webhook enruta a `_publicar_aviso(tipo='paquete_lunes')`.
- Alerta: "Respondé **'publicar alerta'**" → `_publicar_aviso(tipo='alerta_caja')`.
- `_publicar_aviso(chat_id, cliente, *, tipo)` = el actual `_publicar_paquete` generalizado: toma el último `AvisoVigilante(tipo=…, estado='borrador')` por `generado_at`, difunde `pq.texto` a `listar_vinculos()`, marca `publicado`, soft-audita el evento del tipo, confirma. Devuelve el texto de confirmación (para el dedup).
- El match de comandos: exacto sobre `texto.strip().lower()`; `'publicar'` y `'publicar alerta'` son distintos (una pregunta que MENCIONE cualquiera cae al Q&A). El dedup por `update_id` (paridad con Q&A, ya vigente `df3b0b1`) cubre ambos comandos.
- El Q&A queda **byte-idéntico**.

### 5.7 Auditoría — el CR (regla 11)

Dos eventos nuevos en `AuditEvento` (catálogo **68 → 70**):
- `vigilante_alerta_generada = "vigilante.alerta.generada"` — metadata `{periodo, disparadores:[…], severidad, conceptos_usados}`.
- `vigilante_alerta_publicada = "vigilante.alerta.publicada"` — metadata `{periodo, n_destinatarios}`.

Ambos **soft** (try/except + logger). `test_audit_events.py` sube su aserción `len(AuditEvento)` y `len(CATALOGO_EVENTOS)` a 70 y agrega los dos a la lista esperada.

## 6. Garantía anti-alucinación por la ruta de la alerta

- Ninguna cifra la escribe un modelo: todas salen de servicios de COMPAS (`proyectar_vigente`, `conciliacion`) y se citan por token.
- `verificar` corre sobre el crudo (defensa) antes de sustituir; solo se persiste/difunde el `texto` sustituido, **ya verificado**.
- `publicar alerta` reenvía el `texto` guardado — **no recomputa ni re-verifica ni llama al LLM**.
- Dato incompleto/ambiguo (sin_dato, sin config de proyección) ⇒ **abstención** de ese disparador, no adivinar (regla 7).

## 7. Reglas innegociables

- **Dinero = Decimal**, montos como string en la frontera; formato es-CO (regla 1). Comparaciones de umbral con `Decimal`.
- **TZ única** `now_bogota()`/`today_bogota()`; `periodo` y timestamps coherentes (regla 2).
- **Pydantic strict** en `AvisoVigilante` y en la config (regla 3).
- **`motor.py` 0 diffs** vs `origin/main` (la alerta solo LEE la proyección; no toca la matemática).
- **RUN_SCHEDULER solo en el worker**; job idempotente (regla 6).
- **S1**: el evaluador vive en `cfo/vigilante` (orquestación), `cfo/calc` intacto; `test_s1_aislamiento` sigue verde.
- **Catálogo cerrado** de auditoría: +2 declarados (regla 11).

## 8. Casos borde

- **Alerta apagada** (`ALERTA_CAJA_ACTIVA` ausente/False): job no-op; nada se genera.
- **Sin config de proyección** (`ProyeccionError`): disparador proyectado se abstiene; el real puede seguir.
- **Sin mes en ejecución / bancos sin reportar**: disparador real se abstiene (frescura); el proyectado puede seguir.
- **Ningún disparador**: se retira cualquier borrador pendiente (`superado`); no se envía nada.
- **Caja se recupera con un borrador pendiente sin publicar**: el job del día siguiente lo marca `superado` (no queda un "caja baja" viejo publicable).
- **Revisor no responde**: los borradores diarios se superponen (≤1 pendiente); el revisor ve el de hoy.
- **Reintento de Telegram del "publicar alerta"**: dedup por update_id (no re-difunde).
- **Umbral atención ≤ crítico** (dato malo): el resolver existente lo descarta → ámbar no aplica (comportamiento actual).

## 9. Testing (TDD, real-mongo/mongomock)

- **Modelo generalizado:** `AvisoVigilante` persiste, índice `(tipo, periodo)` único; `paquete.py` sigue verde tras la migración.
- **Config:** resolvers `leer_alerta_caja_activa`/`leer_alerta_horizonte_meses` (default + vigencia configurada); writers crean fila nueva.
- **Evaluador:** proyectado ámbar vs rojo vs sin-quiebre; real bajo/ sobre umbral; abstención por `sin_dato` y por `ProyeccionError`/`CierreError`; horizonte recorta el quiebre lejano.
- **Texto:** cada plantilla arma el crudo correcto; `verificar` pasa; `sustituir_tokens` estampa las cifras; ningún `%`/cifra cruda.
- **Job:** no-op con flag off y con alerta off; genera+envía cuando dispara; retira borrador cuando no dispara; supersede diario; crash-containment.
- **Publicar:** `'publicar alerta'` difunde el borrador de alerta a todos, marca publicado, audita; `'publicar'` sigue tomando el paquete; Q&A byte-idéntico; dedup del comando.
- **Auditoría:** `generada`/`publicada` aterrizan en `audit_log` (patrón `configure_audit`); catálogo 70.
- **Guardas de rama:** `motor.py` 0 diffs; S1; sin float de dinero.

## 10. Fuera de alcance / fast-follows

- Toggle de on/off + horizonte en la UI de Supuestos (junto al editor de umbrales que ya existe).
- Narración con LLM de la alerta (opción; hoy determinista).
- Segundo nivel de recordatorio/resumen (hoy: cada día, sin cooldown, por decisión del CEO).
- Cierre mensual comentado (3ª pieza del vigilante).
- **Go-live (ops del CEO, heredado del paquete):** aprovisionar el worker `compas-jobs` en Render + `VIGILANTE_REVISOR_TELEGRAM_ID`; encender `ALERTA_CAJA_ACTIVA`. Sin eso el job no corre en vivo.
