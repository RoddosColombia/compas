# Auditoría técnico-contable — Módulo IVA del artifact de Fabián (v6)

- **Fecha:** 2026-07-24
- **Auditor:** Claude (rol: auditor técnico-contable de COMPAS; NO genera código)
- **Fuente auditada:** artifact `ce903dff-3396-4937-bea1-f20df3ca4d24` — "RODDOS · Simulador financiero · cartera de motos · MAY-26 → DIC-40 · **v6**" (pestaña **IVA**), abierto y leído en vivo el 2026-07-24.
- **Contraste:** `CLAUDE.md` (reglas RODDOS inamovibles), versión previa `docs/modelo/Dashboard Artefacto.jsx`, y estado actual del backend de COMPAS (`configuracion.py`, `modelo_moto.py`, `audit/events.py`).
- **Alcance del norte:** COMPAS es un sistema **predictivo** de caja; este módulo se juzga por cuánto ayuda a **proyectar el IVA a pagar y meterlo en la curva de caja en su fecha DIAN**, no por ser una liquidación contable oficial.

> **Nota de método / limitación de acceso (honestidad ante todo).** El artifact corre en un iframe *sandbox* de origen cruzado; el visor autónomo de claude.ai **no expone el código fuente** (no pude leer nombres internos de variables ni el cuerpo de las funciones). Por eso la **extracción verbatim de la lógica** se hace citando **el texto que el propio artifact muestra en pantalla** (encabezado del módulo + parámetros + resultados), no identificadores internos. Donde no pude ver una parte, lo digo explícitamente en vez de asumirlo. Las verificaciones "al peso" usan los valores que el artifact exhibe como parámetros del modelo.

---

## 1. Resumen de una línea

Artifact = **simulador financiero de RODDOS a 2030** con tres módulos (Simulador de caja · Deuda con inversionistas · **IVA**) que replica el LoanTape/`MODELO_SIMULADOR_2030` y, en la pestaña IVA, **proyecta la declaración y pago cuatrimestral de IVA a la DIAN a partir de las motos del escenario de ventas**, con curva mensual, fondo de provisión sugerido y consulta por cuatrimestre.

---

## 2. Extracción verbatim de la lógica de IVA

### 2.1 Enunciado del módulo (texto literal en pantalla)

> **"IVA — Declaración y pago cuatrimestral (DIAN)"**
> "Todo se recalcula con las motos del simulador. Meses **reales** (MAY–JUL-26) con facturación cerrada; el resto es proyección según tu escenario de ventas. **IVA generado = ventas c/IVA × 19%/(1+19%)**; **descontable = compras Auteco sin IVA × 19%**; el neto se paga el mes siguiente al cierre del cuatrimestre (**día 15, NIT 901012622 → dígito 2**), con **arrastre de saldo a favor**."

### 2.2 (a) IVA generado

- **Fórmula literal:** `IVA generado = ventas c/IVA × 19% / (1 + 19%)` → es una **extracción** del IVA implícito en un precio que **ya incluye IVA** (factor `0,19 / 1,19 = 0,159664`).
- **Base:** las **ventas de motos** del escenario = unidades vendidas del mes × **precio de venta con IVA por modelo** (parámetros "Precio Raider c/IVA" y "Precio Apache c/IVA" del panel de parámetros IVA; mix Apache 30%).
- **Causación:** el generado se reconoce en el mes de la **venta** de las motos (no se difiere a lo largo del recaudo de las cuotas). Correcto conceptualmente.

### 2.3 (b) IVA descontable

- **Fórmula literal:** `descontable = compras Auteco sin IVA × 19%` → toma el **costo Auteco por modelo** (declarado "sin IVA", es decir base gravable) y le aplica 19%.
- **Fuente única:** **solo compras a Auteco**. El texto no menciona ninguna otra compra deducible.
- Los costos Auteco por modelo "se toman del panel de Operación del simulador" (mismos valores del catálogo de modelos).

### 2.4 (c) Liquidación

