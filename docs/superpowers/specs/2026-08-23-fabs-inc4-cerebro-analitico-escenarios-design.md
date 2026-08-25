# FABS inc4 — Cerebro analítico · Rebanada 1: what-if de escenarios (el caso de la bodega)

- **Fecha:** 2026-08-23 · **Autor:** Claude + CEO (brainstorming aprobado)
- **Incremento:** inc4 (cerebro analítico / CFO conversacional), **primera rebanada**.
- **Flag:** `CFO_ENABLED` (ya encendido en el piloto). Esta rebanada agrega herramientas nuevas al agente; con el flag apagado, COMPAS sigue byte-idéntico.
- **Gate:** crítico (toca lectura/cálculo de plata que el CEO consumirá para decidir) → **gate Kimi** de diseño (este doc) y de código.

## 1. Norte de la rebanada (una línea)

Que el CEO le pregunte a FABS en lenguaje natural un **what-if** —*"si arriendo una bodega de $20M/mes desde septiembre, ¿cómo me pega en caja, en qué mes me quedo sin efectivo, y cuántas motos de más vendo para evitarlo?"*— y FABS **corra el escenario sobre el motor real de COMPAS** y lo narre con evidencia, **sin que el modelo haga una sola operación aritmética** (COMPAS calcula; FABS narra).

## 2. Alcance (y NO-alcance)

**Entra (rebanada 1):**
1. **Impacto de un ajuste recurrente** (un gasto o ingreso hipotético: monto, naturaleza, mes de inicio, mes de fin opcional) sobre la proyección: caja mes a mes con y sin el ajuste, y el delta por mes.
2. **Mes de quiebre**: primer mes en que la caja cruza **por debajo del umbral** (`caja_minima`) y, aparte, primer mes en que la caja se vuelve **negativa** ("sin efectivo") — con y sin el ajuste.
3. **Solver de motos**: cuántas **unidades de más por mes** hay que colocar para que, con el ajuste aplicado, la caja **no cruce el umbral** (o el mínimo alcanzable si no se puede).

**NO entra (rebanadas siguientes / fast-follow):**
- Escenarios arbitrarios multi-variable (varios ajustes + varios cambios de parámetros a la vez, combinaciones libres).
- Anclar la proyección a la **caja real de hoy calculada desde movimientos** (opción C del brainstorming) — ver §7 "Decisión: ancla". Queda como **fast-follow** para afinar el mes exacto de quiebre; NO bloquea esta rebanada.
- Persistir/guardar escenarios con nombre para FABS (`escenarios_impacto/` existe como CRUD, pero conectarlo a FABS es otra rebanada).
- Otros what-if (cambiar plazo, tasa, mix de modelos) — después.
- Nada proactivo (alertas/vigilante) — ese es otro incremento.

## 3. Principio inamovible que esta rebanada DEBE preservar

**El modelo nunca produce una cifra.** Toda cifra —cada delta, cada piso, cada mes, cada cantidad de motos— la calcula COMPAS y viaja con su `Evidencia`. FABS cita cada valor con un token `[[nombre]]`; el verificador **rechaza cualquier número crudo** que el modelo intente escribir y **rechaza cualquier token no respaldado** por el turno; el servicio **sustituye** los tokens por los valores formateados **después** de verificar. Es la garantía de inc2/inc3-A, extendida a respuestas con **varios** valores.

## 4. Motor que se REUSA (ya existe, auditado, `motor.py` INTOCABLE)

Todo esto ya está construido y expuesto por HTTP (`app/proyeccion/`). FABS lo **llama**; no se reescribe nada del motor.

