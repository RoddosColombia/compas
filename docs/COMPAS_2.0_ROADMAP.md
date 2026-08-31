# COMPAS 2.0 — Roadmap de desarrollo (artefacto vivo)

> **Qué es:** el artefacto de control ÚNICO del avance de COMPAS 2.0 (rediseño del cockpit
> presupuestal + predictivo de caja). Muestra la evolución tarea a tarea en el tiempo, no
> solo la foto de hoy. **Manda sobre cualquier presentación, tracker `.xlsx` o correo:**
> si algo lo contradice, gana este archivo.
>
> **Mecánica de actualización (regla del CEO 2026-08-30):** se actualiza **tan pronto
> cierra cada tarea** (no al final del bucket). Cada cambio queda **fechado** en el
> Registro de cambios (§4). Responsable de revisarlo: Claude, en cada cierre de pieza.
>
> **Gobierno:** COMPAS 2.0 vive en `backend/app/` y `frontend/src/` sobre la base v1.1.2.
> `motor.py` es intocable (golden-master 176 meses); todo lo nuevo es capa post-motor.
> Decisiones fundacionales en `docs/COMPAS_2.0_FUNDACIONAL.md`. Reglas innegociables: las
> de `CLAUDE.md`. Mismo estilo que `docs/COMPAS_FABS_ROADMAP.md` (el roadmap de FABS).

## 1. Norte de COMPAS 2.0 (una línea)

Sistema **PREDICTIVO** de presupuesto y caja para RODDOS: el CEO no ve la caja caer bajo
sus umbrales sin que la app se lo advierta con anticipación y con las palancas para
evitarlo — **sin sacrificar la paridad al peso del motor** (golden-master 176 meses).

## 2. Fases / incrementos

Estado: ⬜ Pendiente · 🟡 En curso · ✅ Hecho · 🔒 Bloqueado

| # | Incremento | Qué entrega | Gate | Estado |
|---|---|---|---|---|
| **F0** | **Fase 0 · Andamio del método** | F0-1 `CAPACIDADES.md` (mapa código→C1..C11) · F0-2 candado del motor (2 jobs CI: golden-master + parity-guard) · F0-3 `DESIGN.md` (gramática 8 reglas + tokens marca). AND-1..5 = SkillSpector, AgentShield, permisos operativos, etc. | Gate G-GM (golden-master required en branch protection) | 🟡 **F0-1/2/3 ✅ hechos**; AND-1..5 ⬜ pendientes (operacionales, no bloquean features) |
| **1** | **Funcional · imprescindibles (must)** — RF-F1..F5 | RF-F1 reglas sembradas (semilla real, 90%+ auto-clasif) · RF-F2 costura presupuesto→proyección versionada · RF-F3 valles como entidad (umbral atención D-1) · RF-F4 techo de gasto en ventana · RF-F5 solvers en la app (3 palancas por valle) | gate-waiver GO CEO (Kimi ausente ~semanas, retroactivos pendientes — NUNCA simulado) | ✅ **MERGEADO a main** — 5/5 hechos, ver §4 |
| **2** | **Funcional · debería (should)** — RF-F6, RF-F7, RF-F9 | RF-F6 cargas idempotentes por huella · RF-F7 recomendaciones por impacto (reparto por rubro) · RF-F9 plan de cuentas completo (código+clase obligatorios al crear categoría) | gate-waiver GO CEO | ✅ **MERGEADO a main** — 3/3 hechos, ver §4 |
| **3** | **Funcional · podría (could)** — RF-F8, RF-F10 | RF-F8 rebanada A: simulación compute-only "negocia esta deuda" (rebanada B = persistida, difierida a CR-RF-F8-B con evento audit nuevo) · RF-F10 horizonte 240 meses + agregación por año/trimestre | gate-waiver GO CEO | ✅ **MERGEADO a main** — 2/2 hechos (rebanada A de F8, F10 completa). **CIERRA funcional 10/10.** Ver §4 |
| **4** | **Visual · RV-V1 tokens + RV-V2 completa** | RV-V1 `DESIGN.md §3` con paleta como tokens (`--color-chart-*`, contrato para RV-V2) · RV-V2 rehacer las 2 gráficas principales contra el mockup (rebanada 1: curva de caja · rebanada 2: composición separada · rebanada 3: escenario superpuesto + motos editable + «vender de más») | Kimi ausente ⇒ gate-waiver GO CEO. Gates finales: G-PIXEL (chrome-devtools-mcp + lost-pixel vs mockup) + G-AXE (accesibilidad) | ✅ **MERGEADO a main** — RV-V1 + RV-V2 **CIERRA 10 de 10 AC** (3 rebanadas mergeadas). Ver §4 |
| **5** | **Visual · RV-V3..V10** | RV-V3/V4/V5/V10 tokens tweakcn + escenarios superpuestos + sparklines + acabados (encabezado de tabla fijo, 5 estados) · RV-V6/V7 Fase B del navegador (18→11 entradas, mes como objeto con pestañas) · RV-V8/V9 confianza del dato + bandeja "Por clasificar" con crear-regla | G-TRIVY (npm de librería de gráficos) previo a RV-V3 · G-PIXEL/G-AXE al cierre | ⬜ Pendiente |
| **6** | **Gates finales** (6 gates) | G-SEC (seguridad bloqueante externa) · G-GM (motor-parity-guard required en branch protection) · G-SEMGREP (reglas inviolables) · G-TRIVY (npm) · G-PIXEL (lost-pixel vs mockup) · G-AXE (axe-core en proyección) | — | ⬜ **0/6 pendientes** — ninguno bloqueante hasta go-live; Kimi retroactivo pendiente para TODOS los merges del pipeline (regla del CEO 2026-08-26) |
| **7** | **Backlog (post-plan)** | BK-1 mejoras UI del saldo (② antes→después, ③ puente real/proyectado) — diferidas | — | ⬜ Pendiente |

