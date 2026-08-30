# FABS · Vigilante — Paquete del lunes (draft → reply "publicar")

- **Fecha:** 2026-08-30 · **Autor:** Claude + CEO (brainstorming aprobado)
- **Incremento:** inc5 (vigilante / Comité de Pagos). **Primera pieza:** el paquete semanal del lunes. FABS pasa de RESPONDER a ACTUAR (proactivo).
- **Flag:** `CFO_ENABLED`. Con el flag apagado, ni el job ni el comando existen (byte-idéntico).
- **Gate:** crítico (proactivo + envía al comité + eventos de auditoría nuevos) → **gate-waiver + GO CEO**. NADA de Kimi (ver memoria `kimi-no-disponible-semanas`). Construcción por SDD.
- **Rama:** `feat/fabs-vigilante-paquete-lunes` (desde `main`).

## 1. Norte (una línea)

Cada **lunes 7:00**, FABS arma un **paquete semanal** (caja hoy · rumbo · IVA que viene · cómo viene el gasto), te lo manda a VOS (el revisor) por Telegram como **borrador**, y cuando respondés **"publicar"** se difunde al comité — con el mismo contrato anti-alucinación (el modelo cita tokens, no inventa cifras) y auditado.

## 2. Alcance (y NO-alcance)

**Entra:** el paquete del lunes, generado por job idempotente, entregado como borrador al revisor, publicado al comité por reply "publicar".
**NO entra (después):** la **alerta por umbral** (watchdog diario) y el **cierre mensual comentado** (las otras 2 piezas del vigilante). "Lo que cambió vs la semana pasada" (necesita snapshot histórico semanal). Difusión selectiva / roles finos del comité. Programación configurable del horario (fijo lunes 7:00 en esta pieza).

## 3. Principio inamovible

**El digest respeta el contrato anti-alucinación.** El texto del paquete lo genera `cfo.agente.servicio.consultar` (reusa el pipeline: el modelo cita `[[token]]`, el verificador rechaza cifras crudas, se sustituye tras verificar). Lo que se guarda y se difunde es el texto YA sustituido (verificado en la generación; no se re-genera ni re-verifica al publicar). El vigilante NO computa cifras propias.

## 4. Piezas que se REUSAN (ya existen)

- **Generar el digest:** `cfo.agente.servicio.consultar(pregunta, *, actor_id, cliente=None, historial=None) -> RespuestaCFO` — plano, sin acoplamiento a request; trae su propia verificación + abstención + auditoría (`cfo.consulta`/`cfo.respuesta`) + backstop (nunca lanza). `RespuestaCFO` trae `texto` (sustituido), `texto_crudo` (tokens), `abstuvo`, `conceptos_usados`, `cifras`. Las tools del digest ya existen: `caja_disponible_hoy`, `rumbo_caja`, `iva_del_cuatrimestre`, `tendencia_real`.
- **Enviar por Telegram:** `cfo.telegram.cliente.ClienteTelegram.enviar(chat_id: int, texto: str) -> None` (traga sus errores de red). `crear_cliente_telegram() -> ClienteTelegramProto | None` (None si no hay token).
- **Allowlist (comité):** `cfo.telegram.repositorio.listar_vinculos() -> list[VinculoTelegram]` (`VinculoTelegram.telegram_id`, `.user_id`). En chat 1:1 `chat_id == telegram_id`. `vinculos.resolver(telegram_id) -> user_id | None`.
- **Webhook:** `cfo.telegram.webhook.procesar_update(update, *, cliente_telegram, cliente_llm=None)` — hoy: autoriza por vínculo, dedup por update_id, llama `consultar`, envía. Se le agrega el router de comando ANTES del Q&A.
- **Scheduler:** `app.jobs.scheduler.build_scheduler()` devuelve un `AsyncIOScheduler(timezone="America/Bogota")` **vacío**; `ensure_worker_context(settings)` exige `settings.run_scheduler` (solo `compas-jobs`). Este es el PRIMER job que se registra.
- **Config env-based:** `cfo.config` (`cfo_api_key`, `telegram_bot_token`, …). `core.time.now_bogota`.
- **Auditoría:** `audit.service.emit_audit(evento, entidad, entidad_id=None, actor_id=None, metadata=None)`; `audit.events.AuditEvento` es catálogo CERRADO (regla 11), hoy 66.

## 5. Lo NUEVO que se construye

### 5.1 Config del revisor — `cfo/config.py`
`def vigilante_revisor_telegram_id() -> int | None`: lee `VIGILANTE_REVISOR_TELEGRAM_ID` (env), `int` o None si no está. Es a QUIÉN se le manda el borrador y QUIÉN puede publicar. (Patrón idéntico a `telegram_bot_token`; el CEO lo setea en Render — paso de ops.)

