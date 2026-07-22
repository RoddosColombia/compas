# Codebase Structure

**Analysis Date:** 2026-07-22

## Directory Layout

```
COMPAS/
├── backend/          # FastAPI + Beanie/Motor (Python 3.12)
│   ├── app/          # código de la aplicación
│   └── tests/        # pytest
├── frontend/         # React 19 + Vite + TS + Tailwind 4 + shadcn/ui
│   └── src/
├── docs/             # documentos contractuales (PRD, Spec, STACK, PLAN, CR)
├── migrations/       # scripts idempotentes fechados (20260901_seed_rubros.py)
├── planning/         # auditorías Kimi por fase/ronda + templates
├── scripts/          # utilidades (generate_kimi_audit_pdf.py, setup roles…)
├── render.yaml       # aprovisionamiento Render (web + worker)
└── CLAUDE.md         # reglas innegociables del proyecto
```

## Backend layout (`backend/app/`)

```
app/
├── main.py               # app factory + lifespan (conexiones Mongo, fail-fast, CORS)
├── config.py             # Pydantic Settings (env: solo secretos/conexiones)
├── security.py           # SecurityHeadersMiddleware (Spec §8.3)
├── deps.py               # get_mongo_client (para dependency_overrides en tests)
├── __init__.py           # __version__
├── api/v1/
│   ├── __init__.py       # api_router: monta todos los routers bajo /api/v1
│   └── health.py         # readiness (ping Mongo, reintenta init Beanie)
├── core/
│   ├── money.py          # tipo Money (Decimal), money_str  — REGLA 1
│   ├── time.py           # now_bogota / now_utc — REGLA 2
│   └── ulid.py           # new_ulid (id_banco 'MAN-'+ULID)
├── db/
│   └── mongo.py          # create_client (Motor perezoso), init_beanie_for, ping
├── domain/               # modelos Beanie (Pydantic strict) — capa de datos
│   ├── __init__.py       # DOMAIN_DOCUMENTS (registro explícito para init_beanie)
│   ├── rubro.py          # Rubro + SEMILLA_RUBROS (33 reales, 3 de sistema)
│   ├── mes_control.py    # MesControl, EstadoMes, SaldoBanco, CierreInfo
│   ├── presupuesto.py    # PresupuestoLinea, Ajuste, ModoCalculo
│   ├── transaccion.py    # Transaccion + derivar_id_banco (dedup, REGLA 5)
│   ├── carga.py          # CargaBancaria, EstadoCarga, ErrorCarga
│   ├── configuracion.py  # Configuracion (valor tipado por clave) + semilla DIAN/IVA
│   ├── idempotency.py    # IdempotencyKey (scope usuario+endpoint+key, TTL 24h)
│   ├── bancos.py         # enum Banco (bancolombia/bbva/global66/manual)
│   └── seed.py           # orquestación de semillas
├── auth/                 # JWT/MFA/RBAC (persistencia por Motor crudo, no Beanie)
│   ├── router.py         # /auth: login, mfa/*, refresh, logout, capabilities
│   ├── service.py        # login/refresh rotativo/authenticate; audit fire-and-forget
│   ├── deps.py           # require_permission, require_step_up, require_role, get_current_user
│   ├── permissions.py    # PERMISSIONS — CONFIG ÚNICO de RBAC (§4.1 + §2.4)
│   ├── roles.py          # enum Role (admin/directivo/financiero/consulta)
│   ├── models.py         # User, RefreshSession, índices auth (Pydantic plano)
│   ├── repository.py     # configure_auth: colecciones Motor crudo
│   ├── tokens.py         # firma/verificación JWT, jti, denylist
│   ├── mfa.py            # TOTP (cifrado con MFA_ENC_KEY)
│   └── passwords.py      # hashing de contraseñas
├── audit/                # auditoría append-only (conexión DEDICADA)
│   ├── events.py         # AuditEvento — CATÁLOGO CERRADO de 31 (REGLA 11)
│   ├── service.py        # emit_audit, configure_audit (saga O1 fail-closed)
│   └── models.py         # AuditLog (Pydantic plano) + índice forense
├── ciclo/                # apertura del mes
│   ├── router.py         # POST/GET /meses  (ciclo:abrir)
│   └── service.py        # abrir_mes (arrastre de saldo F-14), _mes_siguiente
├── presupuesto/          # motor del sugerido + acotar + aprobar
│   ├── router.py         # /meses/{mes}/sugerido, /presupuesto, /presupuesto/{rubro}, /aprobar
│   ├── service.py        # generar_sugerido, acotar_linea, aprobar_presupuesto (multi-doc)
│   └── motor.py          # calcular_sugerido_historico — FÓRMULA PURA §1.4.1 (REGLA 10)
├── cargas/               # carga de extractos bancarios
│   ├── router.py         # POST/GET /cargas  (cargas:gestionar)
│   ├── service.py        # procesar_carga (idempotente, transacción multi-doc)
│   └── mapper.py         # MovimientoBancario (DTO) → Transaccion (puro, sin Mongo)
├── transacciones/        # alta manual de movimiento
│   ├── router.py         # POST /transacciones
│   └── service.py        # crear transaccion manual (evento transaccion.creada)
├── cierre/               # cierre de mes + conciliación + reapertura
│   ├── router.py         # /meses/{mes}/cierre/conciliacion, /cierre/confirmar, /reabrir
│   └── service.py        # conciliacion, confirmar_cierre (multi-doc), reabrir_mes
├── control/              # Vista Control (read-only)
│   ├── router.py         # GET /meses/{mes}/control
│   └── service.py        # definido vs ejecutado vs disponible + semáforo (DoD #3)
├── parsers/
│   └── bank_parsers.py   # parsers Bancolombia/BBVA/Global66 (transforma, no interpreta)
└── jobs/
    └── scheduler.py      # worker compas-jobs (RUN_SCHEDULER=true; hoy vacío, REGLA 6)
```

