# PROYECCIONES — el motor de ventas e ingresos por cuotas (C7)

> Destilado de `MODELO SIMULADOR 2030 FIXED.xlsm` / `… CAMBIOS CON APACHE.xlsm`
> (OneDrive `BP 26/Tecnologia/Compas/`). Aquí va la **lógica y los drivers**, NO los
> valores reales (financieros sensibles — viven en el simulador). Este es el molde de
> la capa predictiva de COMPAS (capacidad C7). Fijado: 2026-07-22.

## Qué hace el simulador (a reproducir en COMPAS)

Proyecta, mes a mes (jul-2026 → dic-2030), la **venta de motos** y el **ingreso por
cuotas**, y de ahí el **flujo de caja**, para verificar que la caja **nunca baje del
umbral mínimo requerido** (el "umbral de mayo-2027" del norte = un valor concreto de
**caja mínima requerida** en PARAMETROS).

## Hojas del simulador

| Hoja | Rol |
|---|---|
| **PARAMETROS** | Drivers editables del modelo (ver abajo) |
| **SIMULADOR** | Salida mes×mes: motos vendidas, semanas/mes, RECAUDO SIMULADO, CUOTAS INICIALES, INGRESO BRUTO, COSTO MOTOS, ESTADO |
| **Modelo Pagos** (3529×517) | **Motor de recaudo cuota-a-cuota**: cada venta abre una ventana `SIM# inicio→fin` y su calendario de cuotas semanales; el recaudo del mes = suma de las cuotas activas de todas las ventas vivas |
| **FLUJO DE CAJA** | Caja proyectada mes a mes (ingreso − egreso − pago inventario − gastos fijos…) |
| **Facturación** | Ventas/facturación por modelo |
| **INVENTARIO** | Ciclo de inventario Auteco (lotes, avances, cartera) |
| **GASTOS** | Gastos fijos/operativos por mes |
| **VALIDADOR** | Chequeos de consistencia |
| VBA (`vbaProject.bin`, 175KB) | Parte de la lógica de simulación (a reverse-engineer al construir C7) |

## Drivers (PARAMETROS) — nombres, sin valores reales

- **Por modelo (Sport, Raider, y Apache en la variante):** costo moto Auteco, precio
  venta + IVA, **cuota inicial**, **cuota semanal (plazo 18m/78 sem)**, matrícula.
- **Ciclo inventario Auteco:** motos por ciclo/lote, cupo base mensual, motos por 1er/2do
  avance, mix Sport/Raider, motos iniciales en cartera (Sport/Raider).
- **Pago inventario Auteco:** plazo de pago (días → meses de espera) + viabilidad.
- **Mora & recuperación:** escenario (pesimista/base/optimista), % mora, % recuperación,
  % default, % provisión.
- **Capital & financiación:** aporte socios, deuda inversores, **caja disponible inicio**,
  caja inicial total, tasa interés mensual, **caja mínima requerida** (= el umbral),
  gastos fijos/mes.
- **Costos operativos:** GPS por moto activa/mes, costo por moto nueva (GPS+SOAT+…),
  adelanto de cuota Auteco por moto, TRM USD/COP.

## Recaudo DISCRIMINADO (requisito CEO)

El ingreso proyectado se separa SIEMPRE en dos:
1. **Cuota inicial** (entrada al vender) — `CUOTAS INICIALES`.
2. **Recaudo del crédito** (cuotas semanales de las ventas vivas) — `RECAUDO SIMULADO`.
`INGRESO BRUTO = cuota inicial + recaudo crédito`. COMPAS debe mostrar y proyectar ambos
por separado (no mezclados).

## Cómo se conecta con lo real (ejecución)

- El simulador proyecta; COMPAS **contrasta contra la ejecución real** (recaudo real de
  `Base real ingresos` — Abonos/Recibido) → fila `REAL VS PROYECTADO`.
- Los drivers (motos/mes, precio, cuota) alimentan también el **pre-llenado del % de
  crecimiento** del presupuesto (motor del sugerido) y las **proyecciones de caja**.

## Entregable C7 en COMPAS (cuando lleguemos)

Motor de proyección que: (a) toma los drivers (editables), (b) simula ventas→recaudo
discriminado→flujo de caja mes a mes, (c) contrasta real vs proyectado, (d) marca si la
caja proyectada cruza el umbral mínimo y en qué mes, (e) sirve objetivos de venta
(¿cuántas motos/mes para no cruzar el umbral y garantizar sostenibilidad?).
