# COMPAS — PROJECT.md (ancla persistente del producto)

> Cerebro del proyecto. Se lee al inicio de cada sesión junto con `docs/COMPAS_NORTE.md`
> y la memoria. Ante cualquier duda de alcance, NORTE.md + este doc mandan.
> Fijado con el CEO: 2026-07-22.

## 1. Qué es COMPAS (norte)

Sistema **predictivo e inteligente** para **administrar el presupuesto mensual** de
RODDOS y **proyectar la caja**, para **tomar decisiones presupuestales**. **NO es un
sistema contable.** Objetivo inmediato: superar el **umbral de caja de mayo-2027**.
Largo plazo: objetivos de venta para sostenibilidad, fecha exacta de pago a
proveedores, IVA mínimo, proyecciones de deuda/inversión. (Detalle: `docs/COMPAS_NORTE.md`.)

**Reemplaza el Excel `Flujo de pago de deudas.xlsx`** — ese Excel es el **molde
funcional**: control por categoría y por cuenta, presupuesto mensual, proyección.

## 2. Modelo de datos (CONFIRMADO por el CEO, 2026-07-22)

**Lo ÚNICO que se carga a diario:**
1. **Movimientos del/los banco(s)** (hoy Global66 — única cuenta operativa desde
   abril; Bancolombia se centraliza en septiembre-2026).
2. **Valor de la caja disponible** — para ajustar/corregir constantemente y que la
   información **siempre cuadre** (conciliación).

**Todo lo demás lo DERIVA/CALCULA el sistema** (nadie digita contabilidad):
presupuesto vs ejecutado vs disponible, proyección de caja, objetivos de venta,
fecha de pago a proveedores, seguimiento de IVA.

**Persistencia:** toda la data vive en **MongoDB Atlas** (cluster SISMO-V3, base
`compas`) — infra existente de RODDOS, ya aprovisionada. No se cambia de infra.

## 3. Capacidades centrales (con estado real)

| # | Capacidad | Estado |
|---|---|---|
| C1 | **Categorías administrables** (crear/editar/desactivar desde la app) | ⚠️ **Backend ✅** (CRUD `/rubros` + re-seed MODELO.md, GO Kimi 9.2/9.4, merge 126ac29); falta pantalla frontend (sin gate) y correr la migración del re-seed en prod |
| C2 | Carga diaria de movimientos (parsers Bancolombia/BBVA/Global66) + persistencia en Mongo | ✅ (Global66/BBVA/Bancolombia parseados; carga por app con preservación pendiente C8) |
| C3 | **Auto-clasificación** de los movimientos en sus categorías al cargar (reglas administrables) | ⚠️ **Backend ✅** (reglas Spec §1.9 + carga + reclasificación + aplicar-pendientes, GO Kimi 9.3/9.4, merge 7253bd5; semilla ingresos→Recaudo en prod); falta pantalla de reglas (sin gate) + extensión semilla de egresos (mapeo real del CEO) |
| C4 | Ajuste de caja disponible + conciliación por cuenta (que la info cuadre) | ✅ conciliación por banco + cierre; ⚠️ falta el ajuste de caja diario editable |
| C5 | Control del presupuesto **por categoría Y por cuenta** (como el Excel) | ⚠️ Vista Control por categoría ✅; por cuenta (conciliación) ✅; falta la vista combinada categoría×cuenta |
| C6 | **Módulo de presupuesto inteligente**: preparar el presupuesto del mes siguiente (sugerido → acotar → aprobar) con base en ejecución + caja | ✅ (motor §1.4.1 + acotar + aprobar, GO Kimi) |
| C7 | **Proyección de caja** + motor de ventas/recaudo discriminado (inicial vs cuota crédito) → objetivos de venta, umbral mayo-2027. **Modelos de moto administrables** (agregar modelo nuevo con su estructura de cobro de cuotas — requisito CEO) | ❌ **FALTA** (el valor final). Motor: `docs/modelo/PROYECCIONES.md` (simulador 2030) |
| C8 | Preservación durable del archivo original de cada carga (M-04) | ⚠️ por decidir: **GridFS en Mongo** (recomendado, sin infra nueva) vs S3 SISMO |
| C9 | **Pagos pendientes del mes**: listar pagos programados, ver cómo calzan con presupuesto + caja, y calcular la **caja final proyectada** del mes con los movimientos planteados (eleva la hoja 'Pagos semana', integrada a los movimientos) | ❌ **FALTA** (requisito CEO 2026-07-22) |
| C10 | **Fecha exacta de pago a proveedores** + cronograma de deudas (hoja 'Flujo pago deudas'; M6 capacidad de pago) | ❌ **FALTA** |
| C11 | **Seguimiento de IVA** (Facturas Auteco + IVA cuatrimestral) para pagar lo mínimo | ❌ **FALTA** |

## 4. Arquitectura (resumen; detalle en el mapa de código)

- **Backend:** FastAPI + Beanie/Motor sobre MongoDB Atlas. Dinero=Decimal (string en
  API). Módulos: `auth` (JWT+MFA+RBAC), `cargas` (parsers+upload), `transacciones`,
  `ciclo` (abrir mes), `presupuesto` (motor+acotar+aprobar), `cierre` (cierre+
  conciliación+reapertura), `control` (Vista Control), `audit` (append-only).
- **Frontend:** React 19 + Vite + Tailwind (tema claro RODDOS). Pantallas: Login,
  Meses, Cargas, Control.
- **Infra:** MongoDB Atlas (SISMO-V3), Render (`compas-api`), Vercel (`compas.roddos.com`),
  DNS GoDaddy. Auto-deploy desde `main`.
- **Proceso:** Excel `docs/COMPAS_Control_Desarrollo.xlsx` (tracker) + `planning/phases/`
  (auditorías Kimi ≥9.0 en merges críticos). Memoria en `~/.claude/.../memory/`.

## 5. Estado y foco (2026-07-22)

**Construido y en prod:** auth/RBAC/MFA/audit, parsers, cargas (backend), transacciones,
apertura de mes, motor del sugerido, acotamiento+aprobación, cierre+conciliación+
reapertura, Vista Control (backend+frontend). Todo con gate Kimi en los merges críticos.

**Gaps que el CEO señaló como el corazón operativo (a priorizar):**
1. ~~C1~~ ✅ (2026-07-22, GO 9.2/9.4; re-seed en prod; pantalla Categorías viva).
2. ~~C3 backend~~ ✅ (2026-07-22, GO 9.3/9.4, merge 7253bd5; semilla ingresos en
   prod). Colas: pantalla de reglas (sin gate) + extensión semilla de egresos
   cuando el CEO comparta el mapeo real de `Base real egresos`.
3. **C4 — ajuste diario de caja disponible** (PLAN → gate Kimi aparte).
4. Luego: **C5** vista combinada categoría×cuenta, y **C7** capa predictiva (el valor).
También en vuelo: S4-00, S4-06 (TOCTOU + test step-up), tardías (F-08), CR-001
ExtractoMensual, y el operativo hacia G3.

**Migración de datos reales:** Global66 abr–jul (ya preparado, reconciliado) — se
carga por la app cuando C8 (preservación) esté resuelta. Data siempre persistente en Mongo.