## Frontend layout (`frontend/src/`)

```
src/
├── main.tsx              # bootstrap React
├── App.tsx               # providers (QueryClient, AuthProvider) + router + Layout/navbar
├── App.test.tsx          # test del shell
├── auth/
│   └── AuthContext.tsx   # sesión + capacidades (puede(cap)); navbar derivado de permisos
├── lib/
│   ├── api.ts            # cliente fetch /api/v1: access en memoria, refresh single-flight
│   ├── money.ts          # parseMonto/formatCOP (decimal.js-light + Intl es-CO) — REGLA 1
│   ├── meses.ts          # tipos + llamadas del ciclo mensual
│   ├── control.ts        # tipos + llamada de la Vista Control
│   ├── cargas.ts         # tipos + llamadas de cargas (validación espejo de F-22)
│   └── utils.ts          # cn() (shadcn)
├── pages/
│   ├── LoginPage.tsx     # login + MFA
│   ├── MesesPage.tsx     # ciclo del mes (abrir/generar/acotar/aprobar/cerrar)
│   ├── CargasPage.tsx    # subida de extractos + resultado de la carga
│   └── ControlPage.tsx   # tabla presupuesto vs ejecutado con semáforo
├── components/ui/
│   └── button.tsx        # shadcn/ui
└── test/
    └── setup.ts          # setup Vitest/RTL
```

## Key File Locations

**Entry Points:**
- `backend/app/main.py`: servicio web (`app`), lifespan, healthcheck.
- `backend/app/jobs/scheduler.py`: worker de jobs.
- `frontend/src/main.tsx` + `frontend/src/App.tsx`: SPA.

**Configuration:**
- `backend/app/config.py`: env vars (secretos/conexiones). Reglas de negocio parametrizables NO van aquí — van en la colección `configuracion`.
- `render.yaml`: definición de servicios web + worker.
- `frontend/vite.config.ts`, `frontend/biome.json`, `frontend/vercel.json`.

**Core Logic:**
- Motor del sugerido: `backend/app/presupuesto/motor.py`.
- Transacciones multi-doc: `presupuesto/service.py`, `cierre/service.py`, `cargas/service.py`.
- RBAC: `backend/app/auth/permissions.py`.
- Auditoría: `backend/app/audit/`.

**Testing:**
- `backend/tests/` (pytest; algunos tests requieren Mongo real — cluster de test aislado).
- `frontend/src/**/*.test.tsx` + `frontend/src/test/setup.ts` (Vitest+RTL).

## API Endpoints (bajo `/api/v1`)

