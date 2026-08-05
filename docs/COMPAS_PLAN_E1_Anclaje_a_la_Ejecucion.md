# PLAN E1 — Anclaje de la proyección a la ejecución (stage-gate de arquitectura)

**Fecha:** 2026-08-04 · **Naturaleza:** backend (tercera capa post-motor) + frontend ·
**Estado:** PLAN para gate de arquitectura (Kimi + CEO) — **sin una línea de código hasta el GO del plan**.
**Fuentes:** I-PLAN `docs/COMPAS_Sprint_E1_Anclaje_a_la_Ejecucion.md` · spec de ejecución
`docs/COMPAS_SPEC_EJECUCION_E2_E1.md` (Parte V, B1–B13) · decisiones del CEO §10 del I-PLAN + **D-08**.

> **Regla de oro del plan:** el motor no se toca (R0), el golden no se regenera, la compuerta IVA sigue
> apagada, el catálogo de eventos no crece, y **nada se adivina**: los rubros ambiguos salen en
> `sin_mapear` y se reportan. El anclaje es la VERDAD (no es parametrizable por el usuario) y vive en la
> capa de servicio, como sus hermanas D1/D2.

---

## 0. Cambio de decisión que este plan incorpora (D-08 supersede el kickoff)

El kickoff (I-PLAN §10, 2026-08-02) eligió **Regla B (solo ejecutado)** para el mes en curso. La
instrucción vigente del CEO (**D-08**) cambia a **Regla A**: `ejecutado + max(0, definido − ejecutado)`.
**Este plan implementa Regla A** y deja constancia de que D-08 reemplaza la decisión 4 del kickoff. La
Regla B queda como interruptor futuro fuera de alcance (YAGNI).

---

## 1. Jerarquía de anclaje (sin desviarse)

Para cada mes del horizonte, la serie se arma con la **mejor fuente disponible**. El estado lo da
`MesControl.estado`; el ejecutado y el definido, `control.service` (por grupo/rubro); el ingreso real,
las transacciones de INGRESO del mes.

| Estado del mes | Gasto y costo | Ingreso |
|---|---|---|
| **Cerrado** | Ejecutado real del libro (transacciones del mes, mapeadas a concepto) | Real recaudado |
| **En ejecución** | **Regla A (D-08):** `ejecutado + max(0, definido − ejecutado)` por concepto | Proyectado del motor |
| **Futuro con presupuesto** (`definido`) | El presupuesto **definido vigente** | Proyectado del motor |
| **Futuro sin presupuesto** | El **motor paramétrico** (como hoy) | Proyectado del motor |

**Propiedad viva:** cada mes que cierra empuja su realidad a la serie y **los meses siguientes se
re-acumulan desde ahí** — no solo la caja inicial (que ya se re-ancla hoy vía COCK-09), sino las líneas
de gasto/costo/ingreso. Re-acumulación con `impactos.reacumular` (misma mecánica de caja del motor; no
se reimplementa).

**Auteco SIEMPRE por D2.** La capa E1 **no toca** `pago_inventario` ni `fondeo` de Auteco: esa vía es la
de obligaciones (D2), que **ya tiene el cronograma real en producción** (FIX-K, 9 facturas sep–dic
2026). E1 ancla el resto de conceptos; D2 sigue netizando Auteco. La precedencia (§3) evita que se pisen.

---

## 2. Exclusión de los rubros neutros — por `rubro_id`, nunca por grupo ni `es_sistema`

El set ya vive en `metas_ingreso/service.py`:

```python
RUBROS_NEUTROS_INGRESO_REAL = frozenset({
    "Reversas y devoluciones",       # FIX-B: reversas GMF, devoluciones, reembolsos
    "Tránsito Wava mes anterior",    # CR-WAVA: depósito Wava del mes previo que llega
    "Ajuste de conciliación",        # CR-WAVA: contra-asiento INGRESO de una reapertura
})
```

E1 **reutiliza ese set** (se promueve a un módulo compartido, `rubros_neutros`, para no duplicar la
constante entre `metas_ingreso` y E1 — misma verdad, un solo lugar). La exclusión se resuelve **a
`rubro_id`** (una consulta a `Rubro` por nombre → ids) y se aplica en **dos puntos**:

1. **Ingreso real** de un mes anclado (cerrado): Σ INGRESO del mes **excluyendo esos rubro_id**.
2. **Mapeo rubro→concepto**: esos rubro_id **nunca** entran a ningún concepto del motor.

