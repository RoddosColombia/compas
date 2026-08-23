# SOLICITUD de auditoría Kimi — FABS inc3 Pieza B (canal Telegram + piloto Q&A) · CÓDIGO

- **Target:** PR (código) · **Ronda:** I (inicial) · **Umbral: ≥ 9.0**
- **Rama:** `feat/fabs-inc3b-telegram` · **Rango:** `f4d651b..530219a`
- **Fecha:** 2026-08-22 · **Solicita:** Andrés (CEO) / Claude
- **Gate de DISEÑO ya aprobado por Kimi: 9.3 GO** (B-1 dedup por `update_id`, B-2 reenvío no-silencioso, B-3 vínculo uno-a-uno aplicados). Este es el gate de **CÓDIGO**.
- **Gobernanza de merge (regla CEO 2026-08-17):** la Pieza B **NO mergea** hasta tener **A-retro ≥ 9** (INC3A-I) **Y** **B-código ≥ 9** (esta auditoría). Flag `CFO_ENABLED` **apagado** ⇒ COMPAS/main byte-idéntico (exposición cero).
- **Por qué gate (crítico):** introduce un **webhook público** nuevo, **modifica la matriz de RBAC** (`permissions.py`), **amplía el catálogo cerrado de auditoría** (regla 11, 64→66) y crea un **binding de identidad** `telegram_id↔user_id` que decide qué `actor_id` real queda detrás de cada mensaje.

## Qué es (una línea)

FABS conversable por Telegram para el piloto (CEO/CGO/CFO): webhook fail-closed + allowlist admin del vínculo `telegram_id↔user_id` + hilos por usuario que guardan el texto **CRUDO** del modelo (con `[[tokens]]`, **nunca valores**) + respuesta del servicio de Pieza A por `sendMessage`. Todo **aditivo** sobre Pieza A (el núcleo verificador/sustituidor/prompt **no se toca**) y **detrás del flag**.

## Qué hace, con evidencia verificada al peso

1. **La garantía anti-alucinación sobrevive los turnos (invariante central).** El usuario recibe el texto **sustituido** (valores inline); el hilo persiste `resp.texto_crudo` (con `[[tokens]]`). En el turno siguiente, `historial_para_loop` re-alimenta al modelo SOLO esos tokens — **el modelo nunca vuelve a ver un valor sustituido**, así que no puede lavar una cifra vieja/errónea como propia. Los valores viven solo en el mensaje al usuario y en `ultimo_envio` (en cuarentena, jamás re-inyectado).
2. **Servicio aditivo (Pieza A intacta):** `consultar(pregunta, *, actor_id, cliente=None, historial=None)`. Con `historial=None` (default) el comportamiento es **idéntico a inc2** (el endpoint `POST /api/v1/cfo` no cambia). Expone `RespuestaCFO.texto_crudo` (pre-sustitución) para el hilo. Verificador/sustituidor/prompt **cero cambios**.
3. **Vínculo uno-a-uno (B-3):** único en `telegram_id` **y** en `user_id` (índices únicos Beanie). `repositorio.py` es la **única puerta de escritura** (S1) y traduce `DuplicateKeyError` a excepción de dominio `VinculoDuplicado` en la frontera.
4. **Webhook fail-closed:** flag apagado ⇒ ruta ausente (barrera en `main.py`) **+** guard 404; secret inválido/ausente → 403 (`secrets.compare_digest`, tiempo constante); sin bot token → 503; **no-vinculado → rehúsa sin llamar al servicio** (no gasta LLM, no filtra nada, le dice su `telegram_id`). Parsing defensivo (`_extraer` con `.get`): un update malformado se ignora, **nunca revienta**.
5. **Dedup por `update_id` (B-1) + reenvío no-silencioso (B-2):** un reintento de Telegram del mismo `update_id` **no re-llama al LLM**; reenvía `ultimo_envio`. Persistencia **antes** del envío ⇒ un crash entre guardar y enviar se recupera por el retry de Telegram.
6. **RBAC por permiso, no por rol (regla 9 / H-1):** los 3 endpoints admin (`POST`/`GET`/`DELETE /api/v1/cfo/telegram/vinculos`) van con `require_permission("cfo:telegram_administrar")` (permiso **admin-only** nuevo en la matriz canónica), **no** `require_role` — que el repo reserva a administración de identidad (`/users`) y prohíbe en negocio. El test de matriz canónica se **espejó** (no se debilitó: sigue igualdad total).
7. **Auditoría de estado, no fail-soft:** `vincular`/`desvincular` emiten `cfo.vinculo_creado`/`cfo.vinculo_eliminado` (CR-CFO-2, catálogo 64→66) con `entidad="cfo_vinculo_telegram"` + `entidad_id=str(telegram_id)` (convención state-op del repo, alimenta el índice forense) y **propagan** si la auditoría falla (a diferencia del Q&A, que sí es fail-soft). Un vínculo creado-pero-audit-falló da **5xx**, nunca un falso 409 ni un falso éxito.