## 3. Gates y prerrequisitos

| Gate | Cuándo | Debe cumplirse |
|---|---|---|
| Kimi (por PR crítico) | antes de cada merge que toque motor/RBAC/audit/parsers/aprobación/cierre/migraciones | nota ≥ 9.0 + GO CEO; si Kimi ausente (regla vigente 2026-08-26), **gate-waiver del CEO + auditoría retroactiva pendiente** (NUNCA simulado) |
| G-SEC | antes de liberar | segunda revisión de seguridad externa al equipo |
| G-GM | siempre en CI | `golden-master` + `motor-parity-guard` verdes obligatorios; falta marcarlos como *required* en branch protection |
| G-SEMGREP | siempre en CI | reglas inviolables (Decimal, histórico inmutable, ninguna ruta sin auth) fallan el PR |
| G-TRIVY | antes de introducir librería de gráficos (RV-V3) | escaneo npm limpio |
| G-PIXEL | antes de mergear cualquier RV que toque las 2 gráficas principales | chrome-devtools-mcp + lost-pixel contra `docs/design-references/proyeccion-mockup.html` |
| G-AXE | siempre en las vistas de proyección | axe-core sin issues bloqueantes |

**Prerrequisitos / dependencias externas:**
- **Kimi disponible:** hoy AUSENTE ~semanas → gate-waiver GO CEO por cada merge crítico, con paquete `PAQUETE.pdf` preparado por Claude para cuando Kimi vuelva (regla del CEO 2026-08-26).
- **Branch protection en `main`:** falta marcar `golden-master` y `motor-parity-guard` como *required*.
- **Datos de PROD frescos** (Liz): cargas diarias sin gap (movs + caja).
- **Mockup vinculante:** `docs/design-references/proyeccion-mockup.html` — cualquier PR de RV-V2 que se desvíe se rechaza en G-PIXEL.

## 4. Registro de cambios (fechado, append-only)

