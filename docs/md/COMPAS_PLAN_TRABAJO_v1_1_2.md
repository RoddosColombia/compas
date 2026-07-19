COMPAS

Plan de Trabajo de Desarrollo

Fase 0–1 — 10 semanas, 11 sprints, go-live

COMPAS-PLAN-004 v1.1.2 — Errata de cierre para VERDE (18-jul-2026)

RODDOS S.A.S. — Oficina del CTO

18 de julio de 2026

# Metadatos del documento

| Atributo | Valor |
| --- | --- |
| Código / Versión | COMPAS-PLAN-004 · v1.1.2 (18-jul-2026); v1.1.1 y v1.1 18-jul; v1.0 17-jul |
| Estado | Borrador para aprobación del CEO |
| Auditoría externa | Auditoría 18-jul (ROJO, 51 hallazgos) → v1.1 → re-auditoría 18-jul: AMARILLO, 48/51 resueltos, ROJO levantado. v1.1.1 aplicó la decisión de alcance N-01 (CEO), N-02 y el parche completo; v1.1.2 cerró la errata E-1..E-6 → VERDE 9.3/10, certificado GO (18-jul) |
| Duración | 10 semanas (11 sprints: 0, 0b, 1–5, 6a, 6b, 7, 8) — +1 semana DECLARADA por el alcance nuevo de producto del CEO (N-01, decisión híbrida); el modo 'ligada a ventas' y la pestaña Horizonte se difieren a Fase 1.5 |
| Costo infraestructura | ~$40–70 USD/mes construcción · ~$40–55 operación (STACK v1.1.2 §5) |
| Pre-requisito bloqueante | Aprobación firmada de los 5 documentos v1.1.2 (N-13); verificación de cierre del auditor COMPLETADA — certificado GO VERDE 9.3/10 (18-jul) |
| Criterio de cierre | 12 puntos del DoD del Spec v1.1.2 ✓ + aprobación CEO en Sprint 7 |



# Histórico de versiones — v1.0 → v1.1

| Cambio | Hallazgo | Impacto cronograma |
| --- | --- | --- |
| Mini-migración adelantada: las bases reales mar–jul (egresos/ingresos) se cargan y clasifican al cierre del Sprint 2 como condición del gate G2; el Sprint 7 queda para deudas, facturas, presupuestos históricos y la conciliación formal | F-41 | Ninguno — redistribución |
| Dashboard 'Inicio' se construye en Sprints 5–6 (tras caja/conciliación); Sprint 7 descargado a conciliación + reporte + UAT + gate | F-42 | Ninguno |
| M10 Ingresos (modo Excel) entra explícitamente al Sprint 6 — era requisito del DoD sin sprint | F-40 | Absorbido en Sprint 6 |
| G1 pasa a BLOQUEANTE con checklist de seguridad y aprobador distinto del ejecutor; CI con escaneo desde Sprint 0 | F-28 | Ninguno |
| Workstream legal Ley 1581 arranca en Sprint 0 (paralelo, no bloquea código) | F-20 | Ninguno |
| UAT definido: guion US-01..10, criterio de aprobación y ventana CEO de 48 h pactada como prerrequisito del Sprint 7 | F-42, F-48 | Ninguno |
| Double-run redefinido en términos del dominio y declarado como operación post-plan con responsable | F-46 | Post-plan explícito |
| Composición del equipo declarada + 3 riesgos nuevos (persona clave, contención SISMO, SLA del CEO) | F-48 | Ninguno |
| Fechas de fixtures unificadas: entrega Día 0, layouts congelados como primer entregable del Sprint 1 | F-51 | Ninguno |



Lo que NO cambió en v1.1: stack y proveedores, la regla 'ningún sprint cierra con P0/P1 abiertos', demos con datos reales, y el gate absoluto del CEO en Sprint 7.

## Enmienda v1.1 → v1.1.1 (re-auditoría AMARILLO, 18-jul-2026)

| Cambio | Hallazgo |
| --- | --- |
| DECISIÓN DE ALCANCE DEL CEO (híbrida): go-live pasa a 10 semanas conservando FacturaEmitida, Capacidad de pago, navbar M13 + badges y cadencia 8:30; el modo 'ligada a ventas' (+ costos unitarios) y la pestaña Horizonte se difieren a Fase 1.5; el pre-llenado del '% global' opera desde el Sprint 6b (E-1). El impacto se declara: +1 semana | N-01 |
| Sprint 6 dividido en 6a (facturas + IVA) y 6b (M10 + Capacidad de pago + dashboard + buffer); G4 al cierre de 6b; Sprint 7 → semana 9; go-live → semana 10 | N-02 |
| Demo del Sprint 3 declarada: MODO HISTÓRICO, mes agosto-2026 con may–jul cerrados; '% global' manual en el go-live | N-03, nit 11 |
| Sprint 0 pasa a 3 días (alcance creció ~40%); MFA se mueve a Sprint 0b | nit 4 |
| Verificación RNBD = memo interno firmado y archivado (fecha, umbral, cifra de activos, conclusión, responsable) | N-10 |
| Wireframes con dueño (elabora Tech Lead, aprueba CEO) como entregable del Sprint 2 | nit 12 |
| Nueva sección Fase 1.5 con contenido, método y duración del alcance diferido | N-01, N-12 |



