# FABS · Chat embebido en COMPAS (diseño)

**Fecha:** 2026-08-30
**Autor:** Andrés (CEO) + Claude
**Estado:** aprobado para plan (GO CEO 2026-08-30)
**Rama:** `feat/fabs-chat-embebido` (desde `main` 4499779)
**Predecesores:** FABS inc2 (endpoint `POST /api/v1/cfo`) + inc3B (hilo de Telegram `HiloCFO`) + el vigilante.

---

## 1. Objetivo

Llevar a FABS **dentro de COMPAS**: un panel de chat acoplable, disponible desde cualquier vista del cockpit, que reusa el mismo cerebro (`consultar`) y el **mismo hilo por-usuario que Telegram** — así FABS recuerda entre canales y muestra el historial cruzado. Es el inc5/6 (la última pieza grande de FABS antes de pulido).

## 2. Norte y alcance

**Qué SÍ:**
- El endpoint `POST /api/v1/cfo` pasa de **stateless a conversacional** sobre el `HiloCFO` compartido por `user_id`.
- Un **log de display** (`mostrado` por turno) para pintar el **scrollback cruzado completo** (web + Telegram), servido por `GET /api/v1/cfo/historial`.
- Un **panel acoplable** en el shell del cockpit, gateado por `cfo:consultar`, con pie de evidencia por respuesta.

**Qué NO (fuera de alcance / fast-follows):**
- Streaming de la respuesta (v1 es request/response completo).
- Historia más allá de la retención (200 turnos); archivo histórico = CR futura.
- Pulido visual del panel (Cowork): aquí se entrega **funcional** con Tailwind mínimo.
- Adjuntar/exportar la conversación; múltiples hilos por usuario.
- Cambios al verificador, al motor, o a las tools de FABS (solo se consumen).

## 3. Decisiones del CEO (2026-08-30)

1. **"Mismo hilo que Telegram" = scrollback cruzado COMPLETO** (no solo memoria): la web muestra el historial renderizado, incluidas las burbujas de Telegram.
2. **Ubicación = panel acoplable** (botón "Preguntá a FABS" en el shell, deslizable sobre cualquier vista), no una vista dedicada.
3. **Retención de display = ~200 turnos.**
4. **Split de construcción:** el panel **funcional** se construye aquí (código); Cowork pule los visuales.

## 4. Arquitectura y flujo

```
[Panel FABS en el shell del cockpit]  (visible si useAuth().puede("cfo:consultar"))
   al abrir → GET /api/v1/cfo/historial → pinta el scrollback (rol + texto + canal + ts)
   escribir → POST /api/v1/cfo {pregunta}
        │
        ▼
POST /api/v1/cfo   (require_permission("cfo:consultar"); guard 404 si CFO_ENABLED off)
   ├─ hilo = repositorio.obtener_hilo(user.id)
   ├─ historial = hilos.historial_para_loop(hilo, cfo_hilo_ventana())   # crudo, ventana corta al LLM
   ├─ resp = servicio.consultar(pregunta, actor_id=user.id, historial=historial)
   ├─ hilos.registrar_turno_web(user.id, pregunta, resp.texto_crudo, resp.texto)  # persiste crudo + mostrado, canal="web"
   └─ return RespuestaCFO (texto sustituido + cifras)
        │
        ▼  (Telegram, en paralelo, escribe al MISMO hilo por user_id con canal="telegram" + mostrado)
```

Con `user_id` común (Telegram lo resuelve por `vinculos`; la web autentica como `user.id`), ambos canales comparten `HiloCFO` — memoria y scrollback cruzados sin nada extra.

## 5. Componentes

### 5.1 Endpoint conversacional (`backend/app/cfo/router.py`)

`POST /api/v1/cfo` deja de ser stateless:
- Lee el hilo del usuario, arma el `historial` (crudo, ventana corta) y lo pasa a `consultar`.
- Persiste el turno (crudo + mostrado) al hilo compartido vía `registrar_turno_web`.
- Sigue devolviendo `RespuestaCFO` (texto sustituido + cifras). Mantiene el guard 404 (`cfo_enabled`) y el RBAC `cfo:consultar`.

```python
@router.post("", response_model=RespuestaCFO)
async def consultar(body: ConsultaBody, user: User = Depends(require_permission("cfo:consultar"))) -> RespuestaCFO:
    if not cfo_enabled():
        raise HTTPException(404, "No encontrado.")
    hilo = await repositorio.obtener_hilo(str(user.id))
    historial = hilos.historial_para_loop(hilo, config.cfo_hilo_ventana())
    resp = await servicio.consultar(body.pregunta, actor_id=str(user.id), historial=historial)
    await hilos.registrar_turno_web(str(user.id), body.pregunta, resp.texto_crudo, resp.texto)
    return resp
```

### 5.2 Log de display en el hilo (`backend/app/cfo/telegram/hilos.py` + `modelos.py`)

