COMPAS

Control y Monitoreo Presupuestal y de Administración de Caja

Discovery Document & Product Requirements Document

COMPAS-DD-PRD-001 v1.1.2 — Errata de cierre para VERDE (18-jul-2026)

RODDOS S.A.S. — Oficina del CTO

18 de julio de 2026

# Metadatos del documento

| Atributo | Valor |
| --- | --- |
| Código / Versión | COMPAS-DD-PRD-001 · v1.1.2 (18-jul-2026); v1.1.1 y v1.1 18-jul; v1.0 17-jul |
| Estado | Borrador para aprobación del CEO |
| Auditoría externa | Auditoría fullstack independiente 18-jul-2026 (ROJO de proceso, 51 hallazgos) — correcciones de PRD incorporadas |
| Documentos hermanos | COMPAS-INFO-000 v1.1.2, COMPAS-SPEC-002 v1.1.2, COMPAS-STACK-003 v1.1.2, COMPAS-PLAN-004 v1.1.2 (F-51) |
| Sistema hermano | SISMO V3 — COMPAS reutiliza infraestructura y patrones |
| Fuentes de verdad | Flujo de pagos deudas.xlsx (estructura) + MODELO SIMULADOR 2030 (motor de ingresos, Fase 2) |



# Histórico de versiones — v1.0 → v1.1

| Cambio | Hallazgo |
| --- | --- |
| M2/M6/M8/M9: los compromisos (cuotas de deuda, facturas, IVA) YA NO 'alimentan' la fórmula del sugerido; se presentan como fila informativa 'Compromisos programados' junto al sugerido | F-07 |
| M10 Ingresos (modo Excel) entra explícitamente al alcance de Fase 0–1 | F-40 |
| §2.2: la autoridad del ciclo remite a la tabla única del Spec §2.4 (Directivo acota, Admin aprueba/cierra/reabre) | F-43 |
| §5: tolerancias diferenciadas ($1 cuadre vs $50.000 cierre), RNF de UX/localización, política de retención con base jurídica, paquete de artefactos Ley 1581 | F-44, F-50, F-24, F-20 |
| §2.2/M11: definición de 'base completa' y permisos de exportación | F-18 |
| M12: reporte de junta = Excel + PDF vía impresión del navegador (decisión) | F-49 |



## Parche v1.1 → v1.1.1 (re-auditoría + decisión de alcance del CEO)

| Cambio | Hallazgo |
| --- | --- |
| Decisión híbrida N-01: el go-live (10 semanas) conserva FacturaEmitida, Capacidad de pago, navbar M13 + badges y cadencia 8:30; el modo 'ligada a ventas' y la pestaña Horizonte pasan a Fase 1.5 — §1.3 actualizado con TODO el alcance nuevo listado | N-01 |
| M2: en el go-live el '% global' es manual (pre-llenado desde M10 al existir); demo Sprint 3 en modo histórico | N-03 |
| M6: holgura definida sobre rubros de egreso; navbar #7 menciona Capacidad de pago; M13.1 #5 declara Horizonte como Fase 1.5 con método | nit 12, N-12 |
| M9: FacturaEmitida con tarifa/exentas y base legal del cliente | N-09 |



v1.1.2 (18-jul-2026): errata de cierre E-1..E-6 + barrido de textos, según el informe de calificación final (8.9/10). Ningún cambio de decisión, mecanismo, costo ni criterio de aceptación; E-1 unifica la datación del pre-llenado del '% global' en Sprint 6b.

# Executive Summary

COMPAS es el sistema propio de seguimiento presupuestal y control de flujo de caja de RODDOS S.A.S. Reemplaza el archivo Flujo de pagos deudas.xlsx por una aplicación web en la nube con memoria histórica persistente, ciclo formal de presupuesto mensual (sugerido → definido → ejecutado), carga automatizada de movimientos bancarios (Bancolombia, BBVA, Global66), registro de facturas emitidas a RODDOS, monitoreo del IVA cuatrimestral y proyección simple de ingresos por modelo de moto. Corre sobre los mismos proveedores de SISMO V3, sin cuentas nuevas. En Fase 2 incorporará el motor de precisión del MODELO SIMULADOR 2030.

