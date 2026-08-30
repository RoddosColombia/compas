# FABS inc4 · Rebanada 3 — Tendencias (real vs. mes pasado · rumbo · real vs. presupuesto)

- **Fecha:** 2026-08-29 · **Autor:** Claude + CEO (brainstorming aprobado)
- **Incremento:** inc4 (cerebro analítico), **rebanada 3** (rebanadas 1 —escenarios— y 2 —palancas— YA en vivo).
- **Flag:** `CFO_ENABLED`. Con el flag apagado, COMPAS byte-idéntico.
- **Gate:** crítico (produce cifras que el CEO usa para decidir) → **gate-waiver + GO CEO**. NADA de Kimi (fuera muchas semanas; ver memoria `kimi-no-disponible-semanas`). Construcción por SDD.
- **Rama:** `feat/fabs-inc4-rebanada3-tendencias` (desde `main`).

## 1. Norte de la rebanada (una línea)

Que el CEO pregunte por conversación **cómo viene lo REAL en el tiempo** —*"¿cómo viene el gasto vs el mes pasado?"*, *"¿voy en rumbo hacia mayo-2027?"*, *"¿gasté más o menos de lo que presupuesté?"*— y FABS responda con **cifras reales mes a mes, su delta y su dirección**, con evidencia y **sin que el modelo calcule** (COMPAS calcula; FABS narra).

## 2. Alcance (y NO-alcance)

**Entra (rebanada 3) — tres capacidades, todas sobre data REAL, todo COP, SIN `%`:**
- **① `tendencia_real(metrica)`** — `metrica ∈ {ingreso, gasto, caja}`: los últimos 3 meses reales del métrica + delta (último vs. anterior, COP) + dirección (sube/baja/estable). *"¿cómo viene X vs el mes pasado?"*
- **② `rumbo_caja()`** — la caja real hasta hoy + a dónde la lleva la proyección desde hoy (piso proyectado + mes de quiebre del umbral) + dirección de lo real. *"¿voy en rumbo?"*
- **③ `real_vs_presupuesto(mes?)`** — gasto real ejecutado del mes (último cerrado por defecto) vs. presupuesto aprobado del mes + desvío (COP) + dirección (sobre/bajo/en línea). *"¿gasté más o menos de lo presupuestado?"*

**NO entra (rebanadas siguientes / fast-follow):**
- **Cualquier `%`, tasa o proporción** → rebanada 4 (junto con el cambio del verificador que habilita `%` computados por COMPAS). La dirección va como palabra cualitativa (sube/baja), nunca como porcentaje.
- **Desglose por grupo/rubro** ("¿mi gasto en nómina sube?") → después (el CEO eligió totales: ingreso/gasto/caja). Recaudo real desglosado (rubro "Recaudo de cartera") → después; hoy el recaudo vive dentro del ingreso total.
- **Trayectoria de la PROYECCIÓN como tendencia** ("¿el recaudo proyectado sube?") → no se pidió; `rumbo_caja` toca la proyección solo para el rumbo de caja + umbral.
- **Real vs. una PROYECCIÓN pasada** — COMPAS no guarda fotos de proyecciones (se re-ancla en la caja real de hoy). Por eso la reconciliación "vs. lo planeado" se sirve como **real vs. presupuesto** (③, baseline sí guardado), no real vs. forecast viejo.

## 3. Principio inamovible (idéntico a rebanadas 1–2)

**El modelo nunca produce una cifra.** COMPAS lee los actuals y computa deltas/desvíos; cada resultado (cifra de cada mes, delta, desvío) viaja con su `Evidencia`; FABS cita `[[token]]`; el verificador rechaza toda cifra/mes/conteo cruda; el servicio sustituye tras verificar. Los resultados son **COP** — **no hay `%`**. La **dirección** (sube/baja/estable, sobre/bajo/en-línea) la computa COMPAS y viaja en el `ref` de la evidencia del delta/desvío (mismo patrón que el caveat de plazo de la rebanada 2); el modelo la relata, no la infiere.

## 4. Datos que se REUSAN (ya existen)