Motivo de "por `rubro_id`": el nombre puede cambiar y `es_sistema`/grupo agrupan de más (barren rubros
legítimos). El id es la identidad estable — mismo criterio que FIX-B/CR-WAVA ya establecieron.

---

## 3. Relación con COCK-09 — composición, no reemplazo (se documenta en el docstring del servicio)

Hoy **COCK-09** (rolling forecast) re-ancla **solo la caja inicial** vía `caja_inicial_override` (un
escalar: el saldo de arranque del horizonte). E1 ancla **las líneas por mes** (gasto/costo/ingreso de los
meses cerrado/en-ejecución/futuro-con-presupuesto) y **re-acumula la caja hacia adelante**.

**Conviven por composición, en cantidades distintas** (no hay dos anclajes ambiguos):

- **COCK-09** fija el **punto de partida** (caja inicial del primer mes del horizonte).
- **E1** sobre-escribe **las líneas** de los meses anclados y **re-acumula** la caja desde el punto de
  partida de COCK-09 hacia adelante con `impactos.reacumular`.

Como tocan magnitudes ortogonales (un escalar de arranque vs. las series por mes), no compiten. El
docstring de la capa E1 (`ejecucion/service.py`) y de `_resultado_con` **debe** afirmar explícitamente:
*"E1 compone con COCK-09: COCK-09 ancla la caja inicial; E1 ancla las líneas de los meses cerrados/en
ejecución y re-acumula desde ahí. No hay doble anclaje."* — requisito del CEO.

---

## 4. Garantías duras (candados de merge)

- **R0 · `motor.py` cero diffs.** E1 es post-motor puro. Ni un carácter de `motor.py`.
- **Golden-master verde sin regenerar.** El test golden compara contra `simular()` del artefacto; sin
  ciclo corriendo la serie es la base bit a bit (B1) → el golden no cambia. **No se regenera.**
- **Compuerta IVA intacta y apagada.** `IVA_ALIMENTA_PROYECCION` sigue en su default; E1 no la toca.
- **El anclaje vive en la capa de servicio** (`app/proyeccion/ejecucion/`), enchufado en `_resultado_con`
  **antes** de la reconciliación D2. Ningún endpoint nuevo de cálculo; toda la app hereda la serie
  anclada (Inicio, Proyecciones, valles, techo, goal-seek, escenarios).
- **Cero eventos nuevos sin CR.** E1 **lee**; no emite eventos. Si el diseño llegara a exigir uno (no se
  prevé), **se declara ANTES** y Kimi lo registra en M-3 — nunca se inventa.
- **Precedencia declarada:** orden `motor → EJECUCIÓN (E1) → OBLIGACIONES (D2) → IMPACTOS (D1)`, y la
  ventana de reconciliación de D2 **excluye** los meses anclados por E1 (no sustituye realidad por
  proyección).

---

## 5. Criterios de aceptación — B1–B13 (spec v1.3, Parte V) + 3 adiciones del arquitecto

**Checklist B (de la spec + I-PLAN §7):**

- [ ] **B1** — Sin ciclo corriendo (ningún mes cerrado ni en ejecución) → la serie es **la base bit a
  bit**. Candado de no-regresión (== golden).
- [ ] **B2** — **Mes cerrado** → su gasto/costo en la serie **es el ejecutado real** al peso, y la caja de
  los meses siguientes se re-acumula desde ahí.
- [ ] **B3** — **Mes en ejecución** → **Regla A**: `ejecutado + max(0, definido − ejecutado)`; con
  `ejecutado > definido`, el mes vale el ejecutado (no se "des-gasta").
- [ ] **B4** — **Futuro con presupuesto** → el **definido vigente**.
- [ ] **B5** — **Futuro sin presupuesto** → el **motor paramétrico** (como hoy).
- [ ] **B6** — Invariante **`ingreso − (costo + gasto) == flujo`** al peso en **toda** la serie, incluidos
  los meses anclados.
- [ ] **B7** — **No-colisión con D2**: con facturas registradas, pagos y meses anclados **simultáneos**,
  ningún peso se cuenta dos veces (la ventana de reconciliación excluye los anclados).
- [ ] **B8** — Orden efectivo **EJECUCIÓN → OBLIGACIONES → IMPACTOS**, verificable leyendo
  `_resultado_con`.
