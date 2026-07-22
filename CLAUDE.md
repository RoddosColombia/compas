# CLAUDE.md — COMPAS

Sistema de control presupuestal y flujo de caja de RODDOS S.A.S. Este archivo lo lee Claude Code al inicio de CADA sesión. Las reglas de aquí son innegociables.

## Principio rector (decisión CEO)
**Hacerle fácil la vida a Andrés (CEO, desarrollador solo) para construir esto.** En concreto:
- **Un solo entorno mientras desarrollamos**, con auto-deploy desde `main` (push = vivo) y una sola base `compas` aprovisionada una vez con scripts idempotentes. El endurecimiento de producción (tag `v*` + reviewer + `compas-api-stg` al lado) es tarea de **go-live**, no de ahora — queda documentado, no borrado.
- **Minimizar el trabajo manual del CEO:** Claude hace el trabajo pesado (aprovisionar, scripts, tracker, PRs, preparar los paquetes Kimi). Andrés decide y corre el loop manual de Kimi solo en merges realmente críticos.
- Ante dos caminos, elegir el de menos fricción y menos pasos manuales para el CEO — **sin** sacrificar las reglas innegociables de dinero/auditoría/seguridad de abajo.

## Norte del producto (LEER PRIMERO — prevalece sobre alcance)
COMPAS es un **sistema PREDICTIVO e inteligente para administrar el presupuesto mensual y proyectar la caja**, para tomar decisiones presupuestales (objetivo inmediato: superar el umbral de caja de mayo-2027; largo plazo: objetivos de venta para sostenibilidad, fecha exacta de pago a proveedores, IVA mínimo, proyecciones de deuda/inversión). **NO es un sistema contable.** El ciclo presupuestal es el CIMIENTO que alimenta la predicción, no el fin. Toda la data es **persistente desde el inicio**. Detalle completo y no negociable en **`docs/COMPAS_NORTE.md`** — ante cualquier decisión de alcance, ese doc manda.

## Fuente de verdad
Los documentos en `/docs` son el contrato. Ante cualquier duda, leerlos ANTES de escribir código:
- `docs/COMPAS_NORTE.md` — **el norte del producto (qué ES y qué NO); prevalece sobre todo lo demás en alcance**
- `docs/COMPAS_Discovery_PRD_v1_1_2.docx` — qué se construye (módulos M1–M13)
- `docs/COMPAS_Spec_Tecnica_v1_1_2.docx` — data dictionary, reglas de integridad, API, DoD de 12 puntos
- `docs/COMPAS_STACK_v1_1_2.docx` — stack, infraestructura, seguridad
- `docs/COMPAS_PLAN_TRABAJO_v1_1_2.docx` — sprints, gates, criterios
- `docs/COMPAS_CR-001_Extractos.docx` — extractos mensuales (Sprint 4)
- `docs/RUNBOOK-INFRA.md` y `render.yaml` — aprovisionamiento
- `docs/Calendario_DIAN_2026.md` — semilla de la clave CALENDARIO_DIAN

## Reglas innegociables (violarlas = PR rechazado)
1. **Dinero = Decimal, nunca float.** Backend: `decimal.Decimal` COP 2 decimales. API: montos como string. Frontend: decimal.js-light, NUNCA `Number` sobre montos; formato solo con `Intl.NumberFormat('es-CO')`. Todo cálculo financiero vive en el backend.
2. **Zona horaria única América/Bogotá** (`now_bogota()`). Fechas `YYYY-MM-DD`; meses normalizados al día 1.
3. **Pydantic strict=True en todo.** Ningún dict sin schema; campos no definidos se rechazan.
4. **El histórico es inmutable.** Meses cerrados no se editan (salvo tardías `tardia=true`). `audit_log` es append-only: existe un test en CI que verifica que update/remove FALLA.
5. **Deduplicación en la base de datos:** índice único parcial `(banco, id_banco)` con `partialFilterExpression {id_banco: {$type: 'string'}}`. Manuales: `id_banco = 'MAN-' + ULID`.
6. **`RUN_SCHEDULER=false` en el servicio web, SIEMPRE.** Los jobs viven solo en el worker `compas-jobs` (1 instancia). Todo job es idempotente (snapshot = UPSERT por fecha).
7. **Los parsers transforman, nunca interpretan.** Fila ambigua = error reportado en la carga, jamás adivinado. Global66 conserva moneda_original + tasa_cambio.
8. **Transacciones multi-documento de MongoDB** en los 3 flujos: aprobación de presupuesto, finalización de carga, cierre de mes.
9. **RBAC por dependencia FastAPI** según la matriz del Spec §4.1. La tabla de autoridad §2.4 manda sobre cualquier otra redacción. Navbar del frontend derivado de un único config de permisos.
10. **Fórmula del sugerido = la del Excel, exacta** (Spec §1.4.1): prom_3m + tendencia + prom_3m × crec_pct. Los compromisos programados son fila informativa, NO entran en la fórmula. Todas las líneas en `modo_calculo='historico'` (el modo ventas es Fase 1.5).
11. **Eventos de auditoría:** catálogo cerrado de 31 (29 del Spec §1.11 + `extracto.cargado` de CR-001 + `transaccion.creada` de CR-S2, exigida por Kimi M-1 sprint2-cargas). No inventar eventos nuevos sin CR.
12. **Ningún secreto en el repo** — EXCEPTO `docs/INVENTARIO-SECRETOS.xlsx`, que por **decisión del CEO** (2026-07-20; repo privado, sin cara al público) guarda los valores reales de secretos y está en el allowlist de gitleaks. Se acepta que esos valores queden en el historial de git (sacarlos exigiría rotarlos) y que el repo NO se haga público sin revisarlo. gitleaks corre en CI y bloquea todo lo demás. Fixtures bancarios solo anonimizados.