- **Caja real por mes:** `proyeccion.service._actuals_por_mes(rubro_ajuste_id)` (service.py) — itera `MesControl` en orden y calcula `cierre.service._caja_libro(mc.id, rubro_ajuste_id, mc.saldo_inicial_caja)` = saldo_inicial + Σ signo(transacciones del mes), excluyendo el rubro sistema "Ajuste de conciliación". Devuelve `list[tuple[MesControl, Decimal]]`.
- **Real + forecast de caja en un call:** `proyeccion.service.comparar_vigente(*, escenario, ancla_modo, horizonte_meses, mes_inicio_defecto)` (COCK-09) → `{ancla, actuals:[{mes, caja_real}], forecast:[{mes, caja}]}`. Base del tramo REAL de `rumbo_caja`.
- **Piso proyectado + quiebre:** `proyeccion.service.proyectar_vigente(*, escenario, mes_inicio, horizonte_meses)` → dict con `piso_caja` + `meses[].estado`; el piso + primer mes `estado!="ok"` es el mismo cómputo que ya usan rebanadas 1–2 (runway/escenario). Base del tramo PROYECTADO de `rumbo_caja`.
- **Ejecutado (gasto real) por rubro/mes:** `presupuesto.service._ejecutados_por_rubro_mes(mes_ids, rubro_ids)` — `$group` sobre `Transaccion` EGRESO (maneja `partes` de splits), meses **cerrados**. Patrón a reusar/generalizar para totales.
- **Modelo de datos:** `Transaccion` (`mes_id`, `rubro_id`, `TipoFlujo ∈ {INGRESO, EGRESO}`, `partes` para splits); `Rubro` (`tipo_flujo`, `es_sistema`; "Ajuste de conciliación" se excluye); `MesControl` (`mes` YYYY-MM-01, `estado`, `saldo_inicial_caja`). Dinero `Money=Decimal`; meses normalizados al día 1.
- **Forma de salida y evidencia:** `cfo.calc.evidencia.ResultadoCFO` + `Evidencia`; `cfo.agente.conceptos.formatear` (COP es-CO, contexto `quiebre:` ya soportado).

## 5. Lo NUEVO que se construye (aditivo; `motor.py` cero diffs)

### 5.1 Agregación de actuals mensuales — `proyeccion/service.py`
`async def actuals_mensuales(*, meses: int = 3) -> list[ActualMes]` (dataclass plano `ActualMes(mes: str, ingreso_real: Decimal, gasto_real: Decimal, caja_real: Decimal)`), últimos `meses` con movimientos, en orden cronológico:
- `ingreso_real` / `gasto_real`: `$group` sobre `Transaccion` por `mes_id` sumando por `TipoFlujo` (INGRESO / EGRESO), **excluyendo el rubro sistema "Ajuste de conciliación"** (igual que `_caja_libro`), manejando `partes` de splits (mismo tratamiento que `_ejecutados_por_rubro_mes`).
- `caja_real`: de `_actuals_por_mes` (reusa `_caja_libro`).
- Devuelve valores planos (S1: vive en `proyeccion`, `cfo/calc` no toca dominio). Sin meses reales → lista vacía → abstención honesta aguas arriba.

### 5.2 Totales presupuesto vs. ejecutado por mes — `presupuesto/service.py`
`async def real_vs_presupuesto_mes(mes: str | None = None) -> PresupuestoMes | None` (dataclass plano `PresupuestoMes(mes: str, gasto_real: Decimal, presupuesto_aprobado: Decimal)`):
- `gasto_real` = total ejecutado EGRESO del mes (suma de `_ejecutados_por_rubro_mes` sobre todos los rubros del mes).
- `presupuesto_aprobado` = total del presupuesto **aprobado** del mes (la línea del proceso presupuestal ya aprobada). *La función exacta que expone el aprobado total por mes la fija el plan contra `presupuesto/service` + el dominio de líneas; el contrato de esta función es {gasto_real, presupuesto_aprobado} en Decimal.*
- `mes` por defecto = último **cerrado** (el ejecutado es cerrado-only). Sin mes cerrado / sin presupuesto aprobado → `None` → abstención.

