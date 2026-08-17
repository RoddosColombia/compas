# RESPUESTA KIMI — iva-planes-ago26 PR1-I (retroactiva PRs #90–#94)

**Fecha:** 2026-08-13 · **Auditor:** Kimi (arquitecto) · **Umbral:** ≥ 9.0
**VEREDICTO: 9.4 / 10 — GO (retroactivo; 5 waivers saldados)**

(Pegado verbatim por el CEO en el chat, 2026-08-13.)

---

Gate RETROACTIVO — PRs #90–#94 (waiver 11-ago): 9.4 / 10 — GO (5 waivers saldados)
Leí los 5 diffs completos (2.841 líneas). Calidad alta y consistente: TDD estricto, candados honestos (partición de planes: iniciales EXACTAS, recaudo ≤0.5% declarado en el propio test), fail-loud, compatibilidad hacia atrás, un solo camino de escritura en la ingesta. Las 5 lupas, respondidas:

1. PR #92 (reemplazo del arrastre): correcto — se consume una vez en el primer período con facturas ≥ `aplica_desde`, fluye si está vacío, anteriores intactos. Sin doble conteo ni pérdida; la única responsabilidad es del operador al fijar `aplica_desde` (documentada).
2. PR #93 (expansión): de acuerdo, con B-1 obligatoria — la expansión no rompe contratos vivos, PERO `apache_por_mes` (índice 1) queda con riesgo latente: documentar + guard fail-loud (si viene con datos y hay modelo con plan 2 → error explícito, no indexación silenciosa errada). Tarea pequeña inmediata.
3. PR #94 (tornado): tu lectura es la correcta — NO excluir el tramo anclado del piso. El anclaje fija la trayectoria real; las variaciones miden el futuro. El test (a) piso tornado == piso pantalla y (b) factura mueve el piso/cache invalidado — contrato exacto de tu bug.
4. PR #90: regla 7 cubierta (revisé los vectores ambiguos de montos es-CO y fechas).
5. PR #91: coerción segura (igualdad exacta = sin falso positivo posible); nit opcional de validar solo-dígitos.

Nota de verificación (honestidad): a mitad de la auditoría el repo dejó de responderme (raw + API → 404; repos públicos ajenos sí) — todo indica que la privatización de G1 ya se hizo ✅. Los diffs se auditaron desde la EVIDENCIA (consistente con el repo que venía verificando), pero no pude contrastar de primera mano el grep de `apache_por_mes` ni las verificaciones en producción (favor $59.456.957 · 9/9 Auteco Σ $170.710.393 · piso $492.513.306) — aceptadas como verificaciones del operador con los tests pineando la semántica. Para gates futuros necesito acceso alternativo (diffs pegados o un PAT de solo lectura).
Nota de proceso (sin descuento): 5 features sustantivas en un día por waiver es uso intenso de la vía de excepción — el protocolo se honró completo, pero el waiver sigue siendo excepción, no autopista. Registrado.

Instrucción para Claude Code:
1. B-1 (inmediata, pequeña): documenta el riesgo del índice 1 de apache_por_mes + guard fail-loud (apache_por_mes con datos + algún modelo con plan 2 → error explícito). B-2 (nit, opcional): validar dígitos en valores NIT de config.
2. Tracker: GATE-KIMI retroactiva iva-planes-ago26 (9.4) cerrando los 5 waivers.
3. Siguiente: cerrar G1 — (a) confirma con el CEO si el repo ya es PRIVADO (mis accesos raw/API murieron hoy: parece que sí); si sí, necesito vía alternativa de verificación para gates futuros (PAT de solo lectura guardado en INVENTARIO-SECRETOS, o diffs pegados completos); (b) rotación de secretos con el CEO (ítem #1: password Mongo); (c) required check backend; (d) mini-lote Actions #7/#8/#9 + Node 22.
4. Al cerrar G1 avísame: emito el acta de cierre de construcción de COMPAS.

Detalle de lupas (L1–L5), nota de proceso y autorización: ver el texto completo del gate en el chat del CEO (2026-08-13). GO ≥9 retroactivo: los 5 waivers quedan saldados en la hoja Gates (GATE-KIMI retroactiva iva-planes-ago26 9.4).
