# FABS · Incremento 2 — Loop del agente + verificador cifra→evidencia (design)

- **Fecha:** 2026-08-11 · **Autor:** Claude (con GO del CEO a D1/D2/D3)
- **Incremento:** 2 de 6 (roadmap `docs/COMPAS_FABS_ROADMAP.md`)
- **Estado:** 🟡 En curso — spec aprobado en decisiones, pendiente construcción (SDD)
- **Predecesor:** inc1 (cimiento determinista) MERGEADO a main (`248bfed`), flag `CFO_ENABLED` apagado.

## 0. Una línea

Conectar el **LLM** encima del cimiento de inc1: un **loop acotado** que decide qué
concepto de COMPAS leer (tools de solo lectura), y un **verificador cifra→evidencia**
que **impide publicar cualquier número que no venga de una tool**. El modelo **nunca
calcula**: orquesta tools y narra; si una cifra no está respaldada, **se abstiene**.
Todo detrás del flag `CFO_ENABLED` (apagado ⇒ COMPAS byte-idéntico).

## 1. Alcance (qué entra / qué NO)

**Entra:**
1. **Must-do previo:** blindar `iva_cuatrimestre` (fail-closed si `periodicidad != cuatrimestral`).
2. Cliente Anthropic (SDK nativo), modelo por config, `ANTHROPIC_API_KEY` por env, **inyectable** (mock en tests).
3. Capa de **tools** (esquemas Anthropic + dispatcher) sobre los 3 conceptos de inc1.
4. **Verificador cifra→evidencia** — el control crítico.
5. **Loop acotado** (máx. 3 iteraciones, temp 0.1) con reintento correctivo y abstención dura.
6. **Servicio** orquestador (consulta → loop → respuesta tipada, captura de tokens).
7. **CR-CFO-1:** eventos `cfo.consulta` + `cfo.respuesta` al catálogo cerrado + emisión.
8. **RBAC:** capacidad `cfo:consultar`.
9. **Endpoint** `POST /api/v1/cfo` con **doble barrera** (router condicional por flag + guard) + `require_permission`.

**NO entra (YAGNI — incrementos siguientes):** Telegram/canal (inc3), hilos/memoria de
conversación (inc3), alertas/Comité/jobs (inc4), escrituras sobre datos financieros
(Fase 3), el set completo 240+60 goldens (inc≥3), provisión de IVA (inc6), streaming/SSE
(inc5), enforcement del kill-switch de presupuesto (ops/inc4 — aquí solo se **registran**
tokens). Alegra = cero. CXC socios / devengado = fuera.

## 2. Decisiones aprobadas por el CEO (2026-08-11)

- **D1 — Forma del loop:** loop acotado corto, **máx. 3 iteraciones**, `temperature=0.1`,
  `max_tokens` acotado, modelo por config. Cubre "elige tool → (opcional 2ª tool) → narra"
  con tope duro. La mayoría de consultas resuelven en 1 ronda.
- **D2 — Verificador estricto:** ante una cifra sin evidencia, **no se publica**. El agente
  reintenta **una** vez inyectándole el conjunto correcto de valores; si sigue sin cuadrar,
  **se abstiene** ("con los datos disponibles no puedo afirmar X") — nunca publica un número
  dudoso con advertencia. Es la regla #1 del sistema (lección Deloitte).
- **D3 — Endpoint tras el flag:** exponer `POST /api/v1/cfo` ya en inc2, detrás de
  `CFO_ENABLED`, testeable de punta a punta; inc3 (Telegram) será solo un cliente de este servicio.

## 3. Arquitectura (archivos nuevos, todos bajo `backend/app/cfo/`)

```
app/cfo/
  config.py                 (existe) + CFO_MODEL, api_key helper, límites del loop
  agente/
    __init__.py
    cliente.py              wrapper del SDK Anthropic (inyectable; sin key ⇒ error claro)
    prompt.py               system prompt (el modelo nunca calcula; narra con evidencia)
    tools.py                esquemas de tools + dispatcher → conceptos de calc/
    verificador.py          cifra→evidencia (EL control)  ← corazón del inc2
    loop.py                 loop acotado + reintento correctivo + abstención dura
    servicio.py             orquestador: consulta → loop → respuesta tipada + auditoría
    modelos.py              RespuestaCFO (salida tipada, strict)
  router.py                 POST /api/v1/cfo (doble barrera + require_permission)
tests/cfo/agente/           tests con cliente MOCKEADO (sin API real)
```

**Regla de aislamiento S1 (de inc1, se mantiene):** `cfo/` solo importa la capa de
**servicios** de COMPAS y escribe solo en `cfo_*`. El nuevo código no toca `app.domain.*`
ni el driver de Mongo directamente. `motor.py` **cero diffs**.

