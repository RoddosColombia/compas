# External Integrations

**Analysis Date:** 2026-07-22

## APIs & External Services

**Bank statement ingestion (file-based, NOT live APIs):**
- Bancolombia, BBVA, Global66 - Parsed from uploaded spreadsheets, no external HTTP calls. `backend/app/parsers/bank_parsers.py` (ported in spirit from SISMO v2).
  - Bancolombia: `.xlsx`, sheet 'Extracto', headers row 15, date d/m without year.
  - BBVA: `.xlsx`, active sheet, headers row 14, date d-m-Y.
  - Global66: `.xls/.xlsx`, sheet 'Movimientos de cuenta COP', headers row 4; preserves `moneda_original` + `tasa_cambio` (regla 7). Currently COP sheet only; multi-currency FX mapping is a TODO (needs a sample Global66 export).
  - Parser library: openpyxl. Amounts built as `Decimal` via `app.core.money.Money` (rejects float).
  - Upload endpoint: `POST /cargas` (`backend/app/cargas/router.py`), `UploadFile` (python-multipart).
- **Status: BUILT.** Parsers, mapper (`backend/app/cargas/mapper.py`) and load service (`backend/app/cargas/service.py`) exist.

## Data Storage

**Database:**
- MongoDB Atlas - Cluster SISMO-V3 (shared with SISMO family), database `compas`.
  - Connection: env `MONGODB_URI_COMPAS` (secret, `sync: false` in `render.yaml`).
  - Driver/ODM: Motor 3.7.1 (`AsyncIOMotorClient`, lazy, `tz_aware=True`) + Beanie 2.0.0 (`backend/app/db/mongo.py`).
  - Dedicated audit connection: env `MONGODB_URI_AUDIT` uses user `compas_audit` (role `audit_writer`) against the SAME `compas` DB, enforcing append-only `audit_log` (DoD #6). Fail-fast outside dev; dev falls back to the general connection (`backend/app/main.py` lifespan).
  - Test isolation: `COMPAS_TEST_MONGO_URI` / `COMPAS_TEST_AUDIT_URI` point at isolated `compas_test_*` databases; CI spins a 1-node replica set (auth via keyFile) for multi-document transactions (`.github/workflows/ci.yml`).
- **Status: BUILT.**

**File Storage (statement originals):**
- Interim: local filesystem via `ORIGINALES_DIR` (`backend/app/config.py`). On Render the disk is ephemeral - this is a DEV bridge; without a destination `procesar_carga` raises `OriginalNoPreservableError`.
- Target: AWS S3 - env `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET` declared in `render.yaml` and `Settings`, but no `boto3`/S3 client code exists in `backend/`.
- **Status: DEFERRED (S3 = DISP-02, Sprint 3+ / not built).** Env slots reserved only.

**Caching:**
- None (no Redis/Memcached).

## Authentication & Identity

**Custom auth (no external IdP):**
- JWT access tokens (in-memory on SPA) + refresh tokens (HttpOnly cookie). `backend/app/auth/` (`tokens.py`, `service.py`, `repository.py`, `router.py`, `deps.py`).
  - Access TTL 15 min; refresh family max 30 days, idle 12h (`backend/app/config.py`).
  - Secret: `JWT_SECRET` (fail-fast >=32B outside dev). PyJWT.
  - Passwords + backup codes hashed with bcrypt (`backend/app/auth/passwords.py`).
- MFA (TOTP) - pyotp; secret encrypted at rest with Fernet/AES (key `MFA_ENC_KEY`, fail-fast outside dev). QR provisioning URI issuer "COMPAS RODDOS"; ±1 step clock tolerance; 10 single-use backup codes (`backend/app/auth/mfa.py`). DoD #11.
- RBAC - FastAPI dependency-based (`backend/app/auth/deps.py`, `permissions.py`, `roles.py`) per Spec §4.1 authority matrix.
- **Status: BUILT.**

## Monitoring & Observability

**Error Tracking:**
- Sentry - sentry-sdk (>=2.0,<3.0). Initialized only if `SENTRY_DSN` set; `send_default_pii=False` + `before_send=_scrub_pii` strips PII/financial fields (descripcion, proveedor, valor, cookie, authorization, etc.) - `backend/app/main.py`. DSN is a secret (`sync: false`).
- **Status: BUILT (wired, conditional on DSN).**

**Uptime/Heartbeats:**
- Better Stack - Per-job heartbeats planned (`BETTER_STACK_HEARTBEATS`, 8 URLs one per job, RUNBOOK §7). Referenced in commented `compas-jobs` worker block in `render.yaml` and `backend/app/jobs/scheduler.py` TODO.
- **Status: DEFERRED (arrives with the jobs worker, Sprint 5-6). Not built.**

**Logs:**
- Python stdlib `logging` (`logger = logging.getLogger("compas")`). No external log shipper wired.

## CI/CD & Deployment

**Hosting:**
- Backend: Render `compas-api` (web, Ohio, plan free, `autoDeploy: true` from `main` during dev). `render.yaml`.
- Frontend: Vercel project `compas` at `compas.roddos.com` (static SPA; rewrites + security headers in `frontend/vercel.json`).
- DNS: GoDaddy (per project memory infra-real-roddos; not Cloudflare, despite some code comments referencing CF headers).

**CI Pipeline (`.github/workflows/ci.yml`, GitHub Actions):**
- `backend` - ruff check + ruff format --check + pytest with coverage (mongomock).
- `runtime-imports` - installs only `requirements.txt` and imports the app (catches Render runtime drift).
- `backend-real-mongo` - Mongo 7 replica set + audit role; runs `@requires_real_mongo`.
- `frontend` - biome lint + `npm run build` + vitest.
- `pip-audit` - CVE scan on `requirements.txt` (`--strict`, blocking, DoD #8).
- `gitleaks` - secret scan (blocking, regla 12).

## Environment Configuration

**Required env vars (secrets, `sync: false` in `render.yaml`):**
- `MONGODB_URI_COMPAS`, `MONGODB_URI_AUDIT`, `JWT_SECRET`, `MFA_ENC_KEY`, `SENTRY_DSN`.
- Deferred/reserved: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET` (S3), `BETTER_STACK_HEARTBEATS` (jobs worker).
- Non-secret: `RUN_SCHEDULER=false` (web), `APP_ENV`, `TZ=America/Bogota`.
- Frontend: `VITE_API_URL` (Vercel env).

**Secrets location:**
- Render env vars (manual load per RUNBOOK §8). Repo forbids secrets (gitleaks) EXCEPT `docs/INVENTARIO-SECRETOS.xlsx` (CEO decision, gitleaks allowlist). See `backend/.env.example` for the local template.

## Webhooks & Callbacks

**Incoming:**
- None. Bank data arrives via manual/scheduled file upload (`POST /cargas`), not webhooks.

**Outgoing:**
- Better Stack heartbeats (deferred; per-job HTTP pings once the jobs worker exists).

---

*Integration audit: 2026-07-22*
