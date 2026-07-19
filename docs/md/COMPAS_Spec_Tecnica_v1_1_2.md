COMPAS

Especificación Técnica

Data Dictionary · Domain Model · User Stories · Definition of Done

COMPAS-SPEC-002 v1.1.2 — Errata de cierre para VERDE (18-jul-2026)

RODDOS S.A.S. — Oficina del CTO

18 de julio de 2026

# Histórico de versiones

v1.0 (17-jul-2026) fue sometida a auditoría técnica fullstack independiente el 18-jul-2026 (veredicto ROJO de proceso, 51 hallazgos). Esta v1.1 incorpora todas las correcciones documentales que aplican a este documento. Cada cambio referencia su hallazgo (F-XX).

| Cambio v1.0 → v1.1 | Hallazgo |
| --- | --- |
| §0: glosario de tolerancias (TOLERANCIA_CUADRE $1 / UMBRAL_DIF_BANCO_CIERRE $50.000) y contrato de serialización de montos y fechas | F-44, F-12 |
| §1.4: definición matemática exacta del sugerido + ejemplo numérico resuelto; los compromisos M6/M8/M9 salen de la fórmula y pasan a fila informativa | F-07 |
| §1.5: campos de moneda original para Global66; §1.6: ciclo de vida de cargas (reproceso de fallidas, reaper, threadpool, límites de archivo) | F-03, F-02, F-22 |
| Nuevas entidades: SnapshotCaja, ReglaClasificacion, Configuracion; saldos por banco en MesControl; autorización de tratamiento en Deuda/Factura | F-10, F-45, F-20 |
| §2: índices parciales (manuales, vigente:true), transacciones multi-documento, política de movimientos tardíos, matching de conciliación, ancla de saldo al banco | F-04, F-06, F-09, F-08, F-05, F-14 |
| §2.4: tabla única de autoridad del ciclo mensual | F-43 |
| §4: /api/v1, paginación, POST manual, auth endurecida, matriz permiso×endpoint, idempotencia especificada, PDF de cierre definido | F-11, F-15, F-18, F-13, F-49 |
| §1.11: eventos de auditoría ampliados (+11) con test de inmutabilidad en CI | F-21 |
| §5 DoD: ampliado de 8 a 12 puntos (seguridad, carga/rendimiento, DR cronometrado) | F-28, F-47, F-30 |



## Parche v1.1 → v1.1.1 (re-auditoría)

| Cambio | Hallazgo |
| --- | --- |
| Modo 'ligada a ventas' y costos unitarios quedan ESPECIFICADOS pero marcados Fase 1.5; go-live 100% en modo histórico; demo Sprint 3 declarada (agosto-2026, '% global' manual) | N-01, N-03 |
| FacturaEmitida completada: campo tarifa (19/5/0-exenta), base legal del cliente, acceso a evidencia acotado en la matriz, eventos editada/anulada, colecciones e índices, endpoints y permisos | N-09, N-11, N-08 |
| Catálogo de auditoría cerrado en 29 eventos (incluye crec_modificado, crec_global_aplicado, iva_generado.override, transaccion.tardia, factura_emitida.*); DoD #6 corregido | N-08, nit 1 |
| SnapshotCaja con mes_id y hora de corte; ajuste de conciliación con mes de imputación; herencia de monto_definido y flip atómico de vigente; idempotency único compuesto; jwt_denylist con TTL = 30 días | nits 8, 9, 12, 10 |
| Fixtures: entrega Día 0, congelamiento de layouts como primer entregable del Sprint 1; DoD #9 con volumen sintético; DoD #10 contra instancia temporal tamaño producción; método de 'Horizonte' definido (Fase 1.5) | nits 2, 3, 7; N-12 |



v1.1.2 (18-jul-2026): errata de cierre E-1..E-6 + barrido de textos, según el informe de calificación final (8.9/10). Ningún cambio de decisión, mecanismo, costo ni criterio de aceptación; E-1 unifica la datación del pre-llenado del '% global' en Sprint 6b.

# 0. Base

Prerrequisito: PRD v1.1.2 aprobado. Tecnología: MongoDB Atlas (misma organización de SISMO), database compas. Motor async (Python) + Pydantic/Beanie con strict=True; ningún documento se guarda sin validar schema. Zona horaria única América/Bogotá. Moneda única de registro: COP con Decimal (2 decimales); las transacciones conservan su moneda original cuando aplique (§1.5).

