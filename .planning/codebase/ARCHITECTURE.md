<!-- refreshed: 2026-07-22 -->
# Architecture

**Analysis Date:** 2026-07-22

## System Overview

COMPAS es un monolito modular: una API FastAPI (servicio `compas-api`) + un worker de jobs (`compas-jobs`) + un SPA React. Todo cálculo financiero vive en el backend; el frontend solo presenta.

```text
┌─────────────────────────────────────────────────────────────┐
│                    Frontend SPA (React 19 + Vite)            │
│   Login · Meses · Cargas · Control        `frontend/src/`    │
│   Navbar derivado de GET /auth/capabilities (regla 9)        │
└──────────────────────────┬──────────────────────────────────┘
                           │  fetch /api/v1  (access en memoria,
                           │  refresh en cookie HttpOnly)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│         ROUTERS (FastAPI, /api/v1)  `app/*/router.py`        │
│  auth · cargas · ciclo · presupuesto · cierre · control ·    │
│  transacciones     — RBAC por Depends(require_permission)    │
│  Idempotency-Key, verify_origin, parseo string→Decimal aquí  │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              SERVICES (lógica de negocio)  `app/*/service.py`│
│  motor del sugerido · acotar/aprobar · conciliar/cerrar ·    │
│  procesar_carga · abrir_mes   — transacciones multi-doc Mongo│
└───────────┬───────────────────────────────────┬─────────────┘
            ▼                                     ▼
┌───────────────────────────────┐   ┌─────────────────────────┐
│ DOMAIN (Beanie Documents)     │   │ AUDIT (Motor crudo,     │
│ `app/domain/*.py`             │   │ conexión DEDICADA)      │
│ Rubro, MesControl, Presupuesto│   │ `app/audit/service.py`  │
│ Linea, Transaccion, Carga,    │   │ emit_audit → audit_log  │
│ Configuracion, IdempotencyKey │   │ (append-only, saga O1)  │
└───────────┬───────────────────┘   └───────────┬─────────────┘
            ▼                                     ▼
┌─────────────────────────────────────────────────────────────┐
│         MongoDB (database `compas`)                          │
│  conexión general (app + auth)  ·  conexión audit_writer     │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| App factory + lifespan | Arranca FastAPI, valida reglas de arranque (fail-fast), cablea conexiones Mongo (general + auditoría) | `backend/app/main.py` |
| API router raíz | Monta todos los routers bajo `/api/v1` | `backend/app/api/v1/__init__.py` |
| Auth | Login, MFA, refresh rotativo, RBAC, capabilities | `backend/app/auth/` |
| Cargas | Parseo idempotente de extractos → Transaccion 'Por clasificar' | `backend/app/cargas/service.py` |
| Transacciones | Alta manual de movimiento (única vía de dinero sin archivo) | `backend/app/transacciones/service.py` |
| Ciclo | Apertura del mes (arrastre de saldo) | `backend/app/ciclo/service.py` |
| Presupuesto | Motor del sugerido + acotar + aprobar | `backend/app/presupuesto/` |
| Cierre | Conciliación por banco + cierre de mes + reapertura | `backend/app/cierre/service.py` |
| Control | Vista Control read-only (definido vs ejecutado vs disponible) | `backend/app/control/service.py` |
| Audit | Escritura append-only por conexión dedicada, catálogo cerrado | `backend/app/audit/` |
| Domain | Modelos Beanie con Pydantic strict, índices, validadores | `backend/app/domain/` |
| Core | Money (Decimal), tiempo Bogotá/UTC, ULID | `backend/app/core/` |
| Jobs | Worker scheduler (vacío hoy; regla 6) | `backend/app/jobs/scheduler.py` |

## Pattern Overview

**Overall:** Monolito modular en capas por dominio (router → service → domain), con dos conexiones Mongo (general + auditoría dedicada) y transacciones multi-documento en los 3 flujos financieros críticos.

**Key Characteristics:**
- **Capas estrictas:** el router hace HTTP/RBAC/idempotencia y parsea string→Decimal; el service hace la lógica y las transacciones; el domain solo modela y valida.
- **Dinero como Decimal en todo el trayecto:** nunca float. String en la frontera API.
- **Auditoría de primera clase:** ninguna operación de estado del ciclo se completa sin evento; si el evento falla, se compensa (saga O1).
- **Idempotencia por diseño:** dedup en BD (índices únicos parciales), Idempotency-Key en POST sensibles, jobs idempotentes.

## Layers

**Router (HTTP):**
- Purpose: Validación de entrada, RBAC (`require_permission`), Idempotency-Key, `verify_origin` (CSRF), parseo de montos string→Decimal, traducción de excepciones de negocio a `HTTPException`.
- Location: `backend/app/*/router.py`
- Depends on: capa service, `app/auth/deps.py`.
- Used by: `app/api/v1/__init__.py`.

**Service (negocio):**
- Purpose: Reglas de negocio, transacciones multi-doc de Mongo, emisión de auditoría con saga compensatoria, agregaciones.
- Location: `backend/app/*/service.py` (+ `presupuesto/motor.py`, función pura del sugerido).
- Depends on: domain, `app/audit/service.py`, `app/core/`.

**Domain (modelos):**
- Purpose: Beanie `Document` + Pydantic `strict=True, extra="forbid"`, índices, validadores, semillas reales.
- Location: `backend/app/domain/`
- Nota: `AuditLog`, `User`, `RefreshSession` NO son Beanie Documents — persisten por Motor crudo (auth) / conexión dedicada (audit). Registro explícito de Documents en `app/domain/__init__.py::DOMAIN_DOCUMENTS`.

## Data Flow

### Ciclo presupuestal (flujo primario)

```text
   ABRIR MES                GENERAR             ACOTAR             APROBAR            CONCILIAR/CERRAR      REABRIR
  (ciclo:abrir)          SUGERIDO           (presupuesto:      (ciclo:aprobar,       (ciclo:cierre_        (ciclo:reabrir,
                        (ciclo:abrir)        acotar)            solo Admin)          operativo /           Admin+MFA)
                                                                                     confirmar_cierre)
┌──────────┐  arrastre  ┌──────────┐        ┌──────────┐        ┌──────────────┐    ┌──────────────┐     ┌──────────────┐
│ sugerido │──saldo────▶│ sugerido │──PATCH▶│ propuesto│──POST─▶│ en_ejecucion │───▶│   cerrado    │────▶│ en_ejecucion │
└──────────┘  del mes   │ +líneas  │ monto  │(1ª acota-│ aprobar│ (monto_defini│ tx │ (re-ancla    │     │ (contra-     │
   mes.creado anterior  │ presup.  │ definido│ción M-1)│ multi- │ do fijado en │multi-saldo M+1, │     │  asiento del │
   (evento)             └──────────┘        └──────────┘ doc +  │ ~30 líneas)  │doc │  Ajuste concil│     │  ajuste M-4) │
                        (sin evento:        presupuesto.  saga O1│ presupuesto. │    │  mes.cerrado  │     │ mes.reabierto│
                         borrador)          acotado             │  definido    │    │  saga O1)     │     │  saga O1     │
                                                                └──────────────┘    └──────────────┘     └──────────────┘
```

1. **Abrir mes** (`ciclo/service.py::abrir_mes`) — crea `MesControl` en estado `sugerido`; deriva `saldo_inicial_caja` del consolidado del mes anterior (F-14). Evento `mes.creado`; O1 compensa con delete si el evento falla.
2. **Generar sugerido** (`presupuesto/service.py::generar_sugerido`) — crea las `PresupuestoLinea` vigentes desde el ejecutado de meses cerrados vía UNA agregación `$group`. Borrador recomputable, NO emite evento.
3. **Acotar línea** (`presupuesto/service.py::acotar_linea`) — fija `monto_definido` + `Ajuste` append-only; transiciona `sugerido→propuesto`. Saga O1 sin transacción Mongo (compensa manualmente).
4. **Aprobar** (`presupuesto/service.py::aprobar_presupuesto`, solo Admin) — TRANSACCIÓN MULTI-DOC: fija `monto_definido` en líneas vigentes + `MesControl → en_ejecucion`. Evento `presupuesto.definido` post-commit; si falla, transacción compensatoria revierte.
5. **Conciliar / Cerrar** (`cierre/service.py`) — `conciliacion` es compute-only por banco; `confirmar_cierre` (Admin) es TRANSACCIÓN MULTI-DOC: re-ancla `saldo_inicial(M+1):=R_M`, crea 'Ajuste de conciliación' en M+1, congela M → `cerrado`. Evento `mes.cerrado` + saga O1.
6. **Reabrir** (`cierre/service.py::reabrir_mes`, Admin+MFA) — contra-asiento del ajuste (la Transaccion es inmutable, nunca se borra), restaura ancla previa, M → `en_ejecucion`. Evento `mes.reabierto` + saga O1. LIFO: M+1 debe seguir editable.

### Flujo de carga bancaria

1. `POST /api/v1/cargas` (`cargas/router.py`, `cargas:gestionar`).
2. `procesar_carga` (`cargas/service.py`): hash SHA-256 del archivo → rechazo solo si hay carga previa `completada`; parsea (`parsers/bank_parsers.py`), mapea a `Transaccion` (`cargas/mapper.py`), pre-filtra duplicados dentro de la sesión y `insert_many` de los nuevos + update de la carga en TRANSACCIÓN MULTI-DOC. Evento `carga.completada` / `carga.fallida`.

**State Management:**
- Estado del mes en `MesControl.estado` (`EstadoMes`): `sugerido → propuesto → definido → en_ejecucion → cerrado`. Nota: la aprobación deja el mes directamente en `en_ejecucion` (US-02); `definido` es un valor del enum que no se usa en reposo — la aprobación se registra con `definido_por/at` + evento `presupuesto.definido`.
- Frontend: TanStack Query, keys `['mes','YYYY-MM',vista]`, invalidación tras toda mutación financiera.

## Key Abstractions

**Money (Decimal, nunca float):**
- Purpose: Todo monto COP. Coerciona `Decimal128`→`Decimal` al leer de BSON; rechaza float/bool.
- Examples: `backend/app/core/money.py` (`Money` tipo Annotated, `money_str`).
- Pattern: string en la API (`money_str`), Decimal en backend, `decimal.js-light` + `Intl.NumberFormat('es-CO')` en front (`frontend/src/lib/money.ts`).

**Saga O1 de auditoría:**
- Purpose: Ninguna operación de estado del ciclo se completa sin evento. Como la auditoría vive en conexión dedicada, no entra en la transacción; se emite tras el commit y, si falla, una transacción/compensación revierte el efecto.
- Examples: `ciclo/service.py::abrir_mes`, `presupuesto/service.py::aprobar_presupuesto`, `cierre/service.py::confirmar_cierre`/`reabrir_mes`.

**Catálogo cerrado de eventos:**
- Purpose: 31 eventos canónicos; `AuditEvento(valor)` lanza `ValueError` si no existe (regla 11).
- Examples: `backend/app/audit/events.py` (`AuditEvento`, `CATALOGO_EVENTOS`).

**RBAC por dependencia:**
- Purpose: Autorización declarativa por endpoint desde un único config de permisos.
- Examples: `backend/app/auth/permissions.py` (`PERMISSIONS`), `backend/app/auth/deps.py` (`require_permission`, `require_step_up`, `require_role`).

## Entry Points

**Servicio web (`compas-api`):**
- Location: `backend/app/main.py::app` (`create_app` + `lifespan`).
- Triggers: HTTP; healthcheck `GET /health` (sin tocar BD).
- Responsibilities: Fail-fast de secretos fuera de dev, prohíbe `RUN_SCHEDULER=true`, crea cliente Motor perezoso + conexión de auditoría dedicada, init Beanie idempotente y no fatal.

**Worker de jobs (`compas-jobs`):**
- Location: `backend/app/jobs/scheduler.py` (`python -m app.jobs.scheduler`).
- Triggers: Solo con `RUN_SCHEDULER=true` (1 instancia). Hoy arranca vacío (jobs en sprints posteriores).

## Architectural Constraints

- **Threading:** Async single-loop (FastAPI/Motor). El parseo de Excel (bloqueante) se delega a hilo con `anyio.to_thread.run_sync` (`cargas/service.py`).
- **Global state:** `app/audit/service.py::_audit_collection` y `app/auth/repository.py` guardan singletons de colección/cliente configurados en el lifespan (`configure_audit`, `configure_auth`) y reseteados al cerrar. `app/config.py::get_settings` cacheado con `lru_cache`.
- **Dos conexiones Mongo:** general (`mongodb_uri_compas`, app + auth) y auditoría dedicada (`mongodb_uri_audit`, usuario `compas_audit`/`audit_writer`) a la MISMA database `compas`. Fuera de dev, `MONGODB_URI_AUDIT` es obligatoria (fail-fast).
- **Scheduler:** `RUN_SCHEDULER=false` SIEMPRE en el web (el lifespan revienta si es true). Los jobs viven solo en el worker.
- **Circular imports:** `control/service.py` y `cierre/service.py` reutilizan helpers de `ciclo`/`cierre` (`_mes_siguiente`, `_caja_libro`, `_rubro_ajuste`) — dependencia intencional entre módulos de dominio cercano.

## Anti-Patterns

### Usar float / Number sobre montos

**What happens:** Construir montos con `float` en Python o `Number(x)` en TS.
**Why it's wrong:** Redondeo binario en dinero (regla 1). `Money` rechaza float/bool en tiempo de validación.
**Do this instead:** Backend `Decimal` (parsear string con `Decimal(s)` en el router); front `decimal.js-light` y `formatCOP` (`frontend/src/lib/money.ts`).

### Mapear rol → ítems de UI en el frontend

**What happens:** Condicionar el navbar/acciones por `rol === 'admin'`.
**Why it's wrong:** Duplica la matriz de permisos y se desincroniza del backend (regla 9).
**Do this instead:** `useAuth().puede(cap)` con las capacidades de `GET /auth/capabilities` (`frontend/src/auth/AuthContext.tsx`).

### Completar una operación de ciclo sin auditoría

**What happens:** Escribir estado y seguir aunque `emit_audit` falle.
**Why it's wrong:** Deja un mes operable sin rastro forense (regla 4/11).
**Do this instead:** Saga O1 — emitir tras el commit y compensar si falla (ver `cierre/service.py`, `presupuesto/service.py`).

### Inventar un evento de auditoría nuevo

**What happens:** Pasar un string de evento fuera del catálogo a `emit_audit`.
**Why it's wrong:** El catálogo es cerrado (31); `AuditEvento(evento)` lanza `ValueError`.
**Do this instead:** Añadir el evento con un CR y a `app/audit/events.py`.

### Borrar/editar un asiento histórico

**What happens:** Corregir un mes cerrado mutando o eliminando `Transaccion`.
**Why it's wrong:** El histórico es inmutable (regla 4, §2.2.2); la reapertura usa CONTRA-ASIENTO, no delete.
**Do this instead:** `MesControl.assert_editable()`; en reapertura, `Transaccion.revierte_id` (`cierre/service.py::reabrir_mes`).

## Error Handling

**Strategy:** Cada service define su excepción de negocio (`SugeridoError`, `AcotarError`, `AprobarError`, `CierreError`, `CargaError`, …) con `detalle` + `status`. El router la traduce a `HTTPException(status, detalle)`. Errores de credenciales devuelven un mensaje ÚNICO anti-enumeración.

**Patterns:**
- Excepción de negocio con `status` HTTP explícito en el service.
- `DuplicateKeyError` de Mongo capturado para colisiones reales (apertura de mes, idempotency).
- Saga O1: `try/except` alrededor del `emit_audit` con compensación.
- `with_transaction` reintenta solo `TransientTransactionError`.

## Cross-Cutting Concerns

**Logging:** `logging.getLogger("compas...")`; Sentry opcional con `_scrub_pii` (nunca envía descripcion/proveedor/valor/cookie).
**Validación:** Pydantic `strict=True, extra="forbid"` en todos los modelos; validadores de fecha `YYYY-MM-DD` y datetime UTC-aware.
**Autenticación:** JWT access en memoria + refresh rotativo en cookie HttpOnly; denylist + throttle en Mongo; MFA TOTP con step-up para acciones sensibles (`require_step_up`).
**CORS/Seguridad:** origen exacto del frontend + `allow_credentials`; `SecurityHeadersMiddleware` como capa más externa; `verify_origin` (anti-CSRF) en POST/PATCH sensibles.

---

*Architecture analysis: 2026-07-22*
