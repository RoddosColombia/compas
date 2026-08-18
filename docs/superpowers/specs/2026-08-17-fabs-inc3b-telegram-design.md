# FABS · Inc3 Pieza B — Canal Telegram + piloto Q&A (design)

- **Fecha:** 2026-08-17 · **Autor:** Claude (con GO del CEO al diseño)
- **Fase:** inc3, Pieza B (el canal, sobre la Pieza A ya mergeada en `main`)
- **Rama base:** `main` (`f4d651b`+) · **Rama:** `feat/fabs-inc3b-telegram`
- **Gate:** Kimi (crítico — webhook/identidad/canal que expone a FABS) + CR-CFO-2. Flag `CFO_ENABLED` **apagado** hasta go-live.

## 0. Una línea

Poner a FABS a **conversar por Telegram** con el piloto (CEO/CGO/CFO): un webhook que rechaza updates falsos, un vínculo `telegram_id↔user_id` por allowlist (endpoint admin), hilos de conversación por usuario que **guardan las citas con tokens (no los valores)** para que la garantía anti-alucinación de Pieza A se mantenga turno a turno, y la respuesta del servicio de Pieza A enviada por `sendMessage`. Todo detrás del flag; reactivo puro (responde a quien le escribe).

## 1. Alcance

**Entra:** cliente Telegram saliente (httpx, inyectable) · webhook con verificación de secret token · allowlist `cfo_vinculos_telegram` + endpoint admin (RBAC + auditoría) · hilos `cfo_hilos` (guardan tokens, ventana acotada) · extensión aditiva del servicio (acepta historial, expone `texto_crudo`) · CR-CFO-2 (2 eventos de vínculo) · observabilidad.

**NO entra:** alertas proactivas / Comité de Pagos (inc4) · chat embebido en la app (inc5) · encender el flag / crear el bot / registrar el webhook (go-live, §8) · escrituras sobre datos financieros. `motor.py`/`calc/*`/el núcleo de Pieza A (verificador/sustituidor) **sin cambios** salvo la extensión aditiva del servicio.

## 2. Arquitectura (nuevo módulo `app/cfo/telegram/`)

```
app/cfo/telegram/
  __init__.py
  modelos.py        VinculoTelegram + HiloCFO (Beanie Documents, colecciones cfo_*)
  repositorio.py    única puerta de escritura (S1) para cfo_vinculos_telegram + cfo_hilos
  cliente.py        ClienteTelegram (httpx saliente, lazy, inyectable) + crear_cliente_telegram()
  webhook.py        el handler del update (verifica secret, resuelve usuario, llama servicio, responde)
  vinculos.py       lógica de la allowlist (resolver telegram_id→user_id; alta/baja)
  router.py         POST /api/v1/cfo/telegram/webhook + POST/GET/DELETE /api/v1/cfo/telegram/vinculos
app/cfo/config.py   + telegram_bot_token / telegram_webhook_secret / cfo_hilo_ventana
app/cfo/agente/servicio.py   consultar acepta historial + expone texto_crudo (aditivo)
app/cfo/agente/modelos.py    RespuestaCFO + texto_crudo
app/audit/events.py          CR-CFO-2: cfo.vinculo_creado / cfo.vinculo_eliminado (64→66)
app/domain/__init__.py       registrar VinculoTelegram + HiloCFO en DOMAIN_DOCUMENTS
app/main.py                  montar el router telegram SOLO si cfo_enabled()
```

**S1:** el módulo `telegram/` escribe solo colecciones `cfo_*` (vía `repositorio.py`) e importa solo capa de servicios (`app.cfo.agente.servicio`, `app.audit.service`, `app.auth.*`, `app.core.*`) + `httpx`/`beanie` — nunca `app.domain.*` ni el driver de Mongo directo. Se extiende el test S1 para escanear `cfo/telegram/`.

## 3. Componentes

### 3.1 Cliente Telegram (`cliente.py`) — saliente, inyectable
- `class ClienteTelegram`: import perezoso de `httpx`; `async def enviar(self, chat_id: int, texto: str) -> None` → `POST https://api.telegram.org/bot{token}/sendMessage` (`{chat_id, text}`), timeout acotado, errores logueados (no revientan el webhook).
- `def crear_cliente_telegram() -> ClienteTelegram | None` — `None` si no hay `TELEGRAM_BOT_TOKEN` (env). Token **solo** env (regla 12).
- Tests con un `ClienteTelegramFake` (registra los envíos; sin red).

