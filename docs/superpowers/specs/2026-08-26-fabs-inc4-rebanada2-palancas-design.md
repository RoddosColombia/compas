# FABS inc4 · Rebanada 2 — What-if de palancas (plazo · cuota inicial · cuota semanal)

- **Fecha:** 2026-08-26 · **Autor:** Claude + CEO (brainstorming aprobado)
- **Incremento:** inc4 (cerebro analítico), **rebanada 2** (rebanada 1 — what-if de un ajuste recurrente + solver de motos — YA en vivo `31684e6`).
- **Flag:** `CFO_ENABLED` (encendido en el piloto). Con el flag apagado, COMPAS byte-idéntico.
- **Gate:** crítico (produce cifras que el CEO usa para decidir) → **gate-waiver + GO CEO** (Kimi no disponible ~semanas; ver memoria `kimi-no-disponible-semanas`); Kimi de diseño+código **retroactivos pendientes**, NUNCA simulados. **Construcción por SDD a partir del 29-ago** (subagentes limitados hasta entonces).
- **Rama:** `feat/fabs-inc4-rebanada2-palancas` (desde main `41cb535`).

## 1. Norte de la rebanada (una línea)

Que el CEO pregunte por conversación un what-if que **cambia una palanca del negocio** —*"¿qué pasa si vendo a 78 semanas en vez de 52?"*, *"¿y si bajo la cuota inicial?"*, *"¿y si subo la cuota semanal?"*— y FABS re-proyecte sobre el **motor real** y responda el impacto en caja y el mes de quiebre, **con evidencia y sin que el modelo calcule** (COMPAS calcula; FABS narra).

## 2. Alcance (y NO-alcance)

**Entra (rebanada 2):** what-if de **3 palancas escalares por modelo**, cada una re-proyectando el motor completo:
- **plazo** (`ModeloMoto.plazo_semanas`), **cuota inicial** (`ModeloMoto.cuota_inicial`), **cuota semanal** (`ModeloMoto.cuota_semanal`).
- Aplicable a un **modelo específico** (Raider/Apache/Sport) o a **todos** (default si el usuario no especifica).
- Salida: `piso_sin` (base), `piso_con` (con la palanca), **mes de quiebre**, e `impacto` (delta del piso). Todo COP/mes — **sin `%`**.

**NO entra (rebanadas siguientes / fast-follow):**
- **Mix de modelos** (`participacion_mix`) → **rebanada 4**, junto con el cambio del verificador para permitir `%` computados por COMPAS (el mix mete un `%` en la conversación; abrir el tema del `%` se hace una sola vez, con Kimi de vuelta).
- **Solvers inversos por palanca** ("¿a qué plazo llego al umbral?") → después.
- **Multi-palanca simultánea** (cambiar dos cosas a la vez) → después.
- Cambiar `crec_pct_mensual`/colocación (el ritmo ya lo toca el solver de motos de la rebanada 1) → después.

## 3. Principio inamovible (idéntico a rebanada 1)

**El modelo nunca produce una cifra.** COMPAS re-proyecta con la palanca cambiada; cada resultado (piso con/sin, mes de quiebre, impacto) viaja con su `Evidencia`; FABS cita `[[token]]`; el verificador rechaza toda cifra/mes/conteo cruda; el servicio sustituye tras verificar. Los resultados son **COP/mes** — no hay `%` en la respuesta (por eso el mix queda fuera).

## 4. Motor que se REUSA (ya existe; `motor.py` intocable)

- **Re-proyección con params/modelos propuestos:** el camino interno de pipeline completo (motor → E1 → D2) que ya usa la rebanada 1, `proyeccion.service._resultado_con(...)` (aplica E1 y D2), envuelto por `fabrica_proyectar_unidades` (`service.py`, rebanada 1). **Reconcilia** con la base por construcción.
- **Modelos:** `ModeloMoto` (`domain/modelo_moto.py`: `plazo_semanas`, `cuota_inicial`, `cuota_semanal`, `participacion_mix`, …), cargados por `modelos_moto.service.listar_modelos(activo=True)`; expandidos a líneas del motor por `service._modelo_a_lineas`.
- **Params vigentes:** `parametros_proyeccion.service.obtener_vigente()`.
- **Forma de salida y evidencia:** `ResultadoCFO` + `Evidencia` (rebanada 1), con `piso_con.evidencia.ref="quiebre:<YYYY-MM|nunca>"` (mismo formateo que ya entiende `conceptos.formatear`).

