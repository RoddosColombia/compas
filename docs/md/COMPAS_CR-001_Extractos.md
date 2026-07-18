COMPAS

Change Request CR-001

Gestión de extractos mensuales como fuente de verificación y corrección

COMPAS-CR-001 v1.0 — Primer cambio bajo control de cambios post-GO

RODDOS S.A.S. — Oficina del CTO

18 de julio de 2026

# Metadatos

| Atributo | Valor |
| --- | --- |
| Solicitante / Fecha | CEO Andrés Sanjuan — 18-jul-2026 (post-certificado GO v1.1.2) |
| Requerimiento textual | "Extractos y movimientos tenemos que poder administrar: movimientos diarios y extractos para corregir cifras. La documentación ya está en el proyecto." |
| Evidencia analizada | movements072026_072026.xls (export Global66 de movimientos con ID de transacción) y extracto_movements052026.pdf (extracto mensual Global66 con saldo de inicio $21.955.333,91 y final $7.358.444,05 del período May-2026) |
| Clasificación | PRECISIÓN sobre módulos existentes (M4 Conciliación + M7 Cargas) + 1 entidad nueva liviana. NO es módulo nuevo |
| Impacto en cronograma | NINGUNO — se implementa dentro del Sprint 4 (conciliación), esfuerzo estimado 1–1,5 días ya cubiertos por el buffer del plan |
| Impacto en costo / decisiones / criterios | Ninguno. El DoD no cambia; la demo del Sprint 4 (G3) incluirá la verificación por extracto |
| Documentos afectados | PRD M4/M7 y Spec (entidad ExtractoMensual + 2 endpoints) — se incorporan como v1.2 en el primer re-baseline natural; mientras tanto este CR-001 es el documento normativo del cambio |



# 1. Qué ya estaba cubierto (sin cambio)

- Movimientos diarios: M7 con cadencia 8:30, parsers por banco, deduplicación por (banco, id_banco) — el export de Global66 del proyecto trae 'ID de la transacción', que es exactamente la clave prevista.

- Corrección de cifras: la conciliación de M4 (diferencia vs banco), el ancla mensual del saldo (F-14, con transacción de 'Ajuste de conciliación' auditada) y la política de movimientos tardíos (F-08) ya son el mecanismo formal de corrección.

# 2. El delta que introduce este CR

Hoy el 'saldo según banco' de MesControl.saldos_banco se digitaría manualmente. Con CR-001, ese dato sale del extracto mensual oficial: el Financiero carga el extracto (PDF o export) de cada banco al cerrar el período, COMPAS registra sus saldos y totales, y ejecuta la verificación contra la base transaccional.

## 2.1 Entidad nueva: ExtractoMensual

| Campo | Tipo | Notas |
| --- | --- | --- |
| banco / periodo (YYYY-MM) | Enum, Date | Único compuesto — un extracto por banco por mes |
| saldo_inicial / saldo_final | Decimal | Del documento oficial (ej. 'Inicio de período' / 'Final de período' del PDF Global66) |
| total_debitos / total_creditos / n_movimientos | Decimal, Int | Si el documento los trae o son derivables del detalle |
| archivo_s3_key / archivo_hash | String | El PDF/export original se conserva (prefijo compas/archivos/), SHA-256 anti-duplicado |
| estado_verificacion | Enum | pendiente | cuadrado | con_diferencias |
| resultado | Object | {dif_saldo_final, movimientos_faltantes[], movimientos_sobrantes[]} — calculado |
| cargado_por / created_at | ObjectId, DateTime | Auditoría (evento nuevo: extracto.cargado — catálogo pasa de 29 a 30) |



## 2.2 Verificación automática (regla de negocio)

- Al cargar el extracto: saldo_final del extracto vs. caja calculada del banco en la base → alimenta MesControl.saldos_banco (reemplaza la digitación manual) y la 'Diferencia vs banco'.

- Cruce del detalle (cuando el formato lo permite, ej. Global66 por ID): movimientos del extracto ausentes en la base → lista de faltantes para cargar/corregir; movimientos en la base sin respaldo en el extracto → sobrantes para revisar.

- Las correcciones derivadas usan los mecanismos existentes: carga del movimiento faltante (dedup lo protege), reclasificación auditada, o 'Ajuste de conciliación' (F-14). El extracto NUNCA modifica la base directamente — propone, el humano corrige.

- El cierre de mes (checklist) exige extracto cargado y en estado 'cuadrado' (o diferencia justificada) por cada banco activo.

## 2.3 Superficie técnica

- Endpoints: POST /extractos (multipart, banco+periodo) · GET /extractos?periodo · GET /extractos/{id}/verificacion. Permisos: Financiero/Admin (misma fila de cargas de la matriz).

- Parser del extracto Global66 (PDF, pdfplumber) para saldos y detalle; para Bancolombia/BBVA se parte de los formatos de SISMO v2 y se valida con los documentos del Día 0. Si un extracto no es parseable, los saldos se digitan con el documento adjunto como evidencia — la trazabilidad no se pierde.

- Vista: sección 'Extractos' dentro de Cargas (menú Administración) + tarjeta de estado de verificación en la vista de Caja/Conciliación del mes.

# 3. Justificación del veredicto 'sin impacto'

El criterio del plan (compromiso #7 del Tech Lead) exige declarar el impacto de todo cambio. Este CR: no altera decisiones (la conciliación por banco ya era del alcance), no altera mecanismos de seguridad ni DR, no altera costos (el almacenamiento del PDF usa el prefijo S3 existente), y no altera criterios de aceptación (el DoD-4 de conciliación se cumple ahora con mejor evidencia). La entidad y los 2 endpoints caben en el Sprint 4 junto a la conciliación, cuyo alcance natural ya era este. Lección de la auditoría aplicada: se declara ANTES de construirse, con documento propio y trazabilidad.

| Aprobación requerida: CEO (solicitante) — la firma de este CR-001 autoriza su inclusión en el Sprint 4 y su incorporación documental como v1.2 en el siguiente re-baseline. El auditor externo puede incluirlo en su verificación puntual del gate G3. |
| --- |