# Definiciones Fundamentales

| Término | Definición |
| --- | --- |
| Rubro / Categoría | Concepto de gasto o ingreso clasificable, en 5 grupos: Costo de producto, Operación, Nómina, Deudas y obligaciones, Otros y varios. |
| Presupuesto sugerido | Cálculo automático por rubro con la fórmula EXACTA del Excel: prom. últimos 3 meses cerrados + tendencia $/mes + prom. × crecimiento %/mes (definición matemática y ejemplo en Spec §1.4.1). Punto de partida, nunca decisión. |
| Compromisos programados | Fila INFORMATIVA junto al sugerido: cuotas de deuda del mes + facturas con pago en el mes + IVA con vencimiento en el mes. No altera la fórmula; informa el acotamiento del Directivo (F-07). |
| Presupuesto definido | Presupuesto aprobado por el Admin (con acotamientos de Directivos registrados). Vara de toda la ejecución del mes. |
| Ejecutado / Disponible | Suma de movimientos reales clasificados / Definido − Ejecutado. |
| Caja disponible | Saldo inicial + Ingresos reales − Egresos reales del mes. |
| Diferencia vs banco | Caja calculada − saldo bancario reportado. Condición de cierre: |dif| < $50.000 (UMBRAL_DIF_BANCO_CIERRE). |
| TOLERANCIA_CUADRE | $1 COP — validación de facturas, migración y sumas de control (no es el umbral de cierre) (F-44). |
| Cuatrimestre IVA | Ene–Abr, May–Ago, Sep–Dic (calendario DIAN por NIT, en Configuracion). |



# 1. Visión y Alcance

## 1.1 Qué es COMPAS y qué problema resuelve

Sin cambios de fondo respecto a v1.0: digitaliza el proceso financiero mensual con el mes de control como unidad de trabajo, memoria persistente total, y reemplaza el Excel que hoy se sobreescribe cada mes. Los dolores: sin histórico, carga manual de 3 bancos, presupuesto sin ciclo formal, facturas e IVA en hojas sueltas, y un simulador de ingresos preciso pero inadministrable.

## 1.2 Principios de diseño

- Memoria persistente total. Nada se sobreescribe; todo mes, versión, movimiento y carga queda almacenado y auditable.

- La estructura del Excel es la ley. COMPAS replica Inicio, Control, Pagos semana, Presupuesto, Flujo pago deudas, Bases reales y Facturas.

- Sugerir, no decidir. La fórmula del sugerido es exactamente la del Excel; los compromisos se informan al lado, no dentro (F-07). La decisión humana queda registrada.

- Cero cuentas nuevas. Proveedores de SISMO.

- Simplicidad primero, precisión después. Fase 0–1 = flujo de pagos + ingresos modo Excel; Fase 2 = motor del simulador.

## 1.3 Alcance Fase 0–1 (go-live)

- Catálogo de rubros, ciclo presupuestal completo ('% global' manual, con pre-llenado desde M10 a partir del Sprint 6b), control de ejecución, caja y conciliación por banco, pagos de la semana, deudas CON vista Capacidad de pago, cargas bancarias (3 plantillas) con cadencia diaria 8:30, facturas recibidas Y EMITIDAS (IVA generado desde documentos), IVA cuatrimestral, navbar M13 con badges — alcance del go-live según decisión híbrida N-01 (10 semanas).

- M10 Ingresos en modo Excel (F-40): parámetros por modelo → ingreso proyectado → % cumplimiento; produce el 'proyectado' del dashboard y los ingresos esperados de la semana.

- Migración del histórico (bases desde marzo 2026 al cierre del Sprint 2; deudas, facturas y presupuestos en Sprint 7), dashboard 'Inicio' y analítica histórica.

Fase 1.5 (tras el apagado del Excel, típicamente semanas 5–6 post go-live — decisión N-01): modo 'ligada a ventas' del sugerido + tabla de costos unitarios, y pestaña 'Horizonte' 18–24 meses (método: sugerido iterado con crec_pct default por rubro — N-12). El pre-llenado del '% global' desde M10 NO es Fase 1.5: opera desde el Sprint 6b (E-1).

