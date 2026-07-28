# COMPAS — PLAN MAESTRO (hoja de ruta única)

**Versión:** 1.0 · 2026-07-27 · **Autor:** Claude Cowork (diseño/QA) con decisiones del CEO
**Destino:** `docs/COMPAS_PLAN_MAESTRO.md` en el repo — fuente única de la secuencia de trabajo. Claude Code (terminal) ejecuta contra este documento; Cowork especifica y hace QA; el CEO decide y aprueba.
**Cómo usarlo desde Claude Code:** cada fase se ejecuta como sprint con su sección de este documento (más su spec detallada si existe en `docs/`). Al cerrar una fase: tracker + memoria + marcar aquí el estado. Si una decisión no está cubierta por este documento ni por la spec de la fase, se pregunta al CEO antes de improvisar.

---

## 1. El norte (no cambia)

COMPAS es un sistema **predictivo** para administrar el presupuesto mensual de RODDOS y proyectar la caja para **tomar decisiones**. No es un sistema contable. Ante cualquier disyuntiva de alcance, gana lo que acerque a proyectar caja y decidir.

**Las 4 preguntas que el producto debe responder en cualquier momento del mes:**

1. ¿Cuánto puedo gastar hoy sin comprometer los meses siguientes?
2. ¿Cómo me afecta a futuro lo que ya ejecuté?
3. ¿Qué pasa si subo o bajo un gasto específico a partir de un mes determinado?
4. ¿Qué tengo que lograr para cerrar el horizonte con solvencia?

## 2. Gobierno del trabajo (reglas duras, aplican a toda fase)

1. **El motor es intocable.** `motor.py` no se modifica. Toda funcionalidad nueva es capa POSTERIOR sobre su salida. La suite golden-master (paridad al peso, 176 meses) es gate de todo commit de backend.
2. **Dinero = Decimal, montos como string** (regla 1 del CLAUDE.md). Nunca float en cálculo; Intl solo presenta.
3. **Nada cableado que sea del negocio:** parámetros, umbrales, componentes y reglas se administran desde la interfaz. Si agregar un rubro, cambiar un umbral o crear un escenario exige código, el diseño falló. (Excepciones vigentes conocidas y aceptadas: grupos del plan de cuentas como enum; tope de horizonte 180 — decisión CEO 2026-07-27.)
4. **Simular nunca escribe.** Borradores y escenarios viven aparte de los datos reales hasta guardado explícito. Guardar = versionado + auditoría + nota.
5. **Expand-contract obligatorio:** deploy que entiende el cambio PRIMERO, migración de datos DESPUÉS, verificada e idempotente. Ningún script toca prod sin GO explícito y separado del CEO.
6. **Un escritor por copia de trabajo.** Una sola sesión de Claude Code por rama; Cowork nunca toca el working tree.
7. **TDD y un commit por pieza**, revisable; desviaciones de la spec documentadas en el PR; el código real manda sobre los documentos (⚠ VERIFICAR antes de construir).
8. **Sistema de diseño F1 en todo lo nuevo:** cifra → juicio → acción; color = estado y nunca solo; formato es-CO compacto con exacto en hover; prueba de los 10 segundos (guion en `COMPAS_Guion_Prueba_Comprension.md`; la aplica alguien distinto al CEO).
9. **Specs viven en `docs/` del repo** antes del kickoff (lección F1.1).
10. Aprobación del ciclo y de deploys: **el CEO** (aprobador único).

## 3. Estado actual — HECHO y en producción

| Pieza | Contenido | Evidencia |
|---|---|---|
| Motor C7 verificado | Réplica Decimal del modelo financiero; paridad golden-master 0 discrepancias/176 meses | `tests/test_golden_master.py`, verificación externa 2026-07-26 |
| C1 — Ciclo presupuestal UI | Generar sugerido → acotar → aprobar (Idempotency-Key); vacíos accionables | merge `ed22148` |
| C2 — Cabina del mes | `MesStatusBar` global, `/mes` integradora, cierre real 2 pasos, `QueExigeAtencion` por plata | merge `cd56d95` |
| F1 — Sistema de diseño (piloto Inicio) | Tokens AA, escala tipográfica, `formatCOPCompact/Delta`, `KpiTileV2` (comparación o contexto obligatorios), `ChartCard`, `CashCurve anotada`, titular de juicio; juicio a 60 m + gráfico 18 m | merge `49ab23a` |
| C3 — Variables con impacto | Supuestos con borrador + preview compute-only (paridad al peso), unidades humanas, validación 3 niveles, tornado de sensibilidad, nota al audit log | merge `c84a301` |
| CR-002 | Costos de alistamiento por componentes (Σ = 692.005 exacto); migración corrida en prod, idempotente | tracker C3-VARIABLES |
| F1.1 — Propagación del diseño | §0 (`direccionBuena` en el delta; mínimo neutro sin perforación; el fix de cache de sensibilidad ya venía cubierto en C3 `cf5618e`) + barridos §1 (KpiTile v1 muerto, guardián `barridos.test.ts`) + Proyecciones/Escenarios/Dashboards/Control/Cabina/Reportes/IVA-Flujo diario al estándar F1; perf medida con Profiler 144,5→56,2 ms | merge `1ae570c` (9 commits, uno por pantalla); 138 tests frontend verdes |

