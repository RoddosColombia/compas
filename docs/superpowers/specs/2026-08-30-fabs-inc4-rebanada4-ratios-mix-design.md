# FABS inc4 · Rebanada 4 — Ratios/% + Mix (composición del gasto · mix de modelos)

- **Fecha:** 2026-08-30 · **Autor:** Claude + CEO (brainstorming aprobado)
- **Incremento:** inc4 (cerebro analítico), **rebanada 4** (rebanadas 1 —escenarios—, 2 —palancas—, 3 —tendencias— YA en vivo). Es la que **ABRE el uso de `%`**.
- **Flag:** `CFO_ENABLED`. Con el flag apagado, COMPAS byte-idéntico.
- **Gate:** crítico (toca el verificador anti-alucinación + produce cifras que el CEO usa para decidir) → **gate-waiver + GO CEO**. NADA de Kimi (ver memoria `kimi-no-disponible-semanas`). Construcción por SDD.
- **Rama:** `feat/fabs-inc4-rebanada4-ratios-mix` (desde `main`).

## 1. Norte de la rebanada (una línea)

Que el CEO pregunte por conversación por **composición y mix** —*"¿qué % de mi gasto es nómina?"*, *"¿cuánto pesa la deuda?"*, *"¿cómo está mi mix Raider/Apache/Sport?"*— y FABS responda con **porcentajes que computa COMPAS**, con evidencia, **sin que el modelo calcule** ni escriba un `%` propio.

## 2. Alcance (y NO-alcance)

**Entra (rebanada 4) — dos capacidades, ambas introducen `%`:**
- **① `composicion_gasto(ventana)`** — el % de cada grupo de gasto sobre el gasto REAL total. `ventana ∈ {cerrado, acumulado, curso}` (el CEO pidió las 3).
- **② `mix_modelos()`** — la participación (`%`) de cada modelo activo en el mix, normalizada.

**NO entra (rebanadas siguientes / fast-follow):**
- **What-if de mix** ("¿y si vendo más Raider?") → después (es la palanca de mix diferida de la rebanada 2: re-proyectar con `participacion_mix` cambiado + parsear un `%` de entrada).
- **Composición del gasto PROYECTADO por grupo** → el motor expone el gasto por LÍNEA (gastos_fijos/GPS/deuda/…), NO por los 6 `RubroGrupo`; un desglose proyectado por grupo exigiría trabajo nuevo del motor. La composición va solo sobre gasto REAL.
- **Ratios de ingreso / otros %** (márgenes, crecimiento %) → después.

## 3. Principio inamovible + el `%` (lo delicado, resuelto)

**El modelo nunca produce una cifra — incluido el `%`.** El verificador (`verificador.verificar`) corre sobre el texto **con tokens, ANTES de sustituir**; `_RE_PORCENTAJE` marca como violación cualquier `\d%` **crudo** en ese texto. Como el modelo cita `[[pct_nomina]]` (un token, sin `%` literal), `extraer_cifras` no encuentra `%` → pasa; `sustituir_tokens` lo vuelve `"45,3%"` **después** (el texto sustituido nunca se re-verifica). Por lo tanto:
- El `%` que COMPAS computa entra **por el camino del token**, sin tocar la lógica de seguridad del verificador.
- El bloqueo de un `%` que el modelo escriba por su cuenta **se mantiene** (protege contra "el modelo extrapola un ratio"). Es un test explícito de esta rebanada.
- Lo único que cambia en el verificador es su **docstring/comentario** (líneas ~58-61 y ~149-155: "COMPAS no tiene concepto de porcentaje" deja de ser cierto — el nuevo texto explica que COMPAS SÍ computa `%` pero el modelo los cita por token, y un `%` crudo sigue prohibido).

## 4. Datos que se REUSAN (ya existen)