Excluido (Fase 2+): motor del SIMULADOR 2030, agregación bancaria por API, sincronización Alegra/SISMO, escenarios what-if multi-versión.

# 2. La Empresa y el Equipo

## 2.1 RODDOS S.A.S.

Fintech BNPL colombiana: venta de motos de inventario propio a cuotas semanales (RDX: Raider, Sport, Apache) y financiación de repuestos (RODANTE). No vigilada por la Superfinanciera. La caja es el centro: recaudo semanal, nómina, proveedores (Auteco), deudas e impuestos.

## 2.2 Roles (resumen — la autoridad del ciclo la define la tabla única del Spec §2.4, F-43)

| Rol | Resumen de permisos |
| --- | --- |
| Admin (CEO) | Acceso total. Aprueba presupuesto, confirma cierre, único que reabre (con step-up MFA), gestiona rubros/usuarios/Configuracion. |
| Directivo | Ve todo; acota el presupuesto (queda en ajustes[]); no aprueba, no edita movimientos. |
| Financiero | Carga y clasifica, pagos planeados, deudas, facturas, ejecuta el checklist de cierre. No aprueba presupuesto. |
| Consulta | Solo lectura. Sin exportaciones: 'base completa' = cualquier export o consulta sin filtro de mes sobre transacciones, deudas o facturas (F-18). |



Segregación de funciones: clasificar ≠ aprobar. Matriz permiso × endpoint completa en Spec §4.1.

# 3. Estado Actual — Fuentes de Verdad

El mapeo hoja Excel → módulo COMPAS de v1.0 se mantiene íntegro (Inicio→Dashboard, Control→Control, Pagos semana→Planificador, Presupuesto→Ciclo, Flujo pago deudas→Deudas, Bases reales→Transaccional, Facturas Auteco→Facturas, Proyeccion ingresos→M10). El MODELO SIMULADOR 2030 sigue siendo el motor a portar en Fase 2, con supuestos parametrizables.

# 4. Requerimientos Funcionales — Módulos (delta v1.1.2)

## M1 — Catálogo de rubros

Como v1.0. Rubros de sistema: 'Por clasificar' y 'Ajuste de conciliación' (este último recibe la diferencia auditada al anclar el saldo inicial al banco — Spec §1.3, F-14).

## M2 — Ciclo de presupuesto mensual

Estados sugerido → propuesto → definido → en ejecución → cerrado, como v1.0, con tres precisiones: (1) la vista de acotamiento muestra por rubro: Sugerido (fórmula) · Crecimiento %/mes (EDITABLE por línea, con recálculo inmediato) · Compromisos programados (informativo) · Definido (editable) — el crecimiento es una decisión mensual del equipo, no una configuración: se edita categoría por categoría o con la acción 'Aplicar % global del mes' — aplicación manual, con pre-llenado desde el crecimiento de ventas de M10 a partir del Sprint 6b (N-03, E-1); (2) los compromisos informan sin contaminar la fórmula (F-07); (3) quién hace qué lo define la tabla única del Spec §2.4 (F-43). Wireframes de esta vista se validan antes del Sprint 3 (F-50).

Presupuesto inteligente ligado a ventas — FASE 1.5 (decisión de alcance N-01): además del % de crecimiento global, las categorías cuyo gasto depende directamente de las unidades vendidas (Producto, SOAT/Matrículas, Seguros — grupo Costo de producto) pueden marcarse como 'ligadas a ventas': su sugerido se calcula como unidades proyectadas del mes (M10) × costo unitario por modelo, en vez de la fórmula histórica. Así el presupuesto base del mes SALE de lo que se debe vender. Se activa en Fase 1.5 tras demostrarse contra un mes real cerrado; en el go-live TODAS las líneas usan la fórmula histórica — la nota CEO #1 (cuadre celda a celda con el Excel) se verifica sin ambigüedad (N-03). Cada línea muestra qué modo la calculó.

## M3–M5 — Control, Caja, Pagos de la semana