- [ ] **B9** — **Mapeo por concepto**: Σ de los rubros mapeados a un concepto **==** el valor que ese
  concepto toma en el mes anclado (fixture del plan de cuentas real). Mapeo §10: `pago_inventario` =
  1010 + 4060 (coexisten), `fondeo` = 4030 (**reemplaza** el paramétrico), `iva` = 5060.
- [ ] **B10** — Un mes cerrado con **ejecutado anómalamente bajo no se ancla sin confirmación** (guarda
  anti-mes-mal-cargado: el riesgo más serio de E1). *Diseño propuesto en §6-P4; punto abierto marcado.*
- [ ] **B11** — La capa E1 **no** toca Auteco; la capa D2 **solo** toca Auteco (Auteco siempre vía D2/FIX-K).
- [ ] **B12** — **Todo rubro del mapeo existe en la taxonomía vigente**; los faltantes se crean por la vía
  C1 con registro (M-2). Sembrar contra rubros inexistentes es hallazgo grave. R-1/R-2 → `sin_mapear`.
- [ ] **B13** — El **mes en curso muestra su completitud** ("cargado hasta el día N") y **la fórmula** con
  la que se armó; `meses_anclados` expuesto en la respuesta para que la UI marque el origen de cada cifra.

**Adiciones del arquitecto (obligatorias):**

- [ ] **A1** — Exclusión de los **3 neutros por `rubro_id`** (nunca por grupo ni `es_sistema`), en el
  ejecutado real y en el mapeo rubro→concepto (§2).
- [ ] **A2** — **PASO 0** de verificación de datos: confirmar **cero transacciones clasificadas a rubros
  de sistema** en los meses a anclar (higiene previa; una tx a un rubro de sistema falsearía el ejecutado).
  Si las hay, se **reporta y se detiene** — no se ancla sobre datos sucios.
- [ ] **A3** — **Julio 2026 como primer mes cerrado real** con un escenario de test que lo use (**dato
  real, no idealizado**): fixture con el ejecutado real de julio (gasto ~$237,6 M del I-PLAN §1) que
  verifique B2 + B6 sobre la realidad de producción.

**Residuales parqueados (no se adivinan — I-PLAN §10):** R-1 (1010 entero a `pago_inventario` vs. repartir
con `costo_nueva`) y R-2 (4040 sin concepto) salen en `sin_mapear` y se reportan mientras el CEO no los
zanje. La arquitectura no depende de ellos.

---

## 6. Descomposición por piezas (cada una TDD: red → green → refactor)

> Un PR por pieza salvo que dos sean tan cohesionadas que separarlas cree un estado intermedio sin
> sentido. Cada PR: CI 7/7, golden verde, disclosures, gate Kimi al diff.

### P1 — Lector de ejecución por mes/concepto (`ejecucion/lectura.py`)
Sobre `control.service` (ejecutado y definido por grupo/rubro). Construye el **mapa rubro→concepto** del
§10, aplica la **exclusión de neutros por rubro_id** (§2), y devuelve por mes: `{concepto: valor}` +
`sin_mapear: [rubro…]`. Función **pura** dado el snapshot de control (testeable sin Mongo).
- **Tests:** B9 (Σ rubros == concepto, fixture plan de cuentas real), B12 (todos los rubros del mapeo
  existen), A1 (neutros excluidos por id), R-1/R-2 en `sin_mapear`.
- **Candado:** si un rubro del mapeo no existe → error ruidoso (no se siembra contra inexistentes).

### P2 — Capa de anclaje (`ejecucion/service.py`)
La jerarquía §1 con **Regla A**. Toma `ResultadoProyeccion` crudo + snapshots de control/MesControl y
**sobre-escribe las líneas** de los meses cerrado / en-ejecución / futuro-con-presupuesto; re-acumula
caja con `impactos.reacumular`. **No toca Auteco** (`pago_inventario`/`fondeo` se dejan para D2).
- **Tests:** B1 (sin ciclo → base bit a bit), B2 (cerrado → ejecutado real + re-acumulación), B3
  (Regla A, incl. ejecutado>definido), B4 (futuro con presupuesto → definido), B5 (futuro sin → motor),
  B6 (invariante), A3 (julio real).
- **Candado:** sin meses anclables → no-op bit a bit (== golden).

### P3 — Precedencia y no-colisión con D2 (`_resultado_con` + `reconciliacion.py`)
Insertar E1 **antes** de la reconciliación en `_resultado_con`; la **ventana de D2 excluye** los meses
anclados por E1. Documentar la composición con COCK-09 (§3) en los docstrings.
- **Tests:** B7 (facturas + pagos + anclados sin doble conteo), B8 (orden efectivo verificable), B11
  (E1 no toca Auteco / D2 solo Auteco).
