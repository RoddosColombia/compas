# SOLICITUD DE AUDITORÍA — Gate G1 · G1-R: veredicto final (prerrequisitos cumplidos)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-20
**Ronda previa:** G1-I = mecanismo aprobado 9.1; veredicto NO DISPARAR 8.5 ("GO si nada nuevo aparece") por 2 prerrequisitos: (1) CI verde con gate de código, (2) bloque C con evidencia.
**Estado:** ambos prerrequisitos cumplidos. Se solicita el veredicto final de G1.

## Prerrequisito 1 — CI verde + gate de código: ✅ (desde Sesión 3)
5 jobs verdes (run `29771391813`, `backend-real-mongo` required), Kimi PR-I Sesión 3 **GO 9.5** → A5/A6 cerrados, DoD #8 cumplido.

## Prerrequisito 2 — Bloque C con evidencia: ✅ EJECUTADO 20-jul-2026
Ver G1-CHECKLIST.md adjunto (actualizado con evidencia por ítem). Resumen:
- **C1** readiness: `https://compas-api-von1.onrender.com/api/v1/health/ready` → 200 `{ready, mongo up, beanie ready}`.
- **C3** gate anti-secretos **probado adversarialmente**: PR #20 con credenciales AWS sembradas → gitleaks FAIL (run `29797947548`) → PR bloqueado y cerrado sin merge.
- **C4** cabeceras vivas en el API real (CSP default-src 'none', HSTS preload, nosniff, X-Frame DENY, no-referrer).
- **C6** 4 secretos en Render (fail-fast no saltó → los 4 presentes y válidos).
- **C7** Atlas aprovisionado: `compas` en cluster SISMO-V3; `compas_app` + rol `audit_writer`/`compas_audit` (por **Atlas UI** — hallazgo nuevo: Atlas bloquea `createUser`/`createRole` por driver en TODOS los tiers, corrige la nota H-01; RUNBOOK §2 actualizado); índices auth+forense+dominio + semillas (33 rubros, 3 config) idempotentes; **inmutabilidad verificada EN VIVO**: `compas_audit` no puede insertar fuera de `audit_log` ni hacer update/remove en él.

## Cambios de contexto declarados (decisión CEO 20-jul — auditar)
1. **Entorno único en desarrollo** (principio rector, CLAUDE.md): NO hay `compas_stg` ni prod separada hoy; `compas-api` auto-despliega desde `main`. El endurecimiento (tag `v*` + reviewer CEO + staging) es tarea de **go-live**, documentada, no descartada. → **C2 queda sustituido** hasta go-live.
2. **C5 (S3/CRR) diferido a pre-carga-real**: sin datos reales que respaldar; el guardrail M-04 (tu hallazgo de R-PR1, implementado) **bloquea cargas reales sin S3/preservación**, así que el riesgo de "datos sin backup" no es alcanzable.
3. **S0B-05 resuelto (tu B-1):** rubro de sistema **'Recaudo'** (tipo ingreso) añadido a la semilla (32→33) y sembrado en la base viva. Tests actualizados (semilla, idempotencia, 3 de sistema).

## Contexto adicional desde G1-I
Sprint 1 backend auditado por ti: I-PR1 8.0 NO-GO → fixes → **R-PR1 GO 9.3** (merge `72034a0`). API live con auth+MFA+audit activos.

## Puntos a auditar con lupa
1. ¿Aceptas C2 sustituido y C5 diferido bajo la decisión de entorno único + guardrail M-04? (La alternativa es bloquear G1 hasta S3, que hoy no protege ningún dato real.)
2. C4 se evaluó sobre `onrender.com` (Cloudflare/dominio diferidos): ¿suficiente para G1, re-verificación al cablear dominio?
3. La corrección H-01 (usuarios por UI, no por script): ¿algún control adicional que exijas al flujo manual?

## Evidencia local
- pytest: **212 passed / 23 skipped** (local) · 13 @requires_real_mongo (carga+dedup+transacción, Mongo real) · ruff limpio.
- Verificación en vivo de privilegios de `compas_audit` (salida en RUNBOOK §2 / sesión 20-jul).
- Tracker: S0-06/S0-07 Hecha · S0B-05 Hecha · Sprint 1 (S1-02/S2-01/S2-05) Hecha con GO 9.3.
