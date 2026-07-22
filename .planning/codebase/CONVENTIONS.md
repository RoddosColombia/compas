# Coding Conventions

**Analysis Date:** 2026-07-22

These conventions are enforced by the 12 non-negotiable rules in `CLAUDE.md`. Violating them = PR rejected. Read that file plus `docs/COMPAS_NORTE.md` before writing code.

## Naming Patterns

**Files:**
- Backend: `snake_case.py`, one bounded context per package: `app/<contexto>/{router,service}.py` (e.g. `app/cierre/service.py`, `app/cargas/mapper.py`). Cross-cutting primitives live in `app/core/` (`money.py`, `time.py`, `ulid.py`) and `app/domain/` (one file per aggregate: `transaccion.py`, `mes_control.py`, `presupuesto.py`).
- Backend tests: `backend/tests/test_<area>.py`; tests needing a real Mongo add a `_realmongo` suffix (`test_cierre_realmongo.py`, `test_presupuesto_aprobar_realmongo.py`).
- Frontend: `PascalCase.tsx` for components/pages (`ControlPage.tsx`, `AuthContext.tsx`), `camelCase.ts` for libs (`lib/money.ts`, `lib/cargas.ts`), co-located tests as `*.test.tsx` (`App.test.tsx`).
- Migrations: dated, idempotent, `migrations/YYYYMMDD_<verbo>_<obj>.py` (e.g. `20260901_seed_rubros.py`).

**Functions & variables:**
- Backend: `snake_case`. Domain vocabulary is **Spanish** (`derivar_id_banco`, `confirmar_cierre`, `conciliacion`, `now_bogota`, `month_start`); technical/infra vocabulary is English (`get_settings`, `create_app`, `create_client`). Private/internal helpers prefixed with `_` (`_coerce_decimal`, `_signo`, `_umbral`, `_rubro_ajuste`).
- Frontend: `camelCase` functions (`parseMonto`, `formatCOP`, `formatFecha`, `validarArchivo`), `PascalCase` components. Spanish domain names carry across the stack (`meses`, `cargas`, `control`).

**Types / models:**
- Pydantic/Beanie documents: `PascalCase` (`Transaccion`, `MesControl`, `SaldoBanco`, `CierreInfo`). Enums are `StrEnum` in `PascalCase` with `snake_case` members and dotted string values: `AuditEvento.mes_cerrado = "mes.cerrado"`, `EstadoMes`, `TipoFlujo`, `Banco`, `Role`.
- Collection name constants are module-level UPPER_SNAKE (`TRANSACCIONES_COLLECTION = "transacciones"`) and wired via the Beanie `Settings.name`.

## Code Style

**Backend formatting/linting (`backend/pyproject.toml`):**
- Ruff, `target-version = "py312"`, `line-length = 88`, `src = ["app", "tests"]`.
- Lint select: `["E", "F", "I", "UP", "B", "ASYNC"]`; ignore `B008` (FastAPI `Depends(...)` in defaults is idiomatic). Per-file: `tests/*` ignores `B011`.
- CI runs both `ruff check .` and `ruff format --check .` — format is enforced, not optional.
- Python 3.12 syntax: use `X | None` unions, built-in generics, `datetime.UTC`, `zoneinfo.ZoneInfo`, `StrEnum`.

**Frontend formatting/linting (`frontend/biome.json`):**
- Biome 1.9.4. Formatter: 2-space indent, double quotes (`quoteStyle: "double"`). Linter: `recommended` rules. Ignores `dist`, `node_modules`.
- `npm run lint` → `biome check .`; `npm run build` → `tsc -b && vite build` (type-check is part of build). Both are CI-blocking.
- Path alias `@/` maps to `frontend/src` (used in imports: `import App from "@/App"`).

## The money rule (rule 1 — most important convention)