### 3.2 Allowlist + vínculos (`modelos.py`, `repositorio.py`, `vinculos.py`)
- `VinculoTelegram(Document)`: `telegram_id: int` (índice **único**), `user_id: str`, `creado_por: str`, `creado_at: datetime`. Colección `cfo_vinculos_telegram`.
- `repositorio.py`: `crear_vinculo`, `eliminar_vinculo`, `resolver_usuario(telegram_id) -> str | None` (única puerta de escritura/lectura, S1).
- `vinculos.py`: la lógica (validar el `user_id` existe y está activo antes de vincular; resolver).
- **Endpoint admin** (`router.py`): `POST /api/v1/cfo/telegram/vinculos` `{telegram_id, user_id}` (`require_role(Role.admin)`) → crea + audita `cfo.vinculo_creado`; `GET` lista; `DELETE /{telegram_id}` → audita `cfo.vinculo_eliminado`. Body strict.

### 3.3 Hilos (`modelos.py`, `repositorio.py`) — guardan TOKENS, no valores (el punto clave)
- `HiloCFO(Document)`: `user_id: str` (índice único), `turnos: list[dict]` (`{"rol": "user"|"assistant", "contenido": str}`), `actualizado_at: datetime`. Colección `cfo_hilos`.
- **Qué se guarda:** por turno, `{user: pregunta}` + `{assistant: texto_crudo}` — el `texto_crudo` es la respuesta del modelo **ANTES de sustituir** (con `[[tokens]]`, sin valores). Así, al re-alimentar el historial, el modelo ve su propia cita `[[caja_hoy]]`, **nunca el número** → no puede re-exponer ni comparar cifras (la garantía de Pieza A se mantiene entre turnos).
- **Ventana acotada (costo):** al construir el historial para el loop se toman los **últimos `cfo_hilo_ventana` turnos** (default configurable, p.ej. 8 mensajes). El hilo **persiste completo** (o hasta un máximo alto); **sin TTL naïve** (no expira por reloj). Reset de hilo = fuera de alcance del piloto (comando futuro).

### 3.4 Extensión del servicio (`agente/servicio.py`, `agente/modelos.py`) — aditiva
- `consultar(pregunta, *, actor_id, cliente=None, historial: list[dict] | None = None) -> RespuestaCFO`. El historial (mensajes previos `{role, content}` con tokens) se **antepone** a `[{"role":"user","content":pregunta}]` al llamar `conversar` (y en el reintento). Default `None` ⇒ comportamiento idéntico al de hoy (el endpoint `/api/v1/cfo` de inc2 no cambia).
- `RespuestaCFO` gana `texto_crudo: str | None` = el texto del modelo **antes de sustituir** (para guardar en el hilo). `texto` sigue siendo el **sustituido** (lo que ve el usuario). En abstención, `texto_crudo == texto` (canned, sin tokens).
- El verificador y el sustituidor de Pieza A **no cambian**. El orden verify→sustituir se mantiene.

### 3.5 Webhook (`webhook.py`, `router.py`)
`POST /api/v1/cfo/telegram/webhook`:
1. **Doble barrera:** ruta montada solo si `cfo_enabled()`; guard 404 defensivo.
2. **Verificar** `X-Telegram-Bot-Api-Secret-Token` == `telegram_webhook_secret()`; si no coincide → 403 (rechaza spoofing). Sin secret configurado → 403.
3. Parsear el update: `message.from.id` (`telegram_id`), `message.chat.id` (`chat_id`), `message.text`. Update sin `message`/sin `text` → 200 y se ignora (o "solo texto por ahora").
4. `resolver_usuario(telegram_id)`; **no vinculado** → `sendMessage` "No estás autorizado para usar FABS. Tu ID de Telegram es `{telegram_id}` — pídele al administrador que te vincule." + 200 (NO llama al servicio).
5. Cargar el hilo → `historial` (últimos N).
6. `resp = await servicio.consultar(text, actor_id=user_id, historial=historial)`.
7. Guardar el turno crudo (`pregunta`, `resp.texto_crudo`) en el hilo.
8. Formatear la respuesta: `resp.texto` (narración sustituida) + un bloque **"Cifras (con su fuente)"** con las `resp.cifras` concept-bound (la mitigación de Pieza A: las cifras autoritativas al lado). Abstención → solo el texto.
9. `cliente_telegram.enviar(chat_id, respuesta)` → **200** (Telegram espera 200; procesamiento síncrono es aceptable para el piloto de 3 personas).

**Radar del piloto (idempotencia):** Telegram **reintenta** el mismo update (mismo `update_id`) si el webhook no responde 200 a tiempo. Con la llamada al LLM síncrona (2-10 s) rara vez pasa, pero si pasa habría doble respuesta + doble turno en el hilo. Mitigación barata incluida: **antes de procesar, si el último turno `user` del hilo es idéntico a esta `pregunta`, se ignora** (dedup de duplicados adyacentes). Un fast-200 + proceso async es un refinamiento posterior (no en el piloto).

