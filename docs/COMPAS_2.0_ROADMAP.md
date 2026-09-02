# COMPAS 2.0 — Roadmap · Checklist accionable

> **Qué es:** la fuente única de verdad del avance de COMPAS 2.0. Cada tarea es
> un `- [ ]` (pendiente) o `- [x]` (hecha) con evidencia inline (PR + commit).
> **Manda sobre cualquier otro artefacto:** velocímetro visual, tracker `.xlsx`,
> correos o memoria — si algo lo contradice, gana este archivo.
>
> **Regla de actualización:** cada vez que una tarea cierra, el mismo PR que la
> cierra actualiza este archivo (checkbox + evidencia). Sin excepciones.
>
> **Regla de agregado:** todo hallazgo, hotfix o deuda nueva entra acá como
> checkbox antes de trabajarse. Si no está acá, no existe.

## Norte

Sistema **predictivo** de presupuesto y caja para RODDOS: el CEO no ve la caja
caer bajo sus umbrales sin que la app se lo advierta con anticipación y con las
palancas para evitarlo — **sin sacrificar la paridad al peso del motor**
(golden-master 176 meses).

## Velocímetro · avance ponderado

**Estado 2026-09-02:**

| Bucket | Peso | Hecho | Aporte al total |
|---|---|---|---|
| 1 · Fase 0 (Fundacional + AND) | 8% | 8/8 | 8.00 |
| 2 · Funcional imprescindibles (RF-F1..F5) | 22% | 5/5 | 22.00 |
| 3 · Funcional debería (RF-F6, F7, F9) | 15% | 3/3 | 15.00 |
| 4 · Funcional podría (RF-F8, F10) | 8% | 2/2 | 8.00 |
| 5 · Visual (RV-V1..V10) | 22% | 5/5 | 22.00 |
| 6 · Gates finales (6 gates) | 8% | 6/6 | 8.00 |
| 7 · Infra hotfixes (crisis backend) | 5% | 5/5 | 5.00 |
| 8 · Auditoría Ola 2 (F-03..F-05) | 6% | 1/3 | 2.00 |
| 9 · Deuda funcional descubierta (F-06..F-08) | 4% | 0/3 | 0.00 |
| 10 · Limpieza técnica | 1% | 0/2 | 0.00 |
| BK-1 · Backlog UI del saldo | 1% | 0.5/2 | 0.25 |
| **TOTAL** | **100%** | **35.5 / 39** | **90%** |

**Velocímetro visual:** <https://claude.ai/code/artifact/057cbe89-c263-4194-ae0f-c1b6fba14015>

---

## Bucket 1 · Fase 0 · Andamio del método (8/8 ✅)

