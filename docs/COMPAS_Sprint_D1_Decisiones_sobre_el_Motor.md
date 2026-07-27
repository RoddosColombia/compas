# Sprint D1 — "Decisiones sobre el motor": impactos presupuestales, valles de caja, techo de gasto y goal seek

**Fecha:** 2026-07-27 · **Prerequisito:** F1.1 mergeada (o al menos §0–§2 de F1.1; D1 no toca las mismas pantallas salvo Proyecciones §4)
**Antes del kickoff:** copiar este documento a `docs/COMPAS_Sprint_D1_Decisiones_sobre_el_Motor.md` en el repo (lección de F1.1).
**Decisiones del CEO que gobiernan este sprint (2026-07-27):**

1. **El motor es intocable.** `motor.py` no cambia ni una línea. Todo lo nuevo es FORMULACIÓN POSTERIOR: se aplica sobre la serie que el motor ya produjo. La paridad golden-master sigue protegiendo el núcleo.
2. Tope de horizonte queda en 180 meses.
3. **El hito no es un mes fijo: son los valles** — los meses donde la caja proyectada baja a mínimos. La app debe detectarlos, explicar por qué pasan y dar tiempo de sobra para prepararse.
4. El plan vigente y el brief se complementan: lo que el brief mejora, reemplaza; lo demás sigue.

---

## 1. Objetivo (las 4 preguntas del brief, aterrizadas)

Al cerrar D1, desde la app se responde: **(1)** cuánto puedo gastar de más este mes sin comprometer ningún valle (techo de gasto); **(2)** cómo me afecta a futuro subir o bajar un rubro desde un mes dado (impactos con vigencia); **(3)** qué valles vienen, cuándo, de cuánto y por qué (hitos automáticos); **(4)** cuánto debo vender o recortar para que ningún valle perfore (goal seek y punto de quiebre).

**Prueba de terminado (una sola):** Andrés escribe "arriendos +$3 M desde sep-2026", ve al instante la nueva curva contra la base, el valle de feb-2027 moverse y el delta del saldo final; lo guarda como escenario "Sede nueva"; pregunta cuánto tendría que vender para que ese escenario no baje de $50 M en ningún valle; y la app responde con un número — todo sin que el motor haya cambiado.

## 2. Arquitectura: la capa de impactos (backend, sin tocar el motor)

**Concepto:** un `Ajuste` es un delta declarativo sobre la serie mensual que produce el motor:

```
Ajuste = {
  nombre: str,                      # "Arriendo sede nueva"
  naturaleza: "gasto" | "ingreso",
  rubro_id: ObjectId | null,        # opcional: a qué rubro se atribuye (para trazabilidad y vistas)
  modo: "absoluto" | "porcentaje",  # $ fijos/mes o % sobre la línea del motor
  valor: Money,                     # "$3.000.000" o "0.10" (fracción, regla 1)
  mes_inicio: "YYYY-MM",
  mes_fin: "YYYY-MM" | null,        # null = hasta el final del horizonte
}
```

**Aplicación (service, post-proceso puro):** nueva función `aplicar_impactos(resultado_motor, ajustes) -> ResultadoAjustado`, en `proyeccion/impactos.py` (módulo NUEVO — ni una línea en `motor.py`):

- `naturaleza=gasto, modo=absoluto`: resta `valor` del flujo de cada mes en `[mes_inicio, mes_fin]` y re-acumula la caja de ahí en adelante.
- `naturaleza=gasto, modo=porcentaje`: el % se aplica sobre `gastos_fijos` del mes del motor.
- `naturaleza=ingreso, modo=porcentaje`: el % se aplica sobre el `neto` del mes (el ingreso post-mora del motor) — documentado en el contrato ⓘ: "aplica sobre el ingreso neto proyectado".
- `naturaleza=ingreso, modo=absoluto`: suma directa al flujo del mes.
- La caja ajustada se re-acumula con Decimal; los KPIs (piso, valles, meses bajo mínimo, capital requerido) se recalculan sobre la serie ajustada con las MISMAS definiciones del motor (reutilizar la lógica de KPIs extrayéndola a función compartida si hace falta — extraer, no duplicar).
- **Límite honesto documentado:** los ajustes son efectos directos de caja; no pasan por mora/recuperación ni recalculan cartera/GPS/inventario (eso sería tocar el motor). El contrato ⓘ de cada ajuste lo dice.

