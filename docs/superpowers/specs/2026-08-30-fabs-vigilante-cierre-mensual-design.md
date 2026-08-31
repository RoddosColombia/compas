# FABS · Vigilante — Cierre mensual comentado (diseño)

**Fecha:** 2026-08-30
**Autor:** Andrés (CEO) + Claude
**Estado:** aprobado para plan (GO CEO 2026-08-30)
**Rama:** `feat/fabs-vigilante-cierre-mensual` (desde `main` 7fe8728)
**Predecesores:** paquete del lunes (`df3b0b1`) + alerta de caja (`fe98962`). Reusa el patrón `AvisoVigilante(tipo)` / borrador→publicar.

---

## 1. Objetivo

Tercera y última pieza del vigilante: cuando un mes **cierra**, FABS **lo comenta** — una retrospectiva narrada (con su voz, como el paquete del lunes) de cómo le fue a RODDOS ese mes. Llega al revisor como borrador; con "publicar cierre" se difunde al comité. Cierra el vigilante (alertas + resumen semanal + retrospectiva de cierre).

## 2. Norte y alcance

**Qué SÍ (esta pieza):**
- Un job diario que **detecta el último mes cerrado** y, si no tiene comentario, genera uno **narrado por FABS** (reusa `consultar()` con un prompt de cierre + el contrato anti-alucinación).
- El comentario cubre 5 puntos (§5.3), reusando las tools que ya existen (rebanadas 3/4).
- Flujo idéntico a las otras piezas: borrador al revisor → "publicar cierre" difunde al comité.

**Qué NO (fuera de alcance / fast-follows):**
- UI. Re-generar el comentario si un mes se reabre y re-cierra (el viejo queda; CR futura).
- Cambios al motor, a los umbrales, o a las tools de FABS (solo se consumen).
- Backfill de meses cerrados históricos (el detector solo mira el ÚLTIMO cerrado).

## 3. Decisiones del CEO (2026-08-30)

1. **Disparo:** **al detectar un mes recién cerrado** (job detector), no cron de fecha fija.
2. **Texto:** **narrado por FABS (LLM)**, como el paquete del lunes (no determinista).
3. **Contenido:** los **5 puntos** de §5.3.

## 4. Arquitectura y flujo

```
[cron diario ~7:30 Bogotá]  (job en el worker compas-jobs; no-op si CFO_ENABLED off)
        │
        ▼
generar_y_entregar_cierre()   (cfo/vigilante — orquestación; espeja paquete.py)
   ├─ mc = último MesControl estado=CERRADO (sort -mes, first_or_none)
   │      ninguno → None (nada que comentar)
   ├─ periodo = mc.mes[:7]  (YYYY-MM)
   ├─ ¿ya existe AvisoVigilante(tipo='cierre_mensual', periodo)? → None (idempotente, un comentario por mes)
   ├─ resp = consultar(_PROMPT_CIERRE(periodo), actor_id='vigilante', cliente=crear_cliente())
   │      abstuvo sin cifras → None (no guarda borrador vacío)
   ├─ guarda AvisoVigilante(tipo='cierre_mensual', periodo, texto=resp.texto, texto_crudo=…, estado='borrador')
   ├─ soft-audit vigilante.cierre.generado
   └─ envía al revisor: "…  Respondé 'publicar cierre' para difundirlo al comité."
        │
        ▼  [revisor responde "publicar cierre"]  (webhook, match exacto + solo revisor)
   difunde pq.texto (YA verificado) a listar_vinculos() → estado='publicado'
   → soft-audit vigilante.cierre.publicado → confirma al revisor.
```

Garantías heredadas: solo se difunde **texto ya verificado**; **publicar nunca re-llama al LLM**; **soft-audit**; scheduler **solo en el worker** (regla 6) y **no-op con flag off**; **dedup por update_id** en el webhook.

## 5. Componentes

### 5.1 Modelo — CERO cambios

`AvisoVigilante(tipo)` (colección `cfo_avisos_vigilante`, índice único `(tipo, periodo)`) ya es genérico. Esta pieza solo introduce el valor de `tipo` **`'cierre_mensual'`** con `periodo = 'YYYY-MM'` (el mes cerrado). La idempotencia "un comentario por mes" la da el índice `(tipo, periodo)` + el guard en el generador.

### 5.2 Detector + generador (`cfo/vigilante/cierre.py`, orquestación — S1)

