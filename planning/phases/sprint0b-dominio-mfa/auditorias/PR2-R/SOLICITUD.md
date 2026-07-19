# SOLICITUD DE AUDITORÍA — sprint0b-dominio-mfa · PR2-R (re-auditoría)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-19
**Base:** rama `sprint0b-pr2-mfa` · **Fix commit:** `f625f65` (sobre I-PR2 `385682a`)
**Ronda previa:** I-PR2 = **8.8 NO-GO** (3 Medias + 4 Bajas). **Estimación tras fixes: ≥ 9.4.**
**Nivel:** PR (re-auditoría). Diff de los fixes + tests en `EVIDENCIA.md`.

## Qué cambió respecto de I-PR2 (solo los hallazgos)
### Medias (bloqueaban el merge) — TODAS resueltas
- **M1 — challenge de un solo uso.** `service.mfa_verify` ahora: (a) rechaza el canje si el
  jti del challenge ya está en `jwt_denylist` (replay → 401); (b) tras un canje exitoso,
  **denylista el jti** hasta su exp natural. Reutiliza la infraestructura `jwt_denylist`+TTL
  ya existente. **Test nuevo** `test_challenge_no_reutilizable`: 2º canje del mismo challenge
  falla y solo se acuña **una** familia de sesión.
- **M2 — `MONGODB_URI_AUDIT` en `render.yaml`.** Añadido (`sync:false`) a `compas-api`,
  `compas-jobs` y `compas-api-stg`. RUNBOOK §8 actualizado (ya NO es gap C-01).
- **M3 — auditoría del ciclo de vida MFA.** CR registrado (**E-9** en
  `docs/COMPAS_ERRATA_PENDIENTE_v1_1_3.md`, batch CR-002): añadir `mfa.habilitado` y
  `mfa.reset` (catálogo 30→32). No se inventaron eventos (regla 11); el mapeo actual
  (`user.login` post-2º-factor, `user.login_fallido{factor:'mfa'}`) es el puente que aceptaste.

### Bajas
- **B1 (aplicada) — re-enrolar exige step-up.** `/auth/mfa/setup` con `mfa_habilitado=True`
  ahora exige `mfa_at` reciente (misma protección que `/reset`, corrige la asimetría).
  **Test nuevo** `test_reenrolar_sin_step_up_403`.
- **B3 (documentada)** — `mfa_at` no se propaga en `/refresh` → step-up = re-verificar 2º
  factor tras 5 min. Decisión de UX anotada en RUNBOOK (mejora futura `/auth/step-up`).
- **B4 (documentada)** — rotación de `MFA_ENC_KEY` invalida secretos → RUNBOOK (re-enrolar).
- B2 (cadena bcrypt ×10) — aceptada como está; mejora futura (lookup O(1)).

## Puntos a verificar (los que condicionaron el NO-GO)
1. **M1:** ¿el challenge es ahora estrictamente de un solo uso (denylist + rechazo de replay)?
2. **M2:** ¿el secreto de audit ya está en `render.yaml` en los 3 servicios?
3. **M3:** ¿el CR E-9 cubre el hueco forense de forma aceptable como puente?
4. **B1:** ¿la simetría setup/reset (step-up) quedó correcta?

## Evidencia (en EVIDENCIA.md)
Diff de `f625f65` (solo los fixes) + tests nuevos + salida de `pytest` (**166 passed, 9
skipped** @requires_real_mongo) + ruff limpio + protocolo 0/0/0.

## Pregunta al auditor
Con M1/M2/M3 + B1 aplicados (y B3/B4 documentadas), ¿PR-2 alcanza el umbral para **GO** y
cierra el DoD #11?