**Backend — `app/core/money.py`:**
- Money is `Decimal`, **never** `float`. Use the `Money` type: `Annotated[Decimal, BeforeValidator(_coerce_decimal)]`. It coerces BSON `Decimal128`→`Decimal` on read and **rejects `float` and `bool`** (bool is an int subclass, explicitly excluded).
- Serialize amounts to the API as **string** with `money_str(valor)` — `quantize(Decimal("0.01"), ROUND_HALF_EVEN)`. Amounts travel as JSON strings, never numbers.
- All financial computation lives in the backend. Construct domain models with explicit `Decimal`; the API layer parses the incoming string to `Decimal` **before** building the model.

**Frontend — `frontend/src/lib/money.ts`:**
- Amounts arrive from the API as decimal **strings**. Use `decimal.js-light` (`Decimal.config({ precision: 30, rounding: ROUND_HALF_UP })`); **never** `Number(...)` on an amount.
- `parseMonto(value: string): Decimal` for arithmetic; `formatCOP(value)` for presentation via `Intl.NumberFormat('es-CO', {style:'currency', currency:'COP'})` → `"$ 1.234.567,89"`. `.toNumber()` is used **only** inside the formatter for presentation, never for calculation.

## Time & dates (rule 2 — `app/core/time.py`)

- Single timezone América/Bogotá. `now_bogota()` (offset −05:00) is **presentation only**.
- **Persistence, TTLs, JWT claims use `now_utc()` (UTC-aware).** A naive Bogotá datetime would be read as UTC and drift −5h. Naive datetimes are prohibited; models validate `tzinfo is not None` (see `Transaccion._aware`).
- Business dates are strings `YYYY-MM-DD` (BSON has no date-without-time). Months are normalized to day 1 via `month_start(d)` — that is the `MesControl` key. `today_bogota()` for the current business date.
- Frontend dates: `formatFecha("2026-07-18")` → `"18-jul-2026"` (Spanish month abbreviations).

## Pydantic / model conventions (rule 3)

- Every domain document declares `model_config = ConfigDict(strict=True, extra="forbid")`. No dict without a schema; unknown fields are rejected.
- Field-level validators enforce invariants: string date regex `^\d{4}-\d{2}-\d{2}$` + `strptime` round-trip, `valor > 0` (sign comes from `tipo_flujo`, never a negative amount), enum casting `mode="before"`, UTC-aware datetimes.
- Settings (`app/config.py`) use `pydantic_settings.BaseSettings` with `extra="ignore"` (Render/OS inject foreign env vars) and `Literal[...]` for enumerable config (`app_env`) so typos fail at validation, not runtime. `get_settings()` is `@lru_cache`d; tests must call `get_settings.cache_clear()` (autouse fixture does this).
- Env vars are **only** for secrets and connections; parametrizable business rules (thresholds, DIAN calendar) live in the `configuracion` collection, not in config.

## Deduplication & IDs (rule 5)

- Dedup happens **in the database**: partial unique index `(banco, id_banco)` with `partialFilterExpression {"id_banco": {"$type": "string"}}` (see `Transaccion.Settings.indexes`, `name="banco_idbanco_unico"`). Never dedup in application code.
- `id_banco` is deterministic (`derivar_id_banco`): Global66 uses its native reference; Bancolombia/BBVA use an MD5 fingerprint `banco|fecha|tipo|descripcion|valor:.2f` plus an in-file occurrence ordinal (`…|1`, `…|2`) so identical same-day movements don't collapse. MD5 is `usedforsecurity=False` (fingerprint only).
- Manual transactions: `id_banco = 'MAN-' + new_ulid()` (`app/core/ulid.py`, 26-char Crockford base32, time-ordered, no external dep). Unique by construction.

## Audit log (rules 4 & 11)