**Endpoints (compute-only, patrón preview de C3):**

- `POST /proyeccion/impactos` — body: `{ajustes: [...], escenario, horizonte_meses}` → serie ajustada + KPIs + deltas vs. base. RBAC `dashboard:leer` (es lectura con matemática encima; ⚠ VERIFICAR si prefieren `proyeccion:gestionar` por consistencia con preview).
- **Escenarios nombrados:** colección `escenarios_impacto` `{nombre, descripcion?, ajustes[], creado_por, actualizado_at, activo}` con CRUD (`proyeccion:gestionar`), auditados. Duplicar = crear desde existente. **Simular nunca escribe** (el POST de arriba es puro); guardar es explícito.
- `GET /proyeccion/valles` (§3) y `POST /proyeccion/resolver` (§5).

**Tests backend:** ajuste cero == base bit a bit; gasto absoluto mueve flujo y caja exactamente `valor × meses`; porcentaje sobre la línea correcta; vigencias respetadas (antes de `mes_inicio` idéntico a base); re-acumulación Decimal; KPIs ajustados consistentes; golden-master intacta (no se tocó el motor).

## 3. Valles de caja (los hitos, decisión CEO #3)

**Detección (en `impactos.py` o módulo hermano, sobre CUALQUIER serie — base o ajustada):** un valle es un mínimo local de la caja mensual cuya distancia al umbral lo hace relevante: `caja < umbral × factor_atencion` (factor configurable, default 3× — ⚠ afinar con datos reales) o cualquier mínimo local si perfora. Para cada valle:

```
Valle = { mes, caja, distancia_al_umbral, meses_para_prepararse,   # desde hoy
          causas: [ {concepto, monto, vs_promedio} ] }             # los 3 egresos del mes que más se apartan de su promedio móvil
```

Las `causas` salen de las columnas que el motor YA entrega por mes (pago_inventario, iva, int_deuda, gastos_fijos, adelanto, fondeo): el mes del valle se compara contra el promedio de los 6 meses vecinos y se listan los conceptos que explican el hueco — "en feb-2027 la caja cae porque coinciden el pago del lote Auteco ($X, 40 % sobre lo normal) y el IVA cuatrimestral ($Y)".

**UI — tarjeta "Valles de caja"** (en Proyecciones y en la vista de impactos): lista de valles ordenada cronológicamente, cada uno con mes, caja proyectada, cuánto falta ("faltan 7 meses — tiempo de sobra / ● quedan 2 meses"), y sus causas en lenguaje llano. Tono: `critico` si perfora, `atencion` si se acerca, `positivo` si todos los valles quedan holgados. En la CashCurve anotada, los valles se marcan (el mínimo global ya se anota; los valles secundarios ganan un punto con hover-title).

## 4. UI — pestaña "Decisiones" en Presupuesto (petición explícita del CEO)

En `/control` (Presupuesto), junto a "Por categoría / Por cuenta", tercera vista: **"Decisiones"** — layout de dos columnas heredado de C3 (Supuestos):

- **Izquierda — los ajustes:** lista editable (agregar/editar/quitar), cada uno con los campos del §2 en unidades humanas (lib/unidades ya existe: montos con separador, % como %, mes calendario). Selector de rubro opcional (catálogo existente). Botón "Restablecer" (todo a cero) y selector de **escenario nombrado** (cargar/guardar/duplicar/eliminar).
- **Derecha, sticky — el impacto** (reusar `PanelImpacto` de C3 generalizándolo, no copiándolo): BASE → CON TUS AJUSTES con piso, valle más crítico (y si se movió de mes), meses bajo mínimo, saldo final; curva de dos trazos (base tenue + ajustada); y debajo la tarjeta de **valles de la serie ajustada**.
- **Tarjeta "Techo de gasto"** (§5) fija arriba de la pestaña.
- Los casos del brief §4.5 deben poder escribirse tal cual: arriendos +$ desde mes X, salarios +% desde mes Y, publicidad +$, ingreso ±%. Test de aceptación con esos cuatro literales.
- Comparar escenarios: selector doble → las dos curvas + base en la misma gráfica (tres trazos máximo, leyenda permitida aquí — 3 series).