- **Egreso real por rubro/mes:** `control.service._egresos_por_rubro(mes_id) -> dict[str rubro_id, Decimal]` (`$group` EGRESO + expansión de `partes` vía `pares_clasificacion`), y el patrón de `control()` que mapea rubro→grupo con `{r.id: r for r in await Rubro.find_all()}` y agrupa por `r.grupo.value`.
- **Grupos:** `RubroGrupo` (`app/domain/rubro.py`): `INGRESOS_OPERATIVOS`, `COSTO_PRODUCTO`, `OPERACION`, `NOMINA`, `DEUDAS_OBLIGACIONES`, `OTROS`. Los **5 grupos de gasto** = todos menos `INGRESOS_OPERATIVOS`.
- **Selección de meses por ventana:** el mismo criterio que la rebanada 3 — `cerrado` = último `MesControl` `CERRADO`; `acumulado` = últimos 3 meses con movimientos; `curso` = último mes con movimientos. Excluir el rubro sistema "Ajuste de conciliación" (`_rubro_ajuste`).
- **Modelos:** `modelos_moto.service.listar_modelos(activo=True) -> list[ModeloMoto]`; `ModeloMoto.participacion_mix: Money` (fracción 0..1, **sin validación de que sumen 1**), `ModeloMoto.nombre`.
- **Forma de salida y evidencia:** `cfo.calc.evidencia.ResultadoCFO` + `Evidencia`; `cfo.agente.conceptos.formatear` (se le agrega el branch `%`).

## 5. Lo NUEVO que se construye (aditivo; `motor.py` cero diffs)

### 5.1 Agregación de composición del gasto real — `proyeccion/service.py` (o `control/service.py`)
`async def composicion_gasto_real(*, ventana: str) -> ComposicionGasto` (dataclass plano `ComposicionGasto(ventana: str, meses: list[str], por_grupo: dict[str, Decimal], total: Decimal)`):
- Resuelve el/los `mes_id` según `ventana ∈ {cerrado, acumulado, curso}`.
- Suma EGRESO sobre esos meses expandiendo `partes` (`pares_clasificacion`), mapea cada `(rubro, valor)` → `grupo`, agrupa en los **5 grupos de gasto**, **saltando el rubro "Ajuste de conciliación"** (en primario y en partes). `por_grupo` con clave = valor del `RubroGrupo` ("nomina", "deudas_obligaciones", …). `total` = Σ de los 5 grupos.
- Devuelve valores planos (S1). Sin meses con movimientos / total 0 → abstención aguas arriba.
- *Ubicación exacta la fija el plan; el contrato es `ComposicionGasto`.* (Reusa/generaliza el mapeo rubro→grupo de `control/service`; NO importa `cfo`.)

### 5.2 Mix de modelos plano — `modelos_moto/service.py`
`async def mix_activos() -> list[tuple[str, Decimal]]`: `[(m.nombre, m.participacion_mix) for m in await listar_modelos(activo=True)]` — valores planos (str + Decimal), para que `cfo/calc` NO importe `ModeloMoto` (S1).

### 5.3 Calc de ratios — `cfo/calc/ratios.py` (nuevo)
Mismo molde que `cfo.calc.tendencias`/`palanca` (envuelve un servicio, arma `ResultadoCFO` con evidencia, abstiene). **El `%` lo computa la calc** (código COMPAS, no el modelo): divide dos Decimals.
- `async def composicion_gasto(*, ventana: str) -> list[ResultadoCFO]`: llama `composicion_gasto_real(ventana=ventana)`; por cada grupo de gasto emite `pct_{sufijo}` (unidad `"%"`, valor = `cop_grupo / total * 100`, cuantizado a 1 decimal) y `cop_{sufijo}` (unidad COP), más `gasto_total_comp` (COP). Sufijos: `costo_producto`, `operacion`, `nomina`, `deudas`, `otros` (mapeo desde el valor del `RubroGrupo`; `deudas_obligaciones`→`deudas`). Evidencia con `ref` = ventana + mes(es). `ventana` inválida → `ValueError`; sin data/total 0 → abstención (`concepto="composicion"`).
- `async def mix_modelos() -> list[ResultadoCFO]`: llama `mix_activos()`; `total = Σ participacion_mix`; si `total == 0` → abstención (`concepto="mix"`, ref `"sin-mix"`); si no, por modelo emite `mix_{nombre_lower}` (unidad `"%"`, valor = `participacion_mix / total * 100`, normalizado). La `Evidencia` declara que es share normalizado.

