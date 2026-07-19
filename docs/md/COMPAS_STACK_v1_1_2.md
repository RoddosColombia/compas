COMPAS

Stack Tecnológico Definitivo

Mismos proveedores de SISMO V3 — cero cuentas nuevas

COMPAS-STACK-003 v1.1.2 — Errata de cierre para VERDE (18-jul-2026)

RODDOS S.A.S. — Oficina del CTO

18 de julio de 2026

# Histórico de versiones

v1.0 (17-jul) auditada el 18-jul-2026. Esta v1.1 incorpora las correcciones de infraestructura, DevOps, seguridad y costos. Cada cambio referencia su hallazgo (F-XX).

| Cambio v1.0 → v1.1 | Hallazgo |
| --- | --- |
| §2: los jobs financieros salen del proceso web → Render Background Worker dedicado de 1 instancia con RUN_SCHEDULER=true; todos los jobs idempotentes (decisión escrita) | F-01 (Crítica) |
| §4.3: DR reescrito — RPO honesto 24 h, procedimiento de restauración selectiva con regla anti in-place que protege a SISMO, prueba cronometrada trimestral, archivado de 7–10 años a S3 Glacier con Object Lock | F-30, F-31 |
| §5: tabla de costos corregida (nombre exacto de instancia Render, minutos de Actions, staging sin sleep, worker, S3) con total por fase; región declarada; Configuracion en BD en vez de env vars de negocio | F-38, F-39, F-45, F-35 |
| §6: gate humano de producción (GitHub Environments + required reviewer), tags protegidos, contradicción de despliegue resuelta, política de rollback y migraciones expand/contract, render.yaml + runbook de infraestructura, escaneo de seguridad en CI | F-32, F-33, F-37, F-28 |
| §7: alertas con canal y dueño, uptime check, SLOs, alertas de infraestructura Atlas/Render con disparadores numéricos para migrar de cluster, logs WARNING+ archivados | F-36, F-34 |
| §8: paquete completo de seguridad — revocación JWT + logout + MFA + política de contraseñas + almacenamiento del token + IAM S3 por prefijo + defensas de upload + redacción de PII + cabeceras + runbook de secretos | F-15/16/17/19/22/23/26/27/29 |



## Parche v1.1 → v1.1.1 (re-auditoría)

| Cambio | Hallazgo |
| --- | --- |
| Worker con heartbeat POR JOB (Better Stack Heartbeats) + alerta de ausencia + coalesce/misfire_grace_time declarados + catch-up del snapshot + runbook de re-ejecución manual del dump | N-04 |
| Archivado: bucket NUEVO compas-archivo (misma cuenta AWS) con Object Lock habilitado en creación — AWS solo lo permite en buckets nuevos; IAM con PutObjectRetention solo para el job; job agendado (Sprint 6b) | N-05 |
| DR regional coherente: CRR de compas/backups/ y compas-archivo a segunda región (centavos/mes); región primaria heredada de SISMO y NOMBRADA en RUNBOOK-INFRA el Día 0 | N-06, F-39 |
| Break-glass con mecanismo: credenciales en gestor/sobre sellado, custodio nombrado en el RUNBOOK, uso dispara alerta + evento, revisión trimestral; par revisor y 2 personas con acceso a secretos nombrados el Día 0 | N-07 |
| Decisión antivirus DOCUMENTADA (cierra F-22): sin AV en Fase 0–1 con justificación; re-evaluar si se abre la carga a terceros | N-14 |
| Render Standard = 2 GB RAM / 1 vCPU; operación ~$33–55/mes (mínimo con staging pausado); colecciones facturas_emitidas y costos_unitarios añadidas | nits 5, 6; N-11 |



v1.1.2 (18-jul-2026): errata de cierre E-1..E-6 + barrido de textos, según el informe de calificación final (8.9/10). Ningún cambio de decisión, mecanismo, costo ni criterio de aceptación; E-1 unifica la datación del pre-llenado del '% global' en Sprint 6b.

# 0. Resumen Ejecutivo

COMPAS reutiliza el 100% de los proveedores de infraestructura de SISMO V3: MongoDB Atlas, Render, Vercel, Cloudflare, GitHub (+ Actions), Sentry y Better Stack. No se abre ninguna cuenta nueva; solo recursos nuevos dentro de las cuentas existentes. El stack de código es idéntico al de SISMO (Python/FastAPI + React/TypeScript), permitiendo portar auth, RBAC, audit log y exportación Excel. El aislamiento respecto a SISMO es lógico (databases, prefijos S3, secretos propios), no de cuenta: por eso esta versión endurece IAM, DR y el blast radius compartido.

