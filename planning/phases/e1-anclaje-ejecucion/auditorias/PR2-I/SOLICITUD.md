# SOLICITUD DE AUDITORÍA — E1 PR2-I: capa de anclaje (jerarquía §1 + Regla A)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-08-06
**Plan padre:** `docs/COMPAS_PLAN_E1_Anclaje_a_la_Ejecucion.md` (pieza **P2**, §6) · **Contratos:** plan §1 (jerarquía), D-08 (Regla A), spec ejecución Parte V (B1–B6, A3)
**Rama / PR:** `feat/e1-p2-anclaje-service` (4 commits: `5de5052`, `a71a572`, `632aace`, `7ed35a2`)

## Qué hace

P2 es la capa de **anclaje** de la proyección a la ejecución real (segunda pieza de E1). Consume el lector P1 y sobre-escribe las líneas de los meses cerrado/en-ejecución/futuro-con-presupuesto, re-acumulando la caja. Incluye el **Paso 0** (fixture real de julio) y un **ajuste a P1** que el propio P2 destapó.

1. **`scripts/extract_e1_julio_2026.py` (nuevo).** Extractor READ-ONLY de PROD (reusa `control._egresos_por_rubro`, espeja la agregación para INGRESO). Vuelca el ejecutado/ingresos por rubro_id de `2026-07` a un JSON congelado. **Controles fail-loud (regla 7) ANTES de escribir:** Σ egresos == `372.200.776,84` e `ingreso_real` (excl. neutros por id) == `179.710.080,31`. Si no cuadran → `SystemExit`, no escribe. Lógica pura testeable sin Mongo (imports de `app`/Mongo perezosos).

2. **`backend/tests/fixtures/e1_julio_2026_ejecutado.json` (nuevo).** Fixture congelado (46 rubros, 30 con egreso, 2 con ingreso, 3 neutros) con cabecera: extracción, comando (URI oculta), y los 2 totales de control. El test A3 lo lee — hermético, nunca toca PROD.

3. **`backend/app/proyeccion/ejecucion/service.py` (nuevo).** `anclar(*, resultado, caja_minima, anclas, rubros, neutros_ids) -> ResultadoAjustado` — **función pura sobre snapshots**. La jerarquía del plan §1:
   - **Cerrado:** gasto/costo = ejecutado real (mapeado a concepto por P1); ingreso = `ingreso_real`.
   - **En ejecución (Regla A, D-08):** `ejecutado + max(0, definido − ejecutado)` **por concepto**; ingreso = motor (no se ancla).
   - **Futuro con presupuesto:** el `definido` vigente; ingreso = motor.
   - **Futuro sin presupuesto / mes no listado:** motor intacto.
   - Mecánica **idéntica a la reconciliación D2**: delta de flujo → `impactos.reacumular` (caja/flujo/estado) → reescritura POR CONCEPTO aparte (no dentro de `reacumular`, que D1 comparte).

4. **`backend/app/proyeccion/ejecucion/lectura.py` (−4 códigos).** Ajuste a P1 obligado por un hallazgo de B12 (ver "Cambios de valores" y "Puntos a auditar").

## Cambios de valores esperados (verificados al peso)

| Caso | Antes | Después |
|---|---|---|
| Control de julio (Σ egresos) | 372.200.786,62 (Excel del CEO) | **372.200.776,84** (realidad de Mongo, 505 tx, 2 métodos; el Excel traía +9,78 de ruido de centavos — decisión CEO 2026-08-06) |
| Mapeo P1 `_CONCEPTO_POR_CODIGO` | 13 códigos (incluía 0120/0130/0140/4060) | **9 códigos** (quitados los 4 ausentes en PROD) |
| B9 (test P1) | neto vía 0120+0140 | neto vía 0110 (único ingreso real) |
| A3 (fixture julio) | — | `neto` = 179.710.080,31; los 5 conceptos de egreso E1 == mapeo P1 al peso; B6 exacto |