El hilo hoy guarda `turnos: list[dict]` en CRUDO (para el LLM). Se extiende la forma del dict de cada turno (es `list[dict]`, sin cambio de schema estricto) para incluir el texto de display:

Forma del turno (convención documentada):
```python
{"rol": "user"|"assistant", "contenido": <crudo>, "mostrado": <sustituido|None>, "canal": "telegram"|"web", "ts": <ISO-8601>}
```
- Turno `user`: `contenido == mostrado == pregunta` (sin tokens).
- Turno `assistant`: `contenido` = crudo (tokens, lo que re-alimenta al LLM); `mostrado` = texto sustituido (lo que se pinta). `historial_para_loop` sigue leyendo `contenido` (crudo) — **el re-alimentado al LLM no cambia**.

Cambios:
- **Retención:** `_MAX_TURNOS` 40 → **200** (el hilo retiene hasta 200 turnos para display; al LLM se le sigue re-alimentando solo `cfo_hilo_ventana()`). Doc ~200 turnos ≈ decenas de KB (muy por debajo del límite de 16 MB de Mongo).
- **Helper compartido** `_append_turnos(user_id, pregunta, crudo, mostrado, canal, update_id=None)` que arma los dos turnos con `mostrado`/`canal`/`ts` y persiste (recorta a `_MAX_TURNOS`). `registrar_turno` (Telegram) delega en él con `canal="telegram"`, `update_id`=el suyo, `mostrado`=`envio`; **nuevo** `registrar_turno_web(user_id, pregunta, crudo, mostrado)` delega con `canal="web"`, `update_id=None` (la web no tiene dedup por update_id — deja `ultimo_update_id` intacto). `es_reintento`/`registrar_dedup`/`ultimo_envio` de Telegram no cambian.
- **Compat legacy:** turnos previos a esta pieza no tienen `mostrado`/`canal`/`ts`. Se leen con `.get(...)` (sin romper). Un turno `assistant` sin `mostrado` NO se pinta crudo (ver §5.3).

### 5.3 Endpoint de historial (`backend/app/cfo/router.py`)

`GET /api/v1/cfo/historial` (mismo RBAC `cfo:consultar` + guard 404) → devuelve el scrollback renderizado del hilo del usuario:

```python
class TurnoHistorial(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    rol: str          # 'user' | 'assistant'
    texto: str        # user: la pregunta; assistant: el 'mostrado' (sustituido, ya verificado)
    canal: str        # 'telegram' | 'web' | 'desconocido'
    ts: str | None    # ISO-8601 o None (legacy)

@router.get("/historial", response_model=list[TurnoHistorial])
async def historial(user: User = Depends(require_permission("cfo:consultar"))) -> list[TurnoHistorial]:
    if not cfo_enabled(): raise HTTPException(404, "No encontrado.")
    hilo = await repositorio.obtener_hilo(str(user.id))
    return hilos.historial_para_display(hilo)
```

`hilos.historial_para_display(hilo)` (nuevo) mapea `turnos` → `TurnoHistorial`:
- `user` → `texto = contenido`.
- `assistant` con `mostrado` → `texto = mostrado`.
- `assistant` **sin** `mostrado` (legacy) → `texto = "(respuesta anterior)"` (**nunca** se expone el crudo con `[[tokens]]`).
- `canal = turno.get("canal", "desconocido")`, `ts = turno.get("ts")`.

### 5.4 Panel acoplable (frontend, funcional)

- **Trigger:** botón "Preguntá a FABS" en `src/components/layout/AppShell.tsx`, visible solo si `useAuth().puede("cfo:consultar")` (regla 9: derivado del config de permisos, no de rol→UI). Al hacer clic abre un **panel lateral deslizable** (slide-over) sobre la vista actual.
- **Al abrir:** `apiJson<TurnoHistorial[]>("/cfo/historial")` → pinta el scrollback (burbujas user/assistant, con una marca sutil del canal: p.ej. un ícono para las de Telegram). Estado local del componente (no hace falta TanStack Query global; una carga al abrir + append al responder).
- **Enviar:** `apiJson<RespuestaCFO>("/cfo", {method:"POST", body:{pregunta}})`. Optimista: pinta la burbuja del usuario + un estado "FABS está pensando…", luego reemplaza con la respuesta. **Pie de evidencia**: bajo cada respuesta, las `cifras` con su fuente (reusa el formato de Telegram: `• {valor} {unidad} — {fuente} ({ref})`).
- **Montos:** se muestran tal cual llegan del backend (ya formateados es-CO dentro del texto; el front NUNCA hace `Number` sobre montos — regla 1).
- **Sin streaming** (v1). Errores de red/permiso: mensaje claro en el panel (usa `ApiError`).
- **Alcance del código aquí:** el panel funcional (estado, llamadas, gating, lista de mensajes, input, pie de evidencia) con Tailwind mínimo. **Cowork** hace el diseño visual fino (tema claro + acentos RODDOS, tipografías del Blueprint).

