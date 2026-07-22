# CERTIFICADO KIMI — sprint4-vista-control · I-PLAN

**Resultado:** **9.3 / 10 — ✅ GO para construir con TDD** · **Fecha:** 2026-07-22
Sin hallazgos Medios/Altos. Diseño correcto y consistente con lo certificado.

## Respuesta a las 2 preguntas
- **(a) Bordes con `definido==0`:** CORRECTOS. Gasto sin presupuesto → rojo; 0=0 → verde; pct `null` sin dividir por cero (regla 7).
- **(b) `ejecutado` = solo egresos:** CORRECTO. Es la misma E(i) del motor (§1.4.1) → comparable celda a celda (DoD #3). Rubros de sistema fuera por no tener línea.

## Verificaciones
- **Caja:** excluir SOLO el ajuste es lo correcto; 'Por clasificar' SÍ cuenta en la caja (es dinero bancario real; excluirlo haría caja ≠ banco) pero no aparece como línea. Doble criterio bien resuelto.
- **Subtotales:** linealidad garantizada (Σ disponible = Σ definido − Σ ejecutado).
- **Guarda de estado:** en_ejecucion/cerrado coherente con M-1; `dashboard:leer` en §4.1.
- **$group:** mismo patrón del motor (dorado Sprint 3).

## 3 Bajas para fijar en TDD (verificadas en I-PR1, sin re-auditoría de plan)
- **B-1:** el semáforo se computa sobre el pct **cuantizado** que se reporta (90.005→90.00→verde). Bordes: 90.00→verde, 90.01→amarillo, 100.00→amarillo, 100.01→rojo.
- **B-2:** `pct_ejecutado` como **string** (regla 1; JSON number lo vuelve float binario).
- **B-3 (consideración):** egresos en rubros SIN línea vigente (rubro creado a mitad de ciclo) no aparecen en el desglose aunque entran a la caja → fila informativa **"sin presupuesto"** o nota. Para G3 no aplica (el motor genera líneas de todos los rubros).

## 8 tests esperados en el gate de código I-PR1
dorado de celda · bordes del semáforo · caja con el ajuste presente · guardas ·
RBAC 4 roles · equivalencia $group · linealidad de subtotales · serialización (strings).

**Veredicto:** "Construyan."
