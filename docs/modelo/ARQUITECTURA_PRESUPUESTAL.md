# ARQUITECTURA PRESUPUESTAL — el contrato de cuentas + motor (COMPAS)

> Destilado de DOS fuentes que se complementan (decisión CEO 2026-07-23):
> - **`Compas_RODDOS_Arquitectura Presupuestal Operativa.xlsx`** → la **ARQUITECTURA
>   de las cuentas** (autoridad de la estructura: 3 niveles, códigos, Fijo/Variable,
>   naturaleza, los 6 grupos, el motor y sus fórmulas).
> - **`Flujo de pagos deudas.xlsx`** → la **TAXONOMÍA REAL** (qué cuentas existen de
>   verdad: `Base real egresos`/`ingresos`, hoja `Presupuesto`) y las **mecánicas de
>   pago** (`Flujo pago deudas` = servicio de deuda, `Pagos semana`, `Facturas Auteco`).
>
> Aquí va la **lógica, la estructura y las fórmulas — NO las cifras** (los valores
> reales viven en los Excel/Simulador, sensibles). Mismo criterio que `MODELO.md` y
> `PROYECCIONES.md`. Ante duda de alcance manda `COMPAS_NORTE.md`. Fijado: 2026-07-23.

## 1. Plan de cuentas (3 niveles: GRUPO → RUBRO)

Cada rubro tiene **código** (jerárquico), **Tipo** (`Fijo`/`Variable` — para separar
el gasto estructural del discrecional) y **Naturaleza** (`Ingreso`/`Egreso`).
Estructura del archivo de Arquitectura; el contenido se valida contra las 32
categorías reales de `Base real egresos` y las líneas de `Proyeccion ingresos`.

| Código | Rubro | Grupo | Tipo | Naturaleza |
|---|---|---|---|---|
| **0000** | **INGRESOS OPERATIVOS** | ingresos_operativos | — | Ingreso |
| 0110 | Recaudo de cartera (cuotas) | ingresos_operativos | Variable | Ingreso |
| 0120 | Cuotas iniciales | ingresos_operativos | Variable | Ingreso |
| 0130 | RODANTE (crédito de repuestos) | ingresos_operativos | Variable | Ingreso |
| 0140 | Otros ingresos | ingresos_operativos | Variable | Ingreso |
| **1000** | **COSTO DE PRODUCTO** | costo_producto | — | Egreso |
| 1010 | Producto (inventario de motos) | costo_producto | Variable | Egreso |
| 1020 | SOAT / Matrículas | costo_producto | Variable | Egreso |
| 1030 | Seguros (Hunter) | costo_producto | Variable | Egreso |
| **2000** | **OPERACIÓN** | operacion | — | Egreso |
| 2010 | Arriendos | operacion | Fijo | Egreso |
| 2020 | Tecnología y software | operacion | Fijo | Egreso |
| 2030 | Mobiliario / planta / equipo | operacion | Variable | Egreso |
| 2040 | Servicios públicos y telecom | operacion | Fijo | Egreso |
| 2050 | Mercado y aseo | operacion | Variable | Egreso |
| 2060 | Cafetería | operacion | Variable | Egreso |
| 2070 | Transporte / peajes / combustible / parqueo | operacion | Variable | Egreso |
| 2080 | Papelería | operacion | Variable | Egreso |
| 2090 | Marketing y publicidad | operacion | Variable | Egreso |
| 2100 | Gastos de representación | operacion | Variable | Egreso |
| 2110 | Viajes corporativos | operacion | Variable | Egreso |
| 2120 | Renting | operacion | Fijo | Egreso |
| 2130 | Grúas y traslados | operacion | Variable | Egreso |
| 2140 | Freelance | operacion | Variable | Egreso |
| **3000** | **NÓMINA** | nomina | — | Egreso |
| 3010 | Sueldos empleados | nomina | Fijo | Egreso |
| 3020 | Sueldos directivos | nomina | Fijo | Egreso |
| 3030 | Bonificaciones | nomina | Variable | Egreso |
| 3040 | Beneficios Heads | nomina | Variable | Egreso |
| 3050 | Dotación empleados | nomina | Variable | Egreso |
| 3060 | Planillas nuevas | nomina | Variable | Egreso |
| 3070 | Planillas anteriores | nomina | Variable | Egreso |
| **4000** | **DEUDAS Y OBLIGACIONES** | deudas_obligaciones | — | Egreso |
| 4010 | Préstamos (socios y terceros) | deudas_obligaciones | Fijo | Egreso |
| 4020 | Deudas tarjetas de crédito | deudas_obligaciones | Fijo | Egreso |
| 4030 | Garantía cupo (Auteco) | deudas_obligaciones | Fijo | Egreso |
| 4040 | Deudas impuestos | deudas_obligaciones | Fijo | Egreso |
| 4050 | Deudas proveedores anteriores | deudas_obligaciones | Fijo | Egreso |
| 4060 | Inventario Auteco (150 días) | deudas_obligaciones | Variable | Egreso |
| **5000** | **OTROS Y VARIOS** | otros | — | Egreso |
| 5010 | Otros gastos | otros | Variable | Egreso |
| 5020 | Gastos notariales | otros | Variable | Egreso |
| 5030 | Asuntos legales | otros | Fijo | Egreso |
| 5040 | Gastos bancarios | otros | Fijo | Egreso |
| 5050 | Gastos financieros | otros | Variable | Egreso |
| 5060 | Impuestos | otros | Fijo | Egreso |
| 5070 | Por clasificar (sistema) | otros | Variable | Egreso |

