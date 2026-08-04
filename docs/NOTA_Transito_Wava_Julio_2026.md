# Nota — Tránsito Wava al cierre de julio 2026

> **⚠️ ENMENDADA (2026-08-03) — CR-WAVA se construyó ANTES de E1 (reorden CEO 2026-08-02).**
> Julio **YA NO cierra "sin Wava"**: cierra **CON el tránsito declarado** (`transito_wava = 37.280.415`),
> porque el módulo CR-WAVA está en producción. Los depósitos Wava-por-julio que aterricen en agosto se
> **clasifican contra el rubro `Tránsito Wava mes anterior`** (NO son recaudo de agosto). La versión previa
> de esta nota (julio sin tránsito, depósitos = ingreso de agosto "esta única vez") queda **superada**.

**Fecha original:** 2026-08-01 · **Enmienda:** 2026-08-03 · **Decisión:** Andrés San Juan (CEO)
· **Registra:** Claude Code · **Relacionado:** `docs/COMPAS_CR-Wava_Transito_Cierre.md`,
`docs/COMPAS_IPLAN_CR-WAVA.md`

## Qué pasó (vigente tras la enmienda)

Julio 2026 **se cierra CON la funcionalidad de tránsito Wava** (CR-WAVA en producción). La caja de cierre
de julio se muestra en **dos líneas nombradas**: `Bancos` (= `R_julio`, Σ saldos bancarios conciliados) y
`Tránsito Wava` (= `$37.280.415`, declarado al confirmar el cierre), con el `Total` = Bancos + Tránsito.
El tránsito **nunca se suma dentro de un banco**.

## Monto del tránsito declarado

- **Dinero en tránsito Wava al cierre de julio 2026:** **$ 37.280.415** *(cifra real del CEO, se declara en
  el diálogo de cierre)*.
- **Caja bancaria de cierre de julio (`Bancos` = `R_julio`):** la que arroja la conciliación al confirmar.
- **Caja total de julio:** `R_julio + 37.280.415` — **ahora es un dato dentro del sistema** (línea propia
  del cierre), no un ajuste informativo externo.

## Precisión de transición (crítica — no doble contar)

Como **julio SÍ declara el tránsito**, los depósitos de Wava que aterricen en agosto son la **llegada** de
ese tránsito declarado:

- **SÍ** clasificar esos depósitos contra el rubro **`Tránsito Wava mes anterior`**. Con **CR-WAVA-2**
  (patrón real `"recibido de wava"`, decisión CEO 2026-08-03) la clasificación es **automática** en la carga y
  en `aplicar_pendientes`: un depósito Wava con remanente vivo va al rubro tránsito antes que cualquier regla.
  Antes del despliegue de CR-WAVA-2, o para depósitos que no matcheen el patrón, la whitelist del guard
  `es_sistema` permite la clasificación **manual**.
- Cada llegada **NO infla el recaudo** (`ingreso_real` los excluye por `rubro_id`) y **NO cambia la caja
  total** (bancos suben, remanente de tránsito baja, total igual). Es **reconocimiento del tránsito**, no
  recaudo de agosto ni doble conteo.
- El **remanente** (`declarado − Σ llegadas`, roll-forward, clamp en 0) rueda hasta agotarse; si al cerrar
  agosto queda remanente, la app muestra el **aviso** informativo.

## Acción

1. Merge de CR-WAVA + correr la migración `20260803_wava_transito.py` en PROD (DRY-RUN → visto → APPLY).
2. Andrés cierra julio en la app (Admin + confirmación) declarando **`transito_wava = 37.280.415`** en el
   diálogo de cierre.
3. Agosto muestra: **Bancos 665.715.578 · Tránsito 37.280.415 · Total 702.995.993**.
4. Los depósitos Wava-por-julio que lleguen en agosto se **clasifican al rubro `Tránsito Wava mes
   anterior`** — **automático** con CR-WAVA-2 desplegado (patrón `"recibido de wava"`); manual como respaldo.