## Puntos a auditar con lupa

- **Invariante anti-alucinación end-to-end (lo más importante):** ¿algún camino por el que un **valor sustituido** re-entre al contexto del modelo vía el hilo (`turnos`, `historial_para_loop`, `ultimo_envio`, la corrección intra-turno)? Si un valor puede re-inyectarse, es brecha crítica.
- **Alternancia del historial:** `registrar_turno` guarda pares `[user, assistant]` y recorta a 40; `historial_para_loop` toma la ventana y **descarta un `assistant` líder**. ¿Empieza SIEMPRE en `user` y alterna, para toda ventana (par/impar/≥len/1/0)? (la API de Anthropic rechaza lo contrario).
- **RBAC:** ¿la desviación `require_permission` es correcta y admin-only real? ¿algún camino no-admin muta la allowlist? ¿el test de matriz se espejó (no se relajó)?
- **Integridad de auditoría:** ¿el orden `crear_vinculo` → (duplicado ⇒ `VinculoDuplicado` antes de auditar) → `emit_audit` garantiza que la auditoría solo dispara en éxito real y que un fallo de audit no se disfraza?
- **Flag-off = COMPAS idéntico:** `motor.py` 0 diffs; importar el módulo es inerte (sin lectura de token, sin Mongo, httpx lazy); rutas ausentes con el flag apagado.
- **S1:** `cfo/telegram/**` escribe solo `cfo_*` (vía `repositorio.py`) e importa solo capa de servicios + Beanie/pymongo/httpx — nunca `app.domain.*` ni el driver async.

## Evidencia local (verde)

- **Suite backend completa: 1085 passed / 98 skipped (requires_real_mongo) / 0 failed** con el flag apagado (COMPAS byte-idéntico).
- `tests/cfo/telegram/`: **36 passed / 3 skipped** (los 3 skips = unicidad/upsert que exigen Mongo real). `python -m ruff check app/cfo/` limpio.
- `motor.py` **cero diffs** (`git diff f4d651b..HEAD -- app/proyeccion/motor.py app/presupuesto/motor.py` vacío). Sin `float(` en `cfo/telegram/`. S1 escanea `cfo/telegram/` y pasa **limpio, sin exención**.
- **Review final whole-branch (opus): "Ship-ready", 0 Critical / 0 Important.** El invariante anti-alucinación se probó end-to-end (traza turn1→stored→turn2). Construido por **SDD**: 7 tareas, subagente fresco + review por tarea (Task 6 revisado por opus por tocar RBAC) + review final whole-branch.

## Alcance / no-alcance

- **Entra:** módulo `app/cfo/telegram/` (7 archivos + tests) + toques aditivos (servicio `historial`/`texto_crudo`, config del canal, catálogo +2, permiso RBAC +1, registro Documents, `main.py` tras el flag). CR-CFO-2.
- **NO entra:** **encender el flag** (go-live: `setWebhook` + secret + envs en Render + `ANTHROPIC_API_KEY` + carga de los 3 vínculos + **O-1** auditoría retroactiva antes de encender en prod) — es tarea de operación del CEO, fuera de esta pieza. Jobs/Comité de Pagos = inc4. Chat embebido = inc5. `motor.py`/`calc/*` sin cambios.
- **Límites residuales declarados (aceptados para el piloto flag-off):** (1) **dedup TOCTOU** — el dedup es check-then-set sin claim atómico; si Telegram RE-entrega el mismo `update_id` mientras la 1ª petición sigue en el LLM (LLM más lento que el timeout de entrega de Telegram), ambas pasan `es_reintento==False` → doble respuesta + doble costo LLM. **No afecta la garantía anti-alucinación**; ventana estrecha, 3 usuarios, flag apagado; endurecimiento futuro = claim atómico del `update_id` antes de llamar al LLM (documentado en `webhook.py`). (2) Un fallo de `sendMessage` se absorbe con 200 (trade-off deliberado: devolver no-200 re-cobraría el LLM en el retry de Telegram).

## Pregunta al auditor

¿El canal Telegram preserva la garantía anti-alucinación de Pieza A **entre turnos** de forma sólida (el modelo nunca re-ve un valor)? ¿La desviación de RBAC (`require_permission` en vez de `require_role`) y la ampliación de la matriz canónica son correctas y admin-only? ¿El webhook es fail-closed sin huecos y la auditoría del vínculo íntegra? ¿Listo para merge (flag apagado) y para encender en go-live tras O-1?
