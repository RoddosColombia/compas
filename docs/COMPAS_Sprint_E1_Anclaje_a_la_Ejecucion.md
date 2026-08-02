# Sprint E1 — "Anclaje a la ejecución": la proyección deja de vivir de supuestos

**Fecha:** 2026-07-28 · **Origen:** decisión del CEO ("lo más importante de esta app") + brief §4.6
**Naturaleza:** backend (tercera capa post-motor) + frontend. **`motor.py` cero diffs** — como D1 y D2.
**Antes del kickoff:** copiar a `docs/`. Prerequisito: V1 en producción ✅.

---

## 1. El problema, con los números de hoy

| Fuente | Gasto de julio 2026 |
|---|---|
| La proyección (motor, supuesto genérico) | **$ 193,5 M** |
| El presupuesto aprobado del mes | **$ 331,7 M** |
| Lo realmente ejecutado a hoy (72 % del mes) | **$ 237,6 M** |

Tres cifras para el mismo mes, y la única que decide —la proyección— es la única que no mira la realidad. El ciclo presupuestal tiene la verdad al lado y la proyección la ignora.

**Objetivo:** que la proyección se ancle al ciclo **mes a mes y día a día**, de modo que el umbral se mida contra lo que de verdad pasó, no contra lo que se supuso en julio de 2026.

## 2. Decisiones del CEO (2026-07-28) — gobiernan este sprint

1. **Mes en ejecución → lo EJECUTADO, actualizado día a día.** La proyección del mes en curso usa el gasto real cargado, y se refresca con cada carga diaria de movimientos.
2. **Ingreso → el PROYECTADO del motor**; a principio de cada mes, el mes que cerró se actualiza con **el ingreso real logrado**. (El motor sigue mandando el ingreso futuro: es su parte más verificada.)
3. **El mapeo rubro↔concepto ya está definido** en `Compas_RODDOS_Arquitectura Presupuestal Operativa.xlsx` (hoja *Plan de Cuentas*) y en COMPAS (34 rubros con código y grupo). **No se inventa: se usa** (§4).

⚠ **Advertencia de diseño que el CEO debe zanjar (afecta la lectura, no la arquitectura).** Con la decisión 1 al pie de la letra, el **día 1 de cada mes** el gasto ejecutado es ~$0 → la proyección de ese mes se ve artificialmente buena y la caja proyectada, optimista; se corrige sola a medida que avanza el mes. Dos formas de evitar ese sesgo, ambas compatibles con "lo ejecutado, día a día":

- **(A) Ejecutado + resto del presupuesto aprobado** (recomendada): los días transcurridos valen lo real; los días que faltan valen lo aprobado que queda (`max(0, definido − ejecutado)`). Al cerrar el mes converge a puro ejecutado. Nunca miente ni en un sentido ni en el otro.
- **(B) Solo ejecutado** (literal): fiel a la instrucción, con el sesgo optimista de principio de mes. Si se elige, la UI **debe** advertirlo en el mes en curso ("gasto parcial: 21 de 31 días cargados").

**Implementar (A) por defecto, con la fórmula visible y un interruptor para (B)** si el CEO lo prefiere tras verlo. El resto del sprint no cambia con la elección.

## 3. La jerarquía de fuentes (el corazón)

Para cada mes del horizonte, la serie se arma con la **mejor fuente disponible**:

| Estado del mes | Gasto y costo | Ingreso |
|---|---|---|
| **Cerrado** | Ejecutado real (transacciones del mes) | Real recaudado |
| **En ejecución** (hoy: julio) | Ejecutado + resto aprobado (regla A) | Proyectado del motor |
| **Futuro con presupuesto aprobado** | El presupuesto aprobado | Proyectado del motor |
| **Futuro sin presupuesto** | El motor paramétrico (como hoy) | Proyectado del motor |

Y la propiedad que lo hace vivo: **cada mes que cierra empuja su realidad a la serie y los meses siguientes se recalculan desde ahí** — no solo la caja inicial (que ya se re-ancla hoy), sino la línea de gasto y costo. La calidad de la proyección pasa a depender de la disciplina de carga diaria (ver `COMPAS_Protocolo_Diario_Cargas.md`): eso es deseable y hay que decirlo en la UI.

## 4. El mapeo rubro → concepto del motor (del archivo del CEO)

Extraído de la hoja *Plan de Cuentas* (grupo → rubro → código). El reemplazo es **quirúrgico por rubro**, no por grupo, precisamente para no cruzar Auteco con la operación:

| Concepto del motor | Rubros que lo sustituyen cuando hay ejecución real |
|---|---|
| `neto` (ingreso) | 0110 Recaudo de cartera · 0120 Cuotas iniciales · 0130 RODANTE · 0140 Otros ingresos |
| `pago_inventario` (lote Auteco) | **4060 Inventario Auteco (150 días)** — "pago de facturas de moto a 150 d" |
| `fondeo` (costo del plazo) | **4030 Garantía cupo (Auteco)** — fee de la línea rotativa |
| `costo_nueva` (alistamiento) | 1020 SOAT/Matrículas · (parte de) 1010 Producto |
| `gps` (GPS mensual de cartera) | 1030 Seguros (Hunter) — "GPS/seguro por unidad" |
| `gastos_fijos` | **Todo** OPERACIÓN (2010–2120) + NÓMINA (3010–3070) + OTROS Y VARIOS (5010–5050, 5070) |
| `int_deuda` | 4010 Préstamos · 4020 Tarjetas · 4050 Proveedores anteriores |
| `iva` | 4040 Deudas impuestos · 5060 Impuestos |

**⚠ Tres ambigüedades del plan de cuentas que necesitan una línea tuya** (no las resuelvo por mi cuenta porque cambian la caja):

1. **1010 "Producto (inventario de motos)" vs. 4060 "Inventario Auteco (150 días)"** — los dos apuntan a la compra de motos a Auteco. ¿1010 es el **costo causado** (contable) y 4060 el **pago real** (caja)? Si ambos reciben movimientos de caja, hay doble conteo en tu propio plan. En junio se ejecutaron $69,0 M en "Producto": ¿eso fue pago de motos o de otra cosa?
2. **4030 "Garantía cupo (Auteco) — fee 1 % mensual"** vs. el **fondeo del motor (1,6 % sobre los días que exceden 90)** — ¿son el mismo costo con dos nombres, o dos cobros distintos que coexisten?
3. **4040 "Deudas impuestos" vs. 5060 "Impuestos" vs. el IVA del motor** — ¿cuál recibe el pago del IVA a la DIAN?

## 5. Arquitectura — la tercera capa, y el orden de aplicación

Post-motor puro, como sus hermanas. **Orden obligatorio** (importa, y hay que testearlo):

```
motor.proyectar()
   → capa EJECUCIÓN (E1)      : reemplaza meses cerrados y el mes en curso con la realidad
   → capa OBLIGACIONES (D2)   : reconcilia Auteco con facturas registradas — SOLO en meses futuros
   → capa IMPACTOS (D1)       : ajustes what-if del usuario
```

**Regla de precedencia:** en un mes ya cerrado o en ejecución **manda la ejecución real**; la reconciliación paramétrica de D2 no debe volver a tocar esos meses (sería sustituir realidad por proyección). Ajustar `reconciliacion.py` para que su ventana **excluya** los meses anclados por E1, y testear la no-colisión.

Reutilizar sin duplicar: `impactos.reacumular` (misma mecánica de caja del motor), `kpis.calcular_kpis`, y las fuentes de verdad que ya existen — `control.service` (ejecutado y definido por grupo/rubro), `MesControl` (estados del ciclo) y las transacciones de INGRESO para el ingreso real.

**Endpoint:** el anclaje no es opcional ni parametrizable por el usuario — es la verdad. Se aplica dentro de `_resultado_con`, igual que la reconciliación, de modo que **toda** la app (Inicio, Proyecciones, valles, techo, goal seek, escenarios) hereda la serie anclada sin cambios. Exponer en la respuesta: `meses_anclados: {mes: "cerrado" | "en_ejecucion" | "presupuesto"}` para que la UI lo marque.

## 6. UI — que se vea de dónde sale cada cifra

- **Tabla de Proyecciones:** los meses anclados llevan marca de origen (`real` · `en curso` · `presupuesto` · `proyección`), con el mismo patrón visual de la ventana reconciliada de V1. El mes en curso muestra además la advertencia del §2 si se elige la regla (B).
- **Gráfico:** el tramo anclado se distingue del proyectado (línea sólida vs. punteada — ya está pedido en el brief §4.6) y las barras del tramo real llevan el mismo tratamiento.
- **Fila de comparación en el mes en curso** (lo que hoy vive solo en Presupuesto): proyectado vs. ejecutado vs. desviación, para que la conexión sea evidente sin cambiar de pantalla.
- **Efecto arrastre** (brief §4.6): al cerrar un mes con desviación, decir en una frase cuánto cambió el saldo final del horizonte y el mes del valle. Con los datos de E1 es una resta.