### 5.2 Modelo `PaqueteVigilante` — `cfo/vigilante/modelos.py` (nuevo)
`class PaqueteVigilante(Document)` (colección `cfo_paquetes_vigilante`, S1): `semana: str` ('YYYY-MM-DD' del lunes, **índice único** = idempotencia), `texto: str` (sustituido, lo que se difunde), `texto_crudo: str` (tokens, trazabilidad), `estado: str` ('borrador'|'publicado'), `generado_at: datetime`, `publicado_at: datetime | None`, `conceptos_usados: list[str]`.

### 5.3 Los 2 eventos de auditoría — `audit/events.py` (este spec = la declaración/CR)
Bloque nuevo `# ── CR-CFO-3 (2) — FABS vigilante paquete lunes (GO CEO 2026-08-30) ──` (catálogo 66→68):
- `vigilante_paquete_generado = "vigilante.paquete.generado"` (metadata `{semana, abstuvo, conceptos_usados}`).
- `vigilante_paquete_publicado = "vigilante.paquete.publicado"` (metadata `{semana, n_destinatarios}`).
Actualizar el conteo del catálogo + el test de completitud.

### 5.4 Generador + entrega del borrador — `cfo/vigilante/paquete.py` (nuevo)
`async def generar_y_entregar_paquete() -> PaqueteVigilante | None`:
- `semana = now_bogota().date().isoformat()` (el lunes de hoy). Si ya existe `PaqueteVigilante(semana=…)` → return None (idempotente, regla 6).
- `resp = await consultar(_PROMPT_PAQUETE, actor_id="vigilante", cliente=crear_cliente())`. `_PROMPT_PAQUETE` = plantilla fija: "Compón el paquete semanal del lunes para el CEO: caja disponible hoy, el rumbo de la caja hacia el umbral, el IVA del cuatrimestre que viene, y cómo viene el gasto vs el mes pasado. Cita cada cifra con su token; si un dato no está disponible, omítelo con honestidad." (el modelo llama las tools, cita tokens, se sustituye).
- Si `resp.abstuvo` y no hay cifras → NO guardar borrador vacío; log + return None (nada útil que decir).
- Guardar `PaqueteVigilante(semana, texto=resp.texto, texto_crudo=resp.texto_crudo, estado="borrador", generado_at=now, conceptos_usados=resp.conceptos_usados)`. Emitir `vigilante.paquete.generado`.
  *(Nota: `consultar` audita su propio `cfo.consulta`/`cfo.respuesta` con `canal="api"` hardcodeado — limitación pre-existente, no hay param de canal hoy. El evento `vigilante.paquete.generado` es lo que distingue esta generación como proactiva/del job. Hilar un param `canal`/`origen` por `consultar` es un fast-follow, no de esta pieza.)*
- `revisor = config.vigilante_revisor_telegram_id()`; si None → log (ops no lo configuró), return el paquete igual (queda de borrador). Si hay revisor → `enviar(revisor, "📋 *Borrador del paquete del lunes*\n\n{texto}\n\n_Respondé_ `publicar` _para difundirlo al comité._")`.
- Nunca lanza (envuelve en try/except-log; un job proactivo no debe reventar el worker).

### 5.5 El job del cron — `app/jobs/scheduler.py`
En `build_scheduler()`, registrar el PRIMER job: `sched.add_job(_job_paquete_lunes, "cron", day_of_week="mon", hour=7, minute=0, id="vigilante_paquete_lunes", coalesce=True, misfire_grace_time=3600, replace_existing=True)`. `_job_paquete_lunes` = wrapper async que llama `cfo.vigilante.paquete.generar_y_entregar_paquete()` (import perezoso para no acoplar el scheduler al dominio cfo si el flag está off — si `not cfo.config.cfo_enabled()`: no-op). El registro NO corre en el web (regla 6, ya garantizado por `ensure_worker_context`).

### 5.6 Router de comando "publicar" — `cfo/telegram/webhook.py`
En `procesar_update`, DESPUÉS de resolver `user_id` (autorizado) y ANTES del path de Q&A: si `texto.strip().lower() == "publicar"` **y** `telegram_id == config.vigilante_revisor_telegram_id()` → **comando de publicación** (no pregunta):
- Buscar el último `PaqueteVigilante` en estado `borrador` (el de esta semana). Si no hay → `enviar(chat_id, "No hay un paquete pendiente para publicar.")`, return.
- Si hay → por cada `v in listar_vinculos()`: `enviar(v.telegram_id, paquete.texto)`. Marcar `estado="publicado"`, `publicado_at=now`. Emitir `vigilante.paquete.publicado` (`{semana, n_destinatarios}`). Confirmar al revisor (`enviar(chat_id, "✅ Paquete publicado al comité (N destinatarios).")`). return.
- Si `texto=="publicar"` de un NO-revisor → cae al Q&A normal (inocuo; FABS responde). Un mensaje que solo CONTIENE "publicar" (p. ej. "¿debería publicar X?") NO matchea (comparación exacta del texto completo).
El comando de publicación **no** re-genera ni re-verifica: difunde el `texto` ya verificado del borrador.

## 6. Contrato de datos

