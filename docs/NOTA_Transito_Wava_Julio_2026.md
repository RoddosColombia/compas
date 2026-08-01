# Nota — Tránsito Wava al cierre de julio 2026 (ajuste conocido)

**Fecha:** 2026-08-01 · **Autor de la decisión:** Andrés San Juan (CEO) · **Registra:** Claude Code
**Relacionado:** `docs/COMPAS_CR-Wava_Transito_Cierre.md`

## Qué pasó

Julio 2026 **se cerró sin la funcionalidad de tránsito Wava** (aún no construida; ver CR-WAVA, que va
después de E1). Por tanto, la **caja de cierre de julio refleja solo los bancos** (`R_julio` = Σ saldos
bancarios reportados y conciliados). El recaudo de julio que a la fecha de cierre **seguía en Wava por
tiempos de settlement NO está incluido** en esa caja bancaria.

## Monto del tránsito conocido

- **Dinero en tránsito Wava al cierre de julio 2026:** **$ ______________** *(pendiente: lo declara
  Andrés)*.
- **Caja bancaria de cierre de julio (`R_julio`):** la que arroja la conciliación al confirmar el cierre.
- **Caja total "económica" de julio (informativa, fuera del sistema):** `R_julio + $______` = caja
  bancaria + tránsito.

> Este monto es un **ajuste conocido documentado**, no un dato dentro del sistema: la caja del sistema
> para julio es la bancaria. Cuando exista CR-WAVA, el tránsito pasa a ser una línea propia del cierre.

## Precisión de transición (crítica — no doble contar)

Como **julio no contó el tránsito**, los depósitos de Wava que aterricen en el banco a **inicios de
agosto SÍ son ingreso de agosto, esta única vez** — es **reconocimiento tardío, no doble conteo**.

- **NO** clasificar esos depósitos de agosto contra un "tránsito" (no existe tránsito declarado para
  julio en el sistema).
- La regla *"clasificar los depósitos Wava contra el tránsito del mes anterior"* **empieza a regir con
  el PRIMER cierre que declare tránsito** — es decir, **el cierre de agosto en adelante**, ya con
  CR-WAVA en producción.

## Acción

1. Andrés cierra julio en la app (Admin + confirmación) con la caja bancaria conciliada.
2. Andrés completa el monto `$______` de esta nota.
3. Los depósitos Wava-por-julio que lleguen en agosto se dejan como **ingreso normal de agosto**
   (esta única vez).
4. CR-WAVA se construye después de E1; desde el cierre de agosto el tránsito ya se declara en el sistema.