### 5.3 Calc de tendencias — `cfo/calc/tendencias.py`
Tres funciones, mismo molde que `cfo.calc.escenario`/`palanca` (envuelven un servicio, arman `ResultadoCFO` con evidencia, abstienen ante error/sin-data). **La dirección la computa la calc a partir de las cifras que le da COMPAS** (compara dos Decimals) y la mete en el `ref` del delta/desvío; el modelo solo la relata.
- `async def tendencia_real(*, metrica: str) -> list[ResultadoCFO]`: valida `metrica ∈ {ingreso, gasto, caja}`; llama `actuals_mensuales(meses=3)`; arma conceptos **namespaced** `{metrica}_real_m0` (más reciente), `_m1`, `_m2` (COP; ref = ancla de mes) y `delta_{metrica}_real` (COP = m0 − m1, `ref="direccion:<sube|baja|estable>"`). Con < 2 meses reales → abstención honesta ("aún no hay suficiente historia").
- `async def rumbo_caja() -> list[ResultadoCFO]`: combina DOS fuentes ya existentes — la **caja real** de `comparar_vigente`/`_actuals_por_mes` (últimos meses reales) y el **piso proyectado + quiebre** de `proyectar_vigente` (mismo `piso_caja` + primer mes `estado!="ok"` que ya usan rebanadas 1–2; `comparar_vigente` NO trae el umbral, por eso el piso/quiebre viene del proyector). Conceptos: `caja_real_ult` (última caja real), `caja_real_previo` (penúltima; para la dirección), `piso_proyectado` (`ref="quiebre:<YYYY-MM|nunca>"`) y `delta_caja_real` (COP = ult − previo, `ref="direccion:..."`). Sin actuals ni config → abstención.
- `async def real_vs_presupuesto(*, mes: str | None = None) -> list[ResultadoCFO]`: llama `real_vs_presupuesto_mes`; conceptos `gasto_real_mes` (COP), `presupuesto_mes` (COP) y `desvio_presupuesto` (COP = gasto_real − presupuesto, `ref="direccion:<sobre|bajo|en-linea>"`). Sin mes cerrado / sin aprobado → abstención.

### 5.4 Registrar las tools — `cfo/agente/tools.py`
Tres entradas en `DISPATCH` + `TOOLS_SCHEMA` (wrappers async de UN dict posicional, patrón de las tools existentes):
- `tendencia_real`: `input_schema` estricto, `required:["metrica"]`, `metrica` enum `["ingreso","gasto","caja"]`.
- `rumbo_caja`: sin parámetros (`properties:{}`, `additionalProperties:false`, `required:[]`).
- `real_vs_presupuesto`: `mes` opcional (string `YYYY-MM`, `additionalProperties:false`).
`resultado_a_dict` intacto (sigue strippeando `valor`/`detalle`).

### 5.5 Prompt — `cfo/agente/prompt.py`
Bloque corto (aditivo, sin tocar reglas 1–7 ni los bloques de escenarios/palancas): cuándo usar cada tool; citar cada cifra con SU token; **la dirección viene en el `ref` del delta/desvío — relátala, no la calcules**; recordatorio de que NO hay `%` (si preguntan por un %, abstenerse, va en rebanada 4).

## 6. Contrato de datos (conceptos citables nuevos — todos namespaced, unidad COP)

- ① `ingreso_real_m0/m1/m2`, `gasto_real_m0/m1/m2`, `caja_real_m0/m1/m2` (según métrica), `delta_ingreso_real` / `delta_gasto_real` / `delta_caja_real`.
- ② `caja_real_ult`, `caja_real_previo`, `piso_proyectado` (ref quiebre), `delta_caja_real` (compartido de forma; ver nota).
- ③ `gasto_real_mes`, `presupuesto_mes`, `desvio_presupuesto`.
*Nota de no-colisión (lección rebanada 2): `sustituir_tokens` arma `{r.concepto: r}` last-wins sobre TODO el turno. Los nombres de arriba no chocan con conceptos de rebanadas 1–2 (`piso_sin`/`piso_con`/`piso_*_palanca`/`caja_hoy`/`runway`/`iva_cuatrimestre`). `delta_caja_real` lo emiten tanto ① (metrica=caja) como ②; como ambos representan el MISMO dato (delta de la caja real del último par de meses) y provienen de la misma fuente, coexisten sin ambigüedad — pero el plan DEBE verificar que las dos rutas produzcan el mismo valor+evidencia para ese concepto, o namespacearlos (`delta_caja_real_tend` vs `delta_caja_real_rumbo`) si difieren.*
- Montos Decimal en backend, string en el borde. Dirección en `ref="direccion:<...>"`; nunca un `%`.

## 7. Manejo / meses