## 7. Tests / criterio de terminado

1. **Sin ciclo corriendo** (ningún mes cerrado ni en ejecución) → la serie es **la base bit a bit**. Es el candado de no-regresión.
2. **Mes cerrado** → su gasto/costo en la serie **es el ejecutado real**, al peso, y la caja de los meses siguientes se re-acumula desde ahí.
3. **Mes en ejecución** → aplica la regla (A): ejecutado + resto aprobado; con `ejecutado > definido`, el mes vale el ejecutado (no se "des-gasta").
4. **Invariante de V1 intacto:** `ingreso − (costo + gasto) == flujo` al peso en toda la serie, incluidos los meses anclados.
5. **No-colisión con D2:** con facturas registradas Y meses anclados, ningún peso se cuenta dos veces (la ventana de reconciliación excluye los anclados).
6. **Mapeo:** la suma de los rubros mapeados a un concepto == el valor que ese concepto toma en el mes anclado (test por concepto, con fixture del plan de cuentas real).
7. `motor.py` cero diffs · golden-master verde · suites backend y frontend verdes.

## 8. Orden de ejecución

1. Resolver las 3 ambigüedades del §4 con el CEO (o dejar el rubro sin mapear y reportarlo — nunca adivinar).
2. Backend: lector de ejecución por mes/concepto (sobre `control.service`) → capa de anclaje con la jerarquía §3 → precedencia y no-colisión con D2 → exposición de `meses_anclados`.
3. Frontend: marcas de origen en tabla y gráfico → fila de comparación del mes en curso → frase de efecto arrastre.
4. Un commit por pieza, TDD, desviaciones al PR, tracker `E1-ANCLAJE`, plan maestro §4/§7.

## 9. Fuera de alcance

Recalibrar los supuestos del motor a partir de los actuals (eso es aprendizaje del modelo, no anclaje — se evalúa después, con más meses cerrados), el §7 de D2 (página Obligaciones), F4, D3, F6, F7. Y por supuesto: **ningún cambio al motor**.

## 10. Decisiones del CEO en el kickoff (2026-08-02) — resuelven §2 y §4

Vía AskUserQuestion, el CEO zanjó las 4 decisiones que gobiernan el mapeo y la lectura:

1. **`pago_inventario` = 1010 'Producto' + 4060 'Inventario Auteco (150d)'** (ambos coexisten, se suman).
2. **`fondeo` = 4030 'Garantía cupo (Auteco)'** — es el MISMO costo que el fondeo del motor con otro nombre → 4030 REEMPLAZA el fondeo paramétrico cuando hay ejecución real (no se suma).
3. **`iva` = 5060 'Impuestos'** (el pago del IVA a la DIAN cae en 5060).
4. **Mes en curso = Regla B (solo ejecutado)** — NO la regla A. El gasto del mes en ejecución vale
   únicamente lo ejecutado real cargado; a principio de mes se ve optimista por diseño. **La UI DEBE
   advertirlo** ("gasto parcial: N de M días cargados", §6) — es requisito, no opcional. (Se implementa
   B; la regla A queda como posible interruptor futuro, no en alcance ahora — YAGNI.)

### Residuales abiertos que estas decisiones dejan (E1 los PARQUEA y REPORTA — nunca adivina)

- **R-1 · 1010 en dos conceptos:** la decisión 1 manda 1010 a `pago_inventario`, pero §4 también lo
  ponía "(parte de)" en `costo_nueva`. Para NO doble-contar (la preocupación de §4.1), E1 mapea **1010
  entero a `pago_inventario`** y deja `costo_nueva` = **solo 1020** SOAT/Matrículas, y lo reporta como
  supuesto a confirmar. Pendiente 1 línea del CEO: ¿1010 entero a inventario, o se reparte con costo_nueva?
- **R-2 · 4040 'Deudas impuestos' sin concepto:** al ser `iva` solo 5060, 4040 queda sin mapear. E1 lo
  deja **sin mapear y lo reporta** (aparece en `sin_mapear`). Pendiente 1 línea: ¿4040 va a `int_deuda`,
  a `iva` junto con 5060, o se queda fuera?

Mientras R-1/R-2 no se confirmen, esos rubros salen en la respuesta bajo `sin_mapear` y NO se suman a
ningún concepto (fiel a §8.1: "dejar el rubro sin mapear y reportarlo — nunca adivinar"). La
arquitectura (lector de ejecución → anclaje → precedencia → `meses_anclados`) no depende de R-1/R-2.