Como v1.0, con: conciliación POR BANCO además del consolidado (saldos_banco, F-10); condición de cierre con UMBRAL_DIF_BANCO_CIERRE; conciliación de pagos planeados con matching determinista y confirmación humana cuando haya ambigüedad (F-05); los movimientos bancarios tardíos de meses cerrados entran marcados tardia=true sin tocar cifras congeladas (F-08).

## M6 — Deudas y obligaciones

Como v1.0, con corrección F-07: las cuotas del mes no alimentan la fórmula del sugerido; aparecen en la fila 'Compromisos programados' del grupo Deudas y obligaciones y pueden enviarse a Pagos de la semana. Altas de acreedores persona natural exigen evidencia de autorización de tratamiento (F-20).

Vista 'Capacidad de pago' (decisión CEO): el módulo de deudas responde la pregunta ¿el presupuesto de este mes me da para acelerar o voy poco a poco? Muestra: (1) la holgura del mes = disponible del presupuesto definido (solo rubros de EGRESO, nit 12) − compromisos programados restantes; (2) por acreedor: saldo, cuota pactada y meses restantes al ritmo actual; (3) simulador de aceleración: 'si abono $X extra este mes a este acreedor, la deuda termina en <mes>' — con el abono enviable a Pagos de la semana en un clic (donde se valida contra presupuesto como cualquier pago). Prioriza visualmente los acreedores por costo/urgencia según el orden que defina el Admin.

## M7 — Carga de movimientos bancarios

Como v1.0, con: ciclo de vida completo de cargas (reproceso de fallidas, reaper — F-02); transacciones manuales con id sintético (F-04); Global66 con moneda original + tasa conservadas (F-03); límites de archivo y rechazo de .xlsm (F-22); reglas de clasificación como entidad administrable, las aprendidas requieren aprobación del Financiero (F-10).

Cadencia operativa diaria (decisión CEO): todos los días a las 8:30 a.m. se cargan los movimientos del día anterior de los 3 bancos. COMPAS lo soporta con: un job a las 8:30 (América/Bogotá) que verifica si ya existe carga con movimientos del día anterior por cada banco y, si falta alguna, envía recordatorio al canal del Financiero; el indicador 'días desde última carga por banco' en el dashboard con semáforo (verde = al día); y el reporte de cada carga mostrando la fecha máxima de movimiento cargada. La caja y el control del día siempre reflejan hasta ayer.

## M8 — Facturas emitidas a RODDOS

Como v1.0, con corrección F-07 (la factura aparece como compromiso programado del mes de pago, no dentro de la fórmula) y autorización de tratamiento para proveedores persona natural (F-20).

## M9 — IVA cuatrimestral

Como v1.0, con: calendario DIAN en Configuracion (editable por Admin con auditoría, no env var — F-45); el saldo proyectado aparece como compromiso programado del mes de vencimiento (F-07).

IVA generado desde facturas emitidas (corrección de vacío, decisión CEO): en v1.0 el IVA generado era un valor parametrizado. Ahora ambos lados del cálculo salen de documentos reales: IVA descontable = Σ IVA de las facturas emitidas A RODDOS (M8, registradas ante la DIAN por los proveedores) e IVA generado = Σ IVA de las facturas emitidas POR RODDOS (registro/carga masiva con base gravada, tarifa 19/5/exenta e IVA por factura — N-09; base legal del tratamiento de datos de clientes: ejecución del contrato y deber de facturación). Saldo del cuatrimestre = generado − descontable, calculado por el motor al cargar cada factura de cualquiera de los dos lados. En Fase 2, las facturas emitidas se leerán automáticamente desde la facturación de ventas (Alegra/SISMO); en Fase 0–1 se cargan por plantilla igual que las recibidas.

## M10 — Ingresos (modo Excel) — EN ALCANCE Fase 0–1 (F-40)

- Parámetros por mes y modelo (motos nuevas, precio, cuota semanal, cuota inicial, % recaudo) → ingreso proyectado del mes y por semana.

- Produce: 'Ingreso proyectado' y '% cumplimiento' del dashboard 'Inicio', e 'ingresos esperados de la semana' para M5.

