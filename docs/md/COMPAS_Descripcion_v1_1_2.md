COMPAS

Control y Monitoreo Presupuestal y de Administración de Caja

Descripción general del sistema

COMPAS-INFO-000 v1.1.2 — re-baseline completo (18-jul-2026)

RODDOS S.A.S. — Oficina del CTO

18 de julio de 2026

# ¿Qué es COMPAS?

COMPAS es el sistema propio de seguimiento presupuestal y control de flujo de caja de RODDOS S.A.S. Es una aplicación web en la nube que reemplaza el archivo Flujo de pagos deudas.xlsx conservando su estructura y forma de trabajo — la navegación replica las hojas del Excel: Inicio · Control · Pagos semana ★ · Presupuesto · Ingresos · Egresos · Deudas — con memoria histórica persistente, trazabilidad total y automatización de las tareas manuales.

Su unidad de trabajo es el mes de control: cada mes se abre con un presupuesto sugerido calculado con la misma fórmula del Excel (promedio 3 meses + tendencia + % de crecimiento, editable mes a mes por categoría o con un % global), acompañado de la fila informativa de compromisos programados (cuotas de deuda, facturas por pagar, IVA por vencer). Los directivos lo acotan, el Admin lo aprueba, y sobre ese presupuesto definido se ejecuta y se hace seguimiento. Al cerrar, el mes queda guardado, consultable y comparable — nada se sobreescribe.

# Qué hace (go-live, Fase 0–1)

- Presupuesto mensual con ciclo formal: sugerido → propuesto → definido → en ejecución → cerrado, con versionado y registro de quién acotó y quién aprobó.

- Control de ejecución: presupuesto vs. ejecutado vs. disponible por categoría y grupo, con semáforos y alertas.

- Caja y conciliación: caja del mes y diferencia contra el saldo de cada banco y el consolidado.

- Pagos de la próxima semana (módulo prioritario): validación contra presupuesto (✔ Cabe / ✖ Excede), caja después de cada pago y seguimiento de estado hasta la conciliación con el pago real.

- Carga de movimientos bancarios: plantillas de Bancolombia, BBVA y Global66 (con moneda original), deduplicación garantizada, clasificación asistida y cadencia diaria: todos los días a las 8:30 se carga el día anterior, con recordatorio automático si falta un banco.

- Deudas con Capacidad de pago: calendario de cuotas por acreedor y el simulador que responde ¿me da para acelerar o voy poco a poco?: holgura del mes, meses restantes por deuda y efecto de un abono extra, enviable a Pagos semana en un clic.

- Facturas — ambos lados: las emitidas A RODDOS (proveedores, con fecha de pago por días de crédito) y las emitidas POR RODDOS (ventas), ambas con IVA discriminado.

- IVA cuatrimestral: saldo proyectado = IVA generado (facturas emitidas) − IVA descontable (facturas recibidas), monitoreado en vivo con alertas antes del vencimiento.

- Ingresos por modelo de moto: proyección paramétrica (unidades, cuotas, % recaudo) con % de cumplimiento contra el recaudo real.

- Histórico y analítica: comparación mes vs. mes, series por categoría y exportación a Excel — auditada y restringida por rol (el rol Consulta no exporta).

# Cómo está construido

Sobre los mismos proveedores de SISMO V3 (MongoDB Atlas, Render, Vercel, Cloudflare, GitHub, Sentry, Better Stack), sin cuentas nuevas, con costo incremental de ~$40–70 USD/mes en construcción y ~$40–55 en operación (mínimo ~$33 con staging pausado). Mismo stack (Python/FastAPI + React/TypeScript), con autenticación endurecida (MFA, revocación), roles con segregación de funciones, auditoría inmutable de 29 eventos verificada en CI, respaldo diario con restauración probada y cronometrada, y archivado tributario de largo plazo con bloqueo contra borrado. El paquete de documentos pasó por auditoría técnica independiente de 4 rondas (ROJO → VERDE 9.3/10 con certificado GO) y esta versión v1.1.2 incorpora el cierre completo y la decisión de alcance del CEO.

# Hoja de ruta

| Fase | Alcance | Duración |
| --- | --- | --- |
| Fase 0–1 (go-live) | Todo lo descrito arriba + migración del histórico del Excel (bases al Sprint 2; deudas, facturas y presupuestos al Sprint 7). | 10 semanas (decisión de alcance N-01) |
| Double-run | COMPAS + Excel en paralelo hasta 4 conciliaciones semanales cuadradas + 1 cierre mensual completo → Excel a solo-lectura. | Post go-live |
| Fase 1.5 | Modo 'ligada a ventas' del presupuesto (unidades proyectadas × costo unitario) + pestaña Horizonte 18–24 meses. (El pre-llenado del % global desde la proyección de ventas ya opera desde el go-live.) | 1–2 semanas, tras el apagado del Excel (típicamente semanas 5–6 post go-live) |
| Fase 2 | Motor de proyección de ingresos del MODELO SIMULADOR 2030 con escenarios, caja proyectada a 12–18 meses y lectura del recaudo real desde SISMO. | 4 semanas (tras operación estable medida por SLOs) |


