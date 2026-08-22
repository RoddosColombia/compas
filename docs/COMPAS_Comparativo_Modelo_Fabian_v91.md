# Comparativo — Modelo Financiero LoanTape v9.1 (Fabián) vs. motor de proyección de COMPAS

**Fecha:** 2026-08-17 · **Autor:** Claude Code (a pedido del CEO)
**Fuente A:** `Modelo Financiero LoanTape v9.1 - corregido_1.xlsm` (16 hojas; hoja `IVA` nueva)
**Fuente B:** `backend/app/proyeccion/motor.py`, `app/proyeccion/service.py`, `app/iva/liquidacion.py` (main `f5091ff`)

Método: lectura de las fórmulas reales del libro (no de su descripción) y contraste celda-a-función
contra el motor. Todo lo que sigue está verificado contra el archivo; donde hay cifras, salen del
propio libro o de una corrida de COMPAS contra producción.

---

## 1. Veredicto corto

El modelo v9.1 y COMPAS **coinciden en la matemática del IVA al peso** y en la estructura del flujo.
Las diferencias reales están en **cinco puntos donde v9.1 es más realista** (tope de colocación,
timing de la recuperación de mora, costo bruto de Auteco, presets de mora y fondo de IVA) y en
**cuatro donde COMPAS es más preciso** (fechas DIAN reales, descontable con facturas reales, saldo a
favor declarado, anclaje a la ejecución). Ninguno de los dos está "mal": v9.1 es un simulador de
escritorio con supuestos frescos; COMPAS es el sistema con los datos reales.

**La prueba de que ambos calculan bien lo mismo:** el IVA descontable del cuatrimestre may–ago 2026
da **$170.710.393 en v9.1** (celda `IVA!C52`) y **$170.710.393 en COMPAS** (Σ de las 9 facturas
Auteco cargadas). Cero diferencia.

---

## 2. Lo que coincide (COMPAS ya replica bien)

| Concepto | v9.1 | COMPAS | ¿Igual? |
|---|---|---|---|
| IVA generado | `ventas_con_IVA × 19/119` (`IVA!D17`) | `iva_desde_total()` | ✅ idéntico |
| IVA descontable Auteco | `compras_sin_IVA × 19 %` (`IVA!C68`) | `iva_desde_base()` / facturas | ✅ idéntico |
| IVA neto y a pagar | `neto = gen − desc`; `MAX(0, …)` (`IVA!C69`) | `liquidar()` + `neto_a_pagar` | ✅ idéntico |
| Períodos | cuatrimestres ene–abr / may–ago / sep–dic (`IVA!A28:A42`) | `Periodicidad.cuatrimestral` | ✅ idéntico |
| Saldo a favor | arrastre al siguiente período (`IVA!C9`) | arrastre + declarado | ✅ COMPAS ⊃ v9.1 |
| Mora / default | `−recaudo × %` (`FC!17`, `FC!19`) | `motor._ajustes` | ✅ idéntico |
| Provisión de cartera | `−recaudo × %` y **fuera del flujo** (`PARAMETROS!C69 = "No"`) | informativa, no toca caja | ✅ misma doctrina |
| GPS | `−motos_activas × GPS` (`FC!25`) | `gps_moto × activas` | ✅ idéntico |
| Costo por moto nueva | `−motos_mes × C48` (`FC!27`) | `costo_alistamiento_total` | ✅ idéntico |
| Intereses de deuda | `−tasa × capital` (`FC!L26`) | `tasa_deuda × deuda` | ✅ idéntico |
| Estado de caja | `NEGATIVO / CRÍTICO (< mínimo)` (`FC!40`) | `meses_bajo_minimo`, piso | ✅ idéntico |

**Nota sobre la tasa de deuda (corrige una alerta que di antes):** `PARAMETROS!C43 = 0,1157` se usa
como **tasa mensual** sobre el capital (`FC!L26 = −0,1157 × 28.527.080 = −3.300.000/mes`). No es un
error de unidades: es el pago mensual de intereses a inversionistas. El `0,1157` que hay en COMPAS
es **correcto y coherente** con el modelo. Retiro esa observación.

---

## 3. Donde v9.1 es más realista — lo que vale traer