### 3.1 Tools (solo lectura)
Tres tools, una por concepto de inc1, cada una devuelve el `ResultadoCFO` **completo**
(incluida `disponible` y `evidencia`), con `valor` serializado a **string** (regla 1, nunca float):
- `caja_disponible_hoy` → `calc.caja.caja_hoy()`
- `runway_meses` → `calc.runway.runway()`
- `iva_del_cuatrimestre` → `calc.iva.iva_cuatrimestre()`

El dispatcher es un `dict[str, coroutine]` cerrado; una tool desconocida → error, jamás se inventa.

### 3.2 Verificador cifra→evidencia (corazón)
Entrada: (a) el texto final del modelo; (b) el **conjunto cerrado de evidencias** =
los `ResultadoCFO.valor` de las tools ejecutadas en este turno (solo los `disponible=True`).

Algoritmo:
1. Extraer del texto los **candidatos a cifra monetaria/unitaria** con una heurística
   conservadora: montos con separador de miles o prefijo `$` (`704.722.003`, `$36.204.698`),
   y números con unidad explícita (`4,2 meses`). Se **ignoran** por diseño: años
   (`2024`–`2030`), fechas (`10 de septiembre`, `2026-09-10`), y ordinales/cantidades pequeñas
   sin formato de dinero (`3 meses` cuando es etiqueta de período, `C2`, `los últimos 3`).
2. Normalizar cada candidato a `Decimal` (formato es-CO: `.` miles, `,` decimales).
3. Cada candidato debe estar **dentro de tolerancia** de **algún** valor del conjunto:
   dinero ±$1 COP (redondeo), meses ±0,1. Si un candidato no matchea ninguno → **cifra sin evidencia**.
4. Veredicto: `ok` si todos matchean; `sin_evidencia` con la lista de cifras huérfanas si no.

Esta heurística prioriza **no molestar** cifras inocuas (fechas/años) y **atrapar**
montos inventados. Se prueba de forma adversarial (ver §5). Documentada como el punto
más delicado del inc2 — cualquier cambio pasa por review.