## 4. Config (`app/cfo/config.py`)
- `telegram_bot_token() -> str | None` (env `TELEGRAM_BOT_TOKEN`; None ⇒ cliente None).
- `telegram_webhook_secret() -> str | None` (env `TELEGRAM_WEBHOOK_SECRET`; None ⇒ webhook rechaza todo).
- `cfo_hilo_ventana() -> int` (env `CFO_HILO_VENTANA`, default 8).
- Todos por env; secretos **nunca** en repo.

## 5. Auditoría — CR-CFO-2 (catálogo cerrado, regla 11)
Dos eventos nuevos (64 → 66):
- `cfo.vinculo_creado` — el admin vincula un `telegram_id` a un `user_id`. `actor_id`=admin, `metadata={telegram_id, user_id}`.
- `cfo.vinculo_eliminado` — baja del vínculo. `metadata={telegram_id}`.
El Q&A **reusa** `cfo.consulta`/`cfo.respuesta` (ya en el catálogo) con `metadata.canal="telegram"`. La política O1 fail-soft de auditoría se mantiene (una consulta es lectura).

## 6. Seguridad
- **Webhook:** secret token obligatorio (rechaza updates falsos); sin él, 403. El secret solo por env.
- **Sin suplantación:** `telegram_id` no vinculado ⇒ rehúsa (no llama al servicio, no filtra datos). El `actor_id` es el `user_id` REAL de la allowlist ⇒ RBAC + auditoría aplican.
- **Respuesta solo al que escribió** (`chat_id` del update). Reactivo puro (no envía no solicitado — proactivo = inc4).
- **Tokens/secretos** (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `ANTHROPIC_API_KEY`): solo env en Render; gitleaks en CI.
- **PII:** la pregunta del usuario se guarda en `cfo.consulta.metadata.pregunta` y en el hilo (`cfo_hilos`) — usuario interno tras la allowlist. Minimización si se abre a más gente (fuera de alcance).

## 7. Flag + pruebas
- **Flag apagado ⇒ COMPAS idéntico:** el router telegram no se monta; `crear_cliente_telegram()`/`crear_cliente()` devuelven None sin tokens. Ruta ausente de `create_app()`.
- **Todo con mocks:** `ClienteTelegramFake` (envíos) + `ClienteFake` de Anthropic (Pieza A) ⇒ CI verde **sin** `TELEGRAM_BOT_TOKEN` ni `ANTHROPIC_API_KEY`.
- Tests: webhook rechaza secret inválido; `telegram_id` no vinculado → mensaje de "no autorizado" (sin llamar al servicio); vinculado → consulta + respuesta enviada; el hilo guarda `texto_crudo` (tokens, no valores) y lo re-alimenta (turno 2 ve `[[caja_hoy]]`, no el número); endpoint admin crea/lista/borra + audita; ventana acotada; flag-off ⇒ ruta ausente; S1 cubre `cfo/telegram/`; `motor.py` 0 diffs; Decimal/cero float; ruff.

## 8. Go-live (pasos del CEO/ops, NO en esta pieza)
1. Crear el bot en @BotFather → `TELEGRAM_BOT_TOKEN`.
2. `setWebhook` a `https://compas-api…/api/v1/cfo/telegram/webhook` con un `secret_token` → `TELEGRAM_WEBHOOK_SECRET`.
3. `ANTHROPIC_API_KEY` + `TELEGRAM_*` en Render (compas-api).
4. Encender `CFO_ENABLED` (respetando **O-1**: no en prod sin auditoría retroactiva).
5. Cargar los 3 vínculos (endpoint admin): cada usuario le escribe al bot, este le dice su `telegram_id`, y el admin lo vincula.

## 9. DoD
1. Webhook seguro (secret verificado), reactivo, responde 200; no-vinculado rehúsa sin llamar al servicio.
2. Vínculo por endpoint admin (RBAC admin + auditoría CR-CFO-2); allowlist en `cfo_*`.
3. Hilos guardan tokens (no valores) y la garantía de Pieza A se mantiene entre turnos (test explícito); ventana acotada; sin TTL naïve.
4. Servicio extendido aditivamente (historial + texto_crudo); el endpoint `/api/v1/cfo` de inc2 sin cambio de comportamiento.
5. Flag-off ⇒ COMPAS idéntico; `motor.py` 0 diffs; S1 cubre telegram/; Decimal/cero float; ruff; suite verde. Todo con mocks (sin tokens/key).
6. Roadmap + paquete Kimi de código (`planning/phases/fabs/auditorias/INC3B-I/`).

---
*Pieza B de inc3. Ante conflicto de alcance mandan `COMPAS_NORTE.md`, `CLAUDE.md`, el roadmap de FABS. El flag sigue apagado hasta el go-live (§8) + decisión del CEO.*