- **Neto por cuatrimestre** = generado − descontable, con **arrastre de saldo a favor** entre cuatrimestres (declarado en el encabezado; no pude ver el detalle numérico línea a línea del arrastre en pantalla).
- **Periodicidad:** **cuatrimestral**. Etiquetas vistas: "**2026 · C2 (May–Ago)**", con mapeo fecha→cuatrimestre ("15/08/2026 cae en el 2026 · C2 (May–Ago) · PARCIAL (mixto)"). Implica C1 = ene–abr, C2 = may–ago, C3 = sep–dic.
- **Fecha de pago:** "el mes siguiente al cierre del cuatrimestre (**día 15**)". KPI "PRÓXIMO PAGO A LA DIAN: **$26 M · vence 15/09/2026 · 2026 · C2 (May–Ago)**".

### 2.5 Parámetros y constantes visibles

| Parámetro | Valor en el artifact |
|---|---|
| Tarifa IVA | **19 %** |
| % provisión mensual | **70 %** |
| Día límite DIAN | **15** (día fijo, editable) |
| Precio de venta c/IVA | por modelo (Raider / Apache), tomados del panel de Operación |
| Costo Auteco (base descontable) | por modelo, tomado del panel de Operación |
| Mix Apache | 30 % |
| Horizonte | 176 meses (MAY-26 → DIC-40) |
| Meses con dato real | **3 / 176** (MAY–JUL-26 con facturación cerrada) |

### 2.6 Supuestos que hace el artifact

- **Ventas gravadas = solo motos.** No contempla otras ventas gravadas (repuestos, accesorios, servicio de taller) para el generado.
- **Descontable = solo Auteco.** No contempla otras compras con IVA deducible (GPS, mercadeo, papelería, etc.).
- **Precio de venta y costo Auteco son "limpios" por unidad;** el IVA de intereses de financiación de la cuota no se modela aparte.
- **Todo el IVA se proyecta desde el motor de ventas** (unidades × precio/costo por modelo) — **no** desde documentos/facturas cargadas.

### 2.7 Salidas / features del módulo (verbatim de pantalla)

- KPIs: "IVA A PAGAR (HORIZONTE) $4,72 mM · 44 cuatrimestres" · "PRÓXIMO PAGO A LA DIAN $26 M" · "PROVISIÓN SUGERIDA ACUM. $3,3 mM · al 70% del IVA neto mensual" · "MESES CON DATO REAL 3/176".
- Gráfico "IVA NETO MENSUAL, PAGOS A LA DIAN Y FONDO DE PROVISIÓN ($ millones)" con series **IVA neto**, **Pago DIAN**, **Saldo fondo**.
- Panel "Consultar un cuatrimestre por fecha" (mapea una fecha a su cuatrimestre y estado real/parcial/proyectado).
- Panel "¿Cuánto se paga si se venden N motos?" (simulación de un cuatrimestre con tarifa/precios/costos actuales).
- Botón "Exportar IVA a Excel".

---

## 3. Veredicto de corrección