## 0.1 Glosario de tolerancias y umbrales (F-44)

| Constante | Valor | Se aplica a |
| --- | --- | --- |
| TOLERANCIA_CUADRE | $1 COP | Validación de facturas (subtotal+seguro+iva=total), sumas de control de migración, verificaciones internas de totales. |
| UMBRAL_DIF_BANCO_CIERRE | $50.000 COP (default, editable por Admin en Configuracion) | Condición de cierre de mes y KPI 'Diferencia vs banco'. |
| UMBRAL_CARGA_STALE | 15 minutos | Reaper de cargas: 'procesando' más antigua → 'fallida' con motivo. |



## 0.2 Contrato de serialización (F-12)

- Los montos viajan por la API como string decimal (Pydantic v2 serializa Decimal como string). El frontend NUNCA convierte montos a Number: los maneja con decimal.js-light y solo formatea con Intl.NumberFormat('es-CO').

- Todo cálculo financiero (disponible, caja tras pago, %, totales, sugeridos) se computa en backend. El frontend presenta, no calcula.

- Fechas como YYYY-MM-DD; datetimes ISO-8601 con offset -05:00 explícito.

# 1. Data Dictionary

## 1.1 Entidad: User

| Campo | Tipo | Req | Validación / Notas |
| --- | --- | --- | --- |
| _id | ObjectId | Auto | PK |
| nombre | String(100) | Sí | Mín 3 chars |
| email | String(100) | Sí | Email válido, único. Login |
| password_hash | String(256) | Sí | bcrypt. Política: mín 12 chars Admin/Directivo, 10 resto; verificación HIBP k-anonymity; backoff por cuenta 5 fallos → 15 min (F-26) |
| rol | Enum | Sí | admin | directivo | financiero | consulta |
| token_version | Int | Sí | Default 1. Incrementa al desactivar/cambiar contraseña → revoca todos los JWT emitidos (F-15) |
| mfa_secret / mfa_habilitado | String, Boolean | Cond | TOTP obligatorio para admin y directivo antes del go-live; códigos de respaldo de un solo uso; cuenta break-glass custodiada (F-16) |
| activo | Boolean | Sí | Soft delete; desactivar incrementa token_version |
| created_at / updated_at | DateTime | Auto | now_bogota() |



## 1.2 Entidad: Rubro

| Campo | Tipo | Req | Validación / Notas |
| --- | --- | --- | --- |
| grupo | Enum | Sí | costo_producto | operacion | nomina | deudas_obligaciones | otros |
| nombre | String(80) | Sí | Único dentro del grupo |
| tipo_flujo | Enum | Sí | egreso | ingreso |
| orden | Int | Sí | Orden en la vista Control |
| activo / es_sistema | Boolean | Sí | Soft delete; 'Por clasificar' y 'Ajuste de conciliación' son de sistema (F-14) |



## 1.3 Entidad: MesControl

| Campo | Tipo | Req | Validación / Notas |
| --- | --- | --- | --- |
| mes | Date (YYYY-MM-01) | Sí | Único. Llave de negocio |
| estado | Enum | Sí | sugerido | propuesto | definido | en_ejecucion | cerrado |
| saldo_inicial_caja | Decimal | Sí | Al cerrar el mes anterior se fija = saldo bancario consolidado reportado; la diferencia contra el saldo calculado se contabiliza como transacción de 'Ajuste de conciliación' auditada — evita deriva acumulativa (F-14). Editable solo por Admin con step-up MFA y evento saldo_inicial.editado |
| saldos_banco | Array[{banco, saldo, fecha_reporte}] | No | Saldo por banco + consolidado calculado (F-10) |
| ingresos_esperados_semana | Decimal | No | Producido por M10 (ParametroIngreso); editable por Financiero con auditoría |
| definido_por / definido_at / cerrado_por / cerrado_at | ObjectId, DateTime | No | Trazabilidad del ciclo |



## 1.4 Entidad: PresupuestoLinea + motor del sugerido (F-07)