v1.1.2 (18-jul-2026): errata de cierre E-1..E-6 + barrido de textos, según el informe de calificación final (8.9/10). Ningún cambio de decisión, mecanismo, costo ni criterio de aceptación; E-1 unifica la datación del pre-llenado del '% global' en Sprint 6b.

# 1. Equipo y dedicación (F-48)

| Rol | Persona/s | Dedicación |
| --- | --- | --- |
| Tech Lead (construcción) | 1 desarrollador senior (el mismo perfil que construyó SISMO) | 100% durante las 10 semanas, con ventana protegida: soporte SISMO limitado a incidentes P0/P1 |
| Par de revisión | 1 desarrollador/revisor designado | Revisión de PRs críticos + required reviewer del environment production; receptor de la documentación de módulos portados (mitiga bus-factor 1) |
| Financiero (negocio) | Equipo financiero RODDOS | Fixtures Día 0, clasificación en Sprint 2, taller de limpieza (Sprint 6a), UAT, acta de conciliación |
| CEO | Andrés Sanjuan | Gates G3/G5 con SLA pactado: ventana de respuesta de 48 h — prerrequisito del Sprint 7 |



# 2. Pre-requisitos bloqueantes (Día 0)

- Los 5 documentos v1.1.2 (PRD, SPEC, STACK, PLAN, INFO-000) aprobados y firmados por el CEO — re-baseline completo con certificado GO 9.3/10 del 18-jul (F-51, N-13).

- 1 extracto real de cada banco entregado, anonimizado por el script del Spec §1.6.1 antes de entrar al repo (F-25). Los layouts se congelan como primer entregable del Sprint 1.

- Flujo de pagos deudas.xlsx congelado a fecha de corte.

- Usuarios con rol asignado; ventana de 48 h del CEO para gates pactada por escrito.

- Acceso a cuentas existentes verificado + IAM user S3 dedicado (STACK §8.2) + NOMBRAMIENTOS en el RUNBOOK-INFRA: par revisor, custodio del break-glass y las 2 personas con acceso a secretos de producción; región primaria nombrada (N-06, N-07).

- Calendario DIAN del NIT y condiciones de crédito por proveedor confirmadas.

- Memo interno FIRMADO Y ARCHIVADO de la verificación RNBD: fecha, umbral (100.000 SMMLV), cifra de activos confirmada por el contador, conclusión y responsable — responsabilidad demostrada (Ley 1581 art. 4) sin que COMPAS almacene el balance (N-10).

# 3. Fases y sprints (v1.1.2)

