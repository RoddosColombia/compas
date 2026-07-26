# RUNBOOK — Carga semanal de movimientos (Fase 1: Excel curado)

Cómo cargar los movimientos de caja semana a semana desde el Excel del CEO
**`Flujo de pagos deudas.xlsx`** (hojas `Base real egresos` con columna `Categoría` +
`Base real ingresos`). Es la fuente **clasificada a mano**, alineada al Plan de Cuentas.
Todo es **idempotente**: re-correr solo agrega los movimientos nuevos (dedup por
`ID banco` nativo de Global66 / huella determinista).

> **Fase 2 (futuro):** conexión directa a SISMO para el desglose de recaudo
> (cuota inicial vs semanal). Hoy trabajamos **neto** (lo que entra a la cuenta).

## Pasos (cada semana)

1. **Actualiza el Excel** en OneDrive y **guárdalo** sobre la copia local (gitignored,
   nunca al repo — Ley 1581 / regla 12):
   ```
   docs/modelo/Flujo de pagos deudas.xlsx
   ```

2. **Exporta la URI de prod** al entorno (del inventario de secretos, nunca por argv):
   ```
   export MONGODB_URI_COMPAS="<valor de docs/INVENTARIO-SECRETOS.xlsx → MONGODB_URI_COMPAS (prod)>"
   ```

3. **Dry-run** (no escribe — muestra qué entraría + cuadre por rubro):
   ```
   FLUJO_DRYRUN=1 PYTHONUTF8=1 python migrations/20260726_carga_flujo_deudas.py \
       "docs/modelo/Flujo de pagos deudas.xlsx"
   ```

4. **Carga real** (idempotente: `nuevas=N · duplicadas=resto`):
   ```
   PYTHONUTF8=1 python migrations/20260726_carga_flujo_deudas.py \
       "docs/modelo/Flujo de pagos deudas.xlsx"
   ```

5. **¿Entraron aportes de capital de inversionistas?** Sácalos del recaudo operativo
   (van al rubro `Aportes de capital`, siguen en caja pero no inflan la operación).
   Reclasifícalos con el patrón del inversionista (los nombres NUNCA van al repo):
   ```
   APORTES_PATRONES="patron1,patron2" PYTHONUTF8=1 python <script de reclasificación>
   ```
   *(los aportes actuales — Becerra/Fabián/Paula — ya están reclasificados).*

## Reglas del proceso

- **La clasificación de egresos viene del Excel** (columna `Categoría`). COMPAS **NO
  auto-clasifica ni adivina** comercios (decisión CEO 2026-07-26).
- **Ingresos = neto** que entra a la cuenta → rubro `Recaudo` (operativo). Los aportes
  de capital se separan aparte.
- Categoría que no mapee a un rubro del Plan de Cuentas o valor/fecha inválido =
  **error reportado, jamás cargado adivinando** (regla 7).
- Meses cerrados no se re-cargan (histórico inmutable, regla 4).

## Cada carga es acción gated
Carga de datos reales → **GO del CEO + gate-waiver** en el tracker (hoja Gates),
auditoría Kimi retroactiva pendiente mientras Kimi esté ausente.
