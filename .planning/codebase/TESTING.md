# Testing Patterns

**Analysis Date:** 2026-07-22

## Test Framework

**Backend runner:**
- pytest with `pytest-asyncio` (`asyncio_mode = "auto"` in `backend/pyproject.toml` — no per-test `@pytest.mark.asyncio` needed).
- Config: `backend/pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, `pythonpath = ["."]` (so `import app` works under both `pytest` and `python -m pytest`), `addopts = "-ra"`.
- Fixtures/plumbing: `backend/tests/conftest.py`.

**Frontend runner:**
- Vitest 3 + React Testing Library (`@testing-library/react`, `@testing-library/jest-dom`), jsdom environment.
- Setup: `frontend/src/test/setup.ts`; config in `frontend/vite.config.ts`.

**Run Commands:**
```bash
# Backend (fast, mongomock — default; real-mongo tests auto-skip)
cd backend && pytest -q
cd backend && pytest -q --cov=app --cov-report=term-missing   # CI's coverage report

# Backend real-mongo suite (needs COMPAS_TEST_MONGO_URI → a real replica set)
cd backend && pytest -m requires_real_mongo -q

# Frontend
cd frontend && npm run test        # vitest run (one-shot)
cd frontend && npm run test:watch  # vitest watch
```

## The two-tier Mongo strategy (the central testing decision)

`backend/tests/conftest.py` documents this explicitly. Two tiers because mongomock has hard limits:

**Tier 1 — mongomock (`mongomock-motor`, `AsyncMongoMockClient`), default & fast:**
- Used for domain construction/validation, readiness (`/health/ready`), `init_beanie` wiring, business logic that doesn't depend on real Mongo semantics.
- A session-scoped autouse fixture `_beanie_documents_initialized` runs `init_beanie` once against mongomock so Beanie 2.0 `Document` instances can be constructed in pure unit tests (Beanie forbids instantiating a Document before init).
- The `app` fixture builds the FastAPI app with `create_client` monkeypatched to return the mock and `dependency_overrides[get_mongo_client]` set; it pops `RUN_SCHEDULER` so the web app never starts the scheduler (rule 6).

**Tier 2 — real Mongo (`@pytest.mark.requires_real_mongo`), for what mongomock cannot fake:**
- **Skipped by default.** `pytest_collection_modifyitems` skips any `requires_real_mongo` item unless invoked with `-m requires_real_mongo`. The marker is registered in `conftest.py` and `pyproject.toml`.
- Required because mongomock does **not** support:
  1. The partial unique index `(banco, id_banco)` with `partialFilterExpression {id_banco:{$type:'string'}}` (rule 5) — no `DuplicateKeyError`, no partial-uniqueness.
  2. Multi-document transactions (rule 8: budget approval, load finalization, month close) — no sessions/commit/abort, no `TransientTransactionError`.
  3. DB privilege enforcement (rule 4 / DoD #6) — mongomock ignores roles, so an immutability check there would be a placebo.
- These tests read `COMPAS_TEST_MONGO_URI` (and `COMPAS_TEST_AUDIT_URI` for the audit-role tests) and `pytest.skip(...)` when the env var is absent, so local `pytest` stays green without a cluster. Per project memory, the URI points at the SISMO cluster into isolated `compas_test_*` databases.

## Test File Organization

**Backend — `backend/tests/`, flat, one file per area:**
- `test_domain_*.py` (money, rubro, mes_control, configuracion, indexes, persistence), `test_auth_*.py`, `test_audit_*.py`, `test_cargas*/test_bank_parsers`, `test_ciclo_*`, `test_cierre_*`, `test_control`, `test_presupuesto_*`, `test_transaccion*`, `test_rbac_*`, plus cross-cutting `test_scheduler_flag`, `test_security_headers`, `test_sentry_scrub`, `test_health`.
- Files needing real Mongo carry a `_realmongo` suffix (`test_cierre_realmongo.py`, `test_presupuesto_aprobar_realmongo.py`); DoD-#6 immutability lives in `test_audit_immutable.py`.

**Frontend — co-located:**
- `frontend/src/App.test.tsx` next to `App.tsx`. Tests import via the `@/` alias.

## Backend Test Structure

**Real-mongo class pattern (from `test_cierre_realmongo.py`):**
```python
@pytest.mark.requires_real_mongo
class TestCierreReal:
    @pytest_asyncio.fixture
    async def entorno(self, monkeypatch):
        uri = os.environ.get("COMPAS_TEST_MONGO_URI")
        if not uri:
            pytest.skip("COMPAS_TEST_MONGO_URI no configurado")
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("JWT_SECRET", "x" * 40)
        monkeypatch.setenv("COOKIE_SECURE", "False")
        monkeypatch.delenv("RUN_SCHEDULER", raising=False)
        get_settings.cache_clear()
        app = create_app()
        client = AsyncIOMotorClient(uri, tz_aware=True)
        dbname = "compas_test_cierre"
        await client.drop_database(dbname)          # clean slate
        db = client[dbname]
        await init_beanie(database=db, document_models=DOMAIN_DOCUMENTS)
        repository.configure_auth(client, dbname)
        configure_audit(client, dbname)
        # ... seed users/config/rubros ...
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac, db
        repository.reset_auth(); reset_audit()
        await client.drop_database(dbname)          # teardown
        client.close(); get_settings.cache_clear()
