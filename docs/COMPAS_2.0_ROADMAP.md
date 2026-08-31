# COMPAS 2.0 — Roadmap de desarrollo (velocímetro)

> **Qué es:** el artefacto de control **ÚNICO** del avance de COMPAS 2.0.
> Muestra la evolución tarea a tarea en el tiempo, no solo la foto de hoy. **Manda sobre
> cualquier presentación, tracker XLSX o correo:** si algo lo contradice, gana este
> archivo.
>
> **Mecánica de actualización (regla del CEO 2026-08-30):** se actualiza **tan pronto
> cierra cada tarea** — en el MISMO PR que la mergea, o en un PR chico separado si el
> PR original ya está mergeado. Cada cambio queda **fechado** en el Registro de cambios
> (§7). Se lee en GitHub o en cualquier editor Markdown, cero dependencias.
>
> **Por qué reemplaza al Dashboard del XLSX:** el Excel dependía de que el CEO abriera
> el archivo con auto-cálculo encendido y sin caché vieja — no era confiable. Este `.md`
> se ve al instante en el navegador y no tiene fórmulas. Ver el patrón espejo en
> `docs/COMPAS_FABS_ROADMAP.md` (mismo estilo, para FABS).

## 1 · Norte de COMPAS 2.0 (una línea)

Sistema **PREDICTIVO** de presupuesto y caja para RODDOS: el CEO no ve la caja caer bajo
sus umbrales sin que la app se lo diga con anticipación y con las palancas para evitarlo.
Documento base: `docs/COMPAS_2.0_FUNDACIONAL.md`.

## 2 · Velocímetro (foto de hoy)

Estado: ⬜ Pendiente · 🔄 En curso · ✅ Hecho · 🔒 Bloqueado

| Bucket | ✅ Hechas | 🔄 En curso | ⬜ Pending | Total | % avance |
|---|---:|---:|---:|---:|---:|
| **2.0 · Fase 0** (andamio) | 3 | 0 | 5 | 8 | 38% |
| **2.0 · Funcional** (RF-F1..F10) | **10** | 0 | 0 | **10** | **100%** ✅ |
| **2.0 · Visual** (RV-V*) | 1 | 1 | 3 | 5 | 20% |
| **2.0 · Gates** (6 gates) | 0 | 0 | 6 | 6 | 0% |
| **2.0 · Backlog** | 0 | 0 | 1 | 1 | 0% |
| **TOTAL 2.0** | **14** | **1** | **15** | **30** | **46.7%** |

Actualizado por última vez: **2026-08-30** (con base en `origin/main`).

## 3 · Alcance funcional (RF-F1..F10) — **CIERRA 10/10 ✅**

