# NORTE de COMPAS — qué estamos construyendo (y qué NO)

> Documento corto y prioritario. Ante cualquier decisión de alcance, ESTO manda.
> Decisión del CEO (Andrés), reiterada varias veces. Fijado: 2026-07-22.

## Qué ES COMPAS

Un **sistema predictivo e inteligente para administrar el presupuesto mensual** de
RODDOS y **proyectar la caja**, con el fin de **tomar decisiones presupuestales**.

**Objetivo inmediato:** garantizar **superar el umbral de caja de mayo 2027**.

**Objetivos de largo plazo** (con base en la **ejecución presupuestal real** y la
administración del efectivo):
1. Organizar **proyecciones y objetivos de largo plazo**.
2. Entender **qué objetivos de venta** garantizan la **sostenibilidad** de RODDOS.
3. **Calcular con precisión la fecha de pago a proveedores**.
4. **Seguimiento constante del IVA** para trabajar en pagar **lo mínimo posible**
   (IVA cuatrimestral).
5. Mejor **presentación** de proyecciones para fondos de **deuda** e **inversión**.

## Qué NO ES

- **NO es un sistema contable.** No reproduce la contabilidad de RODDOS.
- El ciclo presupuestal (sugerido → acotar → aprobar → ejecución → cierre, Vista
  Control, conciliación) es el **CIMIENTO** que captura la ejecución real —
  **no es el objetivo**. El objetivo es la **capa predictiva** que se alimenta de él.

## Reglas de producto derivadas del norte

- **Toda la data es persistente desde el inicio** (requisito no negociable del CEO):
  la carga de movimientos entra por la app con preservación durable del original
  (S3/Object Lock). Nada de datos efímeros ni atajos que no persistan.
- **Punto de partida de datos:** abril 2026 en adelante (llegó la inversión). Cuenta
  operativa única desde abril = **Global66**; se centraliza en **Bancolombia** en
  septiembre 2026.
- Al priorizar, elegir siempre lo que acerque a **proyectar caja y decidir**
  (predicción), no lo que solo registre el pasado (contabilidad).

## El molde del valor (lo que el CEO compartió para que se entienda)

- `Dashboard Artefacto.jsx` — proyecciones; recaudo discriminado **cuota inicial vs
  cuota de crédito**.
- Excel de simulación `Flujo de pagos deudas.xlsx` (hojas Presupuesto, Proyección,
  Pagos semana, Flujo pago deudas…).
- Excel de gastos reales `Base real egresos` (categorías → rubros).