| Capa | Proveedor | Recurso COMPAS | Cuenta |
| --- | --- | --- | --- |
| Base de datos | MongoDB Atlas 7.0 | Database 'compas' (cluster compartido, Opción A; disparadores numéricos para Opción B en §7) | Existente |
| Backend API | Render | Servicio web 'compas-api' (instancia Standard) | Existente |
| Jobs financieros | Render | Background Worker 'compas-jobs' — 1 instancia (F-01) | Existente |
| Frontend | Vercel | Proyecto 'compas' | Existente |
| DNS / TLS / WAF | Cloudflare | compas.roddos.com (single-region consciente, F-39) | Existente |
| Repo + CI/CD | GitHub + Actions | Repo privado 'compas' (monorepo) + Environments protegidos | Existente |
| Errores / Logs | Sentry / Better Stack | compas-api, compas-web / source 'compas' (PII redactada) | Existente |
| Archivos y backups | S3 (bucket SISMO + bucket nuevo compas-archivo con Object Lock) | Prefijos compas/archivos/ y compas/backups/ con IAM propio (F-19) + archivado N-05 | Existente (cuenta AWS) |



# 1. Filosofía Arquitectónica

## 1.1 Principios irrenunciables

- Validación estricta en la frontera: Pydantic strict=True; ningún payload sin schema.

- Dinero = Decimal COP end-to-end, nunca float — incluido el frontend: montos como string decimal + decimal.js-light, cálculo solo en backend (Spec §0.2).

- Todo evento financiero es auditable y el histórico es inmutable; todo job es idempotente (re-ejecutar nunca corrompe).

- Reutilizar antes que reescribir: módulos de SISMO portados con documentación de qué se portó (mitigación de persona clave).

## 1.2 Anti-principios

- No microservicios ni GraphQL; no Docker en Fase 0–1 (Render hace el build).

- No integraciones bancarias por API en Fase 0–1: carga por archivo. La evaluación de agregadores (Belvo) queda para el roadmap post-Fase 2 del PRD §1.3.

- No duplicar datos de SISMO: el recaudo real (Fase 2) se leerá por API interna.

- No reglas de negocio en variables de entorno: umbrales y calendario DIAN viven en la colección Configuracion, editables por Admin con auditoría (F-45); env vars solo para secretos y conexiones.

# 2. Backend

| Componente | Selección | Notas |
| --- | --- | --- |
| Lenguaje / Framework | Python 3.12 + FastAPI 0.115+ | REST /api/v1 + OpenAPI |
| Validación / ODM | Pydantic v2.9+ strict / Beanie 1.27+ / Motor 3.6+ | Transacciones multi-documento en los 3 flujos críticos (Spec §2.2.6) |
| Jobs financieros (F-01) | Render Background Worker 'compas-jobs' (1 instancia) + APScheduler con RUN_SCHEDULER=true | DECISIÓN: el servicio web NUNCA arranca el scheduler (flag por entorno). Jobs (8): RECORDATORIO DE CARGA DIARIA 8:30 América/Bogotá (verifica carga del día anterior por banco; si falta, alerta al Financiero), snapshot diario de caja (UPSERT por fecha, corte 23:59, con CATCH-UP de días faltantes), recálculo de sugeridos, alertas IVA/vencimientos, reaper de cargas, dump nocturno, ARCHIVADO MENSUAL a compas-archivo (N-05), verificación referencial. Todos idempotentes; jobstore en MongoDB; APScheduler con coalesce=True y misfire_grace_time por job; CADA JOB reporta a un heartbeat de Better Stack — la AUSENCIA de ejecución dispara alerta (N-04); runbook de re-ejecución manual del dump |
| Parsing bancario | openpyxl 3.1+ (read_only streaming) y pandas 2.2+ | En threadpool del API (anyio.to_thread) para cargas interactivas; límites de F-22 |
| Excel salida / HTTP | openpyxl / httpx 0.27+ | Reporte de cierre; Fase 2: SISMO API |
| Testing | pytest 8+ · k6 para carga (F-47) | Fixtures reales anonimizados fuera del repo |



| Regla de oro: el parser transforma, nunca interpreta. La conversión de moneda de Global66 no es interpretación del parser: es un mapeo documentado (tasa del extracto conservada con el monto original — Spec §1.5). |
| --- |