## Estructura
```
backend/   → FastAPI + Beanie/Motor (Python 3.12). app/main.py, app/jobs/scheduler.py
frontend/  → React 19 + Vite + TS + Tailwind 4 + shadcn/ui. Rutas /:mes/:vista
docs/      → los documentos contractuales
migrations/→ scripts idempotentes fechados (20260901_seed_rubros.py)
```

## Convenciones
- API bajo `/api/v1`, paginación limit/cursor, Idempotency-Key en POST sensibles (scope: usuario+endpoint+key).
- TanStack Query keys: `['mes', 'YYYY-MM', vista]`; invalidar tras toda mutación financiera (refresca badges).
- Conventional Commits. Trunk-based, ramas cortas. Merge a main = deploy a staging; producción SOLO por tag v* con reviewer (Iván).
- Tests: pytest (backend), Vitest+RTL (frontend), Playwright (flujo crítico), k6 (carga, DoD-9).
- Demo de cada sprint con datos reales de RODDOS, nunca datos de juguete.

## Contexto de negocio mínimo
RODDOS vende motos a cuotas semanales (Raider, Sport, Apache). 5 grupos de rubros: Costo de producto, Operación, Nómina, Deudas y obligaciones, Otros. Bancos: Bancolombia, BBVA, Global66 (los parsers se portan de SISMO v2). Carga diaria 8:30. IVA cuatrimestral (NIT 901012622-1, dígito 2: 13-may-26, 10-sep-26, 14-ene-27). Usuario inicial: andres@roddos.com (superadmin); segunda cuenta: Iván.

## Qué NO hacer
- No microservicios, no GraphQL, no Docker (Render hace el build), no localStorage para tokens (access en memoria, refresh en cookie HttpOnly).
- No agregar alcance sin CR: el patrón del proyecto es declarar ANTES de construir (lección de la auditoría — ver histórico de versiones en los docs).
- No tocar la lógica de un mes cerrado ni "corregir" el histórico en migraciones.

## Cierre de sesión (obligatorio)
Al terminar cada sesión de trabajo: (1) actualiza docs/COMPAS_Control_Desarrollo.xlsx con openpyxl — busca la fila de la tarea en la hoja 'Tareas' por su ID, cambia Estado (Hecha/En curso/Bloqueada), pon Fecha cierre (YYYY-MM-DD) y en Evidencia el hash del commit o PR; NO toques encabezados, fórmulas del Dashboard ni las validaciones de datos; (2) si el trabajo cerró un punto del DoD o un Gate, actualiza esa hoja también; (3) commit del Excel junto con el código de la sesión. Si una tarea nueva no existe en el tracker, agrégala como fila nueva siguiendo el formato de las existentes en vez de construir sin registro.

## Auditoría adversarial con Kimi (obligatorio antes de merge crítico)
Procedimiento portado de SISMO-V3. Kimi es **auditor adversarial externo**: revisa ANTES de todo merge crítico y **NO genera código**. No reemplaza al par revisor humano (Iván) ni al CI; es una capa adicional.

- **Alcance (gate obligatorio):** (1) el **PLAN** de cada sprint/sesión crítica ANTES de construir; (2) los **PRs críticos**: auth/RBAC/audit log, parsers/cargas bancarias, aprobación de presupuesto, cierre de mes, y migraciones de datos reales. Lo no-crítico no requiere gate.
- **Umbral:** **≥ 9.0** (plan y código). Merge solo con nota ≥ 9.0 + autorización del CEO. RECHAZO o nota < 9.0 bloquea el merge.
- **Rondas:** `I` (inicial) → `R` (re-auditoría tras resolver hallazgos) → `R…B` si hace falta otra vuelta, hasta alcanzar el umbral.
- **Artefactos — UNA carpeta por ronda, autocontenida.** Cada intercambio con Kimi vive en `planning/phases/<fase>/auditorias/<TARGET>-<RONDA>/` (TARGET ∈ `PLAN|PR1|PR2|PR3`, RONDA ∈ `I|R|R2…`), con nombres FIJOS:
  - `SOLICITUD.md` — lo escribe Claude.
  - `EVIDENCIA.md` — solo en PRs de código (diff + tests reales).
  - `PAQUETE.pdf` — lo genera Claude; **es el que Andrés sube a Kimi**.
  - `RESPUESTA.md` — Andrés pega la respuesta de Kimi. `CERTIFICADO.md` si hay un cierre/GO aparte.
  Formato de SOLICITUD/RESPUESTA en `planning/TEMPLATES/`. NO usar nombres ad-hoc ni `docs/audits/`.
- **Entrega (loop manual):** `python scripts/generate_kimi_audit_pdf.py <carpeta-ronda>/SOLICITUD.md [<carpeta-ronda>/EVIDENCIA.md]` → escribe `<carpeta-ronda>/PAQUETE.pdf` (SOLICITUD [+ EVIDENCIA] + extracto del tracker). Andrés sube ese PDF a Kimi y pega la respuesta en `RESPUESTA.md` de la misma carpeta. Kimi no tiene CLI/API en este entorno.
- **La SOLICITUD debe traer evidencia, no promesas:** qué hace, cambios de valores verificados "al peso", semántica preservada, puntos a auditar con lupa, y evidencia local (pytest/ruff/build verdes). **En auditorías de PR (código), el PDF DEBE incluir los archivos/diff reales + las salidas de tests** (una descripción no es evidencia; Kimi da NO-GO por evidencia si falta el código).
- **Regla de oro:** ningún merge crítico sin `AUDITORIA-KIMI ≥ 9.0` registrada; el resultado del gate se anota en la hoja 'Gates' del tracker.