### 3.1 Tope de colocación mensual (ALTA)
```
SIMULADOR!C10 = IF(INVENTARIO!K$23=1, 0,
                   MAX(0, MIN(ROUND($R$14*(1+$R$15)^(ROW()-9), 0), $R$16) − INVENTARIO!K9))
   R14 = 80 (base) · R15 = 1 % mensual · R16 = 150  ← TOPE de motos/mes
```
COMPAS **no tiene tope**: con 15 % mensual proyecta 10.054 motos en el mes 36. El tope es la forma
más honesta de acotar (capacidad de piso, de cupo Auteco, de gente). El tramo 2 que acabamos de
construir mitiga, pero un techo explícito es lo que hace el modelo.
→ **Propuesta:** `colocacion_max_mensual` opcional en Supuestos; el motor aplica `min(serie, tope)`.

### 3.2 Crecimiento por POTENCIA, no encadenado (MEDIA-ALTA)
v9.1: `ROUND(base × (1+g)^k)`. COMPAS: `ROUND(anterior × (1+g))` mes a mes.
El encadenado **acumula el redondeo** y crece más rápido: con base 80 y 1 %, al mes 36 la potencia
da 113 y el encadenado ~118 (+4 %); a 60 meses la brecha se abre. La potencia es la matemática
correcta.
→ **Ojo:** cambiarlo mueve el golden master (que certifica el encadenado del artefacto anterior).
Requiere tu GO explícito + regenerar el golden declarando el cambio.

### 3.3 La recuperación de mora llega un mes DESPUÉS (ALTA)
```
FC!E18 = −D17 × E7      ← la mora del mes ANTERIOR se recupera este mes
```
COMPAS la recupera en el **mismo mes** (`recuperacion = −mora × pct` dentro del mismo período).
Con mora 8 % y recuperación 65 %, COMPAS adelanta ~$0,05 de cada peso de recaudo un mes. Es una
diferencia de *timing* que aplana artificialmente los valles — justo lo que la herramienta debe
mostrar. v9.1 tiene razón: la mora es diferimiento, no pérdida (`PARAMETROS!D70`).
→ **Propuesta:** desplazar la recuperación un mes (parámetro `meses_rezago_recuperacion`, default 1).

### 3.4 El pago a Auteco es 1,2013 × el costo, no el costo (ALTA)
```
PARAMETROS!C58 = 0,95 %  (seguro Auteco sobre subtotal)
PARAMETROS!C59 = 19 %    (IVA compras Auteco)
PARAMETROS!C60 = (1+C58)×(1+C59) = 1,201305   ← factor bruto a pagar
```
COMPAS programa el pago de inventario con el **costo neto** (`costo_moto`), sin seguro ni IVA. Es
decir **subestima ~20 % el egreso de inventario**. (El IVA vuelve luego como descontable, pero la
plata sale primero — y eso es exactamente lo que un flujo de caja debe capturar.)
→ **Propuesta:** `pct_seguro_auteco` + `pct_iva_compras` en Supuestos; el pago de lote usa el factor.
**Es probablemente la corrección de mayor impacto en caja de toda la lista.**

### 3.5 Presets de escenario obsoletos en COMPAS (ALTA)
| | v9.1 (`PARAMETROS!C29:C34`) | COMPAS (`PRESETS_ESCENARIO`) |
|---|---|---|
| Pesimista | mora **14 %** · recup **50 %** | 6 % · 30 % |
| Base | mora **7 %** · recup **70 %** | 3 % · 40 % |
| Optimista | mora **4 %** · recup **90 %** | 1,5 % · 60 % |
| % default | 3 % | 3 % ✅ |
| % provisión | **5 %** | 2 % (en prod) |

Los presets de COMPAS quedaron de una versión vieja del modelo. Ahora que la mora **sí** impacta
(fix SUP-1), esto importa de verdad: tu supuesto de 8 % / 65 % está a un punto del base de Fabián
(7 % / 70 %), lo que confirma que estabas trabajando con la realidad nueva.
→ **Propuesta:** actualizar los tres presets a v9.1. Con el delta de SUP-1, tu 8 % daría
pesimista 15 % / optimista 5 %.

### 3.6 Fondo de provisión de IVA con % configurable (MEDIA)
```
IVA!C8  = 70 %                       ← % del IVA neto mensual que se reserva
IVA!D23 = MAX(0, neto_mes) × 70 %    ← provisión del mes
IVA!E25 = −E23 − IF(E22<0, MAX(0, −E22 − D24), 0)   ← flujo: reserva + exceso no cubierto
FC!36   = IVA!25                     ← y así entra al flujo de caja
```
COMPAS prefondea el **100 %** del pago repartido en partes iguales entre los meses del período
(`plan_fondo_provision`). v9.1 reserva un **% editable** del neto de cada mes y, al pagar, consume el
fondo; si no alcanza, el faltante golpea la caja ese mes. El de v9.1 es más flexible y modela el
golpe residual.
→ **Propuesta:** `pct_provision_iva` configurable (default 100 % = comportamiento actual).