Nuevo módulo `cfo/vigilante/cierre.py` (importa servicios/dominio; S1 permite orquestación en `cfo/vigilante`, precedente `paquete.py`).

`async def generar_y_entregar_cierre() -> AvisoVigilante | None` — espeja `paquete.generar_y_entregar_paquete`:
- `mc = await MesControl.find(MesControl.estado == EstadoMes.CERRADO).sort(-MesControl.mes).first_or_none()`; `None` → return `None`.
- `periodo = mc.mes[:7]`.
- Si existe `AvisoVigilante(tipo='cierre_mensual', periodo==periodo)` → return `None` (idempotente; **nunca backfill** porque solo se mira el último cerrado, y una vez comentado no se re-genera).
- `resp = await consultar(_PROMPT_CIERRE(periodo), actor_id="vigilante", cliente=crear_cliente())`.
- `resp.abstuvo and not resp.cifras` → return `None` (no borrador vacío).
- Guarda `AvisoVigilante(tipo="cierre_mensual", periodo=periodo, texto=resp.texto, texto_crudo=resp.texto_crudo, estado="borrador", generado_at=now_bogota(), conceptos_usados=list(resp.conceptos_usados))`.
- Soft-audit `vigilante.cierre.generado` con metadata `{periodo, abstuvo, conceptos_usados}` (helper `_audit_soft`, mismo patrón que `paquete.py`).
- Envía al `config.vigilante_revisor_telegram_id()` (si hay) `resp.texto` + la línea "Respondé 'publicar cierre' para difundirlo al comité." (guardas de revisor/cliente nulos como en `paquete.py`).

> **Caveat honesto (documentado):** el detector solo considera el ÚLTIMO mes cerrado. Si se cierran dos meses antes de que corra el job, el intermedio no se comenta (comentar un cierre días tarde es de bajo valor). Aceptado por el CEO.

### 5.3 Prompt de cierre — los 5 puntos

`_PROMPT_CIERRE(periodo)` (prompt fijo, con el mes interpolado por código — NO es una cifra; el modelo NO escribe cifras, cita por token):

> "Comentá el cierre del mes {periodo} de RODDOS, que acaba de cerrar. Cubrí, en orden y breve: (1) cómo cerró la caja del mes frente a cómo venía; (2) el real vs. el presupuesto — qué rubro se salió y por cuánto; (3) la composición del gasto del mes cerrado; (4) la tendencia del mes frente a los meses previos; (5) qué significa este cierre para el rumbo hacia el umbral de caja. Cita cada cifra con su token; si un dato no está disponible, omítelo con honestidad. Sé claro y conciso."

FABS resuelve cada punto con las tools vivas: `caja`/`rumbo_caja` (1, 5), `real_vs_presupuesto(mes=periodo)` (2), `composicion_gasto(ventana="cerrado")` (3), `tendencia_real` (4). El período se pasa como texto en el prompt para anclar las tools con parámetro `mes` al mes correcto.

### 5.4 Job diario (scheduler)

Tercer job en `build_scheduler()`:
`scheduler.add_job(_job_cierre_mensual, "cron", hour=7, minute=30, id="vigilante_cierre_mensual", coalesce=True, misfire_grace_time=3600, replace_existing=True)`.

`_job_cierre_mensual()` (wrapper delgado, espeja `_job_paquete_lunes`): import perezoso de `cfo.config`; **no-op si `not cfo_enabled()`**; luego import perezoso de `generar_y_entregar_cierre` y llamarlo dentro de try/except + logger (un proactivo no revienta el worker). `ensure_worker_context`/`main` sin cambios; docstring del scheduler actualizado para nombrar los TRES jobs.

> Nota: el cierre NO tiene un interruptor propio de config (a diferencia de la alerta, que sí — `ALERTA_CAJA_ACTIVA`). Se gobierna solo por `CFO_ENABLED`, como el paquete del lunes: ambos son resúmenes narrados de bajo riesgo (un humano libera). Si más adelante se quiere apagarlo por separado, es una CR trivial (una clave + un gate, como la alerta).

### 5.5 Publicar — 3er comando `publicar cierre`