**F1.1 CERRADA (2026-07-27).** Mergeada `1ae570c` (GO CEO — push=deploy); la **prueba de los 10 segundos por un tercero (no Andrés)** en Proyecciones y Dashboards se aplicó y **PASÓ**. Dos nits del QA visual quedan como arrastre a resolver en la rama D1: la conclusión de Dashboards usa punto decimal (es-CO = coma) y el multiplicador se distorsiona con el mes 1 parcial (cambiar a "pasa de X a Y en 24 meses"). Specs de F1.1 (`COMPAS_Sprint_F11_Propagacion_Diseno.md`) y D1 (`COMPAS_Sprint_D1_Decisiones_sobre_el_Motor.md`) ya en `docs/` (rule §9).

## 4. Fases por ejecutar (en este orden)

### D1 — Decisiones sobre el motor · spec: `COMPAS_Sprint_D1_Decisiones_sobre_el_Motor.md`

**Responde las preguntas 1, 3 y 4.** Capa de impactos (`impactos.py`, post-proceso puro): ajustes por rubro/naturaleza con modo absoluto/% y vigencia; escenarios nombrados (CRUD auditado); **valles de caja** (hitos automáticos con causas explicadas y meses de anticipación — decisión CEO: el hito es el mes de menos caja, pueden ser varios); solvers por bisección (techo de gasto auditable con parámetros visibles, goal seek, punto de quiebre); pestaña **"Decisiones"** en Presupuesto con panel de impacto sticky.
**Terminado cuando:** el caso "arriendos +$3 M desde sep-26 → nueva curva + valle movido + delta → guardar escenario → goal seek de venta necesaria" corre completo; `motor.py` con cero diffs; golden-master verde; los 4 casos literales del brief §4.5 pasan como tests.

### D2 — Obligaciones genéricas + metas de ingreso

**Primer ítem (arrastre de D1 — QA Cowork 2026-07-27):** completar la **tarjeta de techo de gasto** con el cruce contra el **gasto YA ejecutado del mes** (consumido / disponible / % + alerta al excederlo — la mitad operativa del §4.7 del brief, que D1 dejó documentada como diferida). Los datos ya existen en la Vista Control (`control.service`); es atarla al mes de la Cabina. Alternativamente puede salir como un **D1.1 corto** antes de D2.

Generalizar la lógica Auteco existente (verificada; NO reconstruirla) como entidad **Obligación** de dos naturalezas: (a) valor fijo con cuotas (acreedor, monto, cuotas, periodicidad, tasa, inicio, gracia → calendario generado); (b) valor variable por facturación con términos (plazo base sin interés, plazo máximo, tasa del excedente — atributos, no constantes). **Registro factura a factura** (fecha, valor, plazo elegido 90–150) → fecha/mes de pago, interés causado como concepto separado, reflejo automático en flujo, proyección y techo. Meses sin factura → supuesto editable (último valor / promedio N / valor definido), marcado como proyectado. **El plazo como palanca:** simular 90/120/150 por factura o como política, viendo alivio de caja vs. costo financiero. Auteco pasa a ser un registro de esta entidad, nunca caso especial. La deuda de inversores migra a obligación tipo (a). Además: **ingreso proyectado como meta** por mes (editable, con líneas), comparado contra el real y contra el motor, con % de cumplimiento en Presupuesto.
**Terminado cuando:** registrar una factura con plazo 150 mueve el pago de mes, muestra el interés al 1,6 % separado y ajusta el techo; la lógica existente produce los mismos resultados que antes (test de regresión de paridad); una obligación nueva aparece sola en flujo, gráfica y techo.