| Fase | Sprint | Semana | Propósito |
| --- | --- | --- | --- |
| F1 — Setup | Sprint 0 | 1 (d1–3) | 3 días (nit 4): recursos en cuentas existentes vía render.yaml + RUNBOOK-INFRA con nombramientos y región (F-37, N-06/07): repo, database, api + WORKER de jobs con heartbeats, bucket compas-archivo con Object Lock, CI/CD con pip-audit/gitleaks/Dependabot, secrets, environments protegidos, esqueleto con auth endurecida (token_version, logout). ARRANCA workstream legal Ley 1581 (F-20). |
| F1 — Setup | Sprint 0b | 1 (d4–5) | Catálogo de rubros semilla, MesControl, Configuracion, audit log (catálogo completo de 29 eventos, Spec §1.11) con test de inmutabilidad en CI + MFA TOTP (movida de S0, nit 4). GATE G1 BLOQUEANTE: checklist de seguridad aprobado por el par revisor (F-28). |
| F2 — Datos | Sprint 1 | 2 | Congelar layouts (fixtures Día 0) + parser Bancolombia + esquema canónico + dedup (índice parcial, manuales MAN-) + pantalla de cargas con ciclo de vida completo (fallida/reaper/reproceso, F-02) + POST manual. |
| F2 — Datos | Sprint 2 | 3 | Parsers BBVA y Global66 (con moneda original, F-03) + reglas de clasificación + 'Por clasificar' + MINI-MIGRACIÓN: bases reales mar–jul cargadas y clasificadas (F-41) + wireframes del navbar y la vista Presupuesto (elabora Tech Lead, aprueba CEO — nit 12). GATE G2 incluye la mini-migración cuadrada. |
| F3 — Presupuesto | Sprint 3 | 4 | Motor del sugerido (fórmula §1.4.1 del Spec) + fila informativa de compromisos + ciclo de estados + versionado + aprobación según tabla de autoridad. Demo nota CEO #1 EN MODO HISTÓRICO con agosto-2026 (may–jul cerrados y migrados): 4 columnas vs Excel; el '% global' se aplica manual (N-03, nit 11). |
| F3 — Presupuesto | Sprint 4 | 5 | Vista Control + caja + conciliación por banco + semáforos + transacciones multi-documento en aprobación/carga/cierre + política de tardías. GATE G3 (Directivo) con julio real. |
| F4 — Compromisos | Sprint 5 | 6 | Pagos de la semana + deudas (matriz) + conciliación con matching determinista (F-05) + SnapshotCaja/job diario en el worker + PRIMERA VERSIÓN del dashboard 'Inicio' (F-42). |
| F4 — Compromisos | Sprint 6a | 7 | Facturas recibidas Y EMITIDAS (IVA descontable + generado desde documentos reales, con tarifa/exentas y eventos de auditoría — N-08/N-09) + IVA cuatrimestral completo + taller de limpieza del histórico con el Financiero (riesgo 2). |
| F4 — Compromisos | Sprint 6b | 8 | M10 INGRESOS MODO EXCEL (parámetros por modelo → proyectado → % cumplimiento; desde aquí el '%' global puede pre-llenarse) + vista Capacidad de pago de deudas + dashboard 'Inicio' completo + job de archivado mensual (N-05) + buffer 2 días (N-02). GATE G4. |
| F5 — Datos reales | Sprint 7 | 9 | Migración restante (deudas, facturas Auteco, presupuestos históricos) + conciliación formal TOLERANCIA_CUADRE con acta + reporte de cierre + prueba de restauración cronometrada (DoD-10) + UAT CON GUION (casos US-01..10, criterio: 100% críticos ✓) + capacitación. GATE G5 BLOQUEANTE ABSOLUTO: aprobación CEO (ventana 48 h pactada). |
| F6 — Go-live | Sprint 8 | 10 | Deploy a producción vía tag + reviewer + monitoreo (SLOs activos) + inicio del double-run (ver §7). |



# 4. Gates de aprobación (v1.1.2)