**Aportes cruzados:** `2130 Grúas y traslados` y `2140 Freelance` NO estaban en el
plan del archivo de arquitectura pero SÍ aparecen en `Base real egresos` (gasto
real) → se suman. Rubros de sistema para el ciclo: `Por clasificar`, `Ajuste de
conciliación`, y el `Recaudo` histórico se subsume en `0110 Recaudo de cartera`.

### Reglas del plan de cuentas
- **Administrable (regla 9 / C1):** alta, edición y **baja lógica** (un rubro con
  historia no se borra). Se pueden **activar cuentas y grupos a medida que RODDOS
  crece** — nada hardcodeado.
- **Código** = orden jerárquico estable; el grupo es el millar (1000, 2000…).
- **Tipo Fijo/Variable** = rigor del gasto: los Fijos son el piso estructural
  (nómina, arriendos, deuda) y los Variables el discrecional/operativo. Alimenta el
  gasto fijo mensual y el `burn` del runway.

## 2. Motor de ingresos (venta de motos a plazos) — lógica, no valores

Réplica de la macro/función del **SIMULADOR 2030** (no de sus datos). El ingreso se
mide por **DOS vías separadas** (recaudo discriminado, requisito CEO):
- **Vía 1 — Recaudo de cartera (0110):** `Σ cuotas semanales activas`. Por mes:
  `ingreso_semanal_base × semanas_de_cobro_del_mes`, o cuota-a-cuota por venta viva
  (cada venta abre una ventana de `plazo_semanas`). **Semanas exactas:** se cuentan
  los días de cobro reales del mes — `INT((fin_mes − primer_día_cobro)/7) + 1`
  (p. ej. jul-2026 = 5 miércoles).
- **Vía 2 — Cuotas iniciales (0120):** `motos_originadas_mes × cuota_inicial_prom`.
- `ingreso_operativo = Vía 1 + Vía 2 + Otros (0140)`. Se muestran SIEMPRE separadas.

**Modelos de moto ADMINISTRABLES** (paralelo de C1, requisito CEO): cada modelo con
`costo Auteco · precio venta+IVA · cuota inicial · cuota semanal · plazo (semanas) ·
matrícula · mix`. Alta/edición desde la app; baja lógica. Hoy: Raider, Sport, Apache.

