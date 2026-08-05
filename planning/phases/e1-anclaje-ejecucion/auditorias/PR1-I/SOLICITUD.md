# SOLICITUD DE AUDITORÍA — E1 PR1-I: lector de la ejecución real → conceptos del motor

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-08-05
**Plan padre:** `docs/COMPAS_PLAN_E1_Anclaje_a_la_Ejecucion.md` (pieza **P1**, §6) · **Docs contrato:** I-PLAN §10 (mapeo), spec ejecución `docs/COMPAS_SPEC_EJECUCION_E2_E1.md` Parte V (B9, B12)
**Rama / PR:** `feat/e1-p1-lectura-ejecucion` / commit `911bea2` (PR pendiente de abrir)

## Qué hace

P1 es la **primera pieza** de E1 (anclar la proyección a la ejecución real). Entrega **una sola función pura** que traduce el ejecutado por rubro (la verdad del libro) a los conceptos que proyecta el motor. **No ancla nada todavía** (eso es P2): esta capa solo MAPEA. Cambios:

1. **`backend/app/domain/rubros_neutros.py` (nuevo, 23 líneas).** Promueve la constante `RUBROS_NEUTROS_INGRESO_REAL` (los 3 neutros: *Reversas y devoluciones*, *Tránsito Wava mes anterior*, *Ajuste de conciliación*) desde `metas_ingreso/service.py` a un módulo de dominio compartido. Una verdad, un solo lugar — para que E1 y metas no dupliquen el set.
2. **`backend/app/metas_ingreso/service.py` (−13/+5).** Deja de definir la constante local y la **importa** del nuevo módulo. Cero cambio de comportamiento (mismo frozenset).
3. **`backend/app/proyeccion/ejecucion/__init__.py` (nuevo, 7 líneas)** + **`ejecucion/lectura.py` (nuevo, 132 líneas).** El lector:
   - `mapear_a_conceptos(*, rubros, valor_por_rubro_id, neutros_ids) -> ResultadoMapeo` — **función pura, sin Mongo**, determinista, `Decimal` en todo.
   - Mapeo por código del **I-PLAN §10**: `neto` ← 0110/0120/0130/0140; `pago_inventario` ← 1010 + 4060; `fondeo` ← 4030; `costo_nueva` ← 1020; `gps` ← 1030; `int_deuda` ← 4010/4020/4050; `iva` ← 5060. `gastos_fijos` = todo lo de los grupos operación/nómina/otros que **no** esté mapeado por código, **no** sea de sistema y **no** sea neutro (robusto a que la taxonomía sume rubros nuevos, p.ej. 2140).
   - **A1 — exclusión de neutros por `rubro_id`, ANTES de cualquier regla de grupo.**
   - **R-1** (parqueado): 1010 va **entero** a `pago_inventario`, no se reparte a `costo_nueva`.
   - **R-2** (parqueado): 4040 (Deudas impuestos) **no mapea** → sale en `sin_mapear` (se reporta, no se suma a nada).
   - **B12**: si un código que el mapeo referencia **no existe** en la taxonomía → `ValueError` ruidoso (no se siembra contra inexistentes).

## Cambios de valores esperados (verificados al peso)

P1 es **aditivo**: no altera ningún valor de la app existente (el motor no se toca, ningún endpoint la consume aún). El único movimiento es la promoción de una constante idéntica.

| Caso | Antes | Después |
|---|---|---|
| `RUBROS_NEUTROS_INGRESO_REAL` en metas | definida local en `metas_ingreso/service.py` | importada de `domain/rubros_neutros.py` (mismo frozenset, sin diff de valor) |
| Salida de `mapear_a_conceptos` | n/a (código nuevo) | `{concepto: Σ Decimal}` + `sin_mapear`, verificado en 5 tests |

## Semántica preservada (NO cambia en este PR)

- **R0 · `motor.py` cero diffs** — P1 no lo toca (verificable en el diff: no aparece).
- **Golden-master intacto** — P1 no entra a `_resultado_con` todavía (eso es P3); ningún consumidor la llama.
- **Compuerta IVA** — no se toca (`IVA_ALIMENTA_PROYECCION` en su default).
- **Catálogo de eventos** — P1 **lee**, no emite; catálogo sin crecer.
- **Dinero = Decimal** — toda la función opera en `Decimal`, cero `float`.
- **Metas de ingreso** — comportamiento idéntico (misma constante, ahora importada).

## Puntos a auditar con lupa

1. **Orden de la exclusión de neutros (A1) vs. la regla de grupo.** *Reversas y devoluciones* es grupo `otros` y **no** es de sistema: si no se excluyera por id **antes**, caería en `gastos_fijos`. Verificar que el `continue` por `neutros_ids` está antes de `_concepto_de`. (test `test_a1_neutros_excluidos_por_id`).
2. **Fidelidad del mapeo §10 y los residuales.** ¿1010 entero a `pago_inventario` (R-1) y 4040 a `sin_mapear` (R-2) es exactamente lo parqueado en el I-PLAN §10? ¿5060 (grupo `otros`, con código) mapea a `iva` por código y **no** cae en `gastos_fijos`?
3. **`gastos_fijos` por grupo — que no barra de más.** ¿Un rubro de sistema del grupo `otros` (p.ej. 5070 *Por clasificar*, `es_sistema=True`) queda **fuera** de `gastos_fijos`? ¿Un rubro nuevo sin código (2140 *Freelance*) **sí** entra por grupo?
4. **B12 — completitud del guard.** ¿El chequeo `set(_CONCEPTO_POR_CODIGO) - codigos_presentes` cubre **todos** los códigos referenciados? ¿Los rubros neutros sin código no lo disparan?
5. **Pureza y reporte de `sin_mapear`.** ¿Solo se reporta un rubro sin concepto si movió dinero (`valor != 0`) y no es de sistema, para no ensuciar con vacíos? ¿La función es determinista (orden de `sin_mapear` estable con `sorted`)?

## Evidencia local

- **pytest:** `backend/tests/test_e1_lectura.py` → **5 passed** en 0.07s (B9, R-1, R-2, A1, B12). Ver `EVIDENCIA.md`.
- **ruff:** `All checks passed!` sobre `ejecucion/`, `domain/rubros_neutros.py` y el test.
- **Reglas innegociables verificadas:** Decimal en todo (regla 1); `motor.py` sin tocar (R0); catálogo de eventos sin crecer (regla 11); Pydantic no aplica (función pura sobre dataclasses frozen, sin dicts sin schema).

## Cumplimiento del DoD / reglas de CLAUDE.md

- Regla 1 (dinero = Decimal): ✅ toda la aritmética en `Decimal`.
- Regla 10/motor (fórmula del motor intacta): ✅ P1 no toca el motor ni la fórmula del sugerido.
- Regla 11 (catálogo de eventos cerrado): ✅ P1 no emite eventos.
- Plan E1 §4 (garantías duras): ✅ R0, golden intacto (sin consumidor), IVA apagada, aditivo.
- TDD (CLAUDE.md): ✅ 5 tests definen el comportamiento (B9/B12/A1/R-1/R-2) antes de la implementación mínima.
