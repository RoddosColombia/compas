# Gate G1 (BLOQUEANTE) — checklist de seguridad · fin de Sprint 0

**Aprobación (CR-003):** CEO Andrés (decisión) + auditoría adversarial Kimi ≥ 9.0 (evidencia).
**Ámbito:** cierre del andamiaje de seguridad de Fase 0–1 (RUNBOOK §9 + checklist de seguridad del PLAN).
**Leyenda estado:** ✅ hecho/verificado · 🟡 listo en repo, pendiente prerrequisito externo · ⏳ operacional (CEO).

## A. Controles de seguridad (código/gates) — responsable: Claude Code
| # | Requisito | Estado | Evidencia |
|---|---|---|---|
| A1 | Auth endurecida (login/refresh/logout, backoff, denylist, token_version) | ✅ | Sesión 2 — Gates 'Kimi PR-1/PR-2/PR-3 (Sesión 2)' Aprobados; `main` |
| A2 | RBAC por dependencia (§4.1/§2.4) + tests negativos por rol | ✅ | Sesión 2 PR-3 (RBAC) GO 9.5 |
| A3 | MFA TOTP admin/directivo + step-up + respaldo + HIBP + reset | ✅ | Sprint 0b PR-2 — Gate 'Kimi PR-2 R' GO; **DoD #11 Cumplido** |
| A4 | Cabeceras de seguridad (CSP/HSTS/nosniff/Referrer/frame-ancestors) API+SPA | ✅ | Sprint 0b PR-3 — Gate 'Kimi PR-3' 9.2 GO; **DoD #12 Cumplido** |
| A5 | `audit_log` append-only verificado en CI (update/remove FALLA; insert/find OK) | ✅ | `tests/test_audit_immutable.py`; job `backend-real-mongo` VERDE (run `29771391813`); **Gate 'Kimi PR-I Sesión 3' GO 9.5** → A5 CERRADO |
| A6 | CI con pip-audit + gitleaks + Dependabot bloqueantes | ✅ | Sesión 3 PR #6; 5 jobs VERDES (`29771391813`); pip-audit 0 CVEs; **Kimi PR-I GO 9.5 → DoD #8 CUMPLIDO**, A6 CERRADO |
| A7 | Secretos fuera del repo; fail-fast fuera de dev (JWT/MFA/AUDIT) | ✅ | `app/main.py` fail-fast; `render.yaml` (`sync:false`); `tests/test_audit_failfast.py` |

## B. Gobernanza — responsable: CEO
| # | Requisito | Estado | Evidencia |
|---|---|---|---|
| B1 | Aprobador ≠ ejecutor resuelto | ✅ | **CR-003** (CEO + evidencia Kimi); tracker hoja CRs + Gates G1 |
| B2 | Custodio del break-glass nombrado | ✅ | RUNBOOK §0 (Andrés); break-glass MFA documentado §8 |
| B3 | Acceso a secretos de producción (máx. 2) | ✅ | RUNBOOK §0 (Andrés + Iván) |

## C. Operacional (infra real) — responsable: CEO/Andrés (S0B-03)
| # | Requisito | Estado | Evidencia a adjuntar |
|---|---|---|---|
| C1 | **Readiness** 200 en staging (no solo liveness): `GET /api/v1/health/ready` → `{status:"ready", mongo:"up", beanie:"ready"}` (Kimi G-2 — `/health` daría 200 aunque Mongo esté caído) | ⏳ | salida del `GET /api/v1/health/ready` de `compas-api-stg` |
| C2 | Deploy staging por merge a main; **producción BLOQUEADA** sin tag `v*`+reviewer (probar el bloqueo) | ⏳ | evidencia del intento de deploy a prod bloqueado |
| C3 | pip-audit + gitleaks **bloquean un PR de prueba con secreto sembrado** | ⏳ | run rojo del PR de prueba (secreto sembrado) |
| C4 | Cabeceras vivas: `curl -I https://compas.roddos.com` y `.../api/health` | ⏳ | salida de `curl -I` (CSP/HSTS/nosniff/…) |
| C5 | Región primaria y de réplica anotadas (§0); buckets + CRR verificados | ⏳ | objeto de prueba replicado + notas §0 |
| C6 | Provisionar `MONGODB_URI_AUDIT` y `MFA_ENC_KEY` en Render (valores) | ⏳ | secretos cargados (RUNBOOK §8) |
| C7 | **Aprovisionamiento de datos/roles en Atlas** (Kimi G-1) — `compas_stg` primero, `compas` después: `scripts/create_audit_role.py` (rol `audit_writer` + `compas_audit`; sin él los inserts a `audit_log` fallan en runtime), `scripts/create_auth_indexes.py` (únicos + TTL; sin TTL regresa la L4), `migrations/20260901_seed_rubros.py` y `..._seed_configuracion.py` (semillas idempotentes) | ⏳ | logs idempotentes de los 4 scripts contra `compas_stg` |

## G-3 (Kimi) — reviewer de deploy a producción
CR-003 resolvió el aprobador de **G1** (CEO + evidencia Kimi; Iván derogado). Para el **deploy a
producción** (F-32: tag `v*` + required reviewer), y siendo coherentes con CR-003 y con que el CEO
es la autoridad única: el **required reviewer de producción es el CEO Andrés**, con la evidencia
adversarial de Kimi como control independiente (mismo patrón que G1). Se acepta la limitación de
operador único (mismo tradeoff de bus-factor ya reconocido en CR-003). *A confirmar por el CEO en
RUNBOOK §9; si prefiere reactivar a Iván solo para deploys, es una decisión suya.*

## Prerrequisitos duros antes de evaluar G1
1. **Sesión 3 (CI)** verde y con gate de código Kimi ≥ 9.0 (cierra A5/A6). ← en curso (PR #6).
2. **Bloque C con evidencia** — operacional del CEO (S0-06/S0-07/S0B-03), **incluida C7**
   (aprovisionamiento de Atlas: rol/usuario de audit + índices de auth + semillas).
3. **Ruta crítica (orden):** S0-06 (infra) → C6/C7 (secretos + Atlas) → C1 (readiness) → C4
   (cabeceras vivas) · en paralelo: run verde de Actions para A5/A6.

Cuando A5/A6 estén verdes y el bloque C (C1–C7) tenga evidencia, se genera el paquete de auditoría
G1 (`auditorias/G1-I/`) para el veredicto final de Kimi del Sprint 0.