**Secuencia real (2026-07-28):** el backend de D2 se mergeó primero (`23e3166`); entre D2-backend y el §7 de D2 se ejecutó **V1** (abajo) para resolver la ceguera del CEO en Proyecciones; el **§7 de D2** (página Obligaciones + registro de facturas + simulador UI + bloque de metas) queda como frontend pendiente. Spec: `COMPAS_Sprint_D2_Obligaciones.md`.

### V1 — "Ver el egreso" (frontend) · spec: `COMPAS_Sprint_V1_Ver_el_Egreso.md`

**En producción (`dd86979`, PR #45).** Proyecciones deja de mostrar solo el ingreso: cada mes se reagrupa en tres buckets de negocio — Ingreso (`neto`), Costo (`pago_inventario + fondeo + costo_nueva + adelanto`; el fondeo Auteco es costo, mapeo CEO), Gasto (`gastos_fijos + gps + int_deuda + iva`) — que **reconcilian con el flujo** (candado del invariante). Tabla con los tres totales + fila expandible por mes (desglose, lote Auteco real/proyectado) + fila de totales; gráfico compuesto (barras ingreso arriba, costo+gasto apiladas abajo, línea de caja con eje derecho propio, umbral, ventana reconciliada sombreada, hover con "de los cuales Auteco"), con agregación trimestral/anual en horizontes largos; KPI "Compromiso Auteco". Solo frontend, **`motor.py` cero diffs**. El §0 (coherencia de la reconciliación) se resolvió en el backend de D2.
**Terminado cuando:** para cada mes `ingreso − (costo + gasto) == flujo` al peso incluida la ventana reconciliada (candado, también en la ruta agregada); `interes_obligaciones == |fondeo|` se muestra pero NUNCA se suma a los buckets (anti-doble-conteo). ✅

### F4 — Fase 4 fusionada: gráficos y flujo diario analítico

Los gráficos nuevos del plan original + el §4.3/4.4 del brief: **flujo diario analítico** (día de saldo más bajo, filtros por categoría/rubro/estado, proyectado vs. ejecutado diario con desviación, subtotales y pesos por categoría, alertas de cobertura); **gráfica de composición** (bandas: obligaciones/gasto operativo/ingreso, línea de caja encima, tooltips por mes con detalle completo — requiere tooltips en el SVG o evaluar librería ligera, decisión documentada); **mora por cosecha y envejecimiento** (con LoanTape cargado); **embudo de cobranza**; **proyectado vs. real por mes** (cuando existan cierres). Cada gráfico con su pregunta y la decisión que habilita; los que no respondan nada accionable, se eliminan.
**Terminado cuando:** cada gráfico pasa la prueba de los 10 segundos y el flujo diario responde "¿qué día me quedo corto?" en menos de 5 segundos.

### D3 — Base de gastos fijos inteligente

Detección automática de recurrentes desde el histórico real (mismo rubro/beneficiario con periodicidad estable) → lista candidata con valor típico y variabilidad → confirmación/corrección del CEO; clasificación en 3 niveles (ineludible / comprometido / discrecional — solo los dos primeros restringen el techo de D1); alertas de recurrente ausente o patrón nuevo; vigencias e incremento anual (ya soportados por la plantilla). *Se ejecuta cuando haya ≥4–6 meses ejecutados para que el patrón valga.*
**Terminado cuando:** la app propone la base, el CEO la cura desde la UI, y el techo de gasto lee de ella.

### F6 — Lo que la app genera (ampliada)

PDF de Reportes con el sistema F1 + **resumen ejecutivo automático** (qué pasó, por qué importa, qué decidir — lenguaje llano); export Excel/CSV de vistas y escenarios conservando estructura; **tablero configurable** (tarjetas elegibles/reordenables, indicadores propios con regla de semáforo, vistas guardadas con nombre); coherencia total pantalla↔export.

### F7 — Alertas como reglas

Reglas creables desde la UI (variable, comparador, umbral, mes de aplicación, mensaje), no condiciones fijas; qué interrumpe al CEO y por qué canal; una alerta que no exige acción es spam. Integra los valles de D1 y las alertas de D3/F4.

### Aparcado (decisión CEO 2026-07-27 — se reevalúa con D1–D3 en producción)

Motor de fórmulas genérico (variables definibles + dependencias + detección circular), granularidad variable (diaria/semanal/trimestral), dimensiones nuevas (sede/proyecto/cliente), horizonte >180, móvil completo (el piso de usabilidad va en F1.1).

## 5. Criterios de aceptación globales (del brief, ajustados a las decisiones)

Al cierre de D2 deben pasar TODOS; cada fase marca los suyos:

- Agrego un rubro nuevo y totales/flujo/proyección se actualizan sin recargar. *(hoy ✓)*
- Veo ingreso proyectado como meta junto al gasto, con % de cumplimiento. *(D2)*
- En flujo diario identifico el día de saldo más bajo en <5 s. *(F4)*
- La gráfica de proyecciones tiene eje de tiempo y ninguna cifra desbordada. *(F1.1)*
- Escribo un incremento de arriendo desde un mes y veo nuevo saldo, nuevo valle y delta vs. base. *(D1)*
- Al cerrar un mes, la proyección se re-ancla y me dice cuánto cambió el horizonte. *(re-anclaje ✓; arrastre cuantificado: D1/D2)*
- La tarjeta de techo de gasto muestra valor, parámetros editables y alerta al excederlo. *(D1)*
- Registro una factura Auteco con su plazo y el pago aparece solo en el mes correcto; con 150 días veo el interés separado y el efecto en los valles. *(D2)*
- Simulo 150 días como política y la app me dice caja liberada vs. costo total. *(D2)*
- La lógica de plazos existente produce los mismos resultados que antes. *(D2, regresión)*
- La app me propone recurrentes del histórico y yo los curo. *(D3)*
- Cambio el mínimo de caja y alertas, referencias y techo se ajustan. *(umbral ✓ hoy; techo: D1)*
- Los valles se recalculan solos ante cualquier cambio de supuestos o ajustes. *(D1)*
- Pregunto cuánto debo vender para que ningún valle baje de X y responde con un número. *(D1)*
- Armo una vista propia, la guardo y la recupero. *(F6)*
- Creo una regla de alerta desde la UI y aplica de inmediato. *(F7)*
- Ninguna de las anteriores exige despliegue nuevo ni cambio de código.

## 6. Decisiones del CEO registradas (vigentes)

| Fecha | Decisión |
|---|---|
| 2026-07-23 | Caja veraz: provisión NIIF 9 fuera del flujo |
| 2026-07-26 | Cuota inicial COMPLETA como ingreso; alistamiento como egreso desglosado (CR-002); "no ajustemos" el 692.005 — colchón $17.905 sembrado |
| 2026-07-26 | Adelanto Auteco = $0 mientras no lo exijan |
| 2026-07-26 | Aprobador único del ciclo y deploys: Andrés |
| 2026-07-26 | Horizonte por defecto 18 m (gráficos) con juicio a 60 m; titular reconciliador; "mil M" (no "MM") |
| 2026-07-27 | Motor intocable; funcionalidad nueva = formulación posterior |
| 2026-07-27 | Tope de horizonte queda en 180 |
| 2026-07-27 | El hito de solvencia = los valles (mes/es de menos caja), detectados y explicados |
| 2026-07-27 | Plan vigente y brief se complementan; capa 5 (fórmulas) aparcada |

## 7. Registro de estado (actualizar al cerrar cada fase)

| Fase | Estado | Cierre |
|---|---|---|
| C1 · C2 · F1 · C3+CR-002 | ✅ En producción | 2026-07-26/27 |
| F1.1 | ✅ Cerrada — prueba 10s de un tercero PASÓ | 2026-07-27 |
| D1 | ✅ En producción (`95acf9c`, PR #42, GO CEO) — pasada visual pendiente en prod | 2026-07-27 |
| D2 — backend | ✅ En producción (`23e3166`, PR #43, GO CEO). Fix §0 coherencia incluido; motor.py cero diffs; golden-master verde; candado de paridad al peso. Gate-waiver: CI Actions bloqueado por billing de la org → gates locales verdes como control compensatorio, Kimi retroactivo pendiente | 2026-07-28 |
| V1 — "Ver el egreso" | ✅ En producción (`dd86979`, PR #45, GO CEO). Frontend Proyecciones: 3 buckets + candados (invariante + anti-doble-conteo, incl. ruta agregada), tabla con desglose, gráfico compuesto doble eje + hover, KPI Compromiso Auteco. motor.py cero diffs; Vercel prod success. Confirmación visual autenticada pendiente del CEO | 2026-07-28 |
| D2 — §7 frontend | 📝 Página Obligaciones + registro + simulador UI + metas block. Backend ya expone los datos | — |
| F4 | 📝 Definida aquí | — |
| D3 | 📝 Definida aquí (espera histórico) | — |
| F6 · F7 | 📝 Definidas aquí | — |
| Capa 5 | ⏸ Aparcada | — |