## 5. Lo NUEVO que se construye (aditivo; `motor.py` cero diffs)

### 5.1 Generalizar la fábrica de proyección — `proyeccion/service.py`
Hoy `fabrica_proyectar_unidades` re-proyecta el pipeline completo con `motos_base + n`. Se generaliza a **`fabrica_proyectar_con_overrides`** que acepta overrides de **params** (motos_base) **y/o de modelos** (un campo de `ModeloMoto` para un modelo o todos):
- Firma propuesta: `fabrica_proyectar_con_overrides(*, params_overrides: dict | None = None, modelo_overrides: list[ModeloOverride] | None = None, escenario, mes_inicio, horizonte_meses) -> Callable[[], Awaitable[ResultadoProyeccion]]` (o directamente `-> ResultadoProyeccion`), donde `ModeloOverride = {modelo: str|"todos", campo: str, valor: Decimal|int}`.
- **Mecánica del override de modelo:** cargar los `ModeloMoto` vigentes (activos) → `model_copy(update={campo: valor})` sobre el/los modelo(s) objetivo → pasar la lista modificada por el MISMO camino que `fabrica_proyectar_unidades` (expansión a líneas + `_resultado_con` con E1/D2). NO re-cargar los modelos dentro del pipeline si ya se inyectan (verificar contra el código de la rebanada 1). SIN `anclas_override` (arranque real).
- **`fabrica_proyectar_unidades` delega en la general** (params_overrides={motos_base: base+n}) → un solo camino de código; los tests/golden de la rebanada 1 deben quedar **idénticos** (regla de oro: cero cambios de comportamiento en lo vivo).
- `motor.py` cero diffs; función aditiva; S1 (esto vive en `proyeccion`, no en `cfo`).

### 5.2 Calc de palanca — `cfo/calc/escenario.py` (o `cfo/calc/palanca.py`)
`async def impacto_palanca(*, palanca: str, nuevo_valor: Decimal, modelo: str = "todos") -> list[ResultadoCFO]`:
- Valida `palanca ∈ {plazo_semanas, cuota_inicial, cuota_semanal}` y `modelo ∈ {Raider, Apache, Sport, todos}` (contra los modelos vigentes; si el modelo no existe → abstención honesta).
- Base = `fabrica_proyectar_con_overrides()` sin overrides (o la proyección vigente); Con = con el `modelo_override`.
- Devuelve `piso_sin` (COP), `piso_con` (COP, `ref="quiebre:<...>"` = primer mes `estado!="ok"` de la serie con la palanca), `impacto` (COP = piso_con − piso_sin, **computado por COMPAS**, no por el modelo). Evidencia con ancla de horizonte (como el fix de rebanada 1). Sin config → abstención (patrón `runway.py`).
- **Reconciliación:** base y con corren el MISMO pipeline completo → el piso de "con" y el de la proyección vigente cuadran.

### 5.3 Registrar la tool — `cfo/agente/tools.py`
Nueva tool `simular_palanca` en `DISPATCH` + `TOOLS_SCHEMA` (wrapper async de UN dict posicional, como los de la rebanada 1):
- `input_schema` estricto: `additionalProperties:false`, `required:["palanca","nuevo_valor"]`, `palanca` enum `["plazo_semanas","cuota_inicial","cuota_semanal"]`, `nuevo_valor` string (semanas o COP), `modelo` enum `["Raider","Apache","Sport","todos"]` (default "todos"). El wrapper valida y parsea `nuevo_valor` string→Decimal (regla 1, raise si inválido) y llama la calc con kwargs.
- Descripciones claras para que el modelo elija la palanca y extraiga el valor + el modelo de la pregunta.

### 5.4 Prompt — `cfo/agente/prompt.py`
Bloque corto: usar `simular_palanca` para "¿qué pasa si cambio el plazo/cuota…?"; devuelve `[[piso_sin]]`/`[[piso_con]]`/`[[impacto]]`; citar con tokens, nunca escribir cifras. (Regla 1/2 sin cambios.)

## 6. Contrato de datos