| # | Chequeo | Veredicto | Evidencia |
|---|---|---|---|
| 3.1 | ¿Periodicidad **cuatrimestral** (no bimestral/mensual)? | **OK** | Título "Declaración y pago **cuatrimestral**"; etiqueta "2026 · **C2 (May–Ago)**"; corte ene–abr / may–ago / sep–dic. Coincide con `CLAUDE.md`. |
| 3.2 | ¿Tarifa **19 %** sobre base correcta? | **OK** | Parámetro Tarifa = 19 %. Generado extrae IVA de precio c/IVA con `0,19/1,19`. **Verificado al peso** (§3.8). |
| 3.3 | ¿IVA como **% plano simulado** o **por documento**? | **APROX** | Es **driver-based** (unidades × precio/costo por modelo), mejor que un % plano sobre un ingreso agregado, pero **no** por factura. No hay entidad Factura. Gap vs diseño objetivo (§5). |
| 3.4 | ¿El IVA a pagar golpea la caja **en la fecha DIAN**? | **APROX / A VERIFICAR** | (a) Usa **"día 15"** del mes siguiente al cierre, no la **fecha real por dígito NIT** (13-may / 10-sep / 14-ene). Cae en el mes correcto → impacto mensual OK, fecha exacta desviada 1–5 días. (b) **No es evidente que el IVA neto se reste de la curva de caja** del simulador; en la versión previa la fórmula de egresos **no** incluía IVA. **Riesgo material — debe confirmarse** (§3.9). |
| 3.5 | ¿Maneja bien que **Auteco es autorretenedor** (no confunde ReteFuente con IVA)? | **OK** | El módulo IVA **no aplica ninguna ReteFuente**; usa Auteco solo como fuente de **IVA descontable** (compras sin IVA × 19%). No mezcla rete con IVA. |
| 3.6 | ¿**Signo** saldo a pagar vs a favor? ¿**Arrastra** saldo a favor? | **OK (declarado, no verificado línea a línea)** | Encabezado: "con **arrastre de saldo a favor**". Neto = generado − descontable; negativo ⇒ a favor que se arrastra. No pude ver el detalle numérico del arrastre en pantalla. |
| 3.7 | ¿Errores conceptuales de formulación? | **2 GAPS + 1 RIESGO** | Ver §3.10. |
| 3.8 | **Verificación al peso — generado** | **OK** | Panel "N motos": 200 motos, 30% Apache ⇒ 140 Raider + 60 Apache. "Ventas con IVA = **$1.647.000.000**" = 140 × (precio Raider c/IVA) + 60 × (precio Apache c/IVA). Cuadra exacto con los precios del panel. Generado = 1.647.000.000 × 0,19/1,19 ≈ **$262,96 M**. Extracción correcta. |
| 3.9 | **Enchufe a caja** | **NO VERIFICABLE desde lo visible** | El módulo IVA calcula y grafica la liquidación como vista propia; no encontré evidencia en pantalla de que el "Pago DIAN" se reste de la curva de **caja proyectada** del primer tab. Si no está enchufado, la caja proyectada **sobreestima** el disponible por el monto del IVA. |
| 3.10 | **Sesgos de alcance** | **Cuantificado abajo** | Descontable solo-Auteco ⇒ **sobreestima** IVA a pagar; generado solo-motos ⇒ podría **subestimar** generado. |

### Detalle §3.10 — dirección del error

- **Descontable = solo Auteco** ⇒ ignora IVA descontable de otras compras deducibles ⇒ **IVA a pagar sobreestimado** (sesgo conservador, pero incompleto). Magnitud = 19% de la base de esas otras compras; no cuantificable sin el dato, pero **no es cero**.
- **Generado = solo motos** ⇒ si RODDOS factura repuestos/accesorios/servicio con IVA, el generado está **subestimado** ⇒ IVA a pagar subestimado. Efecto de signo contrario al anterior; el neto real depende de cuál domine.
- **IVA de intereses de financiación** de la cuota: no modelado. Aproximación.
- **Analogía con la "caja negativa espuria" anterior:** aquel bug nacía de un **flujo real mal ubicado/omitido** en la caja. El riesgo §3.9 es del mismo tipo: si el pago de IVA no entra a la curva de caja en su fecha, la caja proyectada queda distorsionada (esta vez **al alza**).

---

## 4. Mejoras que aporta este artifact

### 4.1 Frente a la versión previa (`docs/modelo/Dashboard Artefacto.jsx`)

La versión previa **no tenía módulo de IVA**. El único rastro de IVA/DIAN era **un evento manual hardcodeado**: `{ mes: "JUL-26", monto: -14000000, desc: "DIAN" }` (un egreso único tecleado a mano, sin cálculo). El artifact v6 aporta, **todo nuevo**:

1. Cálculo de **IVA generado / descontable / neto** derivado del escenario de ventas.
2. **Agrupación cuatrimestral** (C1/C2/C3) y mapeo fecha→cuatrimestre.
3. **Curva mensual** de IVA neto + pagos DIAN + saldo del fondo.
4. **Próximo pago** con monto y fecha.
5. **Fondo de provisión** sugerido (reserva mensual = % del IVA neto).
6. Simulador **"¿cuánto pago si vendo N motos?"**.
7. **Export a Excel** de la liquidación.