| Campo | Tipo | Req | Validación / Notas |
| --- | --- | --- | --- |
| mes_id / rubro_id / version | ObjectId, Int | Sí | (mes_id, rubro_id, version) único |
| monto_sugerido | Decimal | Sí | Resultado de la fórmula §1.4.1 (snapshot inmutable) |
| prom_3m / tendencia_mes / crec_pct | Decimal | Sí | Componentes guardados para verificación celda a celda |
| compromisos_programados | Decimal | Calc | Fila INFORMATIVA: Σ DeudaCuota del mes + facturas con mes_pago + IVA con vencimiento en el mes. NO entra en la fórmula; se muestra junto al sugerido para que el Directivo la considere al acotar (F-07, decisión a) |
| monto_definido | Decimal | No | Valor acotado. Null hasta aprobar |
| historia_incompleta | Boolean | Sí | true si el sugerido se calculó con < 3 meses cerrados |
| modo_calculo | Enum | Sí | historico | ventas — default historico; el modo ventas es Fase 1.5 (N-01, E-3) |
| ajustes | Array[{valor_anterior, valor_nuevo, autor_id, comentario, ts}] | No | Append-only: cada acotamiento queda registrado (F-06) |
| vigente | Boolean | Sí | Índice único parcial garantiza una sola vigente (§2.3) |



### 1.4.1 Fórmula oficial del sugerido — definición matemática

Para el rubro R y el mes M, usando exclusivamente meses en estado 'cerrado' (E(i) = ejecutado del rubro en el mes i):

| prom_3m = ( E(M−1) + E(M−2) + E(M−3) ) / 3   ·   tendencia_mes = ( E(M−1) − E(M−3) ) / 2   ·   crec_pct = porcentaje POR RUBRO Y POR MES, editable en la vista del ciclo (estados sugerido/propuesto) por Directivo o Financiero — default: el valor usado el mes anterior. Cambiarlo recalcula el sugerido al instante (solo en versiones no aprobadas) y queda auditado con autor. Acción 'Aplicar % global del mes' (evento presupuesto.crec_global_aplicado; ediciones por línea: presupuesto.crec_modificado — N-08): fija un mismo crec_pct a todas las categorías de una vez; en el go-live el valor se digita MANUALMENTE; desde que exista M10 (Sprint 6b) se pre-llena con el crecimiento de ventas proyectado (Δ% motos nuevas vs mes anterior), editable antes de aplicar (N-03).   →   sugerido = prom_3m + tendencia_mes + prom_3m × crec_pct. Equivalencia Excel (hoja 'Presupuesto'): prom_3m ≡ 'Prom. últ. 3M' · tendencia_mes ≡ 'Tendencia $/mes' · crec_pct ≡ 'Crec. %/mes' · sugerido ≡ 'Sugerido mes sig.'. Con menos de 3 meses cerrados se usan los disponibles y la línea se marca historia_incompleta=true. |
| --- |