## 5. Solvers: techo de gasto y goal seek (formulación pura sobre la capa)

Ambos son búsquedas por bisección sobre `aplicar_impactos` (el motor corre en milisegundos; 30–40 iteraciones son gratis). En `proyeccion/solvers.py`, compute-only:

- **Techo de gasto (`POST /proyeccion/resolver` con `objetivo: "techo_gasto"`):** el mayor delta de gasto mensual uniforme, desde el mes actual, tal que **ningún valle del horizonte** baje de `umbral + colchon`. Parámetros visibles y editables (colchón default $0; horizonte de análisis default el del juicio, 60 m). Respuesta: techo mensual, valle limitante (cuál mes restringe), y con el gasto ya ejecutado del mes en curso (de la Vista Control): consumido, disponible, % — **la tarjeta del brief §4.7**, con estado `atencion/critico` si el ritmo actual lo excede. Todos los parámetros a la vista: auditable, no caja negra.
- **Goal seek:** `{variable: "ingreso_pct" | "gasto_absoluto" | <ajuste elegido>, objetivo: caja_min_en_valles >= X}` → cuánto debe valer la variable. Respuesta con el número + la serie resultante para pintarla. Cubre "¿cuánto debo vender para que ningún valle baje de 50 M?" y "¿cuánto recorto?".
- **Punto de quiebre:** para un ajuste dado, desde qué valor el primer valle perfora, y en qué mes. (Es el mismo solver con la desigualdad invertida.)
- Tests: monotonicidad (más techo → algún valle en el límite), solución verificada re-aplicando el ajuste resultante, casos sin solución (objetivo imposible → mensaje llano, no error críptico).

## 6. Qué del brief queda dónde (choque #4 resuelto — plan fusionado)

| Ítem del brief | Destino |
|---|---|
| 4.5 simulador por rubro + escenarios nombrados · 4.7 techo · 4.9 goal seek/sensibilidad/quiebre · hitos | **D1 (este sprint)** — sensibilidad ya existe (C3) |
| 4.3 flujo diario analítico (día más bajo, filtros, alertas) · 4.4 gráfica compuesta (bandas Auteco/gasto/ingreso, tooltips) | **Fase 4 fusionada** (siguiente spec: gráficos nuevos + estos) |
| 4.8b obligaciones genéricas + facturas Auteco por plazo (§7 del brief) · 4.2 ingreso proyectado editable como meta | **D2** — generaliza la lógica Auteco existente sin tocar el motor (capa de obligaciones que alimenta la de impactos) |
| 4.11 detección automática de recurrentes + clasificación 3 niveles | **D3** — sobre el histórico real (necesita más meses ejecutados para que el patrón valga) |
| 4.10 tablero configurable · export Excel/CSV | **Fase 6 ampliada** (exportes ya estaban ahí) |
| 4.8a motor de fórmulas pleno · granularidad variable · dimensiones nuevas | **Capa 5 — aparcada por decisión CEO** (motor intocable; se reevalúa con D1–D3 en producción) |
| Alertas como reglas configurables | **Fase 7** (el brief la mejora: reglas creables, no condiciones fijas) |

## 7. Para Claude Code

Orden: backend `impactos.py` + tests de paridad → valles → endpoints + escenarios CRUD → solvers → UI pestaña Decisiones (generalizar PanelImpacto extrayendo, no copiando) → tarjeta techo → integración valles en Proyecciones. Un commit por pieza; TDD como C3; `motor.py` con **cero diffs** (verificable en el PR); golden-master en verde como gate de cada commit; desviaciones documentadas en el PR; tracker `D1-DECISIONES` al cierre. ⚠ VERIFICAR al arrancar: dónde viven hoy los KPIs del resultado del motor (para extraer la función compartida), el shape exacto de Vista Control para el "gasto ejecutado del mes" de la tarjeta techo, y el factor de atención de valles contra los datos reales.

**Fuera de alcance D1:** todo lo de la tabla §6 en D2+, cualquier cambio a `motor.py`, alertas persistentes, y el PDF.