### 5.4 Branch de `%` en el formateo — `cfo/agente/conceptos.py`
Agregar en `formatear`: `if r.unidad == "%": return _pct_es(r.valor)` con `_pct_es(d) = f"{d:.1f}".replace(".", ",") + "%"` (p. ej. `"45,3%"`). **Además (fast-follow M3, se cierra acá):** borrar el `CONCEPTOS_CITABLES` muerto (frozenset no consumido para gating) + su test-candado.

### 5.5 Docstring del verificador — `cfo/agente/verificador.py`
Actualizar SOLO el docstring/comentarios (~líneas 58-61, 149-155, y el docstring de módulo si menciona "%"): COMPAS ahora SÍ computa `%` (rebanada 4: `pct_*`/`mix_*`), pero el modelo los cita por TOKEN; un `%` CRUDO en el texto sigue siendo violación (el modelo no extrapola ratios) — por eso `_RE_PORCENTAJE` se mantiene. **Cero cambios de lógica.**

### 5.6 Registrar las tools + prompt — `cfo/agente/tools.py`, `prompt.py`
- `composicion_gasto`: wrapper con `ventana` (enum `["cerrado","acumulado","curso"]`, `required:["ventana"]`, `additionalProperties:false`). `mix_modelos`: no-param (como `rumbo_caja`, cableada directa).
- Prompt: bloque corto (aditivo) — cuándo usar cada tool; citar cada `%` con su token (`[[pct_nomina]]`, `[[mix_raider]]`, …); **el % lo da la herramienta ya calculado — cítalo, NUNCA lo calcules ni escribas un `%` propio** (si escribes un `%` a mano, el verificador te rebota).

## 6. Contrato de datos (conceptos citables nuevos — namespaced, libres de colisión)

- ① `pct_costo_producto`, `pct_operacion`, `pct_nomina`, `pct_deudas`, `pct_otros` (unidad `"%"`); `cop_costo_producto`…`cop_otros` (COP); `gasto_total_comp` (COP).
- ② `mix_{modelo}` por modelo activo (unidad `"%"`; nombre en minúsculas, p. ej. `mix_raider`).
*Nota de no-colisión: ningún concepto existente empieza por `pct_`/`cop_`/`mix_`/`gasto_total_comp` (inventario verificado: rebanadas 1–3 usan `piso_*`, `impacto_*`, `*_real_*`, `delta_*`, `caja_real_*`, `gasto_real_mes`, etc.). `gasto_real_mes` (rebanada 3) ≠ `gasto_total_comp` (rebanada 4) — distintos.*
- Montos Decimal; el `%` se guarda como Decimal en `valor` (Money es un alias de Decimal sin rango, acepta `Decimal("45.3")`), unidad `"%"`.

## 7. Ventanas (composición)

`cerrado` → el último `MesControl` CERRADO (foto firme; puede sesgarse por una nómina puntual). `acumulado` → los últimos 3 meses con movimientos (suaviza). `curso` → el último mes con movimientos (al día, puede estar incompleto). Cada evidencia declara la ventana + el/los mes(es) en `ref`.

## 8. Trampas

