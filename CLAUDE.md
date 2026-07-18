# CLAUDE.md — COMPAS

Sistema de control presupuestal y flujo de caja de RODDOS S.A.S. Este archivo lo lee Claude Code al inicio de CADA sesión. Las reglas de aquí son innegociables.

## Fuente de verdad
Los documentos en `/docs` son el contrato. Ante cualquier duda, leerlos ANTES de escribir código:
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
11. **Eventos de auditoría:** catálogo cerrado de 30 (29 del Spec §1.11 + `extracto.cargado` de CR-001). No inventar eventos nuevos sin CR.
12. **Ningún secreto en el repo.** gitleaks corre en CI y bloquea. Fixtures bancarios solo anonimizados.

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