`PaqueteVigilante` (§5.2). Eventos (§5.3). El `texto` guardado ya está sustituido (verificado en la generación) → seguro para difundir. `semana` único = un paquete por semana.

## 7. Idempotencia / concurrencia

Un paquete por `semana` (índice único). `coalesce=True` + `misfire_grace_time` en el job → si el worker estuvo caído y arranca tarde, una sola ejecución. Si `generar_y_entregar_paquete` corre dos veces la misma semana, la 2ª ve el paquete existente y no hace nada. Publicar dos veces: el 2º "publicar" no encuentra `borrador` (ya está `publicado`) → "no hay paquete pendiente".

## 8. Trampas

1. **No difundir texto no verificado:** solo se difunde `paquete.texto` (sustituido tras verificar en la generación). El comando de publicar NO llama al LLM.
2. **Borrador vacío:** si `consultar` abstiene sin cifras, NO guardar ni enviar un paquete vacío.
3. **Revisor no configurado:** sin `VIGILANTE_REVISOR_TELEGRAM_ID` el borrador se genera pero no se envía (log claro); publicar exige que el emisor sea el revisor.
4. **Comparación exacta de "publicar":** `texto.strip().lower() == "publicar"`, no `in`, para no secuestrar preguntas que mencionen la palabra.
5. **El job no revienta el worker:** try/except-log; un fallo del LLM/Telegram se traga (como `consultar`/`enviar` ya hacen).
6. **Flag off:** con `CFO_ENABLED=false` el job es no-op y el comando cae al Q&A (que también está gated). Cero efecto.
7. **Catálogo cerrado:** los 2 eventos se declaran en events.py (este spec = CR); `emit_audit` los valida.

## 9. Errores / abstención

Sin API key / sin config de proyección → `consultar` abstiene → no se guarda borrador vacío (log). Sin token de Telegram → `crear_cliente_telegram()` None → no se envía (log). Sin revisor → no se envía. Todo fail-soft: el worker sigue vivo.

## 10. Pruebas (TDD)

- **Generador** (fakes: `consultar` devuelve un `RespuestaCFO` conocido con cifras; `enviar` fake): guarda `PaqueteVigilante` estado borrador, emite `vigilante.paquete.generado`, envía al revisor; segunda corrida misma semana → no duplica (idempotencia); `consultar` que abstiene sin cifras → no guarda ni envía.
- **Job/scheduler**: `build_scheduler()` con `run_scheduler=true` registra el job `vigilante_paquete_lunes` con cron lunes 7:00 America/Bogota; con `CFO_ENABLED=false` el wrapper es no-op.
- **Router "publicar"** (webhook con fakes): revisor + "publicar" + borrador pendiente → difunde a todos los vínculos, marca publicado, emite `vigilante.paquete.publicado`, confirma; sin borrador → "no hay paquete pendiente"; no-revisor "publicar" → cae al Q&A (llama `consultar`); "¿debería publicar X?" → Q&A (no matchea el comando).
- **Eventos**: `AuditEvento("vigilante.paquete.generado")` y `.publicado` válidos; conteo del catálogo actualizado; test de completitud verde.
- **Regresión**: `motor.py` 0 diffs; `ruff` limpio; el Q&A por Telegram existente sigue igual (el comando es aditivo y previo).

## 11. Innegociables

Dinero = Decimal (aunque acá el vigilante no computa: reusa las tools); el modelo NO inventa cifras (todo pasa por `consultar`); `motor.py` cero diffs; **eventos de auditoría declarados** (regla 11, este spec = CR, GO CEO); idempotencia del job (regla 6); `RUN_SCHEDULER` solo en `compas-jobs` (regla 6, ya garantizado); flag `CFO_ENABLED`; gate-waiver + GO CEO (NADA de Kimi, NUNCA simulado).

## 12. Dependencia de ops (paso del CEO, como el go-live de Telegram)

Para que corra en vivo: el worker **`compas-jobs`** debe estar corriendo (`RUN_SCHEDULER=true`, 1 instancia) con las env vars (`ANTHROPIC_API_KEY`, `CFO_ENABLED=true`, `TELEGRAM_BOT_TOKEN`, y **`VIGILANTE_REVISOR_TELEGRAM_ID`** = el telegram_id del CEO). Se documenta como pasos guiados; el código no lo requiere para mergear (el job existe y se testea con fakes).

## 13. Sub-rebanadas (para el plan)

**A** generador + modelo + eventos + entrega al revisor (`config`, `modelos`, `paquete.py`, events). **B** el job del cron (scheduler). **C** el router "publicar" en el webhook + difusión + evento publicado. Orden: A (genera+guarda+envía borrador) → B (lo dispara el lunes) → C (publicar).

---
*Vigilante, pieza 1 (paquete del lunes). Método: brainstorming (aprobado) → este spec → writing-plans → SDD → gate-waiver + GO CEO. Alerta por umbral y cierre mensual comentado → piezas siguientes. `motor.py` intocable.*
