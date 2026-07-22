# Technology Stack

**Analysis Date:** 2026-07-22

## Languages

**Primary:**
- Python 3.12 - Backend (`backend/app/`), FastAPI service + jobs worker. `requires-python = ">=3.12"` in `backend/pyproject.toml`.
- TypeScript 5.6 - Frontend (`frontend/src/`), React SPA. Strict via `tsc -b` in build.

**Secondary:**
- JavaScript/JSX (via TSX) - React components in `frontend/src/`.

## Runtime

**Backend Environment:**
- Python 3.12 on Render (`render.yaml` `runtime: python`).
- ASGI server: Uvicorn 0.44.0 (`uvicorn[standard]`). Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2 --proxy-headers` (`render.yaml`).
- Entry point: `backend/app/main.py` → `create_app()` builds the `FastAPI` app; `app = create_app()`.

**Frontend Environment:**
- Node 20 in CI (`.github/workflows/ci.yml`). Vite 6 dev server / build. Deployed as static build (`dist/`) on Vercel.

**Package Managers:**
- Backend: pip. Runtime deps pinned in `backend/requirements.txt`; dev/test deps in `backend/requirements-dev.txt` (`-r requirements.txt`). No lockfile (versions are exact-pinned `==`).
- Frontend: npm. Lockfile `frontend/package-lock.json` present (`npm ci` in CI).

## Frameworks

**Backend Core:**
- FastAPI 0.135.2 - HTTP API under `/api/v1` (`backend/app/api/v1/__init__.py`), RBAC via dependencies, CORS + `SecurityHeadersMiddleware` (`backend/app/main.py`).
- Beanie 2.0.0 - ODM over MongoDB for domain Documents (`backend/app/db/mongo.py`, `init_beanie_for`). Only domain models registered (`DOMAIN_DOCUMENTS`); `AuditLog`/`User`/`RefreshSession` use raw Motor.
- Motor 3.7.1 - Async MongoDB driver (`AsyncIOMotorClient`, `tz_aware=True`, lazy connect).
- Pydantic 2.12.5 + pydantic-settings 2.14.2 - Strict schemas (`strict=True`, `extra="forbid"`) and env config (`backend/app/config.py`, `Settings`).
- APScheduler 3.11.2 - Jobs worker scheduler (`backend/app/jobs/scheduler.py`, `AsyncIOScheduler` TZ America/Bogota). Currently 0 jobs registered (deferred to Sprint 5+).

**Backend Auth/Crypto:**
- PyJWT 2.13.0 - Access/refresh JWTs (`backend/app/auth/tokens.py`).
- bcrypt 5.0.0 - Password + backup-code hashing (`backend/app/auth/passwords.py`).
- pyotp 2.9.0 - TOTP MFA (`backend/app/auth/mfa.py`).
- cryptography 48.0.1 - Fernet encryption of the MFA secret at rest (`backend/app/auth/mfa.py`).

**Backend Utility:**
- openpyxl 3.1.5 - Bank statement `.xlsx` parsing (`backend/app/parsers/bank_parsers.py`).
- httpx 0.28.1 - HTTP client (also FastAPI TestClient transport).
- anyio 4.12.1 - Async primitives.
- python-multipart 0.0.31 - `UploadFile` support for `POST /cargas` (required at runtime by FastAPI).
- sentry-sdk >=2.0,<3.0 - Error tracking (optional; initialized only if `SENTRY_DSN` set).

**Frontend Core:**
- React 19.0.0 + react-dom 19.0.0 (`frontend/package.json`).
- react-router-dom 7.1.1 - Routing (routes `/:mes/:vista` per CLAUDE.md).
- @tanstack/react-query 5.62.0 - Server state / cache. Query keys `['mes','YYYY-MM',vista]`.
- decimal.js-light 2.5.1 - Money math on the client (never `Number` on amounts; regla 1).
- Tailwind CSS 4.0.0 via `@tailwindcss/vite` - Styling. shadcn/ui conventions (`components.json`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`).

