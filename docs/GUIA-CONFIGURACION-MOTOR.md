# Guía de configuración — Encender el motor de COMPAS

Hoy la caja mar–jul **ya está cargada** (1.270 movimientos). Pero las vistas de
proyección/caja salen vacías porque el **motor** aún no tiene sus supuestos y ningún
mes está "en ejecución". Esta guía es el paso a paso para **encenderlo** y empezar a
ver la utilidad: la trayectoria de caja hacia el umbral de mayo-2027.

Todo se hace en la vista **Datos** del cockpit (`/datos`). Los valores salen de tu
Excel de arquitectura (`Compas_RODDOS_Arquitectura Presupuestal Operativa.xlsx`, hojas
**Supuestos**, **Proyección ingresos**, **Presupuesto Operativo**).

---

## Paso 1 — Cargar los modelos de moto

Un renglón por modelo (Raider, Sport, Apache…). Campos:

| Campo | Qué es | De dónde |
|---|---|---|
| Nombre | Raider / Sport / Apache | — |
| Costo Auteco | costo de compra de la moto | Supuestos / Facturas Auteco |
| Precio venta con IVA | precio al cliente | Supuestos |
| Cuota inicial | enganche al colocar | Supuestos |
| Cuota semanal | valor de la cuota del crédito | Supuestos |
| Plazo (semanas) | nº de cuotas | Supuestos |
| Matrícula | costo de matrícula/SOAT por unidad | Supuestos |
| Participación mix | % de la mezcla de venta (los % suman 100%) | Proyección ingresos |

> El motor usa la mezcla (participación) y las cuotas para proyectar recaudo y cuotas
> iniciales por moto colocada.

## Paso 2 — Cargar los supuestos del motor (parámetros)

Una sola hoja de drivers (se versiona por fecha de vigencia). Grupos:

**Caja**
- **Caja inicial** — el saldo real de arranque de la proyección.
- **Caja mínima (UMBRAL)** — el piso que NO quieres cruzar (el objetivo de mayo-2027).

**Colocación**
- **Motos base** — motos colocadas por mes de partida.
- **Crecimiento mensual** — fracción mensual, **a tu criterio** (0.01 = 1%/mes;
  **es compuesto**, así que 1%/mes ≈ 12,7%/año). No hay tope.
- **Horizonte (meses)** — hasta dónde proyectar (p.ej. 60 = 5 años; cubre mayo-2027).

**Inventario Auteco**
- **Adelanto Auteco**, **Plazo (días)** (≈150), **Base (días)**, **Tasa Auteco**
  (fee ~1% mensual de la línea rotativa).

**Gastos (opex)**
- **Gastos fijos** (mensuales), **GPS por moto**, **Costo moto nueva**.

**Deuda / inversores**
- **Deuda**, **Tasa deuda**, **Mes inicio**, **Meses** (calendario del servicio).

**Cartera (riesgo)**
- **% mora**, **% recuperación**, **% default**, **% provisión** (fracciones; el
  escenario Pesimista/Base/Optimista los ajusta con un multiplicador que puedes
  sobrescribir).

> Con el Paso 1 + Paso 2, **se encienden**: Inicio (pulso), Proyecciones, Escenarios,
> Dashboards y Reportes — con tu data.

## Paso 3 — Arrancar el ciclo presupuestal de un mes

Para que **/caja** y **/presupuesto** muestren los movimientos reales, el mes debe
pasar de **"sugerido"** a **"en ejecución"**:

1. En el mes elegido (p.ej. 2026-07), genera el **sugerido** (el motor propone el
   presupuesto por rubro usando el promedio de los 3 meses reales anteriores).
2. Revisa/ajusta las líneas y **aprueba el presupuesto** → el mes queda **en
   ejecución**.
3. Reporta el **saldo de caja disponible** del mes (vista Caja) para la conciliación.

> Al aprobar, `/control` (Presupuesto) muestra ejecutado vs presupuesto del mes, y
> `/caja` habilita el reporte diario de saldos y la conciliación.

---

## Qué vas a ver al terminar

| Vista | Qué muestra |
|---|---|
| **Flujo diario** | La evolución día a día del dinero (ya funciona hoy con la data cargada) |
| **Inicio** | Pulso de caja + Realidad vs proyección (rolling forecast) |
| **Proyecciones** | La curva de caja vs el umbral hacia mayo-2027 — ¿cruzas o no? |
| **Escenarios** | Pesimista / Base / Optimista lado a lado |
| **Presupuesto** | Ejecutado vs presupuesto del mes en ejecución |

## Lo mínimo para "ver utilidad" hoy

Si quieres el resultado más rápido: **Flujo diario ya funciona** (sin configurar nada).
Para la **proyección a mayo-2027**, basta el **Paso 2** con supuestos aproximados +
al menos un modelo de moto (Paso 1). El ciclo presupuestal (Paso 3) es para el control
mensual fino y puede ir después.

> **Opción asistida:** si me pasas estos valores desde tu Excel de arquitectura, yo los
> cargo por migración (como hicimos con el flujo) y te dejo el motor encendido, en vez
> de capturarlos a mano. Tú decides.