### 3.3 Loop (D1) + abstención (D2)
```
consulta → cliente.mensaje(system=prompt, tools=[...], temp=0.1)
  bucle (≤ 3 iter):
    si stop_reason == tool_use: dispatch tools, append resultados, continuar
    si texto final: romper
  verificar(texto, evidencias):
    ok            → publicar
    sin_evidencia → 1 reintento correctivo (inyectar valores válidos + orden de abstenerse)
                    verificar de nuevo → ok ? publicar : ABSTENCIÓN DURA (texto canónico seguro)
  tope de iteraciones alcanzado sin texto → ABSTENCIÓN DURA
```
Abstención dura = respuesta canónica fija ("Con los datos disponibles no puedo confirmar
esa cifra…"), `abstuvo=True`, `motivo ∈ {verificacion, tope_iter, sin_api_key, error_llm}`.

### 3.4 Salida tipada `RespuestaCFO` (strict, extra="forbid")
```
texto: str
abstuvo: bool
motivo: str | None           # solo si abstuvo
conceptos_usados: list[str]   # tools ejecutadas
cifras: list[{valor: str, unidad: str, evidencia: {fuente, fecha_corte, ref}}]
uso: {modelo: str, tokens_in: int, tokens_out: int, iteraciones: int}
```
El frontend/canal nunca ve un número suelto: cada cifra viaja con su evidencia.

## 4. Auditoría — CR-CFO-1 (catálogo cerrado, regla 11)

Dos eventos nuevos (hoy el catálogo tiene 60 → 62):
- **`cfo.consulta`** — se emite al recibir la pregunta. `entidad='cfo'`, `actor_id=user.id`
  real (corrige FP8 del legado), `metadata={pregunta, canal:'api'}`.
- **`cfo.respuesta`** — se emite tras responder. `metadata={abstuvo, motivo, conceptos_usados,
  cifras:[valores+evidencia], uso}`. La **abstención es un `cfo.respuesta`** con `abstuvo=True`
  (no un evento propio — derivable y minimalista).

**Política de fallo (O1):** una consulta a FABS es **lectura** (no mueve plata). Si la
escritura de auditoría falla, se registra `logger.error`+Sentry y **se continúa** (rama
"eventos no críticos" de `emit_audit`) — la respuesta read-only no se bloquea por un fallo
de BD de auditoría. `cfo.consulta` se emite **antes** de responder (queda el rastro de la
pregunta aun si el loop falla).

**Nota PII:** en inc2 el único usuario es interno (RODDOS) y el endpoint está tras auth;
la pregunta puede llevar texto libre. Se guarda tal cual en `cfo.consulta.metadata.pregunta`
(rastro forense). Si en inc3 se abre a más gente, se revisa minimización (fuera de alcance aquí).

## 5. Estrategia de pruebas (eval-first, sin API real)

**Todo se testea con el cliente Anthropic MOCKEADO** — CI verde **sin** `ANTHROPIC_API_KEY`.
El mock devuelve secuencias de mensajes scripteadas (tool_use → resultado → texto final).

- **Verificador (batería adversarial):** modelo alucina `$50.000.000` no presente → `sin_evidencia`;
  cifra correcta `$704.722.003` → `ok`; "período C2 / 10 de septiembre / 2026" → no marca nada;
  "runway de 4,2 meses" con evidencia 4.2 → `ok`; suma inventada de dos valores → `sin_evidencia`.
- **Loop:** 1 tool → narra (camino feliz); 2 tools; tope de iteraciones → abstención;
  reintento correctivo que corrige; reintento que falla → abstención dura.
- **Servicio + auditoría:** emite `cfo.consulta` y `cfo.respuesta` con metadata correcta;
  abstención audita `abstuvo=True`; fallo de auditoría no bloquea la respuesta.
- **Sin key:** el servicio degrada a abstención `motivo='sin_api_key'` (no crash).
- **Flag-off = COMPAS idéntico:** router ausente de `main.py`; suite completa verde; `motor.py` 0 diffs.
- **S1:** el test estático de aislamiento sigue verde con el código nuevo.
- **Decimal en todo el pipeline**, cero float; `ruff check app/cfo/` limpio; `npm run build` no aplica (backend).

Regresión completa de goldens: **no** en cada commit (presupuesto); smoke-set en CI + regresión en release (política $30/mes, memoria fabs-fundacion §D10).

## 6. Config / entorno

- `CFO_ENABLED` (existe): apagado por defecto. Router solo se registra si `True`.
- `CFO_MODEL` (nuevo): default **`claude-haiku-4-5-20251001`** (barato; el modelo solo
  orquesta y narra, no razona cálculo). Override por env a `claude-sonnet-5` si se requiere.
- `ANTHROPIC_API_KEY` (nuevo): **solo env var en Render** (compas-api + Worker), NUNCA en repo
  (regla 12). Acción del CEO al desplegar. Sin key ⇒ FABS se abstiene con `motivo='sin_api_key'`.
- `anthropic` (nuevo): dep de runtime en `requirements.txt`, pin a la última estable verificada al instalar.
- Límites del loop (`CFO_MAX_ITER=3`, `CFO_MAX_TOKENS`, `CFO_TIMEOUT_S`) con defaults en `config.py`.

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El verificador deja pasar una cifra inventada (falso negativo) | Heurística conservadora + batería adversarial + review dedicado; ante duda de parseo, la cifra se considera candidata (se exige evidencia) |
| El verificador molesta cifras inocuas (falso positivo) → FABS inútil | Whitelist de años/fechas/ordinales; tests de "no marcar"; el reintento correctivo recupera antes de abstenerse |
| Costo de tokens desborda $30/mes | Modelo Haiku por default, temp 0.1, loop ≤3 iter, `max_tokens` acotado; se **registran** tokens por turno (enforcement del kill-switch = inc4) |
| La terminal (worktree paralelo) toca `facturas`/main y choca | inc2 crea archivos **nuevos** (bajo `cfo/agente/`), toca `facturas` solo vía el must-do de `iva.py`; fetch+verificar antes de mergear |
| Fuga de la API key | Nunca en repo; env var; gitleaks en CI; la key la pone el CEO en Render |

## 8. Definición de hecho (DoD del inc2)

1. `iva_cuatrimestre` fail-closed por periodicidad (con test).
2. Loop + verificador + servicio + endpoint construidos, **todo testeado con mock** (CI sin key).
3. `cfo.consulta`/`cfo.respuesta` en el catálogo (CR-CFO-1) + capacidad `cfo:consultar`.
4. **Flag-off ⇒ COMPAS byte-idéntico** (suite completa verde, router ausente, `motor.py` 0 diffs).
5. Regla 1 (Decimal/string, cero float), S1 intacto, `ruff` limpio.
6. Verificador con batería adversarial verde (ninguna cifra sin evidencia se publica).
7. Roadmap actualizado al cerrar cada pieza; paquete Kimi (gate crítico) listo.

---
*Este spec alimenta el plan `docs/superpowers/plans/2026-08-11-fabs-inc2-loop-agente.md` y la ejecución por SDD. Ante conflicto de alcance, mandan `COMPAS_NORTE.md`, `CLAUDE.md` y el roadmap de FABS.*