- Conceptos citables nuevos: `piso_sin_palanca`, `piso_con_palanca` (con contexto de quiebre en `ref`), `impacto_palanca` — todos `unidad="COP"`. (Reusan el formateo COP + quiebre de `conceptos.py`.) *Nota: `piso_sin`/`piso_con` ya existen como nombres en la rebanada 1 (`escenario.impacto_escenario`) — el sustituidor (`sustituir_tokens`) arma `{r.concepto: r}` sobre TODOS los `ResultadoCFO` acumulados en el turno (last-wins), así que si ambas tools se disparan en el mismo turno, un `piso_sin`/`piso_con` compartido haría que el resultado de la última tool en ejecutar pise silenciosamente al de la primera. Por eso los conceptos de rebanada 2 van NAMESPACED con el sufijo `_palanca` (`piso_sin_palanca`/`piso_con_palanca`/`impacto_palanca`): evita la colisión por construcción en vez de confiar en que las dos tools nunca coincidan en un turno.*
- Montos Decimal en backend, string en el borde. `plazo_semanas` es entero; `cuota_*` son COP.

## 7. Manejo por-modelo

`modelo` opcional (default "todos"). "Todos" aplica el override a cada `ModeloMoto` activo; un modelo específico solo a ese. Si el usuario nombra un modelo que no existe/está inactivo → abstención honesta (no adivinar). La evidencia debe **declarar a qué modelo(s)** se aplicó (en `detalle`/`ref`) para trazabilidad.

## 8. Trampas (heredadas de rebanada 1)

1. **NO usar `runway_meses` para el mes de quiebre** — escanear `estado`/valles de la serie (primer `estado!="ok"`).
2. **Reconciliación:** base y con DEBEN correr el mismo pipeline completo (motor→E1→D2, `primer_mes_acumula=True`) — si no, el impacto de la palanca da falsa confianza.
3. **NO `anclas_override`** (fuerza arranque semilla).
4. **`%` fuera:** ningún resultado ni evidencia de esta rebanada expone un `%` (el mix, que sí lo haría, está en la rebanada 4).

## 9. Errores / abstención

Sin params/modelos vigentes → 409 → abstención honesta. Palanca/modelo inválidos o `nuevo_valor` no numérico → raise en la frontera de la tool (no adivinar). Valor absurdo (plazo 0, cuota negativa) → validación mínima + el motor decide; si produce una proyección degenerada, se narra el resultado con evidencia, no se inventa. Backstop de `consultar` intacto (nunca revienta al caller).

## 10. Pruebas (TDD)

- **Fábrica generalizada** (`proyeccion`): override de un campo de modelo re-proyecta el pipeline completo; `fabrica_proyectar_unidades` delega y la rebanada 1 queda idéntica (golden/tests de rebanada 1 verdes).
- **Calc `impacto_palanca`** (con fakes): arma piso_sin/piso_con/impacto/quiebre para plazo/cuota inicial/cuota semanal; abstención sin config; modelo inexistente → abstención.
- **Tool `simular_palanca`**: schema estricto; `nuevo_valor` string→Decimal; palanca/modelo inválidos → raise.
- **Reconciliación:** piso_con (con override) == la proyección del mismo pipeline con ese override (no tautológico).
- **e2e** (`test_servicio.py`, ClienteFake): el modelo pide `simular_palanca`, cita tokens, texto con valores sustituidos (no crudos); intento de cifra cruda → reintento → abstención.
- **Golden:** un cambio de palanca de referencia con impacto conocido "al peso".
- **Regresión:** suite completa verde; `motor.py` 0 diffs (`git diff <MERGE_BASE>..HEAD -- motor.py` vacío); sin `float(` en el slice; `ruff` limpio; S1 verde.

## 11. Innegociables

Decimal (nunca float en dinero); `motor.py` cero diffs; S1 (`cfo/**` no importa dominio/motor; la re-proyección vive en `proyeccion/service.py`); catálogo de auditoría **sin eventos nuevos** (reusa `cfo.consulta`/`cfo.respuesta`); flag; gate-waiver + Kimi retroactivo (NUNCA simulado).

## 12. Autorevisión del spec (pendiente tras escribirlo)

Placeholders, consistencia (formas ↔ funciones del motor), alcance (una rebanada), ambigüedad (nombres de palanca/modelo/concepto). Corregir inline.

---
*Rebanada 2 del inc4. Método: brainstorming (aprobado) → este spec → writing-plans → SDD (desde 29-ago) → Kimi retroactivo. Ante conflicto de alcance mandan `COMPAS_NORTE.md`, `CLAUDE.md`, el roadmap de FABS y este spec. `motor.py` intocable. Mix → rebanada 4.*