- **Candado:** con facturas activas pero sin anclaje → idéntico a hoy (no-regresión de D2).

### P4 — Guarda B10 + PASO 0 (higiene A2)
Guarda anti-mes-mal-cargado: un mes cerrado con ejecutado anómalamente bajo respecto al definido se marca
y **no se ancla sin confirmación**. PASO 0: verificar cero txs a rubros de sistema en los meses a anclar.
- **Tests:** B10 (mes anómalo no se ancla; se reporta), A2 (tx a rubro de sistema → detiene y reporta).
- **⚠ Punto abierto de diseño (para el gate):** ¿la confirmación de B10 **es** el cierre del mes (el CEO
  ya validó la conciliación ≈0 al cerrar, FIX-J) + una marca de sospecha `cerrado_sospechoso` en
  `meses_anclados` para la UI; o se requiere una **confirmación explícita adicional** (flag nuevo en
  `MesControl`)? Propuesta: **cierre = confirmación** + marca de sospecha visible (sin flag ni evento
  nuevo). Necesita 1 línea del CEO/Kimi antes de construir P4.

### P5 — Exposición `meses_anclados` + shape de respuesta
`meses_anclados: {mes: "cerrado" | "en_ejecucion" | "presupuesto" | "cerrado_sospechoso"}` +
`sin_mapear` + completitud del mes en curso ("cargado hasta el día N"). Sin campos que rompan el shape
actual (aditivo).
- **Tests:** shape (aditivo, no rompe consumidores), B13 (completitud + fórmula), foto `GET /proyeccion`
  sin ciclo == hoy (diff vacío).

### P6 — Frontend
Marcas de origen en tabla y gráfico (real · en curso · presupuesto · proyección; sólida vs. punteada),
fila de comparación proyectado/ejecutado/desviación en el mes en curso, aviso de completitud (B13) y
frase de efecto arrastre al cerrar un mes.
- **Tests:** vitest (marcas por estado, aviso de completitud, `sin_mapear` visible), build + biome.
- **Candado:** honestidad R5 — el mes en curso muestra la fórmula, no solo el resultado; `sin_mapear`
  se avisa mientras exista.

---

## 7. Estimado y riesgos

**Estimado:** P1 ~0,5 d · P2 ~1 d · P3 ~0,5 d · P4 ~0,5 d · P5 ~0,25 d · P6 ~1 d → **~3,75 días** de
construcción tras el GO del plan (más los gates de código por PR).

**Riesgos y mitigación:**

1. **Doble conteo E1×D2** (el más serio). Mitigación: precedencia dura (§3) + B7 con los tres a la vez +
   candado "sin anclaje → D2 idéntico a hoy".
2. **Mes mal cargado infla la caja futura** (B10). Mitigación: guarda de anomalía + PASO 0; punto de
   diseño zanjado en el gate antes de P4.
3. **Regresión silenciosa del motor/golden.** Mitigación: B1 == golden sin regenerar; R0 verificado en CI
   (foto `GET /proyeccion` sin ciclo con diff vacío).
4. **Mapeo contra rubros inexistentes** (B12). Mitigación: P1 falla ruidoso; R-1/R-2 en `sin_mapear`.
5. **Ambigüedad COCK-09×E1.** Mitigación: composición documentada (§3) + test de que ambos coexisten sin
   doble anclaje.
6. **Sesgo optimista del mes en curso** — resuelto por D-08 (Regla A): el resto del presupuesto tapa los
   días no cargados; converge a puro ejecutado al cerrar.

---

## 8. Lo que este plan NO hace

Recalibrar los supuestos del motor con los actuals (aprendizaje del modelo, no anclaje — se evalúa con más
meses cerrados), F4/D3/F6/F7, y **cualquier cambio al motor**. La Regla B queda como interruptor futuro.

---

## 9. Qué necesito del gate antes de codificar

1. **GO al plan** (Kimi ≥ 9.0 + CEO).
2. **1 línea sobre B10/P4:** ¿cierre = confirmación (propuesta) o confirmación explícita adicional?
3. (Opcional, no bloquea) R-1/R-2: si el CEO ya quiere zanjarlos, entran al mapeo; si no, salen en
   `sin_mapear` y se reportan.
