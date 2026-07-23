# COMPAS — ROADMAP.md (fases GSD)

> Derivado de `.planning/PROJECT.md` §3 (capacidades C1–C11) y `docs/COMPAS_NORTE.md`.
> **No introduce alcance nuevo.** Ante duda de alcance: NORTE.md + PROJECT.md mandan.
> Fijado con el CEO: 2026-07-22.

## Norte (por qué existen estas fases)
COMPAS es **predictivo**, NO contable. El ciclo presupuestal (Fases 0–6, ya en prod)
es el **cimiento** que captura la ejecución real; el **valor** es la capa predictiva
(C7). Objetivo inmediato: **superar el umbral de caja de mayo-2027**.

## Definition of Done (DoD) — aplica a TODA fase crítica
Una fase crítica no se da por cerrada sin:
1. **Reglas innegociables** de `CLAUDE.md` respetadas (Decimal, TZ Bogotá, Pydantic
   strict, histórico inmutable, dedup DB, RBAC, Alegra API, etc.).
2. **TDD** en todo lo que toque MongoDB / parsers / webhooks (test rojo → verde).
3. **Gate Kimi ≥ 9.0** registrado en `planning/phases/<fase>/auditorias/<TARGET>-<RONDA>/`
   — PLAN antes de construir; PR crítico antes de merge — + autorización del CEO.
4. **Tracker** `docs/COMPAS_Control_Desarrollo.xlsx` actualizado (Estado, Fecha
   cierre, Evidencia = hash/PR) y hoja 'Gates' si aplica.
5. CI verde (pytest / vitest / gitleaks / commit protocol).

Fases **críticas** (requieren gate Kimi): auth/RBAC/audit, parsers/cargas,
aprobación de presupuesto, cierre de mes, migraciones de datos reales. C1/C3/C4
tocan MongoDB y reglas de clasificación → tratadas como críticas por seguridad.

---

## FASES COMPLETADAS (en prod, con gate Kimi en los merges críticos)

- **F0 — Auth / RBAC / MFA / Audit log** ✅ — JWT+MFA, matriz RBAC Spec §4.1,
  `audit_log` append-only. (`planning/phases/sprint0-auth-rbac-audit`, `sprint0b-dominio-mfa`)
- **F1 — Parsers bancarios** ✅ — Bancolombia / BBVA / Global66 (portados de SISMO v2).
  (`planning/phases/sprint1-parsers`)
- **F2 — Cargas (backend) + transacciones** ✅ — upload, dedup DB, `transaccion.creada`.
  (`planning/phases/sprint2-cargas`)
- **F3 — Ciclo presupuestal** ✅ — apertura de mes, motor del sugerido (§1.4.1),
  acotar + aprobar. (`sprint3-ciclo`, `sprint3-motor`, `sprint3-acotar-aprobar`)
- **F4 — Cierre + conciliación + Vista Control** ✅ — cierre de mes, conciliación por
  banco, reapertura, Vista Control (back+front). (`sprint4-cierre-conciliacion`,
  `sprint4-vista-control`) — GO Kimi I-PR1 9.4.

> Corresponden a C2, C4(parcial), C5(parcial), C6. La CI/infra (G1, sesión3) también cerrada.

---

## FASES PENDIENTES (orden = prioridad del CEO — el corazón operativo primero)

### FASE 7 — C1: Categorías administrables (CRUD de rubros)  ⏳ EN GATE
- **Objetivo:** crear/editar/desactivar rubros desde la app (hoy solo semilla, sin CRUD).
- **Requisitos:** modelo de rubro con Pydantic strict; RBAC (quién administra);
  no romper histórico ni Vista Control; taxonomía real de `docs/modelo/MODELO.md`.
- **Éxito:** el CEO administra categorías desde la UI; la semilla queda como estado inicial.
- **Gate:** PLAN-I ya empaquetado en `planning/phases/sprint4-categorias/auditorias/PLAN-I/`
  (SOLICITUD + PAQUETE.pdf). **Falta `RESPUESTA.md` de Kimi ≥9.0 para desbloquear código.**

### FASE 8 — C3: Auto-clasificación de movimientos al cargar
- **Objetivo:** clasificar movimientos a su categoría al cargar, con **reglas
  administrables** (hoy todo → 'Por clasificar').
- **Requisitos:** semilla de reglas desde el mapeo categoría→rubro de `Base real egresos`;
  parser transforma, no interpreta (fila ambigua = 'Por clasificar', jamás adivinada).
- **Éxito:** la mayoría de movimientos entran clasificados; reglas editables desde la app.

### FASE 9 — C4(resto): Ajuste diario de caja disponible
- **Objetivo:** editar/ajustar la caja disponible a diario para que la info **cuadre**
  (conciliación viva). Completa lo que falta de C4.
- **Éxito:** el CEO corrige la caja y la proyección se re-cuadra; queda auditado.

### FASE 10 — C5(resto): Vista combinada categoría × cuenta
- **Objetivo:** control del presupuesto por categoría **Y** por cuenta a la vez (como el Excel).
- **Éxito:** una vista cruzada categoría×cuenta consistente con Control y conciliación.

### FASE 11 — C8: Preservación durable del archivo original de cada carga (M-04)
- **Objetivo:** guardar el archivo original de cada carga de forma durable.
- **Decisión pendiente:** **GridFS en Mongo** (recomendado, sin infra nueva) vs S3 SISMO.
- **Éxito:** habilita cargar por la app la migración Global66 abr–jul ya reconciliada.

### FASE 12 — C7: Proyección de caja + motor de ventas/recaudo  ⭐ EL VALOR
- **Objetivo:** proyectar caja; motor de ventas/recaudo discriminado (inicial vs cuota
  crédito) → objetivos de venta y **umbral mayo-2027**. **Modelos de moto administrables**
  (agregar modelo con su estructura de cobro de cuotas — requisito CEO).
- **Referencia:** `docs/modelo/PROYECCIONES.md` (simulador 2030), `Dashboard Artefacto.jsx`.
- **Éxito:** el CEO ve la proyección de caja y decide sobre ella.

### FASE 13 — C9: Pagos pendientes del mes (hoja 'Pagos semana')
- **Objetivo:** listar pagos programados, ver cómo calzan con presupuesto + caja, y
  calcular la **caja final proyectada** del mes. (Requisito CEO 2026-07-22.)

### FASE 14 — C10: Fecha exacta de pago a proveedores + cronograma de deudas
- **Objetivo:** hoja 'Flujo pago deudas' / M6 capacidad de pago → fecha exacta de pago.

### FASE 15 — C11: Seguimiento de IVA (cuatrimestral)
- **Objetivo:** Facturas Auteco + IVA cuatrimestral → pagar lo mínimo posible.

---

## Secuencia recomendada
F7 (C1) → F8 (C3) → F9 (C4) → F10 (C5) → **F12 (C7, el valor)**; F11 (C8) se intercala
antes de migrar datos reales; F13–F15 (C9–C11) elevan las hojas restantes del Excel.