```
Patterns:
- Isolated named database per suite (`compas_test_<area>`), dropped before and after.
- Env set via `monkeypatch.setenv` + `get_settings.cache_clear()` (Settings is lru-cached).
- HTTP-level tests drive the real app through `httpx.ASGITransport` (no live server); a `_token(ac)` helper logs in and returns the `Authorization` header; a `_sembrar(...)` helper seeds the fixture scenario.

**Assertions:** exact `Decimal` equality on money (`assert aj.valor == Decimal("2")`), amounts-as-string on the API (`assert j["diferencia"] == "-2.00"`), and audit event counts (`await db["audit_log"].count_documents({"evento": "mes.cerrado"}) == 1`).

## Signature patterns to reproduce

**Golden / dorado test** — the canonical numeric happy path proving the flow "cuadra" (reconciles) by two independent paths. Example `test_dorado_numerico_cuadra_a_118`: closes June, asserts `diferencia == "-2.00"`, `saldo_inicial_siguiente == "118.00"`, the adjustment tx (egreso 2, system rubro, day-1 of July), M+1 re-anchored to R_M, and that July's disponible equals 118 recomputed via the service (`_caja_libro`) — i.e. the same number reached two ways. Every multi-doc flow has a dorado test.

**Saga / two failure-point convergence** — each transactional flow proves rollback + convergence at **both** failure points:
1. `test_convergencia_falla_emit_compensa` — monkeypatch `emit_audit` to raise after commit; assert full compensation (month still `en_ejecucion`, no adjustment, anchor restored, zero `mes.cerrado` events), then `monkeypatch.undo()` and retry converges to `CERRADO`.
2. `test_convergencia_abort_datos` — monkeypatch `MesControl.save` to raise on the last in-session write (writing `CERRADO`); assert total rollback, then retry converges.
Companion cases: idempotent replay (same `Idempotency-Key` → identical JSON, one event), double-close with a different key → 409, adjustment omitted when `diferencia == 0`, reopen creates a contra-asiento (original never deleted) and restores the prior anchor.

**Immutability (DoD #6)** — `test_audit_immutable.py` uses `COMPAS_TEST_AUDIT_URI` (the `compas_audit` user). A positive test (insert+find succeed) guards against a broken role silently killing the audit; negatives assert `update_one`/`delete_one` raise `OperationFailure` code 13.

## Mocking

- Backend: `monkeypatch` for env vars, for injecting the mongomock client (`monkeypatch.setattr(mongo, "create_client", ...)`), and for forcing failure at a specific point in a saga (patching `emit_audit` or `MesControl.save`). No mocking of Mongo itself in Tier 2 — use the real thing.
- **What NOT to mock:** partial unique indexes, transactions, and DB privileges — those must run against real Mongo or the test is meaningless.
- Frontend: no network in jsdom; tests assert the resulting UI state (e.g. session restore fails → redirect to `/login`) and test pure lib functions (`formatCOP`, `formatFecha`, `validarArchivo`) directly.

## Frontend Test Structure

```typescript
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "@/App";
import { formatCOP, formatFecha } from "@/lib/money";

describe("money — regla 1 (formato es-CO, nunca Number sobre montos)", () => {
  it("formatea un monto-string como COP", () => {
    const out = formatCOP("1234567.89").replace(/\s/g, " "); // normalize NBSP
    expect(out).toBe("$ 1.234.567,89");
  });
});
```
- Money/date formatting tests normalize whitespace (`replace(/\s/g, " ")`) so they don't couple to the NBSP/narrow-space code point Intl inserts.
- Client-side validation mirrors the backend (`validarArchivo` — "espejo del backend"): both sides reject `.xlsm`, unknown extensions, and >10 MB.

## CI Pipeline (`.github/workflows/ci.yml`)

Runs on `pull_request` and push to `main`. Jobs:
- **backend** — `ruff check .`, `ruff format --check .`, `pytest -q --cov=app --cov-report=term-missing` (mongomock tier, coverage is report-only).
- **runtime-imports** — installs **only** `backend/requirements.txt` (no dev deps) and imports the app via `create_app()`, reproducing Render's runtime to catch missing-dependency drift.
- **backend-real-mongo** — the `@requires_real_mongo` suite. Spins a `mongo:7` **replica set of 1 node** with `--keyFile` auth via `docker run` (Actions service-containers can't override the command; transactions need a replica set). Waits for primary, creates root, runs `scripts/create_audit_role.py` to provision the `audit_writer` role, then `pytest -m requires_real_mongo -q`. Provides `COMPAS_TEST_MONGO_URI` and `COMPAS_TEST_AUDIT_URI`. This is a blocking required check.
- **frontend** — `npm ci`, `npm run lint` (biome), `npm run build` (tsc + vite), `npm run test` (vitest).
- **pip-audit** — `pip-audit --requirement backend/requirements.txt --strict` (DoD #8, blocking; exceptions pinned with `--ignore-vuln <GHSA>` under review).
- **gitleaks** — full-history secret scan with `.gitleaks.toml`, `--exit-code 1` (rule 12).

## Coverage

- Reported (`--cov=app --cov-report=term-missing`) but no hard threshold gate is enforced in CI.

## Test Types

- **Unit:** domain model validation, money/time/ulid primitives, permissions, parsers (mongomock or pure).
- **Integration (real Mongo):** transactional flows, partial-index dedup, audit immutability, concurrency, index creation — via `httpx.ASGITransport` against the assembled app.
- **Frontend component/unit:** RTL for the app shell/routing, direct calls for lib functions.
- **E2E:** Playwright and k6 (load, DoD-9) are declared in CLAUDE.md as project standards; not present in the current tree.

---

*Testing analysis: 2026-07-22*