- Cambios de parámetros quedan auditados (parametros_ingreso.modificado). Se construye en el Sprint 6b.

## M11 — Histórico y analítica

Como v1.0. Toda exportación queda en el audit log (exportacion.realizada) y respeta la matriz de permisos; Consulta no exporta (F-18, F-21).

## M12 — Dashboard y reportes

Como v1.0, con decisión F-49: el reporte mensual de junta se entrega en Excel (openpyxl) y en PDF generado desde la vista de impresión del navegador sobre la misma plantilla — sin librería PDF server-side en Fase 0–1.

## M13 — Estructura de navegación: el navbar son las hojas del Excel

Decisión de producto del CEO (18-jul): la navegación principal de COMPAS replica las hojas de Flujo de pagos deudas.xlsx — el usuario que hoy vive en el Excel encuentra la app organizada igual, sin curva de aprendizaje. 'Facturas Auteco' NO es ítem del navbar; facturas, IVA y administración van en un menú secundario.

| # | Ítem del navbar | Hoja Excel origen | Contenido |
| --- | --- | --- | --- |
| 1 | Inicio | Inicio | Dashboard del mes: presupuesto/ejecutado/disponible/% ejecutado, caja disponible, dif. vs banco, ingreso real vs proyectado, resumen por grupo, pendientes por clasificar, tendencia 12 meses. |
| 2 | Control | Control | Presupuesto vs ejecutado vs disponible y % por categoría, subtotales por grupo, drill-down a movimientos. |
| 3 | Pagos semana ★ | Pagos semana | MÓDULO PRIORITARIO: pagos establecidos de la próxima semana con veredicto ✔/✖ contra presupuesto, caja después de cada pago, impacto proyectado, y seguimiento de estado (planeado → ejecutado/conciliado). Badge en el navbar con # de pagos de los próximos 7 días. |
| 4 | Presupuesto | Presupuesto + Segundo semestre | Ciclo del mes (sugerido con sus 3 componentes + compromisos programados + definido) y pestaña Horizonte (FASE 1.5) — proyección 18–24 meses que cubre la vista 'Segundo semestre'. |
| 5 | Ingresos | Proyeccion ingresos + Base real ingresos | Parámetros por modelo (M10), ingreso proyectado vs real, % cumplimiento, y la base real de ingresos con su carga bancaria. |
| 6 | Egresos | Base real egresos | Base transaccional de egresos: filtros por mes/categoría/texto, clasificación, y carga de extractos (Bancolombia, BBVA, Global66). |
| 7 | Deudas | Flujo pago deudas | Matriz acreedor × mes, saldo por acreedor, vista Capacidad de pago con simulador de abonos (M6), envío de cuotas a Pagos semana. |



Menú secundario 'Administración' (fuera del navbar principal): Facturas recibidas (M8), IVA cuatrimestral (M9), Cargas (historial y reproceso), Configuración y usuarios (solo Admin).

### M13.1 Criterios de navegación e implementación — aceptación de los wireframes pre-Sprint 3

Estos 7 criterios son vinculantes: los wireframes y la implementación del frontend se aprueban contra esta lista.

- Una base transaccional, dos entradas. 'Ingresos' y 'Egresos' son dos ítems del navbar pero UNA sola vista y un solo codepath sobre la colección transacciones (filtro tipo_flujo pre-aplicado). Prohibido construir dos pantallas independientes: mismos filtros, misma clasificación, misma carga de extractos. El navbar es presentación; el modelo no se duplica.

- Selector de mes GLOBAL. El mes de control es un selector persistente en el header que gobierna Inicio, Control, Pagos semana y Presupuesto a la vez, y viaja en la URL (/2026-07/control): un link compartido reproduce exactamente la vista. Ninguna vista maneja su propio mes; las cifras entre pestañas siempre cuadran.