| Capacidad | Función a llamar | Ref | Devuelve |
|---|---|---|---|
| Proyección vigente | `proyeccion.service.proyectar_vigente(*, escenario, mes_inicio, horizonte_meses, caja_inicial_override=None)` | `service.py:561` | serie mensual + KPIs (dict, montos string) |
| **Impacto de un ajuste** | `proyeccion.service.proyectar_impactos(*, ajustes, escenario, mes_inicio, horizonte_meses)` | `service.py:662` | `{base, ajustada, valles_base, valles_ajustada, delta_por_mes}` |
| Forma del ajuste | `proyeccion.impactos.Ajuste(nombre, naturaleza, modo, valor, mes_inicio, mes_fin=None, rubro_id=None)` | `impactos.py:36` | `naturaleza ∈ {gasto,ingreso}`, `modo ∈ {absoluto,porcentaje}`, `valor: Decimal` |
| Valles / cercanía al umbral | dentro de la respuesta de impactos (`valles_ajustada`) o `service.valles_vigente(...)` | `service.py:641`, `valles.py:93` | `list[Valle]`: `mes`, `caja`, `distancia_al_umbral`, `meses_para_prepararse`, `causas` |
| Estado por mes (para "mes de quiebre") | `MesProyeccion.estado ∈ {ok,critico,negativo}` en `ajustada.meses[]` | `motor.py:624` | flag por mes |
| Re-simulación con params modificados | `proyeccion.service.proyectar_preview(*, campos, escenario, mes_inicio, horizonte_meses)` | `service.py:582` | proyección real (motor) sobre `ParametrosProyeccion` propuesto (no persistido) |
| Parámetros vigentes (para el override de motos) | `parametros_proyeccion.service.obtener_vigente()` | `parametros_proyeccion/service.py:22` | `ParametrosProyeccion` (incl. `motos_base`, `rampa_unidades`, `caja_minima`) |

**El caso de la bodega, mapeado:**
- Q1 "impacto en flujo" → `proyectar_impactos([Ajuste("Arriendo bodega","gasto","absoluto",Decimal("20000000"),"2026-09",None)])` → `delta_por_mes` + `base`/`ajustada`.
- Q2 "cuándo sin caja" → escanear `ajustada.meses[]` por el primer `estado != "ok"` (umbral) y el primer `estado == "negativo"` (sin efectivo). *(Ver §8 Trampa: NO usar `runway_meses` para esto.)*
- Q3 "cuántas motos de más" → **solver nuevo** (§5).

## 5. Lo NUEVO que se construye (aditivo; `motor.py` cero diffs)

### 5.1 Solver de unidades — `proyeccion/solvers.py` (o `proyeccion/solver_unidades.py`)
Nuevo solver que responde "¿cuántas motos de más por mes para no cruzar el umbral, dado un ajuste?".
- **Firma propuesta:** `resolver_unidades_para_umbral(*, ajustes: Sequence[Ajuste], caja_minima: Decimal, escenario, mes_inicio, horizonte_meses, colchon: Decimal = Decimal("0")) -> UnidadesResultado`.
- **Algoritmo:** bisección sobre `N` = unidades extra **uniformes por mes** (entero ≥ 0). Interpretación de "cuántas motos de más": `N` se suma a `motos_base` (extra parejo todos los meses) — es lo más simple y lo que el CEO quiere decir; `rampa_unidades` (meses puntuales) queda para una variante futura, no para esta rebanada. Cada iteración: `ParametrosProyeccion` vigente → `campos` con `motos_base + N` → `proyectar_preview(campos=…)` → aplicar los `ajustes` (la bodega) → medir el `piso`. Encontrar el **mínimo N** con `piso ≥ caja_minima + colchon`. Reusar el patrón de bisección de `solvers.py` (`_min_valor_que_cumple`, `solvers.py:92`). **Operar sobre objetos `ResultadoProyeccion`** (vía el camino interno tipo `service._resultado_con`, `service.py:425`), no sobre el JSON serializado, porque `aplicar_impactos` recibe el objeto, no el dict.
- **Devuelve** `UnidadesResultado(unidades_extra: int, alcanzable: bool, piso_resultante: Decimal, motos_base: int, meta: Decimal)`. `alcanzable=False` si ni con un tope razonable de unidades se logra (abstención honesta: "no alcanzas ni vendiendo X más").
- **Decisión (aprobada):** **exacto** (re-simulación real por el motor, con mora/cartera/GPS/Auteco), **no** una regla de tres. El coste (~40 previews) es aceptable.
- **Nota de fidelidad:** un `Ajuste` es efecto de caja directo (no recomputa cartera/mora); las **unidades** sí re-simulan el motor. La combinación (unidades por preview + bodega por impacto) es la correcta: el cambio de unidades fluye por el motor, la bodega es un egreso directo encima.