Ejemplo numérico resuelto: E(abr)=48.000.000, E(may)=61.000.000, E(jun)=75.000.000 → prom_3m = 61.333.333,33; tendencia_mes = (75.000.000 − 48.000.000)/2 = 13.500.000; crec_pct = 15% → sugerido jul = 61.333.333,33 + 13.500.000 + 61.333.333,33 × 0,15 = 84.033.333,33. La demo del Sprint 3 (nota CEO #1) se ejecuta EN MODO HISTÓRICO sobre agosto-2026 (may–jul cerrados y migrados), verifica las 4 columnas contra el Excel congelado, rubro por rubro, con TOLERANCIA_CUADRE; toda discrepancia se resuelve contra la celda del Excel como fuente de verdad (N-03, nit 11).

## 1.5 Entidad: Transaccion

| Campo | Tipo | Req | Validación / Notas |
| --- | --- | --- | --- |
| fecha / descripcion | Date, String(300) | Sí | Texto del extracto |
| valor | Decimal | Sí | > 0, siempre en COP. Signo lo define tipo_flujo |
| moneda_original / valor_original / tasa_cambio / tasa_fuente | String ISO-4217, Decimal, Decimal, String | Cond | Obligatorios cuando el extracto no viene en COP (Global66): se conserva el monto original y la tasa aplicada — el COP es re-derivable y auditable (F-03) |
| tipo_flujo | Enum | Sí | ingreso | egreso |
| rubro_id / mes_id | ObjectId | Sí | Default 'Por clasificar'; mes derivado de fecha |
| banco | Enum | Sí | bancolombia | bbva | global66 | manual |
| id_banco | String(40) | Sí | De extracto si banco ≠ manual; para manuales se genera 'MAN-'+ULID (F-04) |
| tardia | Boolean | Sí | true si se insertó con fecha de un mes ya cerrado (§2.2.4, F-08) |
| carga_id / clasificada_por / clasificada_at | ObjectId, DateTime | No | Origen y auditoría |
| pago_planeado_id / factura_id / regla_id | ObjectId | No | Conciliación y regla que clasificó (F-05) |



## 1.6 Entidad: CargaBancaria — ciclo de vida (F-02)

| Campo | Tipo | Req | Validación / Notas |
| --- | --- | --- | --- |
| banco | Enum | Sí | bancolombia | bbva | global66 |
| archivo_nombre / archivo_hash / archivo_s3_key | String | Sí | SHA-256. El rechazo por hash aplica SOLO si existe carga previa 'completada' con ese hash; si la previa está 'fallida', la re-carga se permite (la dedup por (banco, id_banco) hace el reintento seguro) |
| total_filas / nuevas / duplicadas / errores | Int | Sí | Inserción idempotente por lotes: insertMany ordered=False, duplicados contados por DuplicateKeyError |
| estado / motivo_fallo | Enum, String | Sí | procesando | completada | fallida. Reaper (job): 'procesando' > UMBRAL_CARGA_STALE → 'fallida' con motivo |
| usuario_id / created_at | ObjectId, DateTime | Auto | — |



Ejecución del parseo: en threadpool (anyio.to_thread.run_sync) para no bloquear el event loop; archivos en streaming (openpyxl read_only=True). Límites (F-22): 10 MB, ~20.000 filas, ratio de descompresión acotado; .xlsm se rechaza; descarga de originales con Content-Disposition: attachment + nosniff.

### 1.6.1 Parsers por banco

Esquema canónico y mapeos como en v1.0 (Bancolombia, BBVA, Global66), con precisión para Global66: si el export trae equivalente COP se mapea y se conservan ambos montos + tasa; si no, se usa la tasa del extracto con tasa_fuente='extracto'. Los fixtures reales se ENTREGAN el Día 0 y el congelamiento formal de layouts es el primer entregable del Sprint 1 (nit 2, F-51); cada fixture llega anonimizado por script determinista con verificación automática antes de entrar al repo; los fixtures reales viven en S3 privado, el repo solo contiene sintéticos/anonimizados, con gitleaks en CI (F-25, F-51). Cambios de layout → parser versionado.

## 1.7 PagoPlaneado · Deuda · DeudaCuota · FacturaRecibida · PeriodoIVA · ParametroIngreso

Sin cambios estructurales respecto a v1.0, con estas adiciones:

- Matching de conciliación (F-05): candidatos = transacciones con valor exacto y fecha ∈ [fecha_planeada − 2, + 5 días]; desempate por similitud de texto. Auto-conciliación SOLO con exactamente 1 candidato inequívoco; 0 o >1 → confirmación humana vía POST /pagos-planeados/{id}/conciliar. Cada match registra la regla que lo disparó. Pagos parciales de facturas (1—N) solo por confirmación humana.

- Autorización de tratamiento (F-20): Deuda y FacturaRecibida de personas naturales llevan autorizacion_tratamiento: {otorgada, fecha, evidencia_s3_key}; el alta sin evidencia queda marcada y reportada al workstream legal.

- ParametroIngreso entra a Fase 0–1 (F-40): productor de MesControl.ingresos_esperados_semana (Σ cuotas semanales activas × pct_recaudo / semanas del mes) y del 'ingreso proyectado' del dashboard 'Inicio'. El modo 'ligada a ventas' del sugerido queda especificado pero es FASE 1.5 (decisión N-01): PresupuestoLinea tiene el campo modo_calculo (historico | ventas, default historico); en modo ventas, sugerido = Σ unidades proyectadas del mes por modelo × costo_unitario (colección costos_unitarios: (modelo, mes) único, administrada por Financiero). En el go-live TODAS las líneas usan modo historico (N-03); el modo usado queda en el snapshot de la línea.

- Vista 'Capacidad de pago' de deudas (PRD M6): cálculo en backend, nada persistido salvo el orden de prioridad de acreedores (campo Deuda.prioridad, editable por Admin): holgura = Σ(monto_definido − ejecutado) del mes sobre rubros tipo_flujo=egreso (E-2, como PRD M6) − compromisos programados restantes; meses_restantes = ceil(saldo / cuota_pactada); simulación de abono extra = recálculo de meses_restantes con (cuota + abono). El abono simulado se materializa creando un PagoPlaneado.

## 1.7b Entidad: FacturaEmitida (IVA generado — decisión CEO)

| Campo | Tipo | Req | Validación / Notas |
| --- | --- | --- | --- |
| numero | String(30) | Sí | Único. Numeración de facturación de RODDOS |
| fecha_emision | Date | Sí | Imputa el cuatrimestre del PeriodoIVA |
| concepto / cliente | String(200) | Sí | Ej: venta motos, repuestos; cliente opcional (datos personales bajo Ley 1581 si persona natural) |
| base_gravada / iva / total | Decimal | Sí | base_gravada + iva = total con TOLERANCIA_CUADRE; tarifa de referencia 19% con tolerancia de redondeo |
| tarifa | Enum | Sí | 19 | 5 | 0_exenta — iva coherente con la tarifa (0 para exentas), tolerancia de redondeo (N-09) |
| periodo_iva_id | ObjectId | Auto | Por fecha_emision |
| origen | Enum | Sí | manual | carga_masiva (plantilla xlsx) | api_ventas (Fase 2: Alegra/SISMO) |



PeriodoIVA (v1.1.2): iva_generado es calculado = Σ iva de FacturaEmitida del periodo; el override manual del Admin (transición) dispara el evento iva_generado.override (N-08). Eventos: factura_emitida.creada/editada/anulada. Base legal del tratamiento de datos de clientes persona natural: ejecución del contrato de venta y deber legal de facturación, declarada en la política de tratamiento (N-09). saldo_proyectado se recalcula al alta/edición de facturas de ambos lados.

## 1.8 Entidad: SnapshotCaja (F-10)

| Campo | Tipo | Req | Validación / Notas |
| --- | --- | --- | --- |
| fecha / mes_id | Date, ObjectId | Sí | fecha única — el job diario (corte 23:59 América/Bogotá) hace UPSERT por fecha (idempotente, F-01); mes_id materializa la cardinalidad MesControl 1—N (nit 8) |
| caja_calculada / saldos_banco / diferencia | Decimal, Array, Decimal | Sí | Alimenta la tendencia de 12 meses del dashboard |



## 1.9 Entidad: ReglaClasificacion (F-10)

| Campo | Tipo | Req | Validación / Notas |
| --- | --- | --- | --- |
| patron | String(120) | Sí | Match por texto en descripcion (case-insensitive) |
| rubro_id / tipo_flujo / prioridad | ObjectId, Enum, Int | Sí | Primera regla que matchea por prioridad gana |
| origen | Enum | Sí | manual | aprendida (propuesta desde reclasificaciones repetidas; requiere aprobación del Financiero, nunca auto-activada) |
| activa / creada_por | Boolean, ObjectId | Sí | — |



## 1.10 Entidad: Configuracion (F-45)

Las reglas de negocio parametrizables viven en base de datos, no en variables de entorno: {clave, valor, vigente_desde, modificado_por} con evento config.actualizada. Claves iniciales: UMBRAL_DIF_BANCO_CIERRE, CALENDARIO_DIAN (vencimientos IVA por año/NIT), DIAS_CREDITO_POR_PROVEEDOR. El crecimiento %/mes NO vive aquí: es dato del ciclo mensual, editable por línea en la vista de Presupuesto (§1.4.1). Las env vars quedan solo para secretos y conexiones.

## 1.11 Entidad: AuditLog (F-21)

Append-only, retención según política documental del PRD §5. Catálogo v1.1.1: 29 EVENTOS (nit 1, N-08) = 10 de v1.0 (presupuesto.acotado, presupuesto.definido, mes.cerrado, mes.reabierto, transaccion.clasificada, carga.completada, factura.creada, iva.declarado, rubro.desactivado, user.login) + 12 de v1.1 (mes.creado, user.login_fallido, user.bloqueado, user.creado, user.rol_cambiado, user.desactivado, exportacion.realizada, archivo.descargado, config.actualizada, parametros_ingreso.modificado, saldo_inicial.editado, carga.fallida) + 7 de v1.1.1 (presupuesto.crec_modificado, presupuesto.crec_global_aplicado, iva_generado.override, transaccion.tardia, factura_emitida.creada, factura_emitida.editada, factura_emitida.anulada). Inmutabilidad verificada en CI: rol MongoDB custom con insert+find sin update/remove sobre audit_log, y test automatizado de que un update falla.

## 1.12 Entidad: IdempotencyKeys (F-13)

Header Idempotency-Key generado por el cliente en POST sensibles (cargas, aprobaciones, cierres, transacciones manuales). Scope e índice ÚNICO COMPUESTO: (usuario, endpoint, key) (nit 10). Se almacena hash del request + respuesta original: misma clave + mismo payload → replay de la respuesta original; misma clave + payload distinto → 422. TTL 24h + guards de estado en aprobaciones/cierres.

# 2. Domain Model

## 2.1 Cardinalidades

Como v1.0, más: MesControl 1—N SnapshotCaja; ReglaClasificacion 1—N Transaccion (regla_id).

## 2.2 Reglas de integridad

- Rubro no se elimina con movimientos; 'Por clasificar' y 'Ajuste de conciliación' son inmutables.

- Transaccion inmutable en fecha, valor, moneda/tasa, id_banco y banco; reclasificación y conciliación auditadas.

- Deduplicación por índice ÚNICO PARCIAL (banco, id_banco) con partialFilterExpression {id_banco: {$type: 'string'}}; manuales con id_banco sintético 'MAN-'+ULID — test de coexistencia de dos manuales en el DoD (F-04).

- Mes cerrado: rechaza escrituras EXCEPTO transacciones provenientes de cargas bancarias con fecha del mes cerrado, que se insertan con tardia=true, recalculan la diferencia vs banco de ese mes y disparan alerta + auditoría, sin tocar cifras presupuestales congeladas (F-08). Reapertura solo Admin con step-up MFA.

- Una sola versión vigente por (mes, rubro), garantizada por índice único parcial {vigente: true}. El recálculo de sugeridos solo toca versiones nunca aprobadas (monto_definido null) y queda auditado; las aprobadas generan versión nueva (F-06).

- Transacciones multi-documento de MongoDB (F-09) obligatorias en los 3 flujos multi-doc: aprobación de presupuesto (~30 líneas + MesControl), finalización de carga (transacciones + contadores + estado) y cierre de mes (congelar + arrastrar saldo + ajuste de conciliación). Reintento ante TransientTransactionError; $jsonSchema en colecciones críticas como defensa en profundidad; job nocturno de verificación referencial; test 'aprobación interrumpida converge'.

- Facturas: recibidas subtotal + seguro + iva = total; emitidas base_gravada + iva = total e iva coherente con tarifa — ambas con TOLERANCIA_CUADRE.

- Versionado (nit 12): la versión nueva de PresupuestoLinea HEREDA el monto_definido de la anterior como punto de partida; el flip de 'vigente' (apagar anterior + encender nueva) ocurre dentro de la misma transacción multi-documento — nunca hay cero ni dos vigentes.

- La transacción de 'Ajuste de conciliación' del cierre se imputa con fecha del PRIMER DÍA del mes que abre (nit 9), en el rubro de sistema homónimo.

- AuditLog append-only a nivel de permisos de BD, verificado en CI.

## 2.3 Índices requeridos (v1.1.2)

| Colección | Índice | Propósito |
| --- | --- | --- |
| transacciones | (banco, id_banco) unique PARCIAL {id_banco: string} | Deduplicación sin colisión de manuales (F-04) |
| transacciones | (mes_id, rubro_id) · (fecha) | Control, drill-down, series |
| presupuesto_lineas | (mes_id, rubro_id, version) unique · (mes_id, rubro_id) unique PARCIAL {vigente: true} | Versionado y unicidad de vigente (F-06) |
| snapshots_caja | (fecha) unique | Upsert idempotente del job diario |
| facturas_recibidas | (proveedor, numero) unique · (mes_pago) · (periodo_iva_id) | Compromisos e IVA |
| facturas_emitidas | (numero) unique · (periodo_iva_id) | IVA generado (N-11) |
| costos_unitarios [Fase 1.5] | (modelo, mes) unique | Modo ligada a ventas |
| jwt_denylist | (jti) unique + TTL 30 días (= vida máxima del refresh, nit 10) | Revocación |
| deuda_cuotas | (deuda_id, mes) unique · (mes) | Matriz acreedor × mes |
| audit_log | (entidad, entidad_id, timestamp) | Forense |
| idempotency_keys | (usuario, endpoint, key) unique compuesto + TTL 24h | Replay con el scope de §1.12 (nit 10) |



## 2.4 Tabla única de autoridad del ciclo mensual (F-43)

| Acción | Financiero | Directivo | Admin |
| --- | --- | --- | --- |
| Abrir mes / generar sugerido | ✔ | ✔ | ✔ |
| Proponer/acotar líneas (estado propuesto) | ✔ (registra propuesta) | ✔ | ✔ |
| Aprobar presupuesto (→ definido) | ✖ | ✖ | ✔ (aprobador formal único; los acotamientos del Directivo quedan en ajustes[]) |
| Cierre operativo (ejecutar checklist de cierre) | ✔ | ✖ | ✔ |
| Confirmar cierre (→ cerrado) | ✖ | ✖ | ✔ |
| Reabrir mes cerrado | ✖ | ✖ | ✔ + step-up MFA |
| Editar saldo inicial / Configuracion | ✖ | ✖ | ✔ + step-up MFA |



Esta tabla prevalece sobre cualquier otra redacción del PRD o de las user stories (US-02 y M2 corregidas en consecuencia). Doble firma real (Admin + Directivo con dos campos de aprobador) queda como opción de Fase 2 si el CEO la pide.

# 3. User Stories

Las US-01..08 de v1.0 se mantienen con estas correcciones: US-01 añade evento mes.creado; US-02 se alinea a §2.4 (Directivo acota, Admin aprueba); US-08 añade evento exportacion.realizada. Se agregan dos historias:

## US-09 — Carga fallida y reproceso (F-02)

- Una carga BBVA falla por fila ambigua → 'fallida' con motivo visible. El Financiero corrige el archivo y re-sube: el hash previo NO bloquea porque la carga anterior no está 'completada'.

- Una carga muerta a mitad (deploy) queda 'procesando'; a los 15 min el reaper la pasa a 'fallida'. El cierre de mes no queda bloqueado indefinidamente.

## US-10 — Transacción manual e ingreso en moneda extranjera (F-04, F-03)

- El Financiero registra un egreso en efectivo (banco='manual'): el sistema genera id_banco 'MAN-…'; un segundo manual del día no produce DuplicateKeyError.

- Un ingreso Global66 de USD 100 con tasa 4.100: valor=$410.000 COP, valor_original=100, moneda_original='USD', tasa_cambio=4.100, tasa_fuente='extracto'. La conciliación contra el extracto es re-derivable.

# 4. API — Superficie v1.1.2

Prefijo global /api/v1 (F-11). Toda colección pagina con limit/cursor (default limit=100). Identificador de mes unificado: YYYY-MM en path/query. Tokens: access 15 min solo en memoria de la SPA; refresh en cookie HttpOnly; Secure; SameSite=Strict path /auth, idle 12 h, máx 30 días; verificación de Origin en mutaciones (F-15, F-17).

| Recurso | Endpoints (delta v1.1.1) |
| --- | --- |
| Auth | POST /auth/login (rate limit + backoff por cuenta) · POST /auth/refresh (rotación con detección de reuso: refresh ya rotado → revoca la familia) · POST /auth/logout (jti a denylist con TTL) · POST /auth/mfa/verify + step-up (F-15/16/26) |
| Transacciones | GET /transacciones (paginado) · POST /transacciones (banco='manual', Idempotency-Key) · PATCH /transacciones/{id}/rubro |
| Config | GET/PATCH /configuracion (Admin + step-up; evento config.actualizada) |
| Reglas | CRUD /reglas-clasificacion · POST /reglas-clasificacion/{id}/aprobar (aprendidas) |
| Facturas emitidas | CRUD /facturas-emitidas · POST /facturas-emitidas/carga-masiva (Idempotency-Key) — IVA generado (N-11) |
| Deudas · Capacidad de pago | GET /deudas/capacidad-pago?mes · POST /deudas/{id}/simular-abono (no persiste) · POST /deudas/{id}/abono-a-pago-planeado (N-11) |
| Costos unitarios [Fase 1.5] | GET/PUT /costos-unitarios?mes (Financiero/Admin) |
| Reportes | GET /reportes/cierre/{mes}.xlsx (permiso export explícito). El PDF de junta se genera desde la vista de impresión del navegador sobre la plantilla del reporte — sin librería PDF server-side en Fase 0–1; PRD M12 corregido en consecuencia (F-49) |
| Dashboard | GET /dashboard?mes · GET /dashboard/badges — resumen liviano para navbar y tarjetas de Inicio: {pagos_proximos_7d: {n, total}, facturas_sin_conciliar, iva: {saldo_proyectado, dias_al_vencimiento}, por_clasificar: {n, total}} (PRD M13.1) |
| Resto | Como v1.0, bajo /api/v1 y con paginación |



## 4.1 Matriz permiso × endpoint (F-18)

| Capacidad | Consulta | Financiero | Directivo | Admin |
| --- | --- | --- | --- | --- |
| Leer dashboards y vistas | ✔ | ✔ | ✔ | ✔ |
| Exportar reportes (xlsx) / vistas | ✖ | ✔ | ✔ | ✔ |
| Descargar archivos originales — presigned URL ≤ 15 min + evento archivo.descargado | ✖ | ✔ | ✖ | ✔ |
| Cargar extractos/facturas · clasificar · pagos planeados · deudas | ✖ | ✔ | ✖ | ✔ |
| Acotar presupuesto y crec_pct / '% global' | ✖ | ✔ (registra) | ✔ | ✔ |
| Gestionar facturas emitidas (crear/editar/anular) | ✖ | ✔ | ✖ | ✔ |
| Ver/descargar evidencia de autorización de tratamiento | ✖ | ✔ | ✖ | ✔ (presigned ≤15 min + evento, N-09) |
| Capacidad de pago (lectura y simulación) | ✖ | ✔ | ✔ | ✔ |
| Aprobar / cerrar / reabrir / configuración | ✖ | ✖ | ✖ | ✔ (reabrir y config con step-up) |



'Base completa' (definición, F-18): cualquier export o GET sin filtro de mes sobre transacciones, deudas o facturas. Denegado a Consulta por require_permission('export:*'); tests negativos por rol en el DoD; rate limiting en exportaciones; toda exportación al audit log.

# 5. Definition of Done — Fase 0/1 (v1.1.2, 12 puntos)

- RBAC de 4 roles + segregación probada con tests NEGATIVOS por rol, incluido export de Consulta denegado (F-18, F-28).

- Parsers de los 3 bancos con fixtures reales anonimizados, 0 duplicados en solape, coexistencia de 2 manuales (F-04) y reproceso de carga fallida (F-02).

- Ciclo presupuestal completo demostrado con datos reales; el sugerido de la demo cuadra con las 4 columnas del Excel congelado con TOLERANCIA_CUADRE (F-07).

- Migración histórica conciliada contra el Excel con TOLERANCIA_CUADRE; acta firmada por el Financiero.

- Módulo IVA reproduce el cuatrimestre May–Ago 2026 con las facturas reales.

- Audit log con los 29 eventos del catálogo §1.11 + prueba automatizada en CI de que update/remove sobre audit_log falla (F-21, nit 1).

- Dashboard replica la hoja 'Inicio' con cifras idénticas, incluido el ingreso proyectado (M10 modo Excel) (F-40).

- Suite verde en CI incluyendo pip-audit, gitleaks y Dependabot activo (F-28).

- Prueba de carga: 5.000 movimientos < 30 s y p95 de GET /dashboard < 2 s con 12 meses de VOLUMEN (5 reales mar–jul + sintético hasta completar, nit 3) (k6 o Locust, corrida nocturna) (F-47).

- Restauración selectiva mongorestore --nsInclude='compas.*' cronometrada contra INSTANCIA TEMPORAL TAMAÑO PRODUCCIÓN (alineado con STACK §5, nit 7) con verificación de totales de control; RTO medido y documentado (F-30).

- Auth endurecida verificada: logout revoca, usuario desactivado pierde acceso inmediato (token_version), MFA activo para Admin/Directivo, backoff de login (F-15/16/26).

- Cabeceras de seguridad presentes (CSP estricta, HSTS, nosniff, Referrer-Policy, frame-ancestors 'none') con test en CI (F-29).
