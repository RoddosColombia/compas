# FABS · Inc3 Pieza A — Verificación por concepto (citación estructurada) · design

- **Fecha:** 2026-08-17 · **Autor:** Claude (con GO del CEO al enfoque)
- **Fase:** inc3, Pieza A (prerrequisito de seguridad, antes del canal Telegram = Pieza B)
- **Rama base:** `main` (`7a8bd07`+) · **Rama:** `feat/fabs-inc3a-concepto`
- **Gate:** Kimi (crítico — modifica el control anti-alucinación del núcleo). Flag `CFO_ENABLED` sigue apagado.

## 0. Una línea

Cerrar el hueco vinculante de inc2 (el verificador exige evidencia **por unidad**, y caja e IVA son ambos COP → el modelo podría atribuir a "caja" el valor del IVA y pasaría) **quitándole al modelo la posibilidad de escribir un número**: el modelo **cita conceptos** con tokens `[[caja_hoy]]`; el **servicio sustituye** cada token por el valor *concept-bound* correcto; el verificador **prohíbe cifras crudas**. El modelo literalmente no puede confundir una etiqueta porque no emite números.

## 1. El problema (recordatorio)

Hoy (`app/cfo/agente/verificador.py`) `verificar()` agrupa la evidencia por `unidad` (COP/meses) y exige que cada cifra del texto esté dentro de tolerancia de **algún** valor de esa unidad. Como `caja_hoy` e `iva_cuatrimestre` son ambos COP, una respuesta que diga "tu caja es $36.204.698" (que es el IVA) **pasa la verificación** — la cifra existe en el pool COP, aunque con la etiqueta equivocada. Documentado en el docstring de `verificar()`/`servicio.py`; exposición cero con el flag apagado; **debe cerrarse antes de encender** (review final inc2 + decisión CEO 2026-08-17).

## 2. Enfoque aprobado: citación estructurada + ocultar el valor al modelo

En vez de adivinar en prosa a qué concepto se refiere cada cifra (frágil, como los formatos wire de inc2), se elimina la superficie del problema:

1. **El modelo nunca ve el número.** Las tools dejan de devolverle el `valor` crudo: el resultado que ve el modelo es `{concepto, disponible, unidad, evidencia{fuente, fecha_corte, ref}}` — SIN `valor` ni `detalle` numérico. Sabe que `caja_hoy` está disponible con corte a una fecha, pero no la cifra.
2. **El modelo cita por concepto, no por número.** Para mencionar una cifra escribe un token `[[caja_hoy]]` / `[[runway]]` / `[[iva_cuatrimestre]]`. Solo puede citar conceptos que una tool devolvió como `disponible=True` este turno.
3. **El servicio sustituye** cada token por el valor concept-bound correcto, ya formateado con su evidencia (`$704.722.003 (al 2026-08-17)`), tomado del `ResultadoCFO` de ese concepto.
4. **El verificador prohíbe cifras crudas** de plata/%/meses en el texto del modelo (si el modelo alucina un número en vez de un token, se rechaza) y **valida los tokens** (un token de un concepto no leído / no disponible se rechaza).

**Por qué es robusto:** (a) no puede *mislabelar* — cita el concepto, nosotros ponemos el valor de ese concepto; (b) no puede *fabricar* — no ve valores que echar, y si inventa uno crudo el verificador lo caza; (c) refuerza regla #1 en general — sin valores no puede *calcular* (una suma "caja + IVA" se vuelve imposible; cita cada uno o se abstiene). Esto es más simple y más fuerte que la verificación por tolerancia actual.

## 3. Cambios (archivos del núcleo, sobre `main`)

```
app/cfo/agente/tools.py        resultado_a_dict → NO expone valor ni detalle numérico
app/cfo/agente/prompt.py       SYSTEM_PROMPT: cita con [[concepto]], nunca escribas números; CORRECTIVO nuevo
app/cfo/agente/verificador.py  verificar() → prohíbe cifras crudas + valida tokens (nuevo contrato)
app/cfo/agente/servicio.py     sustituye [[concepto]] por el valor concept-bound; corrective retry nuevo
app/cfo/agente/conceptos.py    (NUEVO) formateo concept-bound + el registro de conceptos citables
tests/cfo/agente/…             tests: caja/IVA no se confunde; número crudo se rechaza; token inválido se rechaza; sustitución correcta
```
`motor.py` cero diffs. `app/cfo/calc/*` (los conceptos de inc1) **no cambian** — solo cambia lo que la capa `agente` le muestra al modelo.