`tendencia_real`: últimos 3 meses con movimientos (si hay 2, delta con 2; si hay 1, abstención). `real_vs_presupuesto`: último mes **cerrado** (o el `mes` pedido si está cerrado y tiene aprobado). `rumbo_caja`: ancla = último cerrado o último con movimientos (el que ya usa `comparar_vigente`). Cada evidencia declara el/los mes(es) en el `ref` para trazabilidad.

## 8. Trampas

1. **Excluir "Ajuste de conciliación"** en toda suma de actuals (igual que `_caja_libro`), o el ingreso/gasto real quedaría inflado por los ajustes de cuadre.
2. **`partes` de splits:** sumar por parte, no por transacción, en ingreso/gasto (reusar el tratamiento de `_ejecutados_por_rubro_mes`).
3. **Dirección la computa COMPAS**, no el modelo: la calc compara los dos Decimals y fija `ref="direccion:..."`. El modelo relata la palabra, jamás decide "subió/bajó" por su cuenta ni escribe un %.
4. **`%` fuera:** ningún resultado ni evidencia expone un `%` (va en rebanada 4).
5. **Conceptos namespaced desde el día 1** (ver §6): nada que colisione en un turno compuesto.
6. **Cerrado vs. con-movimientos:** `real_vs_presupuesto` exige cerrado (el ejecutado es cerrado-only); `tendencia_real` acepta meses con movimientos. No mezclar los criterios.

## 9. Errores / abstención

Sin data real suficiente (menos de 2 meses; sin mes cerrado; sin presupuesto aprobado; sin config vigente) → abstención honesta (un único `ResultadoCFO(disponible=False)`, patrón `runway.py`). `metrica` inválida → raise en la frontera de la tool. Backstop de `consultar` intacto (un READ nunca revienta al caller).

## 10. Pruebas (TDD)

- **Agregación `actuals_mensuales`** (golden con `Transaccion` fixtures): suma INGRESO/EGRESO por mes excluyendo Ajuste de conciliación, respeta `partes`, caja de `_actuals_por_mes`; recalculado a mano en el docstring.
- **`real_vs_presupuesto_mes`**: total ejecutado vs. aprobado del mes cerrado; sin cerrado → None.
- **Calc (fakes de servicio):** cada una arma sus conceptos + el `ref="direccion:..."` correcto según el signo; abstención sin data; `metrica` inexistente → abstención/raise.
- **Tools:** schemas estrictos; `metrica` enum; `mes` opcional; `rumbo_caja` sin params.
- **Prompt:** menciona las 3 tools + "la dirección viene en el ref" + "sin %".
- **e2e** (`test_servicio.py`, ClienteFake): el modelo pide una tool, cita tokens, texto con valores sustituidos (no crudos) y relata la dirección; cifra cruda → reintento → abstención `motivo="verificacion"`.
- **Regresión:** suite verde; `motor.py` 0 diffs; sin `float(` en el slice; `ruff` limpio; `test_s1_aislamiento.py` verde.

## 11. Innegociables

Decimal (nunca float en dinero); `motor.py` cero diffs; S1 (`cfo/**` no importa dominio/motor; las agregaciones viven en `proyeccion`/`presupuesto` service y devuelven valores planos); catálogo de auditoría **sin eventos nuevos** (reusa `cfo.consulta`/`cfo.respuesta`); flag; gate-waiver + GO CEO (NADA de Kimi, NUNCA simulado); **sin `%`** (rebanada 4).

## 12. Sub-rebanadas (para el plan)

Construible en 3 sub-rebanadas independientes, en este orden: **3a** `tendencia_real` (+ `actuals_mensuales`) · **3b** `rumbo_caja` (reusa `comparar_vigente`) · **3c** `real_vs_presupuesto` (+ totales presupuesto/ejecutado). Cada una: servicio → calc → tool → prompt → e2e/golden. El plan puede hacerlas en una sola pasada SDD o separarlas.

---
*Rebanada 3 del inc4. Método: brainstorming (aprobado) → este spec → writing-plans → SDD → gate-waiver + GO CEO. Ante conflicto de alcance mandan `COMPAS_NORTE.md`, `CLAUDE.md`, el roadmap de FABS y este spec. `motor.py` intocable. `%` y desglose por grupo → rebanadas siguientes.*