1. **Excluir "Ajuste de conciliación"** de toda suma de egreso — al atribuir cada par `(rubro, valor)` a su grupo, saltar si `rubro == rubro_ajuste`, tanto en el rubro primario como en cada parte (el ajuste vive en el grupo OTROS; si no se excluye, infla OTROS).
2. **`partes` de splits:** el egreso por grupo DEBE expandir `partes` (un split puede repartirse entre grupos distintos) — reusar `pares_clasificacion` (a diferencia del total de caja de la rebanada 3, que NO expande porque un total no necesita atribución; acá la atribución por grupo sí lo exige). El `total` por construcción = Σ EGRESO (excl. ajuste), o sea coincide con el `gasto_real` de la rebanada 3 para la misma ventana.
3. **El `%` lo computa COMPAS** (la calc, código backend), NUNCA el modelo. El modelo cita el token; un `%` crudo del modelo se bloquea (test explícito).
4. **Mix sin validación de suma 1:** normalizar por Σ (share) o abstener si Σ=0. Nunca mostrar `%` que no sumen 100 sin decir que es share normalizado.
5. **Conceptos namespaced** `pct_*`/`cop_*`/`mix_*` — cero colisión (verificado).
6. **`total == 0`** (sin egreso en la ventana) → abstención honesta, no dividir por cero.

## 9. Errores / abstención

Sin meses con movimientos / total 0 (composición) o Σ mix = 0 → abstención honesta (un único `ResultadoCFO(disponible=False)`). `ventana` inválida → raise en la frontera de la tool. Backstop de `consultar` intacto.

## 10. Pruebas (TDD)

- **Agregación `composicion_gasto_real`** (golden con `Transaccion`/`Rubro` fixtures en mongomock): suma EGRESO por grupo, expande `partes`, excluye el ajuste, por las 3 ventanas; recalculado a mano.
- **`mix_activos`**: devuelve (nombre, participacion_mix) de los modelos activos.
- **Calc (fakes de servicio):** `composicion_gasto` computa `pct_{grupo}` = cop/total*100 correcto + `cop_{grupo}` + total; abstención sin data; `ventana` inválida. `mix_modelos` normaliza (Σ=1 → participaciones tal cual; Σ≠1 → normaliza; Σ=0 → abstención).
- **`formatear` branch `%`:** `unidad="%"`, `Decimal("45.3")` → `"45,3%"`.
- **VERIFICADOR (crítico):** un texto del modelo con un `%` CRUDO ("la nómina es 45%") SIGUE dando `ok=False` (el `%` propio del modelo se bloquea); un texto que cita `[[pct_nomina]]` da `ok=True` y sustituye a `"45,3%"`. Confirmar que ningún test/golden existente dependía del viejo texto del docstring.
- **e2e** (ClienteFake): el modelo pide `composicion_gasto`/`mix_modelos`, cita tokens `pct_*`/`mix_*`, texto con `%` sustituido (no tokens crudos, no `%` propio); intento de `%` crudo → reintento → abstención `motivo="verificacion"`.
- **M3 cleanup:** `CONCEPTOS_CITABLES` + su test borrados; suite verde.
- **Regresión:** `motor.py` 0 diffs; sin `float(` en `ratios.py`; `ruff` limpio; `test_s1_aislamiento.py` verde (sin subcadena "motor" en `ratios.py`).

## 11. Innegociables

Decimal (nunca float en dinero/ratio); `motor.py` cero diffs; S1 (`cfo/**` no importa dominio/motor; las agregaciones viven en `proyeccion`/`modelos_moto`/`control` service y devuelven valores planos; los ratios los computa `cfo/calc`); **el verificador NO se debilita** (solo docstring); catálogo de auditoría **sin eventos nuevos**; flag; gate-waiver + GO CEO (NADA de Kimi, NUNCA simulado).

## 12. Sub-rebanadas (para el plan)

**4a** composición del gasto (incluye la infra del `%`: `composicion_gasto_real` → calc → `formatear` branch → docstring del verificador → tools/prompt → e2e; + el cleanup M3 de `CONCEPTOS_CITABLES`). **4b** mix (`mix_activos` → calc → tool/prompt → e2e). Orden: 4a primero (monta el `%`), luego 4b.

---
*Rebanada 4 del inc4. Método: brainstorming (aprobado) → este spec → writing-plans → SDD → gate-waiver + GO CEO. Ante conflicto de alcance mandan `COMPAS_NORTE.md`, `CLAUDE.md`, el roadmap de FABS y este spec. `motor.py` intocable. What-if de mix y composición proyectada → rebanadas siguientes.*
