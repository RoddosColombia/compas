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
| A5 | `audit_log` append-only verificado en CI (update/remove FALLA; insert/find OK) | 🟡 | `tests/test_audit_immutable.py` implementado; verificado LOCAL contra `mongo:7`+auth (10 passed); **pendiente run verde de Actions** (incidente GitHub) |
| A6 | CI con pip-audit + gitleaks + Dependabot bloqueantes | 🟡 | Sesión 3 PR #6 (`ci.yml`, `dependabot.yml`, `.gitleaks.toml`); PLAN-I 9.1 GO; **pendiente run verde + gate de código** |
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
| C1 | `render.yaml` aplicado; `/health` 200 en staging | ⏳ | captura/HTTP 200 de `compas-api-stg` |
| C2 | Deploy staging por merge a main; **producción BLOQUEADA** sin tag `v*`+reviewer (probar el bloqueo) | ⏳ | evidencia del intento de deploy a prod bloqueado |
| C3 | pip-audit + gitleaks **bloquean un PR de prueba con secreto sembrado** | ⏳ | run rojo del PR de prueba (secreto sembrado) |
| C4 | Cabeceras vivas: `curl -I https://compas.roddos.com` y `.../api/health` | ⏳ | salida de `curl -I` (CSP/HSTS/nosniff/…) |
| C5 | Región primaria y de réplica anotadas (§0); buckets + CRR verificados | ⏳ | objeto de prueba replicado + notas §0 |
| C6 | Provisionar `MONGODB_URI_AUDIT` y `MFA_ENC_KEY` en Render (valores) | ⏳ | secretos cargados (RUNBOOK §8) |

## Prerrequisitos duros antes de evaluar G1
1. **Sesión 3 (CI)** verde y con gate de código Kimi ≥ 9.0 (cierra A5/A6). ← en curso (PR #6).
2. **Checklist §9 (bloque C)** con evidencias — operacional del CEO (S0B-03).

Cuando A5/A6 estén verdes y el bloque C tenga evidencia, se genera el paquete de auditoría G1
(`auditorias/G1-I/`) para el veredicto final de Kimi del Sprint 0.