### 4.2 Frente a lo que COMPAS tiene hoy

COMPAS ya tiene los **cimientos** pero **no** el motor de IVA (C11 = ❌ FALTA en `PROJECT.md`):

- ✅ `CALENDARIO_DIAN` **sembrado con las fechas reales exactas** (`ene_abr→2026-05-13`, `may_ago→2026-09-10`, `sep_dic→2027-01-14`) en `configuracion.py`. → **COMPAS es más preciso que el artifact en la fecha de pago** (el artifact usa "día 15" fijo).
- ✅ `ModeloMoto.precio_venta_con_iva` + `ModeloMoto.costo_auteco` (catálogo **administrable**, COCK-02) → la materia prima de generado y descontable ya está modelada y es editable sin tocar código.
- ✅ Evento de auditoría `iva.declarado` ya en el catálogo cerrado.
- ❌ **No hay liquidación cuatrimestral, ni arrastre de saldo a favor, ni enchufe a la proyección de caja.**

**Lo que vale la pena sumar a COMPAS desde el artifact (concreto):**

1. La **liquidación cuatrimestral** `generado − descontable` con **arrastre de saldo a favor**.
2. El **fondo de provisión** (reserva mensual %) para llegar con caja a la fecha DIAN — buena práctica de tesorería, muy alineada con el norte predictivo.
3. La **agregación por cuatrimestre** y el mapeo fecha→cuatrimestre (con estado real/parcial/proyectado).
4. El simulador **"¿cuánto pago si vendo N motos?"** como pieza de **Escenarios** (encaja con la idea 1 del CEO: evaluar decisiones antes de comprometerlas).
5. **Export** de la liquidación.

---

## 5. Brecha hacia el diseño objetivo (IVA por cargue de facturas)

El diseño objetivo calcula el IVA **por cargue de facturas** (aproximado a la realidad), no por driver de ventas. Falta:

### 5.1 Modelo de datos — entidad `Factura` (campos mínimos)

| Campo | Tipo | Nota |
|---|---|---|
| `tipo` | `venta` \| `compra` | eje principal (generado vs descontable) |
| `origen` | `auteco` \| `otra_compra` \| `moto` \| `repuesto` \| `servicio` … | distingue Auteco de otras compras deducibles y motos de otras ventas |
| `tercero_nombre`, `tercero_nit` | str | Auteco NIT 860024781 = **autorretenedor** (no ReteFuente; sí IVA descontable) |
| `fecha` | `YYYY-MM-DD` (Bogotá, normalizada) | define el cuatrimestre |
| `base_gravable` | **Money (Decimal)** | regla 1 (dinero = Decimal, API string) |
| `tarifa_iva` | Decimal | 0.19 general; permitir 0 / exento / excluido |
| `iva_valor` | Money | `= base × tarifa` (o extraído del total si viene c/IVA) |
| `total` | Money | base + IVA |
| `deducible` | bool | para compras: si su IVA es descontable |
| `cuatrimestre` (derivado) | `(anio, C1\|C2\|C3)` | de `fecha` |
| dedup / origen carga | — | coherente con regla 5 (índice único parcial) |

### 5.2 Derivar la liquidación cuatrimestral

```
generado_C     = Σ iva_valor  (facturas tipo=venta,  fecha ∈ C)
descontable_C  = Σ iva_valor  (facturas tipo=compra ∧ deducible, fecha ∈ C)
saldo_C        = generado_C − descontable_C
saldo_favor_ac = arrastre del cuatrimestre anterior (si saldo_{C-1} < 0)
neto_a_pagar_C = max(0, saldo_C − saldo_favor_ac)
nuevo_favor    = max(0, saldo_favor_ac − saldo_C)   # sigue arrastrando
```
Todo en `Decimal`, montos como string en la API, cálculo **solo en backend** (regla 1).

