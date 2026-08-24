# COMPAS — El ciclo mensual

**Estado:** contrato acordado con el CEO (2026-08-23). Manda sobre cualquier
implementación previa que lo contradiga; donde contradice una decisión anterior, se dice
explícitamente y se nombra la decisión que queda superada.

**Por qué existe:** la proyección de agosto-2026 mostró cifras que no se podían rehacer
a mano (la caja del mes no era su arranque más su flujo, y el ingreso del mes ignoraba
la mitad de la cartera). El diagnóstico mostró que las fórmulas del motor están bien —
lo que fallaba eran **las costuras**: qué dato entra, cómo se pega el mes en curso con
la realidad, y cuándo se recalcula. Este documento fija esas costuras.

> **Principio:** COMPAS es un tejido. Cada cifra en pantalla sale de una cuenta atada a
> otra cifra que también está en pantalla. Ningún componente existe "por existir".
> COMPAS **no** es un ERP contable: no hay arqueos ni conciliaciones extensas; se busca
> que las diferencias sean pequeñas por buen seguimiento, y cuando aparecen se corrigen
> a mano con rastro (decisión CEO 2026-08-23).

---

## El flujo

### Paso 0 · Arranque del mes — un solo dato duro

Entra **la disponibilidad real de efectivo con la que cerró el mes anterior**. Es el
punto de partida de la caja de toda la proyección.

- Se **hereda del cierre** del mes anterior. No se perpetúa un valor viejo: si estamos
  en agosto, la proyección arranca del efectivo real al cerrar julio, nunca del de junio.
- Es **editable**: si el saldo declarado no coincide con la ejecución presupuestal, el
  CEO puede teclearlo. No es una contradicción — es el escape de un sistema que no hace
  contabilidad. Todo override queda con rastro (quién, cuándo, por qué) en `audit_log`.
- El parámetro tecleado `caja_inicial` deja de ser la fuente por defecto: queda como
  semilla del primer mes de la historia y como valor del override.

**Fuente de verdad:** el cierre del mes anterior (saldos bancarios reales), con override
manual permitido.

### Paso 1 · El objetivo del mes — esto es lo que muestra la gráfica

El motor proyecta el mes con los **objetivos planteados**, no con lo que va pasando:

- meta de colocación del mes (motos), mezcla por modelo, planes 78/52;
- supuestos vigentes: mora (solo sobre cuotas semanales), recuperación con su rezago,
  incumplimiento, crecimiento por tramos, fondo de aval, IVA;
- **presupuesto de gasto aprobado** del mes;
- recaudo del **mes completo** de la cartera ya originada.

El mes en curso en la gráfica **es proyección pura**. Ni un peso de realidad mezclado.
Responde: *si cumplimos el objetivo, ¿cómo queda la caja?*

**Fuente de verdad:** objetivos y supuestos vigentes + el cronograma de la cartera
existente.

### Paso 2 · Durante el mes — medir precisión, sin contaminar la curva

El libro acumula lo real en paralelo. COMPAS lo muestra **aparte**, como lectura de
desviación contra el objetivo del Paso 1:

- colocaciones: llevamos X de la meta de N motos;
- ingreso: recaudado real vs. lo proyectado a la fecha;
- gasto: ejecutado real vs. el presupuesto.

Esto responde otra pregunta: **¿qué tan buenos son nuestros objetivos?** No mueve la
proyección. Es el termómetro de precisión.

**Fuente de verdad:** el libro (transacciones), contra el objetivo del Paso 1.

### Paso 3 · Cierre del mes

Se cierra la ejecución del presupuesto y quedan en firme, inmutables (regla 4):

- el **efectivo real disponible** al cierre → es el Paso 0 del mes siguiente;
- las **colocaciones reales logradas** → los créditos que de verdad existen y su
  cronograma de recaudo futuro;
- el **gasto real ejecutado** → alimenta el promedio de gasto.

**Fuente de verdad:** el cierre. De aquí en adelante el mes es historia, no proyección.

### Paso 4 · Recálculo — donde COMPAS gana precisión

El motor vuelve a proyectar todo el horizonte, partiendo de más realidad:

- **caja de arranque** = el efectivo real del cierre (Paso 0);
- **cartera viva** = los créditos realmente originados y lo que les falta pagar;
- **gasto hacia adelante** = informado por el **promedio de gasto real** de los meses
  cerrados;
- los supuestos que el CEO decida ajustar viendo la desviación del Paso 2.

El mes cerrado pasa a la curva como tramo real; de ahí en adelante es proyección. Cada
cierre acorta la distancia entre el modelo y la realidad.

### Paso 5 · Vuelve al Paso 0

Con el nuevo arranque. Este es el ciclo a afinar.

---

## El candado aritmético (atraviesa todo el flujo)

Cualquier mes de la tabla se rehace a mano con sus propias columnas:

```
caja(mes)    = caja(mes anterior) + flujo(mes)        ← SIN excepciones, tampoco el 1º
flujo(mes)   = ingreso neto + egresos                 (egresos son negativos)
ingreso neto = cuota inicial + cuotas semanales + ajuste
ajuste       = mora + recuperación + incumplimiento   (mora SOLO sobre las semanales)
```

Si una fila no cuadra con esas cuatro líneas, es un error. Se verifica con un test que
recorre **todos** los meses del horizonte, no una muestra.

