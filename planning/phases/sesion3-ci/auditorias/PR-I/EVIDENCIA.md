# EVIDENCIA — sesion3-ci · PR-I (código) · run real VERDE

## 0. Estado: GitHub Actions VERDE (los 5 jobs) — PR #6
Run `29771391813` (RoddosColombia/compas#6, rama `sesion3-ci`, evento pull_request):
```
✓ backend-real-mongo   in 43s
✓ backend              in 2m48s
✓ pip-audit            in 22s
✓ frontend             in 24s
✓ gitleaks             in 8s
```
El job **`backend-real-mongo` es el prerrequisito de A5/A6 del Gate G1** (DoD #6 real).

> **Nota de honestidad (red→green):** la PRIMERA corrida post-incidente (`29751499120`) salió ROJA
> por 4 causas reales (no el incidente). Se hizo causa raíz y se corrigieron, y ESTA corrida quedó
> verde. Las 4 correcciones (sección 4) son parte de lo que se somete.

## 1. `.github/workflows/ci.yml` (artefacto central)
```yaml
name: CI
"on":
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  backend:                       # ruff check + ruff format --check + pytest (mongomock) + cobertura
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: backend } }
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5   # v4 (SHA-pin)
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5 (SHA-pin)
        with: { python-version: "3.12", cache: pip }
      - run: pip install -r requirements-dev.txt
      - run: ruff check .
      - run: ruff format --check .
      - run: pytest -q --cov=app --cov-report=term-missing
  backend-real-mongo:            # @requires_real_mongo contra mongo:7 con auth (DoD #6)
    runs-on: ubuntu-latest
    services:
      mongo:
        image: mongo:7
        ports: ["27017:27017"]
        env: { MONGO_INITDB_ROOT_USERNAME: root, MONGO_INITDB_ROOT_PASSWORD: rootpw }
    env:
      ADMIN_URI: "mongodb://root:rootpw@localhost:27017/?authSource=admin"
      COMPAS_TEST_MONGO_URI: "mongodb://root:rootpw@localhost:27017/?authSource=admin"
      COMPAS_TEST_AUDIT_URI: "mongodb://compas_audit:audit-pwd-16chars!@localhost:27017/compas?authSource=compas"
      COMPAS_AUDIT_PWD: "audit-pwd-16chars!"
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
        with: { python-version: "3.12", cache: pip }
      - run: pip install -r backend/requirements-dev.txt
      - name: wait-for-mongo          # los servicios arrancan asíncronos → ping con reintentos
        run: |
          python - <<'PY'
          import os, time, pymongo
          uri = os.environ["ADMIN_URI"]
          for _ in range(30):
              try:
                  pymongo.MongoClient(uri, serverSelectionTimeoutMS=1000).admin.command("ping"); break
              except Exception: time.sleep(2)
          else: raise SystemExit("mongo no respondió")
          PY
      - name: crear rol de auditoría   # mismo script del operador (RUNBOOK §2)
        run: python scripts/create_audit_role.py "$ADMIN_URI" compas
      - name: pytest @requires_real_mongo
        working-directory: backend
        run: pytest -m requires_real_mongo -q
  frontend:                      # biome check + tsc/vite build + vitest
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: frontend } }
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5
      - uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4 (SHA-pin)
        with: { node-version: "20", cache: npm, cache-dependency-path: frontend/package-lock.json }
      - run: npm ci
      - run: npm run lint
      - run: npm run build
      - run: npm run test
  pip-audit:                     # CVEs en deps de runtime (DoD #8) — bloqueante
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
        with: { python-version: "3.12" }
      - run: pip install pip-audit
      - run: pip-audit --requirement backend/requirements.txt --strict
  gitleaks:                      # secretos (regla 12) — binario SHA-pineado, no la action con licencia
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5
        with: { fetch-depth: 0 }
      - name: gitleaks
        run: |
          VER=8.18.4
          curl -sSfL ".../gitleaks_${VER}_linux_x64.tar.gz" | tar -xz gitleaks
          ./gitleaks detect --source . --config .gitleaks.toml --redact --no-banner --exit-code 1
```

## 2. Inmutabilidad de `audit_log` en Mongo real (DoD #6) — `tests/test_audit_immutable.py`
```python
pytestmark = pytest.mark.requires_real_mongo
_UNAUTHORIZED = 13  # OperationFailure cuando el rol no tiene la acción

@pytest.fixture
async def audit_col():
    uri = os.environ.get("COMPAS_TEST_AUDIT_URI")   # usuario compas_audit (audit_writer)
    if not uri: pytest.skip("COMPAS_TEST_AUDIT_URI no configurado")
    client = AsyncIOMotorClient(uri, tz_aware=True)
    yield client["compas"]["audit_log"]; client.close()

async def test_insert_y_find_como_compas_audit_funcionan(audit_col):   # POSITIVO
    res = await audit_col.insert_one(_doc())         # sin esto, un rol roto sin insert
    assert res.inserted_id is not None               # pasaría el negativo y el audit
    got = await audit_col.find_one({"_id": res.inserted_id})   # moriría en silencio
    assert got is not None and got["evento"] == "user.login"

async def test_update_sobre_audit_log_falla(audit_col):        # NEGATIVO
    with pytest.raises(OperationFailure) as ei:
        await audit_col.update_one({}, {"$set": {"evento": "tamper"}})
    assert ei.value.code == _UNAUTHORIZED

async def test_remove_sobre_audit_log_falla(audit_col):        # NEGATIVO (append-only)
    with pytest.raises(OperationFailure) as ei:
        await audit_col.delete_one({})
    assert ei.value.code == _UNAUTHORIZED
```
Los 11 `@requires_real_mongo` que corrió el job verde:
```
test_audit_immutable.py::{insert_y_find_como_compas_audit_funcionan, update_...falla, remove_...falla}
test_auth_concurrency.py::test_rotacion_exactamente_una_bajo_concurrencia
test_auth_indexes.py::{todos_los_indices_de_auth_existen, email_unico_se_aplica, ttl_configurado_en_login_throttle}
test_domain_indexes.py::{rubro_nombre_unico_por_grupo, mismo_nombre_distinto_grupo_ok, configuracion_clave_vigencia_unica}
test_real_mongo_marker.py::test_placeholder_dedup_indice_unico_parcial   # skip marcado "Sprint 1"
```

## 3. Salidas locales (además del run verde)
```
# suite rápida (console pytest, reproduce CI):
172 passed, 11 skipped, 9 warnings in 208.37s
# pip-audit con los pins nuevos:
No known vulnerabilities found
# ruff format --check . → All checks passed! · biome check . → No fixes applied
```

## 4. Las 4 correcciones (red→green, causa raíz)
| # | Job | Causa raíz | Fix |
|---|-----|-----------|-----|
| 1 | pip-audit | 10 CVEs en 3 deps | `PyJWT 2.12.1→2.13.0` (PYSEC-2026-175..179), `cryptography 46.0.7→48.0.1` (GHSA-537c-gmf6-5ccf), `pydantic-settings 2.14.1→2.14.2` (GHSA-4xgf-cpjx-pc3j). Suite 172 passed → sin regresión auth/MFA |
| 2 | backend-real-mongo | `ModuleNotFoundError: app`: el `pytest` de consola no pone `backend/` en `sys.path` (`python -m` sí, por el cwd) | `pythonpath=["."]` en `backend/pyproject.toml` — fija ambas invocaciones sin depender de `tests/__init__.py` |
| 3 | backend | `ruff format --check` en `tests/test_domain_rubro.py` | reformateado |
| 4 | frontend | `biome check`: format en `vercel.json`/`money.ts`, orden de imports en `button.tsx` | autofix (EOL normalizados por `.gitattributes`) |

## 5. Diff (main..sesion3-ci) — resumen
24 archivos; núcleo: `ci.yml` (+115), `dependabot.yml` (+21), `.gitleaks.toml`, `.gitattributes`,
tests real-mongo (`test_audit_immutable`+70, `test_auth_indexes`+60, `test_auth_concurrency`+47,
`test_real_mongo_marker`), `requirements*.txt`, `pyproject.toml` (pythonpath). Resto: docs de planning
(PLAN/gates) y RUNBOOK.