### 5.3 Enchufar el IVA a pagar a la proyección de caja

- Para cada cuatrimestre (real o proyectado), colocar un **egreso = `neto_a_pagar_C`** en la **fecha DIAN real** leída de `CALENDARIO_DIAN` por año (dígito 2: 13-may / 10-sep / 14-ene), **no "día 15"**.
- Ese egreso entra como **una fila más del flujo** en el mes de la fecha DIAN (junto a nómina, Auteco, deuda…). Así la curva de caja deja de sobreestimar el disponible.
- **Meses reales:** desde facturas cargadas. **Meses futuros:** proyectar generado/descontable desde el **motor de ventas C7** (unidades × precio/costo por modelo del catálogo `ModeloMoto`) → **puente natural** entre C11 (IVA) y C7 (proyección) + COCK-02 (modelos administrables). El artifact ya demuestra que este puente driver→IVA funciona; solo falta hacerlo por documento para los meses reales y persistirlo.

---

## 6. Recomendaciones priorizadas

> Marca de gate: **[CR+Kimi]** = toca cálculo de plata / IVA ⇒ requiere Change Request y auditoría Kimi ≥ 9.0 antes de merge (reglas 1 y 10, y política de gate crítico). **[UI]** = solo presentación, cálculo en backend (sin gate, salvo que exponga cálculo no verificado).

### P0 — bloqueantes del valor (todos **[CR+Kimi]**)

1. **Entidad `Factura` + liquidación cuatrimestral en backend** (Decimal, arrastre de saldo a favor). Cierra C11. **[CR+Kimi]**
2. **Enchufar el IVA neto como egreso en la proyección de caja en la fecha DIAN real** (`CALENDARIO_DIAN`, dígito 2) — y **verificar que hoy no se esté omitiendo** de la caja (riesgo §3.9). Sin esto la proyección miente al alza. **[CR+Kimi]**
3. **Incluir "otras compras deducibles" en el descontable** (no solo Auteco); sin esto se **sobreestima** sistemáticamente el IVA a pagar. **[CR+Kimi]**

### P1 — precisión y decisión

4. **Fondo de provisión de IVA** como capacidad de tesorería (reserva mensual % del neto). **[CR+Kimi]** (toca proyección de caja).
5. **Generado sobre todas las ventas gravadas** (repuestos/accesorios/servicio), si RODDOS las factura. **[CR+Kimi]**
6. **Simulador "¿cuánto pago si vendo N motos?"** integrado en **Escenarios** (idea 1 del CEO). Depende del motor C7. **[CR+Kimi]** (el cálculo) + **[UI]** (la vista).

### P2 — presentación

7. **Vista IVA del cockpit** (curva IVA neto / pago DIAN / fondo, próximo pago, provisión). **[UI]**
8. **Export a Excel** de la liquidación. **[UI]**
9. **Consulta fecha → cuatrimestre** con estado (real / parcial / proyectado). **[UI]**

---

## Conclusión

El módulo IVA del artifact está **conceptualmente bien en lo esencial** (cuatrimestral ✅, tarifa y extracción 19%/(1+19%) ✅ verificada al peso, no confunde autorretención de Auteco con IVA ✅, arrastra saldo a favor ✅) y es un **salto grande** frente a la versión previa (que no tenía IVA) y frente a COMPAS hoy (que tiene cimientos pero no motor). Sus límites son de **alcance y ubicación en caja**, no de fórmula: es una **proyección por driver de ventas, no por factura**; el descontable **solo cuenta Auteco** (sobreestima el IVA a pagar); usa **"día 15"** en vez de la fecha DIAN exacta (COMPAS ya tiene la fecha exacta sembrada); y **no está confirmado que el pago de IVA golpee la curva de caja** — el riesgo más importante a cerrar. La ruta correcta para COMPAS: **entidad Factura + liquidación cuatrimestral en Decimal + egreso de IVA en la fecha DIAN real, proyectando los meses futuros desde el motor C7** — todo bajo CR con gate Kimi por tocar cálculo de plata.