**Testing:**
- Backend: pytest 9.0.3 + pytest-asyncio 1.3.0 (`asyncio_mode = "auto"`) + pytest-cov 7.1.0. `mongomock-motor` 0.0.36 for fast tests; real-mongo tests marked `@requires_real_mongo` (need replica set for multi-doc transactions).
- Frontend: Vitest 3.2.6 + @testing-library/react 16.1.0 + jest-dom, jsdom env (`frontend/vite.config.ts`, setup `./src/test/setup.ts`).

**Build/Dev Tooling:**
- Backend lint/format: Ruff (target `py312`, line-length 88, rules `E,F,I,UP,B,ASYNC`, `B008` ignored) - `backend/pyproject.toml`.
- Frontend lint/format: Biome 1.9.4 (`frontend/biome.json`, `npm run lint` → `biome check .`).
- Frontend build: `tsc -b && vite build`. Vite 6 (pinned via `overrides`), plugins `@vitejs/plugin-react` + `@tailwindcss/vite`, alias `@` → `./src`.
- Dependency CVE scan: pip-audit >=2.7 (`--strict` on `requirements.txt`, DoD #8).
- Secret scan: gitleaks 8.18.4 (`.gitleaks.toml`, blocks CI; regla 12).
- Kimi audit PDF: fpdf2 2.8.7 (dev-only, `scripts/generate_kimi_audit_pdf.py`).

## Key Dependencies

**Critical:**
- FastAPI + Beanie + Motor + Pydantic - The backend runtime spine.
- PyJWT + bcrypt + pyotp + cryptography - Full auth+MFA stack (built).
- @tanstack/react-query + decimal.js-light - Frontend data + money handling.

**Infrastructure:**
- APScheduler - Jobs worker (built as skeleton; worker service commented out in `render.yaml`, deferred to Sprint 5-6).
- sentry-sdk - Optional error tracking with PII scrubbing (`_scrub_pii` in `backend/app/main.py`).

## Configuration

**Environment (`backend/app/config.py` `Settings`, pydantic-settings):**
- Reads `.env` (dev) + OS/Render env (`extra="ignore"`). `get_settings()` is `@lru_cache`.
- Key vars: `APP_ENV` (Literal dev/staging/production), `TZ` (America/Bogota), `RUN_SCHEDULER` (false on web, regla 6), `MONGODB_URI_COMPAS`, `MONGODB_URI_AUDIT`, `MONGODB_DB` (compas), `JWT_SECRET`, `MFA_ENC_KEY`, `SENTRY_DSN`, auth/session TTLs, login rate-limit knobs, `FRONTEND_ORIGIN` (CORS/Origin), `ORIGINALES_DIR`, S3 vars.
- Fail-fast outside dev: `JWT_SECRET` (>=32B), `MFA_ENC_KEY`, `MONGODB_URI_AUDIT`, and `RUN_SCHEDULER=true` on web is fatal (`lifespan` in `backend/app/main.py`).
- Business rules (thresholds, DIAN calendar) live in Mongo `configuracion`, NOT env (per config docstring).
- Frontend: `VITE_API_URL` (fallback `http://localhost:8000`) in `frontend/src/lib/api.ts`.

**Build:**
- `backend/pyproject.toml` (pytest, ruff), `backend/requirements*.txt`.
- `frontend/vite.config.ts`, `frontend/tsconfig*.json`, `frontend/biome.json`, `frontend/components.json`.
- `render.yaml` (backend blueprint), `frontend/vercel.json` (SPA rewrites + security headers).

## Platform Requirements

**Development:**
- Python 3.12, Node 20+. MongoDB (mongomock for fast tests; a real replica-set Mongo for `@requires_real_mongo`).
- One-environment dev model (CEO decision): push to `main` auto-deploys.

**Production:**
- Backend: Render web service `compas-api` (Ohio region, currently plan `free`, autoDeploy from `main`), health check `/health`.
- Frontend: Vercel (static build) at `compas.roddos.com`.
- Database: MongoDB Atlas (SISMO-V3 cluster), database `compas`.
- Deferred: `compas-jobs` worker (Sprint 5-6), staging service `compas-api-stg` and tag `v*` + reviewer flow (go-live).

---

*Stack analysis: 2026-07-22*