**Superado:** la convención del artefacto `motor.py` — *"primer mes: caja fija (= caja
inicial); el flujo de ese mes no la mueve"*. El primer mes del horizonte acumula su
flujo como cualquier otro. La caja de arranque es un valor ANTERIOR al primer mes, no la
caja del primer mes.

---

## Regla de no-solape (cartera existente vs. objetivo del mes)

El recaudo tiene dos fuentes y **no pueden traslaparse**:

1. **Cartera ya originada** — el cronograma de SISMO. Aporta el recaudo de los créditos
   originados **hasta el cierre del mes anterior**. Del mes en curso hacia adelante trae
   el **mes completo** (cuotas pagadas + pendientes + parciales): son cuotas de créditos
   que existen, y el mes en curso es un mes completo de proyección.
2. **Objetivo del mes en curso y meses futuros** — el motor. Genera las colocaciones de
   la meta y su propio recaudo, desde cero.

Los créditos originados **dentro** del mes en curso pertenecen al objetivo del mes (los
proyecta el motor), así que la cartera existente **se corta al cierre del mes anterior**.
Sin ese corte, las motos ya colocadas del mes se contarían dos veces.

Los desembolsos (cuota 0 del cronograma) **nunca** entran al recaudo: son la cuota
inicial, y esa la aporta el motor.

---

## Qué cambia respecto de lo construido

| # | Hoy | Contrato | Decisión superada |
|---|-----|----------|-------------------|
| ① | La proyección arranca de `caja_inicial` tecleado (`704.722.003`) e ignora el cierre de julio (`665.715.578`) | Hereda del cierre; editable con rastro | — |
| ② | El mes en curso ancla el **gasto real**: `ejecutado + max(0, definido − ejecutado)` por concepto | El mes en curso muestra el **presupuesto**; el ejecutado va al Paso 2 | **D-08 / Regla A** (E1) queda solo para meses cerrados |
| ③ | La rampa del mes en curso = **remanente** hacia la meta (agosto: 35) | La rampa del mes en curso = **la meta** (agosto: 70) | La automatización de **SUP-4** |
| ④ | La carga del cronograma descarta las cuotas pagadas → agosto entra con 2 semanas (`34.992.968`) | Conserva el **mes completo** del mes en curso (`137.504.210` de cuotas semanales) | El filtro «pagada» de **SUP-4** |
| ⑤ | `gastos_fijos` es un número tecleado (`208.000.000`) | El promedio de gasto real de los meses cerrados alimenta el gasto proyectado | — (pieza nueva) |
| ⑥ | La mora se aplica al ingreso bruto (incluida la cuota inicial) | La mora, el incumplimiento y la provisión caen **solo sobre las cuotas semanales** | La base del artefacto (queda como opción editable) |

El **golden master** se conserva: cada cambio del motor entra como parámetro cuyo valor
por defecto reproduce la serie certificada, y el valor de producto (el de este contrato)
se configura como dato. El motor sigue siendo intocable en sus fórmulas.

---

## Verificación de agosto-2026 (los números del contrato)

Fuente: PROD read-only + `cronogramas (5).xlsx` (SISMO, 2026-08-19; 9.879 cuotas, 196
créditos, 1.601 pagadas · 125 parciales · 8.153 pendientes).

| Concepto | Hoy en pantalla | Con el contrato |
|---|---|---|
| Caja de arranque | `704.722.003` (tecleado, de mar–jul) | `665.715.578` (cierre real de julio) |
| Caja de agosto | `704.722.003` — no cuadra con su flujo | arranque + flujo, cuadra al peso |
| Cuotas semanales de la cartera existente | `34.992.968` (2 semanas) | `137.504.210` (mes completo) |
| Meta de colocación | 35 (remanente) | 70 (el objetivo) |
| Gasto del mes | `240.209.500` (real + resto del presupuesto) | el presupuesto aprobado |

**Contraste con la realidad (Paso 2):** el mes completo de la cartera existente más los
desembolsos reales de agosto da `196.984.210` — dentro del rango de `190–230 M` que el
CEO estimó de memoria, lo que confirma que la lectura del contrato es la correcta. Al
día 12 el libro llevaba `99.424.130,75` de ingreso y `150.673.128,72` de egreso.

---

## Orden de construcción

Cada pieza es aditiva, con TDD, y no se mezcla con la siguiente:

1. **P1 · Candado aritmético** — el test que recorre todo el horizonte verificando las
   cuatro fórmulas. Se escribe PRIMERO: es el que demuestra que el resto funciona.
2. **P2 · Arranque heredado** (①) — la proyección lee el efectivo del último cierre;
   override editable con rastro.
3. **P3 · Primer mes acumula su flujo** (candado) — quita la excepción del artefacto.
4. **P4 · Mes en curso = objetivo** (② y ③) — el mes en ejecución deja de anclar gasto
   real; la rampa vuelve a ser la meta.
5. **P5 · Cronograma del mes completo** (④) — la carga conserva pagadas y parciales del
   mes en curso, con el corte de no-solape al cierre anterior.
6. **P6 · Termómetro de desviación** (Paso 2) — colocaciones, ingreso y gasto reales
   contra el objetivo, en su propio bloque.
7. **P7 · Promedio de gasto** (⑤) — el gasto real de los meses cerrados alimenta el
   supuesto hacia adelante (sugerido y aprobado por el CEO, no impuesto).

Pendiente de definir con el CEO antes de P7: sobre cuántos meses cerrados se promedia,
y si el promedio **reemplaza** el supuesto o solo lo **sugiere** para aprobación.