| Fecha | Bucket | Qué cerró / cambió | Evidencia |
|---|---|---|---|
| 2026-08-27 | F0 | **Fase 0 abierta** en modo crítico. F0-1 `docs/CAPACIDADES.md` (C7/C8/C10/C11 ya estaban ✅ en código; C9 parcial sin pantalla) + F0-2 candado del motor (2 jobs CI: `golden-master` + `motor-parity-guard`) + F0-3 `docs/DESIGN.md` (gramática 8 reglas). Velocímetro inicial con 30 tareas del plan en 5 buckets. | rama `feat/compas-2.0-fase0` (`3bbbde9`) |
| 2026-08-27 | 1 | **RF-F1 MERGEADO a main** — reglas sembradas con patrones reales (`Base real egresos`). ≥90% auto-clasif; cada mov con `clasificada_por/at` + `regla_id`. Motor 0 diffs. | (main) |
| 2026-08-28 | 1 | **RF-F2 MERGEADO a main** — costura presupuesto→proyección con serie versionada (`ProyeccionVersion` = única entidad cuyo ciclo de vida cambia en 2.0). Aprobar mes genera ajustes según D-2 (motor > mes en ejecución, presupuesto ≤ mes en ejecución). | (main) |
| 2026-08-28 | 1 | **RF-F3 MERGEADO a main** — objetivo como regla de valles. Umbral de atención administrable (D-1). Valle como entidad con entrada/fondo/salida/duración; alertas por nivel y por "nuevo/más profundo" vs versión aprobada. Reusa `valles.py`. | (main) |
| 2026-08-29 | 1 | **RF-F4 MERGEADO a main** — `techo_gasto_ventana(mes_inicio, ventana_meses=9, referencia)`. Bandera roja si el valle DENTRO de la ventana perfora la ATENCIÓN (no el mínimo), aunque el horizonte cierre bien. Parametriza `techo_gasto`. | (main) |
| 2026-08-30 | 1 | **RF-F5 MERGEADO a main** — cada valle llega con sus 3 palancas (recorte gasto vía `goal_seek`, ingreso extra vía `goal_seek`, unidades extra = stub honesto `disponible=False` porque el solver de unidades vive en FABS `cfo.calc.escenario.motos_para_evitar_umbral`, síncrono-Mongo, no cabe en el hot-path del cockpit). `_palancas_por_valle` en `proyeccion/service.py`. | `6288c00` |
| 2026-08-30 | 2 | **RF-F6 MERGEADO a main** — cargas idempotentes por huella (antes de que entre Bancolombia en septiembre). Índice único parcial `(banco, id_banco)` con `partialFilterExpression {id_banco: {$type: 'string'}}` + candado adicional `unique(banco, archivo_hash) WHERE estado='completada'`. `DuplicateKeyError`/`RevisionIdWasChanged` → `CargaDuplicadaError` (409 idempotente). | (main) |
| 2026-08-30 | 4 | **RV-V1 MERGEADO a main (PR #123)** — DESIGN.md §3 con paleta como TOKENS. 7 tokens `--color-chart-*` en `frontend/src/index.css` (real/proyectado/escenario + ingreso/gasto-fijo/auteco/otros); categóricos DISJUNTOS del semáforo (regla 9). Tailwind 4 genera utilidades. Test estático `design-tokens.test.ts` = candado en CI (3 checks). Motor/backend 0 cambios. Prerrequisito de RV-V2 cerrado. | `a071d46` |
| 2026-08-30 | 2 | **RF-F7 MERGEADO a main (PR #119)** — recomendaciones por impacto (reparto del recorte por rubro; motor corrido al revés). `reparto_por_rubro` función pura (orden por impacto DESC + regla del 50%). Servicio `_recomendaciones_recorte_por_impacto` reusa `_ejecutados_por_rubro_mes` §1.4.1. Frontend `VallesCard` con botón "ver reparto". Motor 0 diffs, golden-master intacto. **24/24 unit + broad regresión + `npm run build` limpio.** | `62d24d5` |
| 2026-08-30 | 3 | **RF-F8 rebanada A MERGEADO a main (PR #120)** — "negocia esta deuda" simulación compute-only. `simular_negociacion_factura(factura_id, plazo?, fecha?)` reusa `_resultado_con(facturas_override=...)`. Endpoint `POST /obligaciones/{id}/facturas/{fid}/simular` RBAC `dashboard:leer`. Frontend `ObligacionesPage` con botón "Simular negociación" + `NegociarDialog` (visible solo con `plazo_max > plazo_base`). **La rebanada B (persistida) queda para CR-RF-F8-B: requiere evento `factura_obligacion.editada` en el catálogo audit, regla 11 prohíbe inventar eventos sin CR.** | `a24466b` |
| 2026-08-30 | 2 | **RF-F9 MERGEADO a main (PR #121)** — plan de cuentas completo. `RubroCrearBody.codigo:str + tipo:TipoRubro` (sin `\| None`) + validación en `crear_rubro` (422 sin código o vacío, 422 sin tipo). Editar/reactivar NO exigen los nuevos campos (regla es "al CREAR", no reescritura del histórico). Semilla intacta: única excepción legítima sin código sigue siendo `Ajuste de conciliación` (`es_sistema=True`). Frontend `CategoriasPage` con campos `required`. Motor 0 diffs. | `7aebfba` |
| 2026-08-30 | 3 | **RF-F10 MERGEADO a main (PR #122)** — horizonte a 240 meses + agregación por año/trimestre. `HORIZONTE_MAX` 180→240; `proyeccion/agregacion.py::agregar_por_periodo` con semántica STOCK vs FLUJO correcta (`caja_final`=último mes del periodo, `piso`=min, `flujo`/`ingreso_bruto`/`egresos`/`motos`=suma). Endpoint `GET /proyeccion/agregada?granularidad=trimestre\|anual`. Frontend `HorizonteLargoCard` visible solo con horizonte ≥ 60 meses. **CIERRA el alcance FUNCIONAL de COMPAS 2.0 (10/10).** | `ab05af7` |
| 2026-08-30 | 4 | **RV-V2 rebanada 1 MERGEADO a main (PR #124)** — curva de caja principal contra el mockup vinculante (7 de 10 AC). `CurvaCajaRV2.tsx` SVG inline sin librería (Trivy pendiente), consume 23 campos reales de `MesProyeccion`, cero hex hardcodeado (todos por token RV-V1). AC cubiertos: #1 (real+proyectado+ancla), #2 (umbrales+valle+duración), #3 (fondo del valle escrito), #4 (tooltip), #6 (selector `3·6·9·12·15·18·30·42·54·60·120·240` combinado), #9 (color solo estado), #10 (23 campos reales). Reemplaza `<ComposicionCaja>` en `ProyeccionPage`. **Diferidos:** AC #5 (escenario superpuesto), #7 (motos editable), #8 (composición separada) para rebanadas 2 y 3. **12/12 unit + 339/339 suite frontend + `npm run build` limpio.** | `031b1ad` |
| 2026-08-30 | 4 | **RV-V2 rebanada 2 MERGEADO a main (PR #131)** — composición del flujo en gráfica PROPIA (AC #8). `ComposicionFlujoRV2.tsx` SVG inline sin librería implementa `drawComp` del mockup: un mes = un grupo de barras (ingreso arriba positivo · gasto-fijo/Auteco/otros abajo apilados) + línea del flujo neto encima (ink 55% opacity) + línea del cero visible. Los 4 categóricos vienen de tokens RV-V1 (`--color-chart-ingreso/gasto-fijo/auteco/otros`), disjuntos del semáforo (regla 9); cero hex hardcodeado. Mapping concepto→campo por valor absoluto (`|gastos_fijos|`, `|pago_inventario|+|adelanto|+|fondeo|` Auteco, `|gps|+|costo_nueva|+|int_deuda|+|iva|+|aval|` otros). Segunda `ChartCard` en `ProyeccionPage` bajo la curva, con conclusión "De qué está hecho el flujo cada mes" (frase del mockup). **RV-V2 avanza a 8 de 10 AC.** Diferidos: AC #5 (escenario superpuesto) + AC #7 (motos editable, depende de exponer solver de unidades que hoy vive en FABS). **9/9 unit + 348/348 suite frontend + `npm run build` limpio.** | `2e39c04` |
| 2026-08-30 | 4 | **RV-V2 rebanada 3 MERGEADO a main (PR #133) — CIERRA RV-V2 10 de 10 AC.** Backend: 2 endpoints compute-only, motor sin tocar. `POST /proyeccion/con-unidades-extra` corre `_resultado_con` con `motos_base + N` (AC #5 · escenario superpuesto). `POST /proyeccion/solver-unidades` envuelve `resolver_unidades_para_umbral` ya existente en `solver_unidades.py` (bisección entera acotada; RF-F5 lo dejó como stub `disponible=False` porque no cabía en el hot-path — aquí se llama por CLIC EXPLÍCITO, no en cada refresco). Frontend: `CurvaCajaRV2` acepta `escenarioData?` opcional y dibuja LÍNEA punteada verde con `--color-chart-escenario` + ÁREA rellena entre base y escenario (fill-opacity 0.12); escala vmax al mayor de las dos series para no recortar. Cero hex hardcodeado. Nuevo `EscenarioBar` debajo de la curva: input libre editable ANTES de activar (AC #7 «editable antes») + toggle "Activar escenario" + botón «Vender de más» que corre el goal-seek de unidades y, si alcanza, pisa el input y activa el escenario. Motor 0 diffs. **6 backend + 2 frontend + 25/25 broad + 350/350 suite frontend + golden-master intacto + ruff limpio + `npm run build` limpio.** | `c510158` |
| 2026-08-30 | — | **fix test_db MERGEADO (PR #125)** — `DOMAIN_DOCUMENTS == 25` (subió con `PaqueteVigilante` de FABS-VIGILANTE-1 `df3b0b1`). Desbloquea suite backend completo. | `4e9ecd7` |
| 2026-08-30 | 4 | **RV-V2 rebanada 2 CONSTRUIDA, sin merger** — `ComposicionFlujoRV2.tsx` cubre AC #8 (composición del flujo en gráfica propia: ingreso arriba, egresos por concepto abajo apilados, línea de flujo neto). Consume tokens `--color-chart-ingreso/gasto-fijo/auteco/otros` de RV-V1. **9/9 tests pasando** (mapping de conceptos, orden apilado, línea de flujo). Vive en rama `feat/rv-v2-composicion` esperando GO del CEO para abrir PR. | rama `feat/rv-v2-composicion` (`13acd0b`) |
| 2026-08-30 | — | **Regla nueva del CEO:** el tracker `.xlsx` se toca **solo en un PR de cierre después del merge de la feature**, cero clobber posible entre ramas paralelas. Aplicada por primera vez con PR #126 (cierra RF-F7..F10 + RV-V1 Hechas + RV-V2 En curso). | `599fc1b` (PR #126) |
| 2026-08-30 | — | **Regla nueva del CEO (segunda del día):** el velocímetro se lee en **este archivo Markdown** (mismo patrón que `COMPAS_FABS_ROADMAP.md`), no en el Dashboard del `.xlsx`. Motivación: el Dashboard depende de fórmulas Excel + caché + auto-cálculo del usuario — no confiable. Este `.md` se ve al instante en GitHub, cero dependencias. El `.xlsx` queda como base de datos histórica pero NO manda: manda este archivo. Primera versión del velocímetro publicada en PR #129; reescrita al estilo FABS en el PR de este cambio. | (este PR) |

## 5. Estado de datos / decisiones abiertas del CEO

- **Alegra:** CERO en esta fase 2.0 (misma decisión que FABS).
- **Fuera de alcance permanente:** CXC socios, interés presuntivo, devengado/P&L, labores contables (COMPAS NO es ERP).
- **Kimi:** ausente ~semanas → **gate-waiver + GO CEO** por cada merge crítico (regla vigente 2026-08-26). Kimi retroactivo pendiente para: RF-F5..F10, RV-V1, RV-V2 rebanada 1 (paquetes `PAQUETE.pdf` preparados por Claude).
- **Repo público hasta cerrar Fase 0:** privatizar + rotar credenciales = parte del gate G-SEC (memoria `kimi-auditoria-plan-maestro`).
- **Pendientes del CEO:** GO para mergear RV-V2 rebanada 2 (`feat/rv-v2-composicion`); decidir orden de RV-V3..V10 vs. Gates.

## 6. Refinamientos conocidos (para siguientes buckets)

- **RF-F8 rebanada B (persistida)** — requiere abrir CR-RF-F8-B con evento audit nuevo `factura_obligacion.editada`. Regla 11 prohíbe inventar eventos sin CR. No urgente hoy (la simulación cubre el 90% del uso).
- **RV-V2 rebanadas 2 y 3** — rebanada 2 (composición AC #8) YA CONSTRUIDA sin merger; rebanada 3 (escenario superpuesto AC #5 + motos editable AC #7) pendiente. AC #7 depende de exponer `motos_para_evitar_umbral` (hoy stub honesto en RF-F5 con `disponible=False` porque vive en FABS síncrono-Mongo).
- **RV-V3 tokens tweakcn** — los 3 categóricos provisionales (`--color-chart-gasto-fijo` blue-600, `--color-chart-auteco` fuchsia-600, `--color-chart-otros` teal-600) se afinan con tweakcn + verificación de daltonismo antes de cerrar RV-V3.
- **G-GM en branch protection** — hoy los jobs `golden-master` y `motor-parity-guard` existen y corren verdes; falta marcarlos como *required* en branch protection de `main` para que un PR no pueda mergearse sin ellos.
- **CI billing bloqueaba el merge automático** — memoria `ci-actions-billing-bloqueado`; hoy resuelto (el CEO desbloqueó). Merges del pipeline 119..129 hechos con `--admin` (autorización explícita del CEO en chat).

---
*Creado 2026-08-30. Este archivo se actualiza al cerrar cada tarea (no al final del bucket), mismo patrón que `docs/COMPAS_FABS_ROADMAP.md`.*