| Gate | Momento | Aprobador | Bloqueante |
| --- | --- | --- | --- |
| G1 | Fin Sprint 0b — esqueleto + checklist de SEGURIDAD (auth endurecida, audit inmutable, CI con escaneo) | Par revisor (distinto del ejecutor, F-28) | SÍ |
| G2 | Fin Sprint 2 — 3 parsers + dedup + mini-migración mar–jul cuadrada | Financiero + Tech Lead | Sí |
| G3 | Fin Sprint 4 — ciclo presupuestal + control con julio real (demo nota CEO #1 ya aprobada en S3) | Directivo | Sí |
| G4 | Fin Sprint 6b — facturas (ambos lados) + IVA (cuatrimestre May–Ago reproducido) + M10 + Capacidad de pago + dashboard | Financiero | Sí |
| G5 | Fin Sprint 7 — UAT con guion + acta de conciliación + restore cronometrado | CEO (ventana 48 h) | BLOQUEANTE ABSOLUTO |



# 5. Riesgos y mitigaciones (v1.1.2 — 10)

| # | Riesgo | Prob. | Mitigación |
| --- | --- | --- | --- |
| 1 | Variantes de formato de extracto por banco | Alta | Fixtures Día 0, layouts congelados Sprint 1, parser versionado, ambigüedad = error reportado. |
| 2 | Calidad del histórico del Excel | Alta | Mini-migración temprana (S2) reparte el riesgo; taller de limpieza AGENDADO en Sprint 6a; lo inconsistente a 'Por clasificar'. |
| 3 | Doble operación Excel + COMPAS agota al equipo | Media | Double-run post-plan con responsable y criterio de apagado medible (§7). |
| 4 | El ciclo de aprobación no se adopta | Media | El sistema exige aprobación para ejecutar; capacitación en Sprint 7; recordatorios. |
| 5 | Scope creep hacia el motor del simulador | Media | Fase 2 fuera de las 10 semanas; cambio = nueva versión del plan. |
| 6 | Supuestos tributarios de IVA errados | Baja | Validación con el contador en Sprint 6a; COMPAS proyecta, el contador declara. |
| 7 | Cluster compartido degrada a SISMO | Baja | Disparadores numéricos + Atlas Alerts (STACK §7); revisión formal a +30 días. |
| 8 | PERSONA CLAVE (bus-factor 1) (F-48) | Media | Par revisor activo desde Sprint 0; documentación de módulos portados como entregable; RUNBOOK-INFRA reproducible. |
| 9 | Contención con la operación de SISMO V3 (F-48) | Media | Ventana protegida del Tech Lead (solo P0/P1 de SISMO); minutos de CI presupuestados aparte (F-38). |
| 10 | Disponibilidad del CEO para G5 (F-48) | Media | Ventana de 48 h pactada por escrito en Día 0; delegado designado para aclaraciones (no para aprobar). |



# 6. Fase 1.5 — alcance diferido por decisión N-01 (típicamente semanas 5–6 post go-live)

Duración estimada: 1–2 semanas; arranca tras el apagado del Excel (típicamente semanas 5–6 post go-live). Contenido: (1) modo 'ligada a ventas' del sugerido — campo modo_calculo por línea y tabla de costos unitarios por modelo versionada por mes (el pre-llenado del '% global' NO es Fase 1.5: opera desde el Sprint 6b — E-1); se demuestra contra un mes real cerrado antes de activarse; (2) pestaña 'Horizonte' en Presupuesto — proyección 18–24 meses con método definido (N-12): sugerido iterado mes a mes usando el crec_pct default por rubro, sobreescribible por línea, cubriendo la vista 'Segundo semestre' del Excel. Ambas entregas usan las especificaciones ya escritas en Spec §1.4.1/§1.7 (marcadas Fase 1.5) y cierran con demo al CEO. Nada requiere migración ni cambio de modelo de datos: son activaciones sobre lo construido.

# 7. Double-run y apagado del Excel (F-46)

El double-run (COMPAS + Excel en paralelo) es operación post-plan, arranca en el Sprint 8 y continúa después del cierre del proyecto con responsable nombrado: el Financiero, con soporte del Tech Lead. Criterio de apagado medible en términos del dominio: 4 conciliaciones semanales de caja cuadradas (|dif vs banco| < UMBRAL_DIF_BANCO_CIERRE) + 1 cierre de mes completo ejecutado en COMPAS con acta → el Excel pasa a solo-lectura. La capacitación ocurre una sola vez, en el Sprint 7 (antes del UAT), no en el 8.

# 8. Workstream legal Ley 1581 (F-20) — paralelo desde Sprint 0

- Política de tratamiento de datos + aviso de privacidad (art. 15; Decreto 1377/2013).

- Formato de autorización incorporado al alta de acreedores/proveedores persona natural (campo autorizacion_tratamiento con evidencia — ya en Spec §1.7).

- Procedimiento ARCO con responsable y plazos legales (10/15 días hábiles, arts. 14–15). Matiz operativo del archivado (E-5): las solicitudes de supresión se ejecutan DE INMEDIATO en la base viva; en el archivo con Object Lock se difieren al vencimiento de la retención legal aplicable (10/5 años por clase), y así se informa al titular en la política de tratamiento.

- Verificación del umbral RNBD (activos > 100.000 SMMLV, Decreto 886/2014 mod. 090/2018) mediante confirmación del contador — probablemente NO aplica; COMPAS no maneja ni almacena información de balance.

- Anexar COMPAS a los contratos/marcos de transmisión internacional existentes de SISMO con Atlas, Render, Vercel, Sentry y Better Stack (art. 26; Circular SIC 005/2017).

Evidencia de avance del workstream es parte del gate G4; los artefactos finales son prerrequisito del go-live (G5).

# 9. Métricas de éxito

| Dimensión | Métrica | Meta |
| --- | --- | --- |
| Cronograma | Desviación del go-live | ≤ 1 semana |
| Calidad | Bugs P0/P1 en producción primer mes | 0 P0 · ≤ 2 P1 |
| Adopción | Criterio de apagado del Excel (§7) | 4 conciliaciones semanales + 1 cierre mensual |
| Datos | Conciliación migración y cierres vs Excel | TOLERANCIA_CUADRE ($1 COP) |
| Operación | SLOs del primer mes (disponibilidad / p95 dashboard) | 99,5% / < 2 s — habilitan Fase 2 |



# 10. Compromisos del Tech Lead (v1.1.2)

- Demo en vivo al cierre de cada sprint con datos reales de RODDOS.

- Ningún merge sin CI verde (incluye pip-audit y gitleaks); ninguna cifra financiera con float, ni en el frontend.

- Los parsers jamás adivinan; toda ambigüedad se reporta al humano.

- El histórico es sagrado; ninguna migración altera meses cerrados.

- Ningún deploy a producción sin reviewer humano; ninguna migración destructiva sin dump verificado.

- Documentar los módulos portados de SISMO para el par revisor (mitigación de persona clave).

- Cualquier cambio de alcance = nueva versión de este plan con impacto explícito.