## 3. Flujo de caja & runway (el corazón)

`caja_final[m] = caja_inicial[m] + ingresos − egresos_operativos − servicio_deuda −
compras_inventario_Auteco`. Regla **anti-doble-conteo**: el inventario Auteco entra
una sola vez (compra a 150 días). `runway = caja_final ÷ burn_neto_promedio`.
Marca la **caja mínima requerida** (el umbral del norte) y el **mes más ajustado**;
alerta cuando la caja proyectada cruza el mínimo.

**Escenarios:** `Base / Optimista / Conservador` (selector tipo INDEX sobre los
drivers). **Horizonte configurable hasta 15 años** (180 meses; el Excel llega a 60/
dic-2030 — COMPAS lo extiende). Hitos de resumen (12/18/24/36/48/60… meses).

## 4. Servicio de deuda (del archivo de deudas)

`Flujo pago deudas`: calendario real **acreedor × mes** (`Empresa · Valor total ·
Cuota · [mes×N]`). Los acreedores (Colfenix, Irreverente, Luis Moreno, socios…)
**NO son rubros** — son el cronograma de pagos que cuelga de `4010 Préstamos` /
`4050 Deudas proveedores anteriores`. Da la **fecha exacta de pago a proveedores**
(objetivo del norte) y su impacto en la caja proyectada. → capacidad **C10**.

`Pagos semana`: la decisión operativa "¿cabe el pago?" — contra caja disponible y
contra el presupuesto de su categoría (✔ cabe / ✖ excede $X) + caja después. → **C9**
(ya construido).

## 5. Business economics + IVA

- **Economía unitaria por moto** (`Business economics RODDOS`): ingreso total del
  crédito (CI + cuota semanal × plazo), contribución bruta/neta, LTV:CAC, payback,
  y **provisión NIIF 9** (`PD × LGD × EAD`).
- **IVA cuatrimestral** (norte + Blueprint §7): IVA generado (ventas gravadas) −
  descontable (compras) = saldo a pagar (salida real de caja). Motos gravadas; SOAT/
  matrícula exentos; GPS con IVA; descontable de compras Auteco. → capacidad **C11**.

## 6. Reconciliación con lo construido (deltas a la fundación C1)

El modelo `Rubro` actual (grupo, nombre, tipo_flujo, orden, activo, es_sistema) debe
extenderse para honrar esta arquitectura:
- **+ `codigo`** (string jerárquico, p. ej. "2070").
- **+ `tipo`** enum `Fijo`/`Variable`.
- **+ grupo `ingresos_operativos`** (0000) en `RubroGrupo` — hoy no existe grupo de
  ingreso (el `Recaudo` vive en `otros`); migrar los rubros de ingreso al grupo 0000.
- **Re-seed** al plan de cuentas completo (incluye 0110-0140, 2130, 2140).
- La Vista Control y C5 (categoría×cuenta) ya leen por grupo/rubro — siguen válidas;
  ganan la dimensión Fijo/Variable para el rigor del gasto.

## 7. Fase 1 vs Fase 2 (Blueprint §1)

- **Fase 1 (hoy):** captura MANUAL de caja inicial, supuestos por modelo y
  presupuestos. Sin históricos ni integraciones. El motor proyecta desde cero.
- **Fase 2 (dormida):** actuals vivos SISMO/Alegra (real vs. proyectado → rolling
  forecast), **originación del loanbook** (`Originación Fase 2`), impuesto de renta.

## Regla de oro
La estructura de cuentas manda desde el archivo de **Arquitectura**; qué cuentas
existen de verdad y cómo se pagan, desde el de **Deudas**. El motor replica las
**fórmulas** del Simulador, nunca sus datos. Todo Decimal (string en API). Toda cifra
se carga después; el armazón no necesita datos para construirse.
