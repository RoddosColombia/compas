# COMPAS — PROJECT.md (ancla persistente del producto)

> Cerebro del proyecto. Se lee al inicio de cada sesión junto con `docs/COMPAS_NORTE.md`
> y la memoria. Ante cualquier duda de alcance, NORTE.md + este doc mandan.
> Fijado con el CEO: 2026-07-22.
>
> **EL ENTREGABLE es el cockpit del Blueprint UX (`docs/Compas_Blueprint_UX.docx`) con el
> motor de proyección 2030 de fondo — ver §6.** Toda la documentación de desarrollo se
> orienta hacia eso. Las capacidades (§3) son el fondo/actuals que lo alimentan.

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
| C4 | Ajuste de caja disponible + conciliación por cuenta (que la info cuadre) | ✅ **Backend ✅** conciliación por banco + cierre + **ajuste diario `PATCH /meses/{mes}/saldos`** (CR-S6, GO Kimi PLAN 9.3, merge 670ba4e con gate-waiver CEO 2026-07-23; auditoría Kimi de código retroactiva pend.); falta pantalla frontend (sin gate) |
| C5 | Control del presupuesto **por categoría Y por cuenta** (como el Excel) | ✅ Vista Control por categoría ✅; por cuenta (conciliación) ✅; **vista combinada categoría×cuenta** ✅ (`GET /meses/{mes}/control/por-cuenta` matriz rubro×banco + pestaña frontend, read-only, GO CEO 2026-07-23) |
| C6 | **Módulo de presupuesto inteligente**: preparar el presupuesto del mes siguiente (sugerido → acotar → aprobar) con base en ejecución + caja | ✅ (motor §1.4.1 + acotar + aprobar, GO Kimi) |
| C7 | **Proyección de caja** + motor de ventas/recaudo discriminado (inicial vs cuota crédito) → objetivos de venta, umbral mayo-2027. **Modelos de moto administrables** (agregar modelo nuevo con su estructura de cobro de cuotas — requisito CEO) | ❌ **FALTA** (el valor final). Motor: `docs/modelo/PROYECCIONES.md` (simulador 2030) |
| C8 | Preservación durable del archivo original de cada carga (M-04) | ⚠️ por decidir: **GridFS en Mongo** (recomendado, sin infra nueva) vs S3 SISMO |
| C9 | **Pagos pendientes del mes**: listar pagos programados, ver cómo calzan con presupuesto + caja, y calcular la **caja final proyectada** del mes con los movimientos planteados (eleva la hoja 'Pagos semana', integrada a los movimientos) | ⚠️ **Backend ✅** "Pagos de la semana": PagoPlaneado + CRUD + veredicto `GET /meses/{mes}/pagos-semana` reusando `_caja_libro` + marcar-pagado multi-doc (CR-S7, merge be9512b, GO CEO 2026-07-23; Kimi retroactivo). Falta: matriz de deudas (→C10), matching automático, dashboard, y pantalla frontend (sin gate) |
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
3. ~~C4 — ajuste diario de caja disponible~~ ✅ (2026-07-23, GO PLAN Kimi 9.3,
   merge 670ba4e + pantalla /caja merge f95d364; gate de código bajo waiver CEO —
   Kimi ausente hasta 25-jul, auditoría retroactiva pendiente).
4. ~~S5-01/C9 — Pagos de la semana~~ ✅ backend (2026-07-23, merge be9512b, GO CEO;
   Kimi PLAN+código retroactivos). Cola: pantalla frontend de pagos (sin gate).
5. Luego: **C5** vista combinada categoría×cuenta, y **C7** capa predictiva (el valor).