- Landing = Inicio con la acción a un clic. Al iniciar sesión se aterriza en Inicio, con una tarjeta prominente 'Pagos de esta semana' (total, # pagos, próximos 3) que lleva al módulo Pagos semana. El badge del navbar se alimenta de GET /dashboard/badges y se refresca tras cada mutación (sin websockets en Fase 0–1).

- Lo oculto emite señales. Facturas e IVA no están en el navbar, pero Inicio muestra la tarjeta 'IVA del cuatrimestre' (saldo proyectado + días al vencimiento) y el menú Administración lleva badge cuando hay vencimiento próximo o facturas sin conciliar. El dato puede vivir en el menú secundario; la señal no.

- Presupuesto en dos pestañas. Pestaña 'Ciclo del mes' (sugerido + compromisos + acotar/aprobar — la vista políticamente delicada, limpia y enfocada) y pestaña 'Horizonte' (proyección 18–24 meses, ex-'Segundo semestre'; se habilita en FASE 1.5 con método definido — N-01/N-12). Nunca mezcladas en una tabla única.

- Navbar derivado de permisos. El menú se construye desde un único config de navegación derivado de la matriz permiso × endpoint (Spec §4.1) — Consulta no ve 'cargar extracto' ni Administración completa. Prohibidos los if de rol regados por componentes.

- Responsive decidido, no descubierto. En tablet (≥768px) el navbar colapsa sus últimos ítems a 'Más' manteniendo siempre visibles Inicio, Control y Pagos semana ★. El comportamiento queda definido en los wireframes, no a mitad de la construcción (F-50).

# 5. Requerimientos No Funcionales (v1.1.2)

- Seguridad: paquete completo del STACK v1.1.2 §8 (revocación JWT + logout + MFA Admin/Directivo + política de contraseñas + step-up en operaciones críticas + IAM S3 por prefijo + presigned URLs + cabeceras).

- Auditoría: 29 eventos (catálogo Spec §1.11), append-only verificado en CI, incluida toda exportación y descarga de archivos (F-21, E-6).

- Retención con base jurídica (F-24): soportes contables y de comercio 10 años (C. de Comercio arts. 28/48) — cubre extractos, facturas y meses cerrados; soportes tributarios mínimo 5 años (E.T. art. 632-1); datos personales de acreedores/proveedores: supresión o anonimización al cumplir la finalidad salvo obligación legal (Ley 1581 arts. 4, 11); archivado a S3 Glacier con Object Lock (STACK §4.3). La frase 'para siempre' de v1.0 se corrige a 'según esta política'.

- Cumplimiento Ley 1581 con artefactos (F-20): política de tratamiento, aviso de privacidad, autorización de titulares con evidencia en el sistema, procedimiento ARCO con plazos, verificación del umbral RNBD con el balance, y anexo de COMPAS a los contratos de transmisión internacional existentes (Atlas, Render, Vercel, Sentry, Better Stack). Workstream legal desde Sprint 0 (PLAN §8); artefactos finales son prerrequisito del go-live.

- Rendimiento VERIFICADO: cargas de 5.000 movimientos < 30 s y p95 de dashboard < 2 s con 12 meses de volumen (5 reales mar–jul + sintético), probados con k6 en el DoD (F-47).

- UX y localización (F-50): moneda $ 1.234.567,89 (es-CO), fechas dd-mmm-aaaa, WCAG 2.1 AA como objetivo (Radix/shadcn), dashboard legible en tablet, vista de impresión para el reporte de junta; wireframes de la vista Presupuesto antes del Sprint 3.

# 6. KPIs de éxito del producto

| KPI | Meta a 90 días del go-live |
| --- | --- |
| Movimientos 'Por clasificar' al cierre de mes | < 5% del total del mes |
| Diferencia vs banco al cierre | < $50.000 COP (UMBRAL_DIF_BANCO_CIERRE; el ajuste de ancla mensual evita la deriva acumulativa — F-14) |
| Ciclo presupuestal (sugerido → definido) | < 5 días hábiles |
| Cargas con duplicados / cargas fallidas sin resolver | 0 / 0 |
| Meses históricos consultables | 100% desde marzo 2026 |
| Desviación del saldo IVA proyectado vs declarado | < 5% |
| % cumplimiento de ingresos visible (M10) | Publicado cada mes en el dashboard |


