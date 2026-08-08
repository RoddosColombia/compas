# SOLICITUD DE AUDITORÍA — COPYS UX: español de negocio en el texto visible

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-08-08 · **Área:** frontend (texto de cara al usuario)
**Rama:** `feat/copys-ux-negocio` · commit `e0c39fe` · **PR #76**
**Checkpoint previo:** Kimi 9.1 — GO con 1 precisión obligatoria (clasificar "umbral" por sentido). Este paquete la aplica y la evidencia con tabla.

## Qué se hizo

Reescritura del **texto visible** de la app a español de negocio, sin tecnicismos.
**Cero cambios** en lógica, variables, props, claves de datos ni backend. 29 archivos, todos
en `frontend/src` (`components/` + `pages/`).

## Precisión obligatoria aplicada — "umbral" tiene 2 sentidos, clasificados

1. **Piso de caja** (`caja_minima`: Proyecciones, Supuestos, Techo de gasto, Tornado)
   → **«mínimo de caja»** (barrido A).
2. **Tolerancia de cierre / conciliación** (Cabina del mes, Reporte de caja: "dentro del umbral"
   = diferencia ≈ 0 al cerrar) → **«margen»** (item 9). **NO** "mínimo de caja" — se evita el bug
   semántico en el flujo de cierre.
3. **Tercer sentido** (umbral de puntaje del calendario DIAN) → detectado solo en comentarios/tests,
   **sin string visible en producción** → no se tocó.

La tabla completa de clasificación por sentido (archivo:línea) está en `EVIDENCIA.md §3`.

## 13 reescrituras puntuales (lista aprobada por el CEO + checkpoint 9.1)

Quita "(regla 4)" en cierre · Runway → «Autonomía de caja» + "al ritmo de gasto actual" ·
Wava «Dinero en camino» + ayuda · Contra-asiento → «Reverso» (reword honesto: "no se borra nada;
queda en cero") · «Provisión de cartera (contable, no afecta la caja)» / «Incumplimiento (cartera
perdida)» · fondeo → financiación · «Meses de caja más baja» · «Unidades reales por mes (primeros
meses)» + «(reemplaza la proyección esos meses)» · «Suma de saldos de bancos» / «Caja según el
sistema» · oculta id interno en toast · fecha con ejemplo (año-mes-día) · «Meses con facturas ya
registradas» · «Participación en ventas (%)» / «Total».

## Puntos a auditar

1. ¿La clasificación de "umbral" por sentido es correcta y completa (piso→mínimo de caja;
   conciliación→margen; DIAN→sin tocar)? ¿Alguna ocurrencia mal clasificada?
2. ¿El texto nuevo es fiel al negocio y no pierde verdad (honestidad R5: nada se borra, la
   provisión no afecta caja, la diferencia se registra en el mes que abre)?
3. ¿Se preservó el alcance (cero lógica/variables/props/backend)?

## Evidencia (ver `EVIDENCIA.md`)

- Tabla de clasificación de "umbral" por sentido (a).
- Diff completo revisado personalmente (b): grep de variables/props vacío; solo texto.
- vitest 248/248 · build OK · biome limpio (c).
- Capturas reales (Playwright) de Cierre con «margen» y Proyecciones con «mínimo de caja» (d).

## Método

Sin lógica nueva → no aplica TDD-de-producción; los tests de UI afectados se actualizaron al
texto nuevo y quedan verdes. Inventario primero (explorador), propuesta al CEO antes de código,
barrido delegado a subagente con la precisión del checkpoint, diff revisado por el coordinador
antes de este paquete.
