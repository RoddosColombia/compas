# Sprint V1 — "Ver el egreso": ingreso, costo y gasto visibles en Proyecciones

**Versión 2.1 · 2026-07-27** (actualizada tras la ejecución del backend de D2 y el fix del §0)
**Origen:** petición directa del CEO ("no puedo ir a ciegas") + brief §4.4
**Naturaleza:** **solo frontend.** El fix de coherencia del §0 ya fue aplicado en D2 (ver §0).

---

## 0. Prerequisito — RESUELTO ✅ (fix de coherencia de la reconciliación)

**Hallazgo original (QA Cowork):** la reconciliación aplicaba los deltas al flujo y re-acumulaba la caja, pero **no reescribía los campos por concepto** (`pago_inventario`, `fondeo`). Dentro de la ventana reconciliada, la suma de conceptos dejaba de explicar el flujo → el invariante de V1 habría fallado y la pantalla habría mostrado el **Auteco paramétrico** en vez del pago real.

**Estado:** verificado en código y **corregido en D2** (TDD rojo→verde, 3 tests nuevos, 40/40 verdes, `motor.py` cero diffs). Dentro de la ventana: `pago_inventario` = capital real, `fondeo` = interés real, 0 en meses sin pago. El fix vive en `reconciliacion.py` (capa D2 §4), **no** en `reacumular` —que D1 comparte y donde reescribir conceptos sería incorrecto—, y propaga a la API por `_serializar`.

**Consecuencia para V1: ninguna condición pendiente.** La serie que llega al frontend ya es coherente concepto-a-concepto en todo el horizonte.

## 1. La regla del sprint: tres totales, no veinte campos

```
Ingreso  −  ( Costo + Gasto )  =  Flujo del mes        ← invariante, test obligatorio
```

| Bucket | Campos del motor | Qué significa en lenguaje de negocio |
|---|---|---|
| **Ingreso** | `neto` (= bruto − mora + recuperación − default) | La plata que de verdad entra. El desglose recaudo de crédito vs. cuota inicial se conserva en el detalle expandible (requisito del NORTE) |
| **Costo** | `pago_inventario` + `fondeo` + `costo_nueva` + `adelanto` | Lo que cuesta poner la moto en la calle: **el pago del lote a Auteco** (real si hay factura registrada, proyectado si no), el costo de financiar su plazo, y el alistamiento (matrícula + GPS + SOAT) |
| **Gasto** | `gastos_fijos` + `gps` + `int_deuda` + `iva` | La operación y las obligaciones: gastos fijos, GPS mensual de la cartera activa, intereses de deuda e IVA |

✅ **Mapeo APROBADO por el CEO (2026-07-27):** el **fondeo Auteco** queda dentro de **Costo** (es costo de inventario, no gasto financiero). No re-litigar durante la implementación.

🚨 **Trampa de doble conteo (leer antes de codificar).** Tras el fix del §0, dentro de la ventana reconciliada el **interés real de las facturas ya viaja dentro de `fondeo`** — y por tanto ya está sumado en **Costo**. El campo `interes_obligaciones` de la respuesta expone **ese mismo interés**, por separado y **solo para mostrarlo** ("de los cuales interés: $X" en el hover y en la fila expandible). **Jamás sumarlo a los buckets:** si se suma, el costo queda inflado y el invariante falla.
**Test que lo ancla:** con una factura de plazo > base, `interes_obligaciones[mes]` debe ser **igual a** `|fondeo|` de ese mes (no adicional), y el invariante del §5.1 debe seguir cumpliéndose.

## 2. La gráfica

En el mismo `ChartCard` de Proyecciones, la curva de caja deja de estar sola:

- **Barras mensuales**: **ingreso hacia arriba** (tono `positivo`) y **costo + gasto apilados hacia abajo** (dos tonos distinguibles: costo más oscuro / gasto más claro — nunca solo color: leyenda + etiqueta directa).
- **Línea de caja acumulada** encima (cyan, la actual) con su **eje derecho propio** — obligatorio: la caja llega a miles de millones y las barras a cientos de millones.
- **Umbral** punteado como hoy, sobre el eje de la caja.
- **Marcar la ventana reconciliada:** los meses con **facturas reales** se distinguen visualmente de los **proyectados paramétricamente** (sombreado sutil o marca en el eje) — requisito literal del brief §7. Los datos ya vienen: `ventana_reconciliada` e `interes_obligaciones`.
- **Hover por mes:** ingreso · costo (con "de los cuales Auteco: $X", indicando real o proyectado) · gasto · flujo · caja.
- El área azul bajo la línea de caja se mantiene atenuada.
- Ventana de 18 meses por defecto; con horizontes largos, **agregar por trimestre o año**.

