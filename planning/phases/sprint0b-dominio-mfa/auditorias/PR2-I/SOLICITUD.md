# SOLICITUD DE AUDITORÍA — sprint0b-dominio-mfa · PR2-I (código)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-19
**Base:** `main` + rama `sprint0b-pr2-mfa` · **Commits:** `29bf705` (núcleo) + `d6b96c3` (flujos) + `385682a` (infra)
**Plan padre:** `planning/phases/sprint0b-dominio-mfa/PLAN.md` §PR-2 (diseño **M-01**, 6 puntos)
**Docs contrato:** Spec §8.1 · §2.4 (step-up) · DoD #11 · reglas 1/2/3/11 de CLAUDE.md
**Nivel:** PR (código). Evidencia con diff + tests en `EVIDENCIA.md`.

## Qué hace PR-2 (MFA TOTP + step-up + HIBP — DoD #11)
1. **Núcleo cripto** (`app/auth/mfa.py`): TOTP (pyotp, ventana ±1), cifrado del
   `mfa_secret` en reposo (Fernet), códigos de respaldo bcrypt de **un solo uso**.
2. **Login en 2 pasos**: contraseña OK + `mfa_habilitado` → `MfaChallenge` (token efímero,
   `type=mfa_challenge`, TTL 5 min); NO se crea sesión ni se emite `user.login` aún.
3. **`/auth/mfa/verify`**: canjea challenge + código (TOTP **o** respaldo) por el par de
   tokens con claim **`mfa_at`**; **throttle por cuenta+IP** (mismo TTL que el rate-limit
   de login); emite `user.login`.
4. **Step-up** (`require_step_up`): exige `mfa_at` dentro de `mfa_stepup_window_min` (5 min);
   para `/auth/mfa/reset` y (futuro) reabrir/config/saldo inicial (Spec §2.4).
5. **Enrolamiento**: `/auth/mfa/setup` (re-auth de contraseña → secreto cifrado, sin activar)
   → `/auth/mfa/activate` (verifica TOTP → habilita + entrega respaldos una vez).
6. **Reset**: `/auth/mfa/reset` (self con step-up) → borra secreto/códigos + **bump
   `token_version`** (revoca sesiones).
7. **HIBP k-anonymity** (`password_acceptable`): longitud + no estar en HIBP (solo el
   prefijo de 5 hex del SHA-1 sale; fail-open si HIBP cae).
8. **Infra**: `MFA_ENC_KEY` fail-fast fuera de dev + en `render.yaml`; break-glass en RUNBOOK.

## Puntos a auditar con lupa (los que anunciaste para PR-2)
1. **Enrolamiento**: ¿el setup protegido por contraseña + activate con TOTP es correcto?
   ¿el secreto queda cifrado y `mfa_habilitado` solo tras activate?
2. **Semántica de step-up**: claim `mfa_at` + ventana. ¿Sólida? ¿el reset lo exige bien?
3. **Respaldo hasheado**: bcrypt + un-solo-uso (consumir elimina). ¿Correcto?
4. **Throttling en `/verify`**: cuenta+IP con TTL. ¿Suficiente contra fuerza bruta de 6 díg.?
5. **Protección del `mfa_secret`**: Fernet en reposo; fail-fast de `MFA_ENC_KEY`. ¿Bien?
6. **Reset con bump de `token_version`**: ¿revoca de verdad las sesiones?

## Decisiones que declaro (autoauditoría)
- **E-1 Login 2 pasos con challenge JWT** (`type=mfa_challenge`, TTL 5 min) en vez de estado
  en servidor. Sin acceso hasta `/verify`. ¿Aceptable?
- **E-2 NO se inventaron eventos de auditoría** para enrolamiento/reset (catálogo cerrado de
  30, regla 11). Solo `user.login`/`user.login_fallido` existentes. ¿Correcto, o falta un CR?
- **E-3 HIBP fail-open** si la API no responde (advisory): no bloquea al usuario por caída de
  un tercero, con log. ¿De acuerdo?
- **E-4 Reset admin-sobre-otro** diferido al módulo `/users` (futuro); hoy solo self con
  step-up (+ `repository.clear_mfa` por script para break-glass). Señalado en RUNBOOK.
- **E-5 Gap pre-existente (no de PR-2):** `MONGODB_URI_AUDIT` falta en `render.yaml` → C-01
  fail-fast en staging/prod. Señalado en RUNBOOK; provisionar con `MFA_ENC_KEY`.

## Evidencia (en EVIDENCIA.md)
Código fuente de `mfa.py` + diffs de tokens/models/repository/service/deps/router/passwords/
main/config/render/RUNBOOK, y salida de pytest (**164 passed, 9 skipped** @requires_real_mongo)
+ ruff limpio + protocolo de commit (0/0/0).

## Pregunta al auditor
¿MFA (TOTP + step-up + respaldo + HIBP + cifrado en reposo + reset) es correcto y fiel a
§8.1/M-01 para GO, o hay un riesgo a resolver antes de mergear?
