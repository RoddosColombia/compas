# ADDENDUM P3.1 — corrección del hallazgo C-1 (re-gate)

**Gate previo:** Kimi 8.7/10 NO-GO (2026-08-07) · **Hallazgo:** C-1 (bloqueante, arquitectónico — del plan §3/B7 aprobado por el propio auditor, no de la implementación) · **Este addendum:** aplica C-1 con TDD y re-pide gate.

## Qué encontró C-1

`_resultado_con` pasaba a D2 `meses_anclados = frozenset(anclas)` (TODOS los regímenes: `cerrado`, `en_ejecucion`, `presupuesto`). Como E1 **nunca ancla Auteco** (sus 5 conceptos son `gastos_fijos/gps/costo_nueva/int_deuda/iva`; en el delta de flujo el `pago_inventario`/`fondeo` paramétrico se cancela), excluir de D2 los meses **no cerrados** no evitaba ningún doble conteo — solo hacía **desaparecer** los pagos reales de FIX-K de esos meses (p. ej. al acotar el presupuesto de septiembre, sus $123.392.031 reales quedaban reemplazados por el paramétrico). Regresión de FIX-K sobre la exigencia #1 del CEO.

## El fix (quirúrgico, Regla B — NO refactor)

1. **`backend/app/proyeccion/service.py` `_resultado_con`:**
   ```python
   meses_anclados = frozenset(m for m, a in anclas.items() if a.estado == CERRADO)
   ```
   Solo los meses **cerrados** se excluyen de D2 (el pasado es del libro; sus facturas ya no están pendientes). En `en_ejecucion`/`presupuesto`, D2 aplica el pago real — compone limpio con E1 (campos disjuntos: E1 escribe los 5 conceptos no-Auteco, D2 escribe `pago_inventario`/`fondeo`; deltas aditivos vía `reacumular`). El conjunto completo (`frozenset(anclas)`) se reserva para las marcas de origen de la UI en **P5** — NO se alimenta a D2. `CERRADO` se importa de `ejecucion.service`.

2. **`backend/app/obligaciones/reconciliacion.py`:** corregido el docstring — la exclusión aplica SOLO a meses cerrados; en no-cerrados D2 aplica el pago real sin doble conteo. (El paréntesis previo "esa realidad ya la puso E1" era falso para Auteco.)

3. **Test de regresión NUEVO** (`test_e1_pipeline.py::test_c1_d2_aplica_pago_real_en_mes_anclado_no_cerrado`, parametrizado `en_ejecucion` + `presupuesto`): mes anclado no-cerrado con factura que paga ahí → D2 aplica el pago real (`pago_inventario == −capital`, `fondeo == −interés`) Y el concepto que E1 ancló por Regla A (`int_deuda == −800.00`) se conserva en la misma fila; el mes no anclado (2026-12) reconcilia normal. **Rojo antes del fix** (daba el Auteco paramétrico `−10.000,00` en vez del real `−1.000.000,00`), **verde después**.

## Lo que NO se tocó (por exigencia del re-gate)

`motor.py` (R0), `ejecucion/service.py`, `lectura.py`, `loader.py`, y `reconciliacion.py` salvo el docstring del punto 2. Los tests existentes (pipeline con 2026-10 `cerrado`, B7 puro con set explícito) siguen **verdes sin modificarlos** — la capa de reconciliación y el candado no cambian.

## Baja B-1 (diferida a P4, con visto de Kimi)

`cargar_anclas` corre dentro de `_resultado_con`, que se invoca por escenario (base/optimista/pesimista) → el mismo trabajo Mongo (depende solo de `mes_inicio`/`horizonte`) se repite hasta 3× por carga de página. Correctitud intacta. Kimi la dejó a criterio ("puede ir en P4"); se difiere a P4 para mantener este re-gate quirúrgico.

## Evidencia (ver EVIDENCIA.md actualizada)

- Test C-1 nuevo: **2 passed** (en_ejecucion + presupuesto). Pipeline existente + B7 puro: verdes sin cambios.
- Regresión completa del backend: ver EVIDENCIA.md (§1).
- ruff check + format: limpios. R0: `motor.py` 0 diffs.
- Diff del fix: `_resultado_con` (1 línea efectiva + comentario), docstring de `reconciliar`, y el test nuevo.