### 5.2 Herramientas nuevas de FABS (parametrizadas) — `app/cfo/agente/tools.py` + `app/cfo/calc/escenario.py`
Hoy las tools son de cero argumentos. Se agregan **tools con parámetros** (primera vez) al `DISPATCH`/`TOOLS_SCHEMA`:
- **`impacto_escenario`** — input: `{ naturaleza: "gasto"|"ingreso", monto: string(COP), mes_inicio: "YYYY-MM", mes_fin?: "YYYY-MM" }`. Llama a `proyectar_impactos` + escanea el mes de quiebre. Devuelve **varios** `ResultadoCFO` con nombres de concepto claros (ver §6).
- **`motos_para_evitar_umbral`** — input: el mismo escenario. Llama al solver §5.1. Devuelve `ResultadoCFO` de `unidades_extra` (+ `piso_resultante`, `alcanzable`).
- El **dispatcher sigue cerrado** (tool desconocida = error, nunca se inventa). El `input_schema` valida estricto (`additionalProperties:false`); `monto` viaja como **string** y se parsea a `Decimal` (regla 1) con error explícito si es inválido — mismo patrón que `AjusteBody` (`proyeccion/router.py:113`).

### 5.3 Extensión de citación multi-valor — `app/cfo/agente/` (mínima)
El núcleo ya acumula `res.resultados: list[ResultadoCFO]` y el verificador/sustituidor ya iteran esa lista casando `[[concepto]]` → `r.concepto`. El cambio:
- **Una tool puede devolver `list[ResultadoCFO]`** (varios valores nombrados) en vez de uno. El loop los agrega todos a `res.resultados` → el modelo puede citar cada uno por su nombre. (Extensión pequeña, no reescritura.)
- **Nuevas unidades citables** además de COP/meses: **`mes`** (un `YYYY-MM`, p. ej. el mes de quiebre) y **`unidades`** (un entero, p. ej. motos). `conceptos.formatear` aprende a formatear estas unidades; el verificador acepta que un token de unidad `mes`/`unidades` sustituya por su texto, y **sigue** rechazando que el modelo escriba esos valores crudos.
- **Nombres de concepto** para el caso bodega (ejemplos, cerrados por turno): `impacto_mensual`, `piso_con`, `piso_sin`, `mes_umbral_con`, `mes_umbral_sin`, `mes_sin_caja_con`, `unidades_extra`, `piso_con_unidades`. Cada uno = un `ResultadoCFO` con su `Evidencia` (fuente = la función/proyección que lo produjo; `fecha_corte`/`ref` = mes_inicio + horizonte + hash del escenario para reproducibilidad).

## 6. Contrato de datos (formas)

- **`ResultadoCFO`** (sin cambios estructurales): `concepto, valor: Money|None, unidad, disponible, evidencia, detalle`. Para esta rebanada `unidad ∈ {"COP","meses","mes","unidades"}`.
- **`impacto_escenario` devuelve** una lista de `ResultadoCFO`, p. ej.: `piso_sin` (COP), `piso_con` (COP), `mes_umbral_con` (mes), `mes_sin_caja_con` (mes|None si nunca), `impacto_mensual` (COP; el egreso mensual del ajuste, que es dato de entrada re-expresado con evidencia), y un `detalle` con la serie completa (no citable, para auditoría). Si no hay config vigente → todos `disponible=False` (abstención).
- **`motos_para_evitar_umbral` devuelve**: `unidades_extra` (unidades), `piso_con_unidades` (COP), y `alcanzable` reflejado en `disponible` (si `alcanzable=False`, `valor=None` + evidencia que explica el tope probado).
- Montos: **Decimal** en backend, **string** en el borde (regla 1). El `mes` es `YYYY-MM`. Las `unidades` son enteros.

## 7. Decisión: ancla de caja inicial (aprobada)

La proyección arranca desde `ParametrosProyeccion.caja_inicial` (hoy 704.7M, el ancla configurada). Con eso, el **impacto relativo** (cuánto baja, cuánto se adelanta el quiebre) es exacto. El **mes absoluto** de quiebre depende del nivel de arranque; si el ancla configurada no es la caja real de hoy, el mes puede correrse. **Decisión:** arrancamos con la caja **configurada** (esta rebanada) y dejamos como **fast-follow** anclar a la **caja real de hoy** (calculada desde movimientos, `caja.service.caja_diaria`, con el `caja_inicial_override` de `proyectar_vigente`). FABS **debe declarar en la evidencia** que el arranque es "caja configurada de la proyección", para que el CEO sepa de dónde parte.