El webhook ya enruta `publicar` (paquete) y `publicar alerta` (alerta) por comando exacto a `_publicar_aviso(tipo, evento)`. Se agrega `publicar cierre` → `_publicar_aviso(tipo='cierre_mensual', evento=AuditEvento.vigilante_cierre_publicado)`:
- El match sigue siendo exacto sobre `texto.strip().lower()` (`comando in ("publicar", "publicar alerta", "publicar cierre")`); una frase que MENCIONE cualquiera cae al Q&A.
- `_publicar_aviso` ya adapta el "no hay pendiente" / confirmación por tipo — se extiende con el caso `cierre_mensual` ("No hay un cierre pendiente…" / "Cierre publicado…").
- Dedup por `update_id` corre ANTES (paridad con Q&A, ya vigente). El Q&A queda byte-idéntico.

### 5.6 Auditoría — el CR (regla 11)

Dos eventos nuevos en `AuditEvento` (catálogo **70 → 72**):
- `vigilante_cierre_generado = "vigilante.cierre.generado"` — metadata `{periodo, abstuvo, conceptos_usados}`.
- `vigilante_cierre_publicado = "vigilante.cierre.publicado"` — metadata `{periodo, n_destinatarios}`.

Ambos **soft** (try/except + logger). `test_audit_events.py` sube `len(AuditEvento)` y `len(CATALOGO_EVENTOS)` a 72 y agrega los dos a la lista esperada.

## 6. Garantía anti-alucinación

Idéntica al paquete del lunes: FABS cita cada cifra por token; `consultar` verifica el crudo ANTES de sustituir; solo se guarda/difunde el `texto` sustituido (ya verificado); `publicar cierre` reenvía ese `texto` — **no recomputa ni re-verifica ni re-llama al LLM**. Dato ausente ⇒ el modelo lo omite (abstención honesta, regla 7).

## 7. Reglas innegociables

- **Dinero = Decimal**, string en la frontera; formateo es-CO por `conceptos.formatear` (regla 1). El generador no hace aritmética de dinero (reusa tools).
- **TZ única** `now_bogota()`; `periodo` = `'YYYY-MM'` del mes cerrado (regla 2).
- **Pydantic strict** (el modelo ya cumple; no hay modelo nuevo) (regla 3).
- **`motor.py` 0 diffs** vs `origin/main` (solo se LEE vía tools/servicios).
- **RUN_SCHEDULER solo en el worker**; job idempotente por `(tipo, periodo)` (regla 6).
- **S1**: `cfo/vigilante/cierre.py` es orquestación; `cfo/calc` intacto; `test_s1_aislamiento` verde.
- **Catálogo cerrado**: +2 declarados (regla 11).

## 8. Casos borde

- **Ningún mes cerrado** → `None`, nada que comentar.
- **Mes cerrado ya comentado** → `None` (idempotente); no se re-genera aunque el job corra a diario.
- **Dos meses cerrados entre corridas** → solo el último se comenta (caveat §5.2).
- **`consultar` se abstiene sin cifras** (sin datos del mes) → no guarda borrador vacío, no envía.
- **Revisor no configurado / cliente Telegram nulo** → guarda el borrador, log, no revienta (como `paquete.py`).
- **Reintento de Telegram de "publicar cierre"** → dedup por update_id (no re-difunde).
- **Mes reabierto y re-cerrado** → el comentario viejo queda (fuera de alcance; CR futura).

## 9. Testing (TDD, mongomock/real-mongo)

- **Generador:** último cerrado se comenta (guarda borrador + audita + envía "publicar cierre"); ya comentado → None; ningún cerrado → None; abstención sin cifras → None; revisor nulo → guarda sin enviar. `consultar` se fakea (no se llama al LLM real).
- **Job:** no-op con flag off; corre `generar_y_entregar_cierre` con flag on; crash-containment.
- **Publicar:** `publicar cierre` difunde el borrador de cierre a todos + marca publicado + audita `vigilante.cierre.publicado`; no toca paquete ni alerta; una frase que menciona "publicar cierre" cae al Q&A; dedup del comando.
- **Auditoría:** `generado`/`publicado` aterrizan en `audit_log` (patrón `configure_audit`); catálogo 72.
- **Guardas de rama:** `motor.py` 0 diffs; S1; sin float de dinero.

## 10. Fuera de alcance / fast-follows

- Interruptor de config propio del cierre (hoy solo `CFO_ENABLED`; CR trivial si se quiere).
- Re-generar el comentario tras reabrir/re-cerrar un mes.
- UI. Cualquier cambio a las tools o al motor.
- **Go-live (ops del CEO, heredado):** el mismo worker `compas-jobs` corre los tres jobs; sin aprovisionarlo, ninguno corre en vivo. `VIGILANTE_REVISOR_TELEGRAM_ID` ya es requisito de las piezas 1/2.
