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

## C. Operacional (infra real) — responsable: CEO/Andrés (S0B-03) — **EJECUTADO 20-jul-2026**
> **Contexto (decisión CEO 20-jul, principio rector en CLAUDE.md):** fase de desarrollo con
> **entorno ÚNICO** — `compas-api` (auto-deploy desde `main`) contra la base `compas` en el
> cluster de SISMO-V3. `compas-api-stg`/`compas_stg` y el endurecimiento de producción
> (tag `v*` + reviewer) se montan en **go-live**. C1/C4/C7 se evaluaron sobre el entorno único.

| # | Requisito | Estado | Evidencia |
|---|---|---|---|
| C1 | **Readiness** 200 (no solo liveness): `GET /api/v1/health/ready` | ✅ | `https://compas-api-von1.onrender.com/api/v1/health/ready` → HTTP 200 `{"status":"ready","mongo":"up","beanie":"ready"}` (20-jul) |
| C2 | Deploy por merge a main; producción bloqueada | 🔁 **Sustituido por decisión CEO** (20-jul): en desarrollo hay UN solo servicio con auto-deploy; no existe prod separada que bloquear. El control (autoDeploy:false + tag v* + reviewer CEO) se **reactiva en go-live** — documentado en `render.yaml` y CLAUDE.md | commit `74e25bc` (render.yaml + principio rector) |
| C3 | pip-audit + gitleaks **bloquean un PR de prueba con secreto sembrado** | ✅ | PR #20 (credenciales AWS falsas sembradas): **gitleaks FAIL en 7s** — run `29797947548`; PR cerrado sin merge (20-jul) |
| C4 | Cabeceras vivas en el API | ✅ | `curl -I https://compas-api-von1.onrender.com/health`: CSP `default-src 'none'`, HSTS preload, nosniff, X-Frame DENY, no-referrer (20-jul). *Dominio `compas.roddos.com` (Cloudflare): diferido, se re-verifica al cablearlo* |
| C5 | Región primaria/réplica anotadas; buckets + CRR verificados | ⏳ **Diferido a pre-carga-real** (S3/AWS = bloque C pendiente). Guardrail vigente: la regla dura M-04 (Kimi R-PR1) **bloquea cargas reales sin S3/preservación** — no hay datos reales que respaldar todavía | RUNBOOK §6 pendiente; M-04 en `app/cargas/service.py` |
| C6 | Provisionar `MONGODB_URI_AUDIT` y `MFA_ENC_KEY` en Render | ✅ | 4 secretos cargados vía Blueprint (URI_COMPAS/URI_AUDIT/JWT/MFA_ENC_KEY); fail-fast NO saltó (el arranque exige los 4); INVENTARIO-SECRETOS col VALOR (20-jul) |
| C7 | **Aprovisionamiento de datos/roles en Atlas** (Kimi G-1) | ✅ | Base `compas` en cluster SISMO-V3: rol `audit_writer` + `compas_audit` + `compas_app` por **Atlas UI** (corrección a H-01: Atlas bloquea createUser/createRole por driver en TODOS los tiers — RUNBOOK §2); índices auth+forense+dominio y semillas (33 rubros, 3 config) por scripts idempotentes; **verificado en vivo**: `compas_audit` NO puede escribir fuera de `audit_log` ni update en él (DoD #6). `compas_stg`: N/A por decisión de entorno único |

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