**Si la lectura se vuelve confusa** (barras + línea + dos ejes), la alternativa aprobada es **dos paneles alineados en el mismo eje X**: arriba la caja, abajo la composición. Decisión del implementador, con captura en el PR.

## 3. La tabla

`Mes · Motos · **Ingreso** · **Costo** · **Gasto** · Flujo · Caja · Estado`

- Montos sin centavos (política F1); flujo negativo en `critico`.
- **Fila expandible por mes**: recaudo de crédito · cuota inicial | pago lote Auteco (real/proyectado) · fondeo (con el interés de facturas cuando aplique) · alistamiento | gastos fijos · GPS · intereses de deuda · IVA.
- **Fila de totales** al pie de la ventana visible.
- Se conserva el colapso a 18 filas con "Ver los N meses completos" (F1.1).

## 4. KPI de Auteco

`KpiTileV2` en Proyecciones: **"Compromiso Auteco"** — lo que sale este mes y el próximo por lote + fondeo, con contexto "se paga con {plazo} días de plazo desde la facturación" y si son facturas registradas o proyección. Tono `atencion` si coincide con un valle.

## 5. Tests / criterio de terminado

1. **Invariante:** para cada mes, `ingreso − (costo + gasto) == flujo` al peso — incluida la ventana reconciliada.
2. **Anti-doble-conteo:** `interes_obligaciones[mes] == |fondeo[mes]|` dentro de la ventana; el interés no se suma dos veces.
3. Suma de los tres buckets == `egresos` + `neto` del motor.
4. Tabla con los tres totales sin centavos; expandible con el desglose completo.
5. Gráfica con barras + línea, dos ejes, leyenda, ventana reconciliada marcada y hover con Auteco real/proyectado.
6. Agregación por trimestre/año con horizonte largo sin romper el layout.
7. `lint + tests + build` verdes; `motor.py` sin tocar.

## 6. Estado del entorno (2026-07-27)

**En el backend de D2** (rama `feat/d2-obligaciones`, 669 tests verdes, `motor.py` cero diffs):

- Obligaciones genéricas de dos naturalezas + facturas con plazo · CRUD auditado (CR-D2, eventos 50→58).
- Calculadora con **candado de paridad** contra `inventario_auteco_mensual` (verificado al peso).
- **Reconciliación anti-doble-conteo** integrada en toda la proyección (vigente, impactos, valles, solvers) — no-op sin facturas — **con el fix de coherencia del §0**.
- Simulador de política de plazos (`POST /proyeccion/simular-plazo`, 90/120/150).
- Metas de ingreso con % de cumplimiento.
- Campos nuevos en la respuesta: `ventana_reconciliada`, `interes_obligaciones`.

**Pendiente de frontend:** este sprint (V1) + el **§7 de D2** (página Obligaciones: lista, detalle, registro de facturas, simulador UI, bloque de metas en Presupuesto).

## 7. Secuencia

1. ~~D2 backend + fix §0~~ ✅ hecho → **PR y merge** (en curso).
2. **V1 "Ver el egreso"** (este documento) — resuelve la ceguera del CEO. Sin facturas registradas aún, muestra el Auteco proyectado, que es exactamente lo que hoy no se ve. *(1 sesión)*
3. **D2 §7 frontend** (página Obligaciones + registro + simulador + metas) — activa la reconciliación de verdad; V1 ya está preparado para mostrarla marcada. *(1–2 sesiones)*
4. Luego: F4 fusionada (flujo diario analítico + gráficos nuevos), D3, F6, F7 según el plan maestro.

## 8. Fuera de alcance

Registro de facturas y simulador UI (D2 §7), flujo diario analítico (F4), y cualquier cambio de backend.