# 3. Frontend

Sin cambios de stack respecto a v1.0 (TypeScript 5.6+, React 19, Vite 6+, Tailwind 4, shadcn/ui, TanStack Query v5, RHF+Zod, React Router 7, Recharts, Lucide, Vitest+RTL+Playwright, Biome), con estas precisiones de la auditoría:

- Montos: nunca Number; decimal.js-light + Intl.NumberFormat('es-CO') formato $ 1.234.567,89; fechas dd-mmm-aaaa (F-12, F-50).

- Tokens: access solo en memoria de la SPA; refresh en cookie HttpOnly; Secure; SameSite=Strict path /auth. Nada en localStorage (F-17).

- Convención de query keys de TanStack Query por mes ['mes', 'YYYY-MM', vista] con invalidación tras toda mutación financiera (F-10); el badge del navbar (GET /dashboard/badges) se refresca con la misma invalidación.

- Navegación (PRD M13.1): mes de control global en el header y en la URL (/:mes/:vista con React Router); 'Ingresos'/'Egresos' comparten componente y codepath (una sola vista de transacciones con filtro pre-aplicado); navbar generado desde un único config derivado de la matriz de permisos del Spec §4.1; en tablet colapsa a 'Más' preservando Inicio, Control y Pagos semana.

- Accesibilidad objetivo WCAG 2.1 AA vía Radix/shadcn; dashboard legible en tablet; 2–3 wireframes de la vista Presupuesto antes del Sprint 3 (F-50).

- El PDF del reporte de junta se produce con la vista de impresión del navegador sobre la plantilla del reporte (F-49).

# 4. Base de Datos

## 4.1 Selección

Database compas en el cluster M10 existente (Opción A), con usuario de conexión propio limitado por database. Opción B (cluster propio ~$60-80/mes) se activa por los disparadores numéricos de §7. PostgreSQL documentado y descartado para Fase 0–1 (sin proveedor nuevo, reutilización de Beanie); el Data Dictionary es portable.

## 4.2 Colecciones (v1.1.2)

users, rubros, meses_control, presupuesto_lineas, transacciones, cargas_bancarias, pagos_planeados, deudas, deuda_cuotas, facturas_recibidas, facturas_emitidas (N-11), periodos_iva, parametros_ingreso, snapshots_caja, reglas_clasificacion, configuracion, costos_unitarios (Fase 1.5), audit_log, idempotency_keys, jwt_denylist (TTL 30 días).

## 4.3 Backups y disaster recovery (F-30, F-31)

- RPO comprometido: 24 h (ruta primaria propia: mongodump nocturno de la database compas → S3 compas/backups/, retención 90 días). Los snapshots de Atlas cada 6 h son capa adicional del cluster, no el compromiso de COMPAS.

- Procedimiento primario de restauración: mongorestore --nsInclude='compas.*' --drop desde el dump S3 a la database compas. REGLA ESCRITA: un snapshot de Atlas jamás se restaura in-place sobre el cluster compartido (sobrescribiría las bases de SISMO V3 en producción); solo a cluster temporal o mediante restauración selectiva por database de Atlas.

- Prueba de restauración CRONOMETRADA con verificación de totales de control: antes del go-live (DoD-10) y trimestral recurrente. RTO objetivo ≤ 4 h, medido, no declarado.

- Archivado de largo plazo (F-31, N-05): job mensual del worker (agendado; se construye en Sprint 6b) al cierre de mes → bucket NUEVO 'compas-archivo' (misma cuenta AWS — un bucket nuevo NO es una cuenta nueva) creado con Object Lock en modo compliance, porque AWS solo permite habilitarlo en buckets nuevos; contenido: audit_log del periodo, colecciones del mes cerrado y originales; lifecycle a Glacier Deep Archive; retención según política del PRD §5 (10 años comercio / 5 tributarios); el IAM del job es el único con PutObjectRetention. Retención configurada POR CLASE de objeto + lifecycle de expiración al vencimiento; la supresión de datos personales del archivo se difiere a ese vencimiento (matiz E-5, ver PLAN §8), mientras en la base viva es inmediata.

