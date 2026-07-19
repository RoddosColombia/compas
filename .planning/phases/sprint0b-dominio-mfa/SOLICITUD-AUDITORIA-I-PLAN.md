# SOLICITUD DE AUDITORÍA — sprint0b-dominio-mfa · I-PLAN

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-19
**Plan padre:** `.planning/phases/sprint0b-dominio-mfa/PLAN.md`
**Docs:** Spec §1.2/§1.3/§1.10/§1.11/§8.1/§8.3 · PLAN §3 · DoD #6/#11/#12 · RUNBOOK §9 (G1)
**Base:** `main` con Sesión 2 mergeada (audit+auth+RBAC, 3/3 GO) · **Nivel:** PLAN (pre-código).

## Qué se propone (Sprint 0b, 3 PRs + Gate G1)
1. **PR-1 dominio base:** Rubro (semilla 5 grupos + 'Por clasificar'/'Ajuste de conciliación' de sistema; migración idempotente), MesControl (mes único, estados, saldos, inmutabilidad de cerrados), Configuracion (+ semilla CALENDARIO_DIAN, umbrales). init_beanie cableado. Dinero=Decimal.
2. **PR-2 MFA/HIBP:** TOTP obligatorio admin/directivo + códigos de respaldo + step-up (reabrir/config/saldo inicial) + HIBP k-anonymity. Cierra DoD #11.
3. **PR-3 cabeceras:** CSP estricta/HSTS/nosniff/Referrer-Policy/frame-ancestors + test CI. Cierra DoD #12.
4. **Gate G1 (bloqueante):** checklist de seguridad.

## Puntos a auditar con lupa (los que anunciaste)
1. **MFA/step-up:** ¿el diseño de TOTP + códigos de respaldo + step-up (MFA reciente para reabrir/config/saldo inicial) es correcto? ¿Break-glass?
2. **Semilla de rubros:** ¿los 5 grupos + los 2 de sistema (inmutables) coinciden con §1.2 y el Excel (PRD M1)? ¿migración idempotente?
3. **Checklist G1:** ¿qué exige exactamente, y cómo tratamos "aprobador ≠ ejecutor" dado que **solo Andrés revisa** (Iván no)? Propongo que el gate adversarial Kimi + Andrés cubran la revisión; ¿aceptable o exige otro mecanismo?
4. **Dinero=Decimal end-to-end** en MesControl (saldos) y Configuracion (umbrales monetarios).
5. **init_beanie ahora sí:** registrar Documents sin romper la escritura de audit por conexión dedicada.

## Micro-ítems de arrastre (Sesión 2) — exhibidos (Kimi los cerrará al verlos)
- **B-1** cookie en el scrubber Sentry → `app/main.py` (commit `c34f9c9`) + `tests/test_sentry_scrub.py`.
- **P-1** `tz_aware=True` → `app/db/mongo.py:27`.
- **P-2** tests de validadores de audit → `tests/test_audit_models.py` (commit `5d5ae41`).

## Evidencia
- Sin código aún (auditoría de plan). Sesión 2 en `main`, 80 tests verdes, ruff limpio.

## Pregunta al auditor
¿El desglose PR-1/2/3 + Gate G1 y el tratamiento de la segregación de revisión (solo Andrés) son correctos para arrancar, o hay un riesgo a resolver en el PLAN antes de construir?