## Semántica preservada (NO cambia en este PR)

- **R0 · `motor.py` cero diffs** (verificable en el diff: no aparece).
- **Golden-master intacto** (golden 48/48 verde; nadie consume `anclar` aún — se enchufa en P3).
- **Compuerta IVA** sin tocar. **Catálogo de eventos** sin crecer (P2 lee, no emite).
- **Auteco 100% en D2:** `anclar` NO toca `pago_inventario`/`fondeo`/`adelanto` (se conservan del motor). Verificado en A3.
- **Dinero = Decimal** en todo; egresos NEGATIVOS en `MesProyeccion`, mapeo POSITIVO (signo aplicado al inyectar).

## Puntos a auditar con lupa

1. **El ajuste a P1 (lo más delicado).** Al probar A3 con el fixture real, **B12 destapó una divergencia semilla↔PROD**: la taxonomía de PROD **no tiene** 0120 (Cuotas iniciales), 0130 (RODANTE), 0140 (Otros ingresos) ni 4060 (Inventario Auteco) — sí están en `rubro.py._seed()`, pero son rubros "dormidos" (los ingresos van todos a 0110 Recaudo; Auteco va por D2). Con ellos en el mapeo, **P1 disparaba `ValueError` (B12) en PROD**. Decisión CEO 2026-08-06: **ajustar el mapeo P1** (no sembrar en PROD). ¿Es inocuo? El `neto` de E1 sale de `ingreso_real` (no del mapeo de ingresos) y E1 no ancla Auteco → quitar esos 4 no cambia ningún valor que E1 use. Quedan 9 códigos, todos presentes en PROD.
2. **Regla A por concepto (B3).** `ejec + max(0, definido − ejec)` aplicado concepto a concepto (no agregado): con un concepto `ejecutado > definido` vale el ejecutado; con `ejecutado < definido` vale el definido. Verificar que el `max` es por concepto y que el ingreso NO se ancla en ejecución.
3. **Coherencia de la invariante B6 y el signo.** `neto + Σ egresos == flujo` al peso en toda la serie. `anclar` reescribe conceptos DESPUÉS de `reacumular` (patrón D2) para que la invariante cierre. Verificar que `egresos` se recalcula con Auteco conservado y que el delta de flujo re-acumula bien los meses siguientes (B2).
4. **Re-acumulación y el primer mes (B2).** Anclar un mes `m>0` propaga a los siguientes; el `m0` tiene caja fija (COCK-09) — su flujo no mueve cajas previas. ¿Correcto que la composición con COCK-09 no genere doble anclaje?
5. **Los controles del extractor (regla 7).** ¿El fail-loud aborta sin escribir si algún total no cuadra? ¿El fixture congela la realidad (montos string) con cabecera reproducible?

## Evidencia local

- **pytest suite E1:** 15 passed (B1–B6 + A3 + P1 5 + extractor 4). Ver `EVIDENCIA.md`.
- **Regresión amplia** (proyección/golden/motor/control/metas/ejecucion): **137 passed**, 3 skipped (real-mongo), 0 fallos.
- **ruff:** `All checks passed!` sobre `ejecucion/` y los tests.
- **R0:** `git diff origin/main -- motor.py` vacío.

## Cumplimiento del DoD / reglas de CLAUDE.md

- Regla 1 (Decimal): ✅. Regla 4 (histórico inmutable): P2 no escribe, solo lee/proyecta. Regla 7 (parsers/extracción fail-loud): ✅ controles al peso. Regla 10/motor (fórmula intacta): ✅ R0. Regla 11 (catálogo cerrado): ✅ no emite eventos.
- Plan E1 §4 (garantías): ✅ R0, golden intacto, IVA apagada, aditivo (sin consumidor aún).
- TDD: los tests B1–B6 + A3 + los del extractor definen el comportamiento (rojo→verde documentado en los commits).