- Resiliencia regional (N-06, F-39): replicación CRR de compas/backups/ y del bucket compas-archivo a una SEGUNDA región (costo de centavos/mes) — ante pérdida regional los dumps y el archivo sobreviven; la región primaria se hereda de SISMO y queda NOMBRADA en el RUNBOOK-INFRA como entregable del Sprint 0 (checklist: el bucket destino de la CRR se crea TAMBIÉN con Object Lock); el RTO regional (~1 día por re-aprovisionamiento) ahora sí es alcanzable porque los datos existen en la réplica.

- La prueba de restauración usa datos reales de forma transitoria en staging con borrado verificado y registrado (F-25).

# 5. Infraestructura y costos (F-38)

| Recurso | Plan exacto | Costo/mes |
| --- | --- | --- |
| compas-api (Render) | Instancia Standard (2 GB RAM / 1 vCPU — nit 5) | $25 |
| compas-jobs (Render) | Background Worker Starter, 1 instancia (F-01) | $7 |
| Staging (Render) | Starter SIN sleep — paridad suficiente para demos/UAT; pruebas de DR y carga se hacen contra instancia temporal tamaño producción (F-35) | $7 |
| Vercel / Cloudflare | Proyecto en plan existente / zona existente | $0 |
| Atlas Opción A | Database en cluster M10 existente | $0 marginal |
| GitHub Actions | Free tier org ≈ 2.000 min/mes COMPARTIDOS con SISMO; pipeline con Playwright ≈ 13–30 min/PR → presupuestar minutos extra durante construcción | $0–16 |
| S3 | Prefijos compas/ + bucket compas-archivo (Object Lock) + Glacier + réplica CRR | $1–4 |
| Sentry / Better Stack | Proyectos en cuentas existentes | $0–10 |



Total estimado: ~$40–70 USD/mes durante la construcción (staging + minutos de CI activos); ~$40–55 USD/mes en operación estable — mínimo ~$33 con staging pausado (nit 6). Si se migra a cluster propio (Opción B): +$60–80. Cifras a reconfirmar contra la facturación real de la organización.

## 5.1 Entornos, región y secretos

- Entornos: development (local) · staging (Render Starter sin sleep + database compas_stg SOLO con datos anonimizados, F-25) · production.

- Región (F-39): single-region, heredada de la infraestructura SISMO (Render/Atlas región efectiva actual + S3 misma región), como decisión consciente de costo para Fase 0–1. Los respaldos y el archivo se REPLICAN a una segunda región (CRR, §4.3): lo single-region es el CÓMPUTO. Ante pérdida regional el RTO es el de re-aprovisionamiento desde runbook + restore desde la réplica (~1 día) (E-4).

- Secretos por entorno en Render/Vercel/Actions: MONGODB_URI_COMPAS, JWT_SECRET propio, SENTRY_DSN, S3 keys del IAM user dedicado. Los umbrales y calendario DIAN NO son secretos: viven en Configuracion (F-45).

# 6. DevOps y CI/CD (F-32, F-33, F-37, F-28)

- Repo GitHub privado 'compas', monorepo backend/ + frontend/; trunk-based; Conventional Commits.

- Despliegue — contradicción de v1.0 resuelta: merge a main → deploy automático SOLO a staging (auto-deploy de producción DESACTIVADO en Render y Vercel). Producción despliega únicamente con tag v* mediante job de Actions con environment: production y required reviewer humano (gate de despliegue). Tags v* protegidos.

- Rollback (F-33): aplicación = redeploy de la versión anterior (Render) / instant rollback (Vercel), capacidad nativa ya pagada. Migraciones backward-compatible (expand/contract) salvo excepción aprobada; dump verificado antes de toda migración destructiva; criterio escrito rollback vs. fix-forward.

- Pipeline por PR: lint → tests backend → tests frontend → build → pip-audit + gitleaks (bloqueantes); Dependabot activo; test de cabeceras de seguridad y de inmutabilidad del audit_log en CI (F-28, F-29, F-21).

- Aprovisionamiento reproducible (F-37): render.yaml (Blueprint) en el repo + docs/RUNBOOK-INFRA.md con el checklist completo (Atlas, Vercel, Cloudflare, S3/IAM, Sentry, Better Stack, secretos, environments). Su existencia es evidencia de cierre del Sprint 0.

# 7. Observabilidad (F-36, F-34)

- structlog JSON con allowlist de campos → Better Stack (30 días) + archivado de logs WARNING+ a S3 para cubrir el ciclo IVA cuatrimestral y auditoría anual.

- Sentry con send_default_pii=False y before_send que elimina descripcion, proveedor, acreedor, valor, Authorization y tokens; test de que ningún log contiene campos de Transaccion/Deuda (F-23).