**Deuda de auditoría retroactiva (Kimi vuelve 25-jul):** C4 (código), C9 (PLAN +
código) — construidos/mergeados bajo GO del CEO con gate-waiver trazable; auditar y
aplicar fix-forward si alguno queda <9.0.
~~S4-00, S4-06~~ ✅ deuda saldada (2026-07-23, PR #26 merge dea4a16, Kimi 9.5).
También en vuelo: tardías (F-08), CR-001 ExtractoMensual, y el operativo hacia G3.
Además la pantalla de reglas ya está viva (ReglasPage, sin gate).

**Migración de datos reales:** Global66 abr–jul (ya preparado, reconciliado) — se
carga por la app cuando C8 (preservación) esté resuelta. Data siempre persistente en Mongo.

## 6. Entregable objetivo — Blueprint UX (el cockpit) · CEO 2026-07-23

El **entregable** del producto es el cockpit de proyección/planeación definido en
**`docs/Compas_Blueprint_UX.docx`** + el **mockup navegable de referencia del CEO** — con
el **motor de proyección de fondo** (`docs/modelo/PROYECCIONES.md`, simulador 2030). El
Blueprint MANDA sobre la UX. Barra lateral fija, fondo blanco RODDOS, rojo solo para
perforación de caja mínima. Ocho vistas en tres grupos:

| Grupo | Vista | Contenido clave | Capacidad |
|---|---|---|---|
| Principal | **Inicio** | KPIs (caja, runway, motos activas, cartera, mora), mini-curva, próximos hitos | C7 + resumen |
| Principal | **Proyecciones** (el corazón) | Curva de caja acumulada a **dic-2030**, umbral $55M + mes crítico; motor de ingresos por modelo (cuota inicial + recaudo semanal); palancas editables; flujo neto por trimestre; cierre por periodo | **C7** |
| Planeación | **Escenarios** | Conservador/Base/Agresivo superpuestos + tarjetas comparativas (usa mora/recuperación) | **nuevo** |
| Planeación | **Presupuesto** | Presupuesto vs real por categoría (barras) + control por categoría (semáforo) | C5/C6/Control |
| Planeación | **IVA** | Generado vs descontable + liquidación + saldo a pagar, **por CUATRIMESTRE** (el Blueprint dice "bimestre" por error; RODDOS es cuatrimestral — CEO 2026-07-23) | C11 |
| Operación | **Dashboards** | Salud operativa: cartera por añada, mora por tramo, cobranza, colocación | **nuevo** |
| Operación | **Reportes** | Board updates / resúmenes inversionistas, exportables a PDF | **nuevo** |
| Operación | **Datos** | Caja inicial de hoy, captura manual de supuestos/presupuestos, importar modelo 2030 | C4/cargas |

**Reframe de fase (Blueprint §1):** Fase 1 = cockpit de proyección con **captura MANUAL**
de supuestos + presupuestos (sin históricos ni integración). Los **actuals** (movimientos
de banco, ya construidos: C1–C4/cargas/ciclo/cierre) son el **fondo** y se vuelven vivos
en **Fase 2** (rolling forecast vs proyectado). O sea: lo construido NO se bota — es la base
de los actuals; el foco del entregable ahora es la **capa de proyección (C7 + Escenarios +
Dashboards + Reportes)**.

## 7. Reconciliación (decisiones CEO — NO las resuelve Claude)
1. **IVA: ✅ RESUELTO — CUATRIMESTRAL** (CEO 2026-07-23). El Blueprint §7 dice "bimestre"
   por error; **RODDOS liquida IVA por CUATRIMESTRE** (NIT 901012622 dígito 2: 13-may-26,
   10-sep-26, 14-ene-27). Al construir el módulo de IVA → cuatrimestre, nunca bimestre.
2. **Excel 2030 canónico:** ¿`FIXED` reemplaza a `CAMBIOS CON APACHE`, o son escenarios
   distintos a reconciliar? (Blueprint §11).
3. **Impuesto de renta:** ¿entra en Fase 1 o Fase 2? (Blueprint §5.6, validar con contabilidad).
4. **Prioridad:** dado el reframe, ¿el próximo foco es **C7 (Proyecciones)** en vez de seguir
   con los actuals/pagos? (a confirmar por el CEO).