- [x] **F0-1** · `docs/CAPACIDADES.md` mapa código→C1..C11 · `3bbbde9`
- [x] **F0-2** · Candado del motor (2 jobs CI: golden-master + motor-parity-guard) · `3bbbde9`
- [x] **F0-3** · `docs/DESIGN.md` gramática 8 reglas + tokens marca · `3bbbde9`
- [x] **AND-1** · SkillSpector checklist pre-instalación (`docs/COMPAS_2.0_AND_1_SKILLSPECTOR.md`) · [PR #139](https://github.com/RoddosColombia/compas/pull/139)
- [x] **AND-2** · ECC `.claude/settings.json` (allow/ask/deny + hooks off + versiones fijadas) · PR #139
- [x] **AND-3** · Skills `spec-miner` + `tdd-guide` (`.claude/skills/`) · PR #139
- [x] **AND-4** · Herramientas declaradas (Browser MCP + tweakcn) · PR #139
- [x] **AND-5** · Candado del método operativo (gates activos en CI) · PR #139

## Bucket 2 · Funcional imprescindibles — must (5/5 ✅)

- [x] **RF-F1** · Reglas sembradas con patrones reales (≥90% auto-clasif) · (main)
- [x] **RF-F2** · Costura presupuesto→proyección con serie versionada (`ProyeccionVersion`) · (main)
- [x] **RF-F3** · Valles como entidad, umbral atención D-1 · (main)
- [x] **RF-F4** · `techo_gasto_ventana(mes_inicio, ventana_meses=9, referencia)` · (main)
- [x] **RF-F5** · 3 palancas por valle (recorte, ingreso extra, unidades stub) · `6288c00`

## Bucket 3 · Funcional debería — should (3/3 ✅)

- [x] **RF-F6** · Cargas idempotentes por huella (índice único parcial) · (main)
- [x] **RF-F7** · Recomendaciones por impacto (reparto por rubro) · [PR #119](https://github.com/RoddosColombia/compas/pull/119) · `62d24d5`
- [x] **RF-F9** · Plan de cuentas completo (código+tipo obligatorios al crear rubro) · [PR #121](https://github.com/RoddosColombia/compas/pull/121) · `7aebfba`

## Bucket 4 · Funcional podría — could (2/2 ✅)

- [x] **RF-F8** · "Negocia esta deuda" rebanada A (simulación compute-only) · [PR #120](https://github.com/RoddosColombia/compas/pull/120) · `a24466b`
- [x] **RF-F10** · Horizonte 240 meses + agregación año/trimestre · [PR #122](https://github.com/RoddosColombia/compas/pull/122) · `ab05af7`

> **RF-F8 rebanada B (persistida):** difierida a `CR-RF-F8-B` — requiere evento
> audit nuevo `factura_obligacion.editada`, regla 11 prohíbe inventar eventos.

## Bucket 5 · Visual (5/5 ✅)

- [x] **RV-V1** · 7 tokens `--color-chart-*` en `frontend/src/index.css` · [PR #123](https://github.com/RoddosColombia/compas/pull/123) · `a071d46`
- [x] **RV-V2 r1** · `CurvaCajaRV2` 7/10 AC · [PR #124](https://github.com/RoddosColombia/compas/pull/124) · `031b1ad`
- [x] **RV-V2 r2** · `ComposicionFlujoRV2` AC #8 · [PR #131](https://github.com/RoddosColombia/compas/pull/131) · `2e39c04`
- [x] **RV-V2 r3** · Escenario superpuesto + «vender de más» AC #5 + #7 · [PR #133](https://github.com/RoddosColombia/compas/pull/133) · `c510158`
- [x] **RV-V3 r1** · 3 tokens categóricos afinados vs daltonismo (blue-700 · fuchsia-800 · amber-900) · [PR #140](https://github.com/RoddosColombia/compas/pull/140) · `0b5b067`
- [x] **RV-V3 r2** · Sparklines de KPI (KpiTileV2 acepta `sparkline?: number[]`) · [PR #141](https://github.com/RoddosColombia/compas/pull/141) · `5008a59`
- [x] **RV-V4** · Escenario superpuesto en `ComposicionFlujoRV2` (línea dashed) · [PR #142](https://github.com/RoddosColombia/compas/pull/142) · `39739b7`
- [x] **RV-V5** · Overlay de escenario en el sparkline (2ª polyline dashed) · PR #142
- [x] **RV-V10** · Encabezado sticky (candado en CI) + 5 estados de fila en `TablaEgreso` · [PR #144](https://github.com/RoddosColombia/compas/pull/144) · `efe4205`
- [x] **RV-V6/V7** · Fase B del navegador (19 → 11 entradas top-level, `Mes` y `Catálogos` colapsables) · [PR #147](https://github.com/RoddosColombia/compas/pull/147) · `e94f653`
- [x] **RV-V8/V9** · Bandeja "Por clasificar" (GET `/reglas-clasificacion/por-clasificar` + `PorClasificarPanel` con crear-regla pre-poblada) · [PR #148](https://github.com/RoddosColombia/compas/pull/148) · `902e66a`

## Bucket 6 · Gates finales (6/6 ✅)

- [x] **G-SEC** · Doc del proceso de revisor externo (`docs/COMPAS_2.0_GATE_SEGURIDAD.md`) · [PR #136](https://github.com/RoddosColombia/compas/pull/136)
- [x] **G-GM** · `golden-master` + `motor-parity-guard` REQUIRED en branch protection · PR #136
- [x] **G-SEMGREP** · 3 reglas inviolables (`.semgrep.yml`) activas en CI · PR #136
- [x] **G-TRIVY** · Escaneo `fs` npm+pip+IaC activo en CI · PR #136
- [x] **G-PIXEL** · Declarado no-activo con proceso de activación (`docs/COMPAS_2.0_GATE_PIXEL.md`) · [PR #137](https://github.com/RoddosColombia/compas/pull/137)
- [x] **G-AXE** · `axe-core` + `vitest-axe` en `ProyeccionPage.a11y.test.tsx` · PR #137 · `6478369`

## Bucket 7 · Infra hotfixes — crisis backend 2026-08-31/09-01 (5/5 ✅)

Cadena de fixes que restauró el backend en producción tras el hang de startup
por Python 3.14 y luego por handshake Atlas lento.

- [x] **HF-1** · Keep-alive cron GitHub Actions (`/health` cada 10 min) · [PR #143](https://github.com/RoddosColombia/compas/pull/143) · `cbaa319`
- [x] **HF-2** · Keep-alive apunta a URL correcta (`api.compas.roddos.com` en vez del servicio Node de onrender) · [PR #146](https://github.com/RoddosColombia/compas/pull/146) · `b5fb85e`
- [x] **HF-3** · Pin Python 3.12.7 vía env var `PYTHON_VERSION` en `render.yaml` · [PR #150](https://github.com/RoddosColombia/compas/pull/150) · `ead0abd`
- [x] **HF-4** · Hard timeout 15s en `ensure_beanie` + startup completo garantizado · [PR #151](https://github.com/RoddosColombia/compas/pull/151) · `c58304b`
- [x] **HF-5** · Log honesto del fallo real + reintento lazy en cada request (middleware ASGI) · [PR #152](https://github.com/RoddosColombia/compas/pull/152) · `16e85f2`

> **Nota infra:** el cluster `sismo-v3.onh5xm` es compartido con SISMO. Hay
> ticket abierto con MongoDB Support por flap de 30 días en `shard-00-01`.
> `w=majority + retryWrites` protege de rollbacks. Decisión pendiente con Iván:
> ¿COMPAS con cluster propio o seguir compartido? Ver
> [[render-startup-hang-fix]] en memoria.

## Bucket 8 · Auditoría Ola 2 — F-03/F-04/F-05 (1/3 🟡)

Hallazgos del artefacto `claude.ai/code/artifact/e6615ca1-a49e-4c9a-8e22-27320d6f538b`
(auditoría independiente contra prod, 2026-09-02). Correcciones que blindan
al sistema para que la próxima degradación de Mongo NO pase 30 días en silencio.

- [x] **F-03** · `/health/ready` honesto — 503 cuando `beanie != up` (los 3 escenarios cubiertos: mongo down / mongo up+beanie pending / ambos up) + `render.yaml` cambia `healthCheckPath` a `/api/v1/health/ready` + timeout duro 3s en `mongo.ping` + middleware lazy PR #152 se salta este endpoint (observacional) · [PR #154](https://github.com/RoddosColombia/compas/pull/154)
- [ ] **F-04** · Cliente HTTP frontend con `AbortSignal.timeout(15000)` + errores tipados (`expired`/`failed`/`unauthorized`) + banner "servicio degradado" cuando readiness falla
- [ ] **F-05** · Single-flight promise para `refresh()` (una sola promesa compartida entre llamados concurrentes; si falla, cerrar sesión limpio en vez de reintentar)

## Bucket 9 · Deuda funcional descubierta — F-06/F-07/F-08 (0/3 ⬜)

Backend construido y desplegado pero **sin UI que lo consuma**. Detectado por
auditoría cruzando 79 llamados del bundle contra 96 rutas del OpenAPI.

- [ ] **F-06** · UI de **Pagos Planeados** — 5 endpoints backend sin pantalla (`GET /meses/{mes}/pagos-planeados`, `GET /meses/{mes}/pagos-semana`, `PATCH /pagos-planeados/{id}`, `POST /pagos-planeados/{id}/cancelar`, `POST /pagos-planeados/{id}/marcar-pagado`)
- [ ] **F-07** · UI de **enrolamiento MFA** — `POST /auth/mfa/setup` y `POST /auth/mfa/activate` sin pantalla (login pide código pero un usuario nuevo no tiene cómo enrolarse)
- [ ] **F-08** · Botón **reabrir mes** — `POST /meses/{mes}/reabrir` sin UI (si el CEO cierra un mes por error hoy no hay vuelta atrás desde la app)

## Bucket 10 · Limpieza técnica (0/2 ⬜)

Deuda técnica de los hotfixes de la crisis. Cero riesgo, valor de higiene.

- [ ] **LT-1** · Quitar prints `[lifespan] A0..A11` de `backend/app/main.py` (ya cumplieron su función diagnóstica; el timeout de 15s + reintento lazy + log de excepciones se quedan como salvaguardas perpetuas)
- [ ] **LT-2** · Eliminar `backend/runtime.txt` (Render lo ignora — el pin ahora vive en `PYTHON_VERSION` env var; queda como archivo muerto en el repo)

## Bucket 11 · Backlog (post-plan) · BK-1 (½ hecho)

- [x] **BK-1 ②** · Δ vs. inicio del mes en el tile "Caja hoy" de Inicio · [PR #149](https://github.com/RoddosColombia/compas/pull/149) · `417043a`
- [ ] **BK-1 ③** · Puente real/proyectado como barra visual en `MesStatusBar` (backlog explícito — requiere diseño más pensado)

---

## Gates y prerrequisitos

| Gate | Cuándo | Debe cumplirse |
|---|---|---|
| **Kimi** (por PR crítico) | antes de cada merge que toque motor/RBAC/audit/parsers/aprobación/cierre/migraciones | nota ≥ 9.0 + GO CEO. **Kimi ausente ~semanas (regla 2026-08-26):** gate-waiver del CEO + auditoría retroactiva pendiente. NUNCA simulado |
| **G-SEC** | antes de liberar | Segunda revisión de seguridad externa al equipo |
| **G-GM** | siempre en CI | `golden-master` + `motor-parity-guard` verdes, REQUIRED en branch protection |
| **G-SEMGREP** | siempre en CI | 3 reglas inviolables (Decimal / audit-log append-only / ruta sin auth) |
| **G-TRIVY** | antes de introducir librería npm | Escaneo `fs` limpio |
| **G-PIXEL** | antes de mergear cualquier RV que toque las 2 gráficas principales | `chrome-devtools-mcp` + `lost-pixel` vs `docs/design-references/proyeccion-mockup.html` (activación pendiente de GO CEO) |
| **G-AXE** | siempre en las vistas de proyección | `axe-core` sin issues bloqueantes |

**Prerrequisitos externos:**

- **Kimi disponible:** HOY AUSENTE ~semanas → gate-waiver GO CEO por cada merge crítico, con `PAQUETE.pdf` preparado por Claude para cuando Kimi vuelva.
- **Branch protection en `main`:** `golden-master` + `motor-parity-guard` marcados como REQUIRED (HF activo).
- **Ticket MongoDB Support** por `sismo-v3-shard-00-01` flap · abierto por el CEO 2026-09-01.
- **Datos de PROD frescos** (Liz): cargas diarias sin gap (movs + caja).
- **Mockup vinculante:** `docs/design-references/proyeccion-mockup.html` — cualquier PR de RV que se desvíe se rechaza en G-PIXEL.

## Estado de datos / decisiones abiertas del CEO

- **Alegra:** CERO en esta fase 2.0 (misma decisión que FABS).
- **Fuera de alcance permanente:** CXC socios, interés presuntivo, devengado/P&L, labores contables (COMPAS NO es ERP).
- **Kimi retroactivo pendiente para:** RF-F5..F10, RV-V1, RV-V2 rebanadas 1/2/3, RV-V3 r1/r2, RV-V4/V5, RV-V6/V7, RV-V8/V9, RV-V10, BK-1 ②, HF-1..HF-5. Paquetes `PAQUETE.pdf` preparados por Claude.
- **Repo público hasta cerrar Fase 0:** privatizar + rotar credenciales = parte del gate G-SEC.
- **Cluster compartido con SISMO:** decisión pendiente (cluster propio para COMPAS vs seguir compartido) — discutir con Iván tras estabilizar el ticket con Support.
- **F-06 Pagos Planeados:** decidir si entra al alcance o se marca como pendiente explícito (5 endpoints sin UI hoy).

## Registro de cambios (append-only, más reciente arriba)

| Fecha | Bucket | Cambio | Evidencia |
|---|---|---|---|
| 2026-09-02 | — | **Roadmap convertido a checklist accionable + rebalanceo de pesos.** Se agregaron 3 buckets nuevos con scope descubierto: Bucket 7 (infra hotfixes), Bucket 8 (auditoría Ola 2 F-03..F-05), Bucket 9 (deuda funcional F-06..F-08), Bucket 10 (limpieza técnica). Pesos rebalanceados de 5→11 buckets. Total ahora refleja realidad ampliada: 88% ponderado con 34.5/39 tareas hechas (contra 99% anterior en scope estrecho). | (este PR) |
| 2026-09-01 | 7 | HF-5 · Log honesto de Beanie + reintento lazy | PR #152 · `16e85f2` |
| 2026-09-01 | 7 | HF-4 · Hard timeout 15s en `ensure_beanie` + prints diagnóstico | PR #151 · `c58304b` |
| 2026-09-01 | 7 | HF-3 · `PYTHON_VERSION=3.12.7` env var | PR #150 · `ead0abd` |
| 2026-09-01 | 5 | **BK-1 rebanada ②** · Δ vs. inicio del mes en tile "Caja hoy" | PR #149 · `417043a` |
| 2026-09-01 | 5 | **RV-V8/V9** · Bandeja Por clasificar + crear-regla pre-poblada · CIERRA bucket visual 5/5 | PR #148 · `902e66a` |
| 2026-09-01 | 5 | **RV-V6/V7** · Fase B del navegador 19 → 11 entradas | PR #147 · `e94f653` |
| 2026-09-01 | 7 | HF-2 · Keep-alive apunta a URL correcta | PR #146 · `b5fb85e` |
| 2026-08-31 | 7 | HF-1 · Keep-alive cron backend (posteriormente corregido en HF-2) | PR #143 · `cbaa319` |
| 2026-08-31 | 5 | **RV-V10** · Encabezado sticky + 5 estados de fila | PR #144 · `efe4205` |
| 2026-08-31 | 5 | **RV-V4 + RV-V5** · Escenarios superpuestos en composición + sparkline | PR #142 · `39739b7` |
| 2026-08-31 | 5 | **RV-V3 r2** · Sparklines de KPI | PR #141 · `5008a59` |
| 2026-08-31 | 5 | **RV-V3 r1** · 3 tokens categóricos vs daltonismo | PR #140 · `0b5b067` |
| 2026-08-31 | 1 | **AND-1..5** · CIERRA Fase 0 (8/8) | PR #139 |
| 2026-08-31 | 6 | **Gates 5..10** · G-SEMGREP + G-TRIVY + G-AXE + G-SEC + G-GM + G-PIXEL — CIERRA 6/6 | PRs #136 · #137 |
| 2026-08-30 | 4 | **RV-V2 rebanada 3** · CIERRA RV-V2 10/10 AC | PR #133 · `c510158` |
| 2026-08-30 | 4 | **RV-V2 rebanada 2** · Composición del flujo AC #8 | PR #131 · `2e39c04` |
| 2026-08-30 | 4 | **RV-V2 rebanada 1** · Curva de caja 7/10 AC | PR #124 · `031b1ad` |
| 2026-08-30 | 4 | **RV-V1** · 7 tokens de gráfico | PR #123 · `a071d46` |
| 2026-08-30 | 3 | **RF-F10** · Horizonte 240 + agregación · CIERRA FUNCIONAL 10/10 | PR #122 · `ab05af7` |
| 2026-08-30 | 3 | **RF-F8 rebanada A** · Simular negociación | PR #120 · `a24466b` |
| 2026-08-30 | 2 | **RF-F9** · Plan de cuentas completo | PR #121 · `7aebfba` |
| 2026-08-30 | 2 | **RF-F7** · Recomendaciones por impacto | PR #119 · `62d24d5` |
| 2026-08-30 | 2 | **RF-F6** · Cargas idempotentes por huella | (main) |
| 2026-08-30 | 1 | **RF-F5** · 3 palancas por valle | `6288c00` |
| 2026-08-29 | 1 | **RF-F4** · Techo de gasto en ventana | (main) |
| 2026-08-28 | 1 | **RF-F3** · Valles como entidad | (main) |
| 2026-08-28 | 1 | **RF-F2** · Costura versionada presupuesto→proyección | (main) |
| 2026-08-27 | 1 | **RF-F1** · Reglas sembradas | (main) |
| 2026-08-27 | 0 | **Fase 0 abierta** · F0-1 CAPACIDADES.md + F0-2 candado motor + F0-3 DESIGN.md | `3bbbde9` |

---

*Última actualización: 2026-09-02. Este archivo es la fuente única del avance
de COMPAS 2.0. Cada tarea se actualiza en el mismo PR que la cierra.*