- Toda alerta tiene canal y dueño: canal WhatsApp/email del equipo financiero para las de negocio (dif vs banco > umbral, categoría >100%, vencimiento IVA 30/15/5, carga fallida, job nocturno fallido) y del Tech Lead para las técnicas.

- Uptime check sobre compas.roddos.com y /health (Better Stack). SLOs mínimos: disponibilidad 99,5% mensual y p95 de carga de dashboard < 2 s — con ellos se mide el '1 mes de operación estable' que habilita la Fase 2.

- Alertas de infraestructura y disparadores de migración a cluster propio (F-34): Atlas Alerts a canal del Tech Lead; se pasa a Opción B si CPU normalizada > 70% sostenida 7 días, o conexiones > 60% del límite, o p99 de SISMO degradado atribuible a COMPAS. Revisión formal de métricas a +30 días del go-live como criterio de permanencia en Opción A.

# 8. Seguridad (paquete v1.1.2)

## 8.1 Autenticación y sesiones (F-15, F-16, F-17, F-26)

- JWT con token_version en el claim, validado en cada request → desactivar usuario o cambiar contraseña revoca acceso de inmediato. POST /auth/logout revoca la familia de refresh (jti en denylist Mongo con TTL). Rotación de refresh con detección de reuso. Topes: access 15 min · refresh idle 12 h · máx 30 días.

- MFA TOTP obligatorio para Admin y Directivo antes del go-live; códigos de respaldo; step-up para reabrir mes, editar saldo inicial y cambiar Configuracion. Break-glass con mecanismo (N-07): credenciales en gestor de contraseñas o sobre sellado bajo un CUSTODIO nombrado en el RUNBOOK-INFRA (Día 0); su uso dispara alerta inmediata dedicada, y el evento queda cubierto por el user.login de la cuenta break-glass (sin reabrir el catálogo de 29); revisión trimestral de que sigue sellado. El par revisor y las 2 personas con acceso a secretos de producción también se nombran el Día 0.

- Contraseñas: mín 12 chars (Admin/Directivo) / 10 (resto), verificación HIBP k-anonymity, backoff progresivo por cuenta (5 fallos → 15 min) además del rate limit por IP; sin expiración periódica salvo compromiso (NIST 800-63B).

- Token storage: access en memoria; refresh en cookie HttpOnly; Secure; SameSite=Strict; verificación de Origin en mutaciones.

## 8.2 Datos y archivos (F-19, F-22, F-23)

- IAM user S3 dedicado limitado a compas/* (Get/Put, sin Delete); Block Public Access + SSE; prefijos compas/archivos/ y compas/backups/ con lifecycle. COMPAS no puede leer backups de SISMO ni viceversa.

- Descarga de originales solo vía presigned URL ≤ 15 min, con permiso explícito de la matriz y evento archivo.descargado.

- Uploads: 10 MB, ~20.000 filas, ratio de descompresión acotado, .xlsm rechazado, parseo streaming, descarga con attachment + nosniff.

- Decisión documentada sobre antivirus (N-14, cierra F-22): NO se adopta escaneo AV de uploads en Fase 0–1. Justificación: solo usuarios autenticados (Financiero/Admin) cargan archivos, los formatos aceptados son xlsx/csv sin macros (.xlsm rechazado), el parseo es streaming sin ejecución de contenido, y las descargas son no-ejecutables (attachment + nosniff). La decisión se re-evalúa obligatoriamente si alguna vez se abre la carga a fuentes externas o terceros.

## 8.3 Perímetro, secretos y gobierno (F-29, F-27, F-28)

- Cabeceras: CSP estricta (sin unsafe-inline), HSTS vía Cloudflare, X-Content-Type-Options: nosniff, Referrer-Policy: no-referrer, frame-ancestors 'none' — middleware + test en CI.

- Runbook de secretos: rotación semestral, inventario con responsable, procedimiento de compromiso (rotar JWT_SECRET + bump global de token_version); acceso a variables de producción restringido a 2 personas; environments de GitHub protegidos.

- El gate G1 del PLAN es bloqueante con checklist de seguridad y aprobador distinto del ejecutor (ver PLAN v1.1.2).

- Cumplimiento Ley 1581: los artefactos y el workstream legal se definen en PRD v1.1.2 §5; este stack aporta los controles técnicos (autorizacion_tratamiento, redacción de PII, IAM, auditoría de acceso).