### 3.7 Fondo AVAL propio / autoseguro (MEDIA)
```
PARAMETROS!C55 = 1 % del recaudo mensual → FC!33 (egreso) y FC!46 (saldo acumulado)
```
Reserva para robo/siniestro que COMPAS no modela. Con recaudo de ~$286M/mes son ~$2,9M/mes.
→ **Propuesta:** `pct_aval_recaudo` como egreso + serie de saldo del fondo.

### 3.8 Menores
- **Inventario en piso**: `motos facturadas (196) − colocadas (189) = 7` que se descuentan de la
  próxima compra ($49,4M) — `PARAMETROS!C63:C67`. COMPAS no lo modela.
- **Contingencias / ajustes manuales por mes** (`FC!44`): COMPAS lo cubre con los impactos de D1.
- **"IVA neto por moto"** (`IVA!C70 = $172.654`): métrica de decisión bonita y trivial de exponer.
- **Adelanto Auteco con interruptor por mes** (`FC!29`), en COMPAS es un parámetro fijo por moto.

---

## 4. Donde COMPAS es más preciso (no cambiar)

1. **Fechas DIAN reales por NIT** (13-may-26 / 10-sep-26 / 14-ene-27, clave `CALENDARIO_DIAN`).
   v9.1 usa "día 15 del mes" genérico y lo anota como simplificación (`IVA!A75`).
2. **IVA descontable con las facturas reales** (479 recibidas del Excel DIAN = $181,2M en may–ago),
   no solo las compras a Auteco ($170,7M). v9.1 no ve el resto de proveedores.
3. **Saldo a favor declarado** con período de aplicación (PR #92): `IVA!C9` de v9.1 es un número
   suelto en 0.
4. **Anclaje a la ejecución real** (E1) y reconciliación de obligaciones (D2): la proyección arranca
   de los meses cerrados reales, no de una caja inicial teórica.
5. Persistencia + auditoría + escenarios + solvers + valles + dos planes de pago por modelo (78/52),
   que v9.1 no tiene (usa plazo único de 78).

---

## 5. Divergencias de DATOS (no de fórmula) — requieren tu palabra

| Dato | v9.1 | COMPAS (prod) |
|---|---|---|
| Mix de modelos | Raider **60 %** · Apache **30 %** · Sport 110 **10 %** | Raider 35 % · Apache **60 %** · Sport 5 % |
| Cuota semanal Raider (78) | 179.900 | **184.900** (tu dato del 11-ago) |
| Cuota semanal Apache (78) | 224.900 | 224.900 ✅ |
| Cuota semanal Sport 110 | 154.900 | 154.900 ✅ |
| Modelos en el catálogo | 4 (incluye Sport 100 al 0 %) | 3 |
| **Mínimo de caja** | **125.000.000** | **30.000.000** |
| Gastos fijos / mes | 193.487.631 | 208.000.000 |
| % provisión cartera | 5 % | 2 % |
| Plazo de pago | 78 semanas único | 78 y **52** (PLAN-52) |

El **mix invertido** (Raider vs Apache dominante) cambia el recaudo de forma material: Apache
recauda $224.900/semana y Raider $184.900. Y el **umbral de $30M vs $125M** es la diferencia entre
que COMPAS te alerte o no.

---

## 6. Prioridad sugerida

| # | Cambio | Impacto en caja | Riesgo | Toca golden |
|---|---|---|---|---|
| 1 | Factor bruto Auteco (1,2013) en el pago de lote | **Alto** (−20 % de egreso hoy) | bajo | no |
| 2 | Tope de colocación mensual | Alto (realismo largo plazo) | bajo | no |
| 3 | Presets de mora/recuperación a v9.1 | Alto (con SUP-1 ya impactan) | bajo | no |
| 4 | Recuperación de mora con 1 mes de rezago | Medio-alto (timing de valles) | medio | **sí** |
| 5 | % de provisión de IVA configurable | Medio | bajo | no |
| 6 | Fondo AVAL 1 % del recaudo | Medio | bajo | no |
| 7 | Crecimiento por potencia en vez de encadenado | Medio | medio | **sí** |
| 8 | Inventario en piso / IVA por moto / menores | Bajo | bajo | no |

Los que "tocan golden" (4 y 7) cambian la certificación contra el artefacto: exigen tu GO explícito
y regenerar el golden declarando el cambio de semántica. Los otros seis son aditivos y se pueden
construir con el candado de "sin configurar = comportamiento idéntico", como se hizo con PLAN-52 y
el tramo 2 de crecimiento.