- `audit_log` is **append-only** — enforced at the DB layer via the `audit_writer` role (user `compas_audit`, `insert`+`find`, no `update`/`remove`). A CI test verifies `update`/`remove` raise `OperationFailure` code 13.
- Closed catalog of **31 events** in `app/audit/events.py` (`AuditEvento(StrEnum)`, exported as `CATALOGO_EVENTOS` frozenset). Member name uses `_`, value uses `<dominio>.<acción>`. **Do not invent events without a CR.**
- History is immutable: closed months are not edited (except `tardia=true` late transactions); historical asientos are never deleted — reversals use a contra-asiento (`revierte_id`), never an update/delete.

## Multi-document transactions (rule 8)

- The three flows use MongoDB multi-document transactions with a saga/compensation pattern: budget approval, load finalization, month close. See `app/cierre/service.py` (`confirmar_cierre`, saga "O1": data writes inside a session, `emit_audit` post-commit, compensate on failure). Requires a replica set — never a standalone.

## Idempotency & RBAC (rule 9)

- Sensitive POSTs require an `Idempotency-Key` header; scope is user + endpoint + key, persisted via `IdempotencyKey` (`app/domain/idempotency.py`). Replay returns the same response; duplicate key on an already-processed mutation surfaces via `DuplicateKeyError`. Endpoint identity is a constant like `_ENDPOINT_CONFIRMAR = "POST /meses/{mes}/cierre/confirmar"`.
- RBAC is a FastAPI dependency: `Depends(require_permission("ciclo:cierre_operativo"))`, plus `require_step_up` for MFA-gated actions (reopen). Origin is verified with `Depends(verify_origin)` on mutations. Authority table Spec §2.4 wins over any other wording. Frontend navbar derives from a single permissions config.

## Import Organization

- Ruff isort (`I`) enforced. Order: stdlib → third-party → first-party (`app.*`). Absolute imports from `app.` (no relative package imports in domain/service code).
- Frontend: external packages, then `@/`-aliased internal imports; blank-line separated.

## Comments

- Module docstrings are dense and mandatory: they cite the rule number and spec section a module enforces (e.g. `"""... regla 5 / Spec §2.3"""`) and record the real bug that motivated the design (e.g. the `Decimal128` read issue, the `python-multipart` deploy drift). Kimi-audit findings are annotated inline (`# Kimi A-01`, `# B-2`).
- Comment the *why* and the invariant, not the *what*. Reference CR/Spec/DoD identifiers when a decision traces to a contract document.

## Scheduler (rule 6)

- `RUN_SCHEDULER=false` in the web service, **always** (default in `Settings.run_scheduler`). Jobs live only in the `compas-jobs` worker (1 instance). Every job is idempotent (snapshot = UPSERT by date). Tests pop `RUN_SCHEDULER` from env to guarantee the web app never starts the scheduler.

## Commits

- Conventional Commits (`docs(...)`, `feat(...)`, `fix(...)`, `merge:`). Trunk-based, short branches. Merge to `main` = deploy to staging; production only via `v*` tag with reviewer.
- **Systematic commit protocol — run before every commit (from global CLAUDE.md):**
  ```bash
  grep -rn "app.alegra.com/api/r1"   # must be 0 results
  grep -rn "journal-entries"         # must be 0 results
  grep -rn "estado.*pending"         # must be 0 results
  ```
  Then the active-BUILD tests must pass. If any fails: do not commit.
- Session close (project CLAUDE.md): update `docs/COMPAS_Control_Desarrollo.xlsx` (sheet 'Tareas') with openpyxl — task Estado, Fecha cierre, Evidencia (commit hash/PR); update 'Gates'/DoD sheet if a gate/DoD point closed; commit the Excel with the session's code. Never touch headers, Dashboard formulas, or data validations.

## Function & Module Design

- Small, single-purpose functions; private helpers `_prefixed`. Services raise a typed domain error carrying an HTTP status (`CierreError(detalle, status=422)`); routers translate it into `HTTPException`. Routers stay thin — validation of path shape (`_mes_key`, `_MES` regex) + permission deps + delegation to the service.
- Money helpers, time helpers, and IDs are centralized in `app/core/` and imported — never re-implemented inline.

---

*Convention analysis: 2026-07-22*
