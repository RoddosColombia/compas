# AUDITORÍA KIMI — E1 PR1-I: lector de la ejecución real → conceptos del motor

**Calificación: 9.5/10 — APROBADO ✅** (umbral ≥ 9.0)
**Fecha:** 2026-08-05 · **PR:** pendiente de abrir · **Rama:** `feat/e1-p1-lectura-ejecucion` · **Commit:** `911bea2`
**Autorización de merge:** GO Kimi 9.5/10 · GO CEO: Andrés (2026-08-05)

## Alcance auditado
Diff real completo del commit `911bea2` (4 archivos: `domain/rubros_neutros.py` nuevo, `metas_ingreso/service.py` −13/+5, `ejecucion/__init__.py` + `ejecucion/lectura.py` nuevos, `tests/test_e1_lectura.py` nuevo) + salida real de tests (5/5) + el plan E1 aprobado. Kimi verificó además en la taxonomía vigente (`domain/rubro.py`) que los 4 códigos de ingreso (0110/0120/0130/0140, líneas 108-111) y 4030 (línea 158) existen → B12 cubierto.

## Confirmaciones
1. **Módulo compartido `rubros_neutros`** — una verdad, un lugar; `metas_ingreso` la importa y re-exporta (cero cambio de comportamiento).
2. **Función pura** — sin Mongo, `Decimal` en todo, dataclasses frozen, determinista (`sorted` en `sin_mapear`).
3. **Mapeo §10 exacto** — neto/pago_inventario/fondeo/costo_nueva/gps/int_deuda/iva + `gastos_fijos` robusto a rubros nuevos.
4. **Lupa 1 (orden A1)** — `continue` por `neutros_ids` antes de `_concepto_de`; *Reversas* no cae en `gastos_fijos`.
5. **Lupa 2 (R-1/R-2)** — 1010 entero a `pago_inventario`; 4040 en `sin_mapear` sin sumar.
6. **Lupa 3 (`gastos_fijos`)** — 5070 sistema fuera y no reportado; 2140 sin código entra por grupo.
7. **Lupa 4 (B12)** — cubre los 13 códigos; error ruidoso con faltantes; neutros sin código no lo disparan.
8. **Lupa 5 (pureza/reporte)** — `sin_mapear` solo si movió dinero y no es sistema; orden estable.
9. **Aritmética B9 re-verificada al peso** — neto 15.000 · pago_inventario 100.000 · fondeo 1.600 · costo_nueva 2.000 · gps 800 · gastos_fijos 13.800 · int_deuda 2.200 · iva 6.000.
10. **Garantías** — R0 (`motor.py` ausente del diff), golden intacto, IVA apagada, catálogo sin crecer, aditivo puro.

## Hallazgos
Ninguno.

## Veredicto
**APROBADO para merge (9.5/10).** Nota para P2: su PASO 0 debe re-verificar en PROD la existencia de 0120/0130/0140 (presentes en la semilla; el re-seed de C1 ya las incluye — rutina, no bloqueante).

---
> Respuesta textual de Kimi (sin editar):

CERTIFICADO DE AUDITORÍA — E1 PR1-I: lector de la ejecución real → conceptos del motor
Fecha: 2026-08-05 · Auditor: Kimi (arquitecto) · Umbral: ≥ 9.0 · Commit: 911bea2 (rama feat/e1-p1-lectura-ejecucion)
Plan padre: docs/COMPAS_PLAN_E1_Anclaje_a_la_Ejecucion.md (GO Kimi 9.5, pieza P1) · Contratos: I-PLAN §10 (mapeo), spec ejecución Parte V (B9, B12)
VEREDICTO: 9.5 / 10 — GO
Método
Verificación del auditor sobre el diff real completo del commit (4 archivos: domain/rubros_neutros.py nuevo, metas_ingreso/service.py −13/+5, ejecucion/__init__.py + ejecucion/lectura.py nuevos, tests/test_e1_lectura.py nuevo) + la salida real de tests (5/5) + el plan E1 aprobado. Además verifiqué en la taxonomía vigente (domain/rubro.py) que los 4 códigos de ingreso del mapeo (0110/0120/0130/0140) existen (líneas 108-111) y que 4030 'Garantía cupo (Auteco)' existe (línea 158) — la condición B12 queda cubierta.
Verificación contra el plan y los puntos de lupa
Punto — Resultado
Módulo compartido rubros_neutros: Exacto: una verdad, un lugar; metas_ingreso la importa y la re-exporta para no romper importadores existentes (mismo frozenset, cero cambio de comportamiento).
Función pura: mapear_a_conceptos recibe snapshots (RubroInfo frozen, valor_por_rubro_id, neutros_ids) — cero Mongo, Decimal en todo, dataclasses frozen, determinista (sin_mapear con sorted).
Mapeo §10: Exacto: neto ← 0110/0120/0130/0140 · pago_inventario ← 1010+4060 · fondeo ← 4030 · costo_nueva ← 1020 · gps ← 1030 · int_deuda ← 4010/4020/4050 · iva ← 5060. gastos_fijos = operación/nómina/otros menos codificados/sistema/neutros (robusto a rubros nuevos, p.ej. 2140).
Lupa 1 — orden A1: Verificado en código: el continue por neutros_ids está antes de _concepto_de — 'Reversas y devoluciones' (grupo otros, no sistema) NO cae en gastos_fijos; el test lo prueba (9999 excluidos, 4000 limpios).
Lupa 2 — R-1/R-2: 1010 entero a pago_inventario (test: costo_nueva queda 0.00) · 4040 'Deudas impuestos' en sin_mapear sin sumar a nada (test: todos los conceptos en 0.00).
Lupa 3 — gastos_fijos no barre: 5070 'Por clasificar' (es_sistema) queda fuera y además no se reporta en sin_mapear (los de sistema no ensucian el reporte) · 2140 'Freelance' sin código entra por grupo. Correcto en ambos sentidos.
Lupa 4 — B12: set(_CONCEPTO_POR_CODIGO) − codigos_presentes cubre los 13 códigos referenciados → ValueError ruidoso con los faltantes listados y la acción ("créalos por C1"). Los neutros sin código no lo disparan (el chequeo solo mira códigos). En la taxonomía vigente los 4 de ingreso y 4030 existen → sin pre-condición bloqueante en PROD (PASO 0 de P2 lo re-verificará de todas formas).
Lupa 5 — pureza/reporte: sin_mapear solo se alimenta si el rubro movió dinero (valor != 0) y no es de sistema — los vacíos no ensucian; orden estable.
Aritmética re-verificada (fixture B9)
neto 15.000 (10.000+5.000) · pago_inventario 100.000 (70.000+30.000) · fondeo 1.600 · costo_nueva 2.000 · gps 800 · gastos_fijos 13.800 (4.000+500+9.000+300) · int_deuda 2.200 (1.000+500+700) · iva 6.000 — al peso, exacto.
Garantías
R0: motor.py ausente del diff (cero diffs) · golden intacto (ningún consumidor aún) · compuerta IVA intacta · catálogo sin crecer (P1 lee, no emite) · aditivo puro (no altera ningún valor existente).
Hallazgos
Ninguno. La implementación reproduce el plan aprobado al pie, con pureza estructural y los 5 criterios (B9/B12/A1/R-1/R-2) probados con tests reales.
Condiciones/notas: solo la nota de P2: su PASO 0 debe re-verificar en PROD la existencia de 0120/0130/0140 (presentes en la semilla; el re-seed de C1 en PROD ya las incluye — rutina, no bloqueante).
Kimi — auditor técnico independiente. Verificación adversarial sobre el diff real; sin código generado.