### 5.5 RBAC

Reusa `cfo:consultar` (financiero/directivo/admin) — **sin permiso nuevo**. El botón/panel solo aparece con ese permiso; el backend lo exige en ambos endpoints. `cfo:telegram_administrar` (solo admin) no aplica aquí (esto es consulta, no administración de vínculos).

## 6. Garantía anti-alucinación

- Turnos nuevos: pasan por `consultar` (verifica el crudo ANTES de sustituir; devuelve el `texto` sustituido). El endpoint persiste `mostrado` = ese texto **ya verificado**.
- Scrollback: `GET /historial` devuelve `mostrado` (ya sustituido/verificado) — **nunca se re-verifica ni re-sustituye**; los turnos legacy sin `mostrado` se enmascaran (§5.3), jamás se expone crudo con tokens.
- El re-alimentado al LLM sigue siendo el CRUDO (`contenido`), preservando el contrato de Pieza A entre turnos y entre canales.

## 7. Reglas innegociables

- **Dinero = string** en la API; el front nunca hace `Number` sobre montos; formato es-CO ya viene en el texto (regla 1).
- **Pydantic strict** en `ConsultaBody`, `TurnoHistorial` (regla 3).
- **RBAC por dependencia** `require_permission("cfo:consultar")` en ambos endpoints; navbar/panel del front derivados del config único (regla 9).
- **`motor.py` intocable**; el chat solo consume `consultar`/tools.
- **Sin secretos**; access token en memoria (ya es el patrón de `api.ts`), refresh en cookie HttpOnly.
- **TZ**: `ts` de los turnos en UTC-aware (mismo patrón que `actualizado_at`).

## 8. Casos borde

- **Usuario sin hilo** (nunca preguntó): `obtener_hilo` → None; `historial_para_loop(None,...)` → []; `historial_para_display(None)` → []; el panel muestra vacío con un placeholder ("Preguntale algo a FABS").
- **Usuario web NO vinculado a Telegram:** tiene su propio hilo web (por `user.id`); funciona igual, sin burbujas de Telegram.
- **Turnos legacy sin `mostrado`:** se enmascaran ("(respuesta anterior)"), no se expone crudo.
- **`consultar` se abstiene:** devuelve `RespuestaCFO` con `abstuvo=True`; el panel pinta el texto de abstención (honesto), igual que Telegram.
- **Retención:** al pasar de 200 turnos, se recortan los más viejos (display), sin afectar la ventana del LLM.
- **CFO_ENABLED off:** ambos endpoints dan 404; el botón igual podría verse (depende del permiso) — el panel maneja el 404 con un mensaje "FABS no está disponible".

## 9. Testing

**Backend (TDD, mongomock):**
- `POST /cfo` conversacional: persiste el turno (crudo + mostrado, canal="web") al hilo del `user.id`; pasa el historial a `consultar` (verificar con un `consultar` fakeado que capture el `historial` recibido); devuelve el texto sustituido. Sin hilo previo → historial vacío.
- `registrar_turno_web`: agrega los 2 turnos con `mostrado`/`canal`/`ts`, no toca `ultimo_update_id`; recorta a 200.
- `registrar_turno` (Telegram) sigue verde y ahora guarda `mostrado`/`canal="telegram"`/`ts` por turno (test del webhook actualizado).
- `historial_para_display`: mapea user/assistant/legacy correctamente; assistant sin `mostrado` → "(respuesta anterior)", nunca crudo con `[[`.
- `GET /historial`: RBAC (401/403 sin permiso), 404 con flag off, devuelve el scrollback del usuario.
- Guardas: `motor.py` 0 diffs; sin float de dinero.

**Frontend (Vitest + RTL):**
- El botón "Preguntá a FABS" aparece solo con `cfo:consultar` (mock de `useAuth`).
- El panel carga el historial al abrir (mock de `apiJson`), pinta burbujas user/assistant + marca de canal.
- Enviar: pinta la pregunta + "pensando…", luego la respuesta con su pie de evidencia; el front no hace `Number` sobre montos.
- `npm run build` (tsc -b) verde tras tocar tipos compartidos.

## 10. Fuera de alcance / fast-follows

- Streaming de la respuesta (SSE/tokens).
- Archivo de historia > 200 turnos.
- Pulido visual del panel (Cowork).
- Un eventual lift de `hilos.py`/`HiloCFO` fuera de `cfo/telegram/` a `cfo/` (hoy es cross-canal pero vive bajo telegram/ por historia; se reusa en su lugar para no tocar el módulo de Telegram ya mergeado — CR trivial si se quiere renombrar).
- Go-live: encender `CFO_ENABLED` en prod (ya está ON hoy) — el chat queda disponible al mergear para quien tenga `cfo:consultar`.