| Método | Ruta | Permiso | Módulo |
|--------|------|---------|--------|
| POST | `/auth/login`, `/auth/mfa/*`, `/auth/refresh`, `/auth/logout` | público/sesión | `auth/router.py` |
| GET | `/auth/capabilities` | autenticado | `auth/router.py` |
| POST/GET | `/meses` | `ciclo:abrir` / `dashboard:leer` | `ciclo/router.py` |
| POST | `/meses/{mes}/sugerido` | `ciclo:abrir` | `presupuesto/router.py` |
| GET | `/meses/{mes}/presupuesto` | `dashboard:leer` | `presupuesto/router.py` |
| PATCH | `/meses/{mes}/presupuesto/{rubro_id}` | `presupuesto:acotar` | `presupuesto/router.py` |
| POST | `/meses/{mes}/presupuesto/aprobar` | `ciclo:aprobar` (+Idempotency-Key) | `presupuesto/router.py` |
| POST | `/meses/{mes}/cierre/conciliacion`, `/cierre/confirmar` | `ciclo:cierre_operativo` / `ciclo:confirmar_cierre` | `cierre/router.py` |
| POST | `/meses/{mes}/reabrir` | `ciclo:reabrir` (+step-up MFA) | `cierre/router.py` |
| GET | `/meses/{mes}/control` | `dashboard:leer` | `control/router.py` |
| POST/GET | `/cargas`, `/cargas/{id}` | `cargas:gestionar` | `cargas/router.py` |
| POST | `/transacciones` | negocio | `transacciones/router.py` |
| GET | `/health` (liveness), readiness | público | `main.py` / `api/v1/health.py` |

## Naming Conventions

**Files:**
- Backend: `snake_case.py`; un `router.py` + `service.py` por módulo de dominio.
- Frontend: componentes/páginas `PascalCase.tsx`; libs `camelCase.ts`.

**Directories:**
- Un directorio por dominio en `backend/app/` (auth, cargas, ciclo, presupuesto, cierre, control, transacciones).
- Modelos de datos aislados en `backend/app/domain/`.

**API:**
- Todo bajo `/api/v1`; `mes` en la ruta es `YYYY-MM` y se normaliza al día 1 (`-01`) en el router.

## Where to Add New Code

**Nuevo endpoint de negocio:**
- Router: `backend/app/<dominio>/router.py` (o dominio nuevo `backend/app/<dominio>/`), y montarlo en `backend/app/api/v1/__init__.py`.
- Lógica: `backend/app/<dominio>/service.py`.
- Proteger con `Depends(require_permission("<cap>"))`; añadir la capacidad a `backend/app/auth/permissions.py`.
- Parsear montos string→Decimal en el router; nunca aceptar montos como número.

**Nuevo modelo persistente:**
- `backend/app/domain/<modelo>.py` como Beanie `Document` con `strict=True, extra="forbid"`, índices y validadores.
- Registrarlo en `backend/app/domain/__init__.py::DOMAIN_DOCUMENTS` (si no, Beanie no lo inicializa).
- Migración idempotente fechada en `migrations/` si necesita semilla.

**Nuevo evento de auditoría:**
- Requiere CR. Añadir a `backend/app/audit/events.py::AuditEvento`; emitir con `emit_audit`.

**Nueva página/flujo frontend:**
- Página en `frontend/src/pages/<Page>.tsx`, ruta en `frontend/src/App.tsx`, tipos+llamadas en `frontend/src/lib/<dominio>.ts`.
- Gatear visibilidad con `useAuth().puede(cap)`; formatear dinero solo con `formatCOP` (`lib/money.ts`).

**Nuevo job programado:**
- `backend/app/jobs/scheduler.py` (solo worker). Idempotente (snapshot = UPSERT por fecha).

## Special Directories

**`docs/`:**
- Purpose: Contrato del proyecto (PRD, Spec técnica, STACK, PLAN, CR, RUNBOOK, calendario DIAN). Fuente de verdad.
- Generated: No. Committed: Sí (incl. `INVENTARIO-SECRETOS.xlsx` en el allowlist de gitleaks por decisión del CEO).

**`planning/`:**
- Purpose: Auditorías Kimi por fase/ronda (`planning/phases/<fase>/auditorias/<TARGET>-<RONDA>/`) + templates.
- Committed: Sí. (Nota: los mapas de codebase van en `.planning/codebase/`, con punto.)

**`migrations/`:**
- Purpose: Scripts idempotentes fechados (`YYYYMMDD_*.py`). Committed: Sí.

**`frontend/dist/`, `frontend/node_modules/`:**
- Generated: Sí. Committed: No.

---

*Structure analysis: 2026-07-22*