### 3.1 `conceptos.py` (nuevo) — formateo y registro
- `CONCEPTOS_CITABLES: frozenset[str]` = {`caja_hoy`, `runway`, `iva_cuatrimestre`} (los `concepto` de los `ResultadoCFO`).
- `def formatear(r: ResultadoCFO) -> str` — el valor concept-bound listo para prosa:
  - COP → `$` + miles es-CO (`Intl`-equivalente en backend, `decimal`), + ` (al {fecha_corte})` si aplica. Ej: `$704.722.003 (al 2026-08-11)`.
  - meses → coma decimal es-CO + ` meses`. Ej: `4,2 meses`.
  - iva incluye la fecha DIAN si está en la evidencia. Ej: `$36.204.698 (vence 2026-09-10)`.
  - Money es `Decimal`; formateo con `decimal`, **cero float**.

### 3.2 `tools.py` — el modelo no ve valores
`resultado_a_dict(r)` para el modelo pasa a: `{"concepto", "disponible", "unidad", "evidencia": {"fuente","fecha_corte","ref"}}`. **Se quita `valor` y `detalle`.** (El `ResultadoCFO` completo — con `valor` — sigue viajando en el loop para que el servicio lo use al sustituir; solo cambia lo que se SERIALIZA hacia el modelo.)

### 3.3 `verificador.py` — nuevo contrato de `verificar()`
`verificar(texto, resultados) -> Veredicto` ahora:
- **Cifras crudas prohibidas:** reusa `extraer_cifras(texto)`; si aparece CUALQUIER cifra COP/meses/pct cruda → es violación (el modelo debió usar un token). Se listan en `cifras_sin_evidencia` (para el correctivo).
- **Tokens válidos:** extrae `\[\[(\w+)\]\]`; cada token debe ser un `concepto` con `disponible=True` en `resultados`. Token desconocido o de concepto no disponible → violación (se lista).
- `ok = (no hay cifras crudas) and (todos los tokens válidos)`.
- `Veredicto{ok, cifras_sin_evidencia}` se mantiene; se agrega `tokens_invalidos: list[str]` (o se reúsan en la misma lista con prefijo). *(Decisión: campo separado `tokens_invalidos` para que el correctivo sea claro.)*

`extraer_cifras`/`_es_monto`/normalizadores/porcentajes: **sin cambios** (siguen detectando lo crudo). Lo que cambia es que ahora "cifra cruda detectada" = violación (antes = candidato a verificar contra evidencia).

**Estrictez deliberada:** la prohibición es total (COP, meses y %), no solo COP. El problema vinculante (D3) es la colisión COP (caja vs IVA), pero prohibir también meses/% crudos mantiene una sola regla simple y refuerza regla #1: FABS no debe enunciar NINGÚN número que no venga de una tool. Efecto colateral: una frase genérica ("los últimos 3 meses") también se marca → el modelo reformula sin el número en el reintento. Es **fail-safe** (jamás publica una cifra dudosa; a lo sumo reformula o se abstiene) y ajustable si el piloto muestra que estorba.

### 3.4 `prompt.py` — el modelo cita, no escribe números
`SYSTEM_PROMPT` agrega/ajusta:
- "NUNCA escribas cifras (montos, meses, porcentajes) directamente. Para mencionar un número, usa su **token de concepto**: `[[caja_hoy]]`, `[[runway]]`, `[[iva_cuatrimestre]]`. El sistema los reemplaza por el valor real con su fecha de corte."
- "Solo cita un concepto si su herramienta lo devolvió como disponible. Si un concepto no está disponible, dilo con honestidad y NO lo cites."
- Se conservan: nunca calcula/suma/estima/extrapola; nada de %; español; no ejecuta.
`CORRECTIVO` nuevo: "Tu respuesta escribió cifras crudas ({cifras}) o citó conceptos inválidos ({tokens}). No escribas números: usa los tokens `[[caja_hoy]]`/`[[runway]]`/`[[iva_cuatrimestre]]` solo para los conceptos disponibles; si no hay dato, dilo sin cifra."