| # | Historia | Estado | En main desde |
|---|---|---|---|
| RF-F1 | Reglas sembradas con patrones reales | ✅ Hecho | 2026-08-27 |
| RF-F2 | Costura presupuesto → proyección (versionada) | ✅ Hecho | 2026-08-28 |
| RF-F3 | Objetivo como regla de valles (umbral atención) | ✅ Hecho | 2026-08-28 |
| RF-F4 | Techo de gasto en ventana | ✅ Hecho | 2026-08-29 |
| RF-F5 | Solvers en la app (3 palancas por valle) | ✅ Hecho | `6288c00` |
| RF-F6 | Cargas idempotentes por huella | ✅ Hecho | 2026-08-30 |
| RF-F7 | Recomendaciones por impacto (reparto por rubro) | ✅ Hecho | `62d24d5` (PR #119) |
| RF-F8 | Obligaciones factura a factura — rebanada A (simular) | ✅ Hecho | `a24466b` (PR #120) |
| RF-F9 | Plan de cuentas completo (código + clase obligatorios) | ✅ Hecho | `7aebfba` (PR #121) |
| RF-F10 | Horizonte 240 meses + agregación por año/trimestre | ✅ Hecho | `ab05af7` (PR #122) |

**Nota RF-F8**: la rebanada A (simulación compute-only) está en main. La rebanada B
(persistencia de la renegociación con evento audit nuevo) queda para CR-RF-F8-B, no
cuenta como pendiente del funcional 2.0.

## 4 · Alcance visual (RV-V1..V10) — 1/5 hecho + 1 en curso

| # | Historia | Estado | Nota |
|---|---|---|---|
| RV-V1 | DESIGN.md + tokens de gráficos (`--color-chart-*`) | ✅ Hecho | `a071d46` (PR #123). Prerrequisito de RV-V2. |
| RV-V2 | Rehacer las 2 gráficas principales (mockup vinculante) | 🔄 En curso | Rebanada 1 (curva) ✅ mergeada (`031b1ad`, PR #124, 7 de 10 AC). Rebanada 2 (composición separada, AC #8) construida en branch `feat/rv-v2-composicion`, sin merger. Rebanada 3 (AC #5 escenario superpuesto + #7 motos editable) pendiente. |
| RV-V3/V4/V5/V10 | Tokens tweakcn, escenarios superpuestos, sparklines, acabados | ⬜ Pending | Bloque should |
| RV-V6/V7 | Fase B del navegador con contadores de estado | ⬜ Pending | Bloque should |
| RV-V8/V9 | Confianza del dato + bandeja «Por clasificar» | ⬜ Pending | Bloque should |

## 5 · Gates (6) — **0/6, todos pendientes**

Ninguno bloqueante hasta go-live. Kimi está ausente ~semanas → **gate-waiver + GO CEO**
por cada merge crítico (regla vigente 2026-08-26). Kimi retroactivo pendiente para
TODOS los PRs de este pipeline (RF-F5..F10, RV-V1, RV-V2 r1).

| # | Gate | Qué exige |
|---|---|---|
| G-SEC | Seguridad bloqueante antes de liberar | Segunda revisión de seguridad externa al equipo. ⬜ |
| G-GM | Golden-master del motor en CI (verde obligatorio) | Ya existe el job; falta marcar `motor-parity-guard` como required en branch protection. ⬜ |
| G-SEMGREP | Reglas inviolables fallando el PR | Decimal, histórico inmutable, ninguna ruta sin auth. ⬜ |
| G-TRIVY | Escaneo npm antes de introducir librería de gráficos | Requisito para RV-V3 (tweakcn). ⬜ |
| G-PIXEL | chrome-devtools-mcp + lost-pixel contra el mockup | Un PR de gráficos que desvíe RV-V2 del mockup no se fusiona. ⬜ |
| G-AXE | axe-core en las vistas de proyección | Accesibilidad. ⬜ |

## 6 · Fase 0 · Andamio (AND-1..5) — 3/8 hecho

`F0-1/F0-2/F0-3` cerrados (CAPACIDADES.md · candado del motor con 2 jobs CI · DESIGN.md).
Las 5 tareas `AND-1..5` (SkillSpector, AgentShield, permisos, etc.) siguen pendientes;
son prerrequisito operacional del go-live, no bloquean el desarrollo de features.

## 7 · Registro de cambios (fechado, append-only)

| Fecha | Evento | Evidencia |
|---|---|---|
| 2026-08-27 | RF-F1 mergeado a main | `62d24d5` (proceso previo al pipeline de esta sesión) |
| 2026-08-28 | RF-F2, RF-F3 mergeados | (main, cierre incremental) |
| 2026-08-29 | RF-F4 mergeado | (main) |
| 2026-08-30 | RF-F5 mergeado (palancas por valle) | `6288c00` |
| 2026-08-30 | RF-F6 mergeado (huella idempotente) | (main) |
| 2026-08-30 | **Pipeline de cierre funcional** — 6 PRs mergeados en un solo turno: | — |
| — | · #125 fix test_db (PaqueteVigilante) | `4e9ecd7` |
| — | · #123 RV-V1 tokens de gráficos | `a071d46` |
| — | · #119 RF-F7 reparto por rubro | `62d24d5` |
| — | · #120 RF-F8 rebanada A (simular negociación) | `a24466b` |
| — | · #121 RF-F9 plan de cuentas completo | `7aebfba` |
| — | · #122 RF-F10 horizonte 240 + agregación | `ab05af7` — **CIERRA funcional 10/10** |
| — | · #124 RV-V2 rebanada 1 (curva de caja, 7 de 10 AC) | `031b1ad` |
| 2026-08-30 | Regla del CEO: el tracker XLSX se toca **solo en un PR de cierre después del merge**, para prevenir clobber entre ramas paralelas | PR #126 (`599fc1b`) |
| 2026-08-30 | Fix: el velocímetro del Dashboard estaba en caché (`None`) porque openpyxl no ejecuta fórmulas Excel al guardar. Añadido `fullCalcOnLoad=True`. También fix del char en RV-V1 (en-dash → middle dot). | PR #127 (`4087ed0`) |
| 2026-08-30 | Fix: RF-F5 estaba mergeado en main pero seguía como Pendiente en la fila del tracker | PR #128 (`851beb6`) |
| 2026-08-30 | **Este archivo creado** — reemplaza al Dashboard del XLSX como fuente única del velocímetro, para no depender de Excel + caché | (este PR) |

## 8 · Cómo actualizar este archivo

**Al mergear una nueva feature 2.0**, en el mismo PR (o en uno chico separado si ya
está mergeado):

1. Cambia la fila de esa tarea en §3/§4/§5/§6 a ✅ con el commit de main.
2. Recalcula los contadores del velocímetro §2 (14→15, 46.7%→50%, etc.).
3. Añade una línea al Registro de cambios §7 con la fecha, evento y evidencia.

**Nada más.** El XLSX puede quedar como backup histórico, pero no manda: manda este `.md`.