## 8. Trampas del motor (del mapa; obligatorio respetarlas)

1. **`runway_meses` NO es "meses hasta el quiebre".** Es una métrica de quema promedio de todo el horizonte y puede ser `None` mientras la caja igual cruza el umbral en un mes puntual (justo lo que hace un gasto fijo nuevo antes de que el crecimiento lo absorba). El "mes de quiebre" se saca **escaneando `estado`/`valles`**, nunca de `runway_meses`.
2. **NO usar `gastos_recurrentes/` ni `metas_ingreso/`** como punto de inyección: por sus propios docstrings NO alimentan el motor (son informativos). El gasto de la bodega entra como `impactos.Ajuste`; las unidades, como override de `ParametrosProyeccion` vía `proyectar_preview`.
3. **`Ajuste` es efecto de caja directo** (no recomputa cartera/mora); las **unidades** sí re-simulan. No confundir los dos caminos.

## 9. Errores / abstención

- Sin parámetros/modelos vigentes → `proyectar_*` da 409 → FABS **se abstiene** honestamente (`disponible=False`, motivo claro), nunca inventa.
- Escenario absurdo (monto negativo, mes fuera de rango) → validación estricta en la tool → error de tool → el modelo re-pregunta o se abstiene; jamás fabrica.
- Solver `alcanzable=False` → FABS lo dice ("ni vendiendo N más te mantiene sobre el umbral"), no maquilla.
- Todo el camino de FABS mantiene el **backstop**: `consultar` nunca revienta al caller.

## 10. Pruebas (TDD)

- **Solver de unidades** (`proyeccion`): tests deterministas con params/escenario conocidos → `unidades_extra` esperado; caso `alcanzable=False`; monotonía (más unidades ⇒ piso no menor); `motor.py` no se toca.
- **Tools de FABS**: `impacto_escenario` y `motos_para_evitar_umbral` devuelven los `ResultadoCFO` nombrados correctos con `ClienteFake` (sin API key); parseo de `monto` string→Decimal; abstención sin config.
- **Citación multi-valor**: el verificador acepta tokens de las nuevas unidades (`mes`, `unidades`) y **rechaza** que el modelo escriba un número/mes/cantidad crudos; sustitución correcta de varios tokens en una respuesta; el caso "el modelo intenta escribir el impacto crudo" → rechazo.
- **Golden**: un escenario de referencia (bodega 20M) con impacto/piso/mes/motos "al peso" (extender `cfo/goldens/`).
- **Regresión**: suite completa verde; flag apagado ⇒ COMPAS byte-idéntico; `motor.py` cero diffs; `ruff` limpio.

## 11. Innegociables (repaso)

- Dinero = **Decimal**, string en el borde; **cero float** en la ruta nueva.
- **`motor.py` cero diffs**; todo aditivo (solvers/tools/calc), reusando `proyectar_*`.
- **S1**: `app/cfo/**` solo escribe `cfo_*`; las nuevas tools **leen** vía `proyeccion.service`/`parametros_proyeccion.service` (capa de servicios permitida) — nunca `app.domain.*` ni el driver directo.
- Catálogo de auditoría: si se emite algún evento nuevo (p. ej. `cfo.escenario_consultado`) requiere **CR** (regla 11). *Decisión de diseño:* **reusar `cfo.consulta`/`cfo.respuesta`** con `metadata.tipo="escenario"` — **sin eventos nuevos**, sin CR de catálogo. (Confirmar en el plan.)
- **Gate Kimi** de diseño (este doc) y de código; flag encendido en piloto ⇒ O-1 no aplica a "encender", pero sí revisar que un escenario mal calculado no llegue al CEO como cifra sin evidencia.

## 12. Autorevisión del spec (pendiente de hacer tras escribirlo)

Escaneo de placeholders, consistencia interna (formas ↔ funciones del mapa), alcance (¿una sola rebanada?), ambigüedad (nombres de concepto, unidades). Corregir inline.

---
*Rebanada 1 del inc4. Método: brainstorming (aprobado) → este spec → writing-plans → SDD → Kimi. Ante conflicto de alcance mandan `COMPAS_NORTE.md`, `CLAUDE.md`, el roadmap de FABS y este spec. `motor.py` intocable.*