### 3.5 `servicio.py` — sustitución + retry
- Tras `verificar(...).ok`: `texto_final = sustituir_tokens(res.texto, res.resultados)` — reemplaza cada `[[concepto]]` por `conceptos.formatear(r)` del `ResultadoCFO` correspondiente (disponible). El `RespuestaCFO.texto` publicado ya trae los valores concept-bound correctos.
- El reintento correctivo usa el `CORRECTIVO` nuevo con las cifras crudas y/o tokens inválidos del veredicto.
- Los abstención/motivos actuales se mantienen (`verificacion` cubre "escribió crudo y no corrigió").
- `RespuestaCFO.cifras` (las `CifraPublicada`) siguen construyéndose de los `ResultadoCFO` (ya concept-bound) — así el canal (Pieza B) puede mostrarlas aparte.

## 4. Flujo (feliz)
```
pregunta → loop: el modelo llama tool(s) → ve {concepto, disponible, evidencia} (SIN valor)
        → narra con tokens: "Tu caja hoy es [[caja_hoy]] y el IVA del cuatrimestre es [[iva_cuatrimestre]]."
verificar: 0 cifras crudas ✓, tokens [[caja_hoy]]/[[iva_cuatrimestre]] disponibles ✓ → ok
sustituir: "Tu caja hoy es $704.722.003 (al 2026-08-11) y el IVA del cuatrimestre es $36.204.698 (vence 2026-09-10)."
→ RespuestaCFO(texto=..., abstuvo=False, cifras=[caja_hoy…, iva…])
```
El caso que hoy se colaría ("tu caja es [el valor del IVA]") es **imposible**: el modelo escribe `[[caja_hoy]]`, y el servicio pone el valor de caja, no el del IVA.

## 5. Estrategia de pruebas (sin API real; cliente mockeado)
- **El caso vinculante:** con evidencia caja=704.722.003 e IVA=36.204.698, un guion donde el modelo cita `[[caja_hoy]]` → la sustitución rinde el valor de CAJA (no el del IVA); y un guion donde el modelo escribe crudo el valor del IVA bajo la etiqueta caja → **rechazado** (cifra cruda) → reintento/abstención.
- **Número crudo prohibido:** cualquier `$…`/`NNN.dd`/`N%`/`N meses` en el texto del modelo → `ok=False`.
- **Token inválido:** `[[ventas]]` (no existe) o `[[runway]]` cuando runway abstuvo → `ok=False`.
- **Sustitución:** `[[caja_hoy]]` → `$704.722.003 (al …)`; `[[runway]]` → `4,2 meses`; múltiples tokens en una frase.
- **Modelo no ve valores:** `resultado_a_dict` no contiene `valor` ni `detalle` (test directo).
- **Regresión:** la suite `tests/cfo/` verde; flag apagado ⇒ COMPAS idéntico; `motor.py` 0 diffs; cero float; ruff limpio.
- Todo con `ClienteFake` (guiones) — CI verde sin `ANTHROPIC_API_KEY`.

## 6. Alcance / no-alcance
- **Entra:** el contrato de citación por concepto en los 4 archivos del núcleo + `conceptos.py` + tests. Solo los 3 conceptos actuales.
- **NO entra:** el canal Telegram, hilos, vínculo de identidad, encender el flag (todo eso es Pieza B / go-live). Nuevos conceptos (umbral, etc.) = futuras tools. Sin cambios a `app/cfo/calc/*` ni a `motor.py`.

## 7. DoD
1. El caso caja/IVA ya no se confunde (test que hoy fallaría, pasa).
2. Cifra cruda en el texto ⇒ rechazo; token inválido ⇒ rechazo; sustitución correcta (tests).
3. El modelo no recibe `valor` (test de `resultado_a_dict`).
4. Flag-off ⇒ COMPAS idéntico; `motor.py` 0 diffs; cero float; S1 intacto; ruff limpio; suite verde.
5. Roadmap + paquete Kimi (gate crítico) listos.

---
*Pieza A de inc3. Ante conflicto de alcance mandan `COMPAS_NORTE.md`, `CLAUDE.md`, el roadmap de FABS. La Pieza B (Telegram + hilos + vínculo + piloto) se diseña después, sobre una A ya auditada.*
