# SOLICITUD DE AUDITORÍA — sprint2-cargas PR1-I: endpoints de cargas + POST manual

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-20
**Docs contrato:** Spec §1.5/§1.6/§1.12 (IdempotencyKeys), §4.1 (RBAC), F-04, F-22, US-10; CLAUDE.md reglas 1,3,4,7,9,11
**Rama:** `feat/cargas-endpoints-manual` · commit `54f12d6` · **SIN mergear — este gate va ANTES del merge** (proceso correcto, según tu nota de I-PR1)

## Qué hace
1. **POST /api/v1/transacciones** (transacción manual, US-10): `id_banco='MAN-'+ULID` (F-04 — dos manuales idénticos coexisten, test); **Idempotency-Key obligatoria** (§1.12: scope (usuario,endpoint,key) con índice único + TTL 24h vía `expires_at`+`expireAfterSeconds:0` patrón E-6; mismo payload → replay de la respuesta original con su status; payload distinto → 422; petición en curso → 409). RBAC `cargas:gestionar` + `verify_origin`. Mes de la fecha debe existir (422) y no estar cerrado (409, regla 4 — tardía es Sprint 4). Rubro explícito: existir+activo+coherente con tipo_flujo (422 si no, regla 7); sin rubro → 'Por clasificar'.
2. **POST /api/v1/cargas** (upload extracto, F-22): solo `.xlsx/.xls`; `.xlsm` rechazado SIEMPRE (422); **límite 10 MB verificado antes de procesar** (413); auto-detección de banco; llama a `procesar_carga` (auditado por ti en R-PR1 9.3, sin cambios); errores mapeados (duplicada→409, no-preservable→409 M-04, negocio→422). `ORIGINALES_DIR` (Settings) como destino interim de preservación.
3. **GET /api/v1/cargas** (+`/{id}`): paginación limit/cursor (convención del proyecto), para la pantalla de cargas.
4. **`app/core/ulid.py`**: ULID puro (48b tiempo + 80b random, Crockford; sin dependencia nueva). **`IdempotencyKey`** Document (índices único+TTL declarados).

## Decisiones declaradas (auditar)
1. **Evento de creación manual:** el catálogo cerrado (30) NO tiene 'transaccion.creada'. Emito `transaccion.clasificada` (metadata `origen:'manual'`) SOLO cuando el usuario clasifica (rubro explícito). La creación sin clasificar queda sin evento propio (la key idempotente y la transacción misma dejan rastro). Si exiges evento de creación → CR al catálogo (como E-9).
2. **Idempotencia mínima, no subsistema:** implementada solo en el POST manual (el punto donde el doble-submit crea dinero duplicado — el ULID aleatorio anula la dedup por id_banco). El upload de cargas ya es idempotente por hash de archivo + dedup (banco,id_banco). Extenderla a aprobaciones/cierres llegará con esos endpoints.
3. **Key fallida no se quema:** si el negocio rechaza (422/409), la marca idempotente se borra → el cliente puede corregir y reintentar con la misma key. El replay solo aplica a respuestas exitosas persistidas.
4. **Happy path del upload** se prueba vía servicio (@requires_real_mongo, R-PR1); el endpoint testea las validaciones F-22 en mongomock (fallan antes de la transacción). ¿Suficiente, o exiges test e2e del endpoint contra Mongo real?

## Semántica preservada
`procesar_carga`/parsers/dedup: sin cambios (tu GO 9.3 intacto). Auth/RBAC/audit: sin cambios. DOMAIN_DOCUMENTS 5→6 (IdempotencyKey).

## Puntos a auditar con lupa
1. La implementación §1.12 (carrera de 2 requests concurrentes con la misma key: índice único respalda; mongomock no lo exige — el flujo find→insert está probado, la carrera real la protege el índice `scope_unico`).
2. F-22: ¿validaciones suficientes en el upload? (extensión, tamaño; el ratio de descompresión acotado del Spec §1.6 NO está implementado — openpyxl en read_only mitiga pero no acota; declarado como pendiente).
3. RBAC: `cargas:gestionar` para las 3 rutas (¿o Consulta debería poder LISTAR cargas? Hoy 403).

## Evidencia local (EVIDENCIA.md: diff completo + salidas)
- pytest: **232 passed / 23 skipped** (20 nuevos: ULID 3, manual 12, cargas endpoint 5+1). ruff limpio. Greps protocolo: 0.
- Real-mongo previo vigente (13 passed R-PR1); el código de servicio no cambió.
