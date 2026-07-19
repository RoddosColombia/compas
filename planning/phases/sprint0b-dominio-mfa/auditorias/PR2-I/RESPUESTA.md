# RESPUESTA KIMI — sprint0b · PR2-I

**Auditoría I-PR2 · MFA (TOTP + step-up + HIBP)**
**NO-GO condicionado — 8.8 / 10** (umbral ≥ 9.0) · 2026-07-19 · `29bf705`+`d6b96c3`+`385682a`

Diseño M-01 completo y correcto (6 puntos). No cruza el 9 por 3 Medias + 4 Bajas
(~medio día). Estimación con todo aplicado: **≥ 9.4 → GO**.

## Medias (bloquean el merge) — TODAS APLICADAS en PR2-R
- **M1 — challenge reutilizable:** `mfa_verify` no invalidaba el challenge tras el canje →
  replays acuñaban familias ilimitadas en 5 min. **FIX:** denylist del jti del challenge
  tras el canje + rechazo de replay (usa `jwt_denylist` con TTL = exp). Test de replay.
- **M2 — `MONGODB_URI_AUDIT` ausente de render.yaml:** **FIX:** añadido (sync:false) a
  api, worker y api-stg (RUNBOOK actualizado; ya no es gap).
- **M3 — ciclo de vida MFA sin auditoría:** habilitar/resetear son forenses. **FIX:** CR
  registrado (E-9 en CR-002) para añadir `mfa.habilitado`/`mfa.reset` (catálogo 30→32);
  el mapeo actual es puente aceptable hasta la firma. No se inventaron eventos (regla 11).

## Bajas
- **B1 — re-enrolar sin step-up:** `/mfa/setup` con MFA ya habilitado pisaba el secreto sin
  step-up (asimetría con /reset). **FIX (aplicado):** exige step-up si `mfa_habilitado`. Test.
- B2 — cadena bcrypt ×10 en respaldos: aceptable con throttle; mejora futura (lookup O(1)).
- B3 — `mfa_at` se pierde en el refresh → step-up = re-login tras 5 min. Decisión de UX
  documentada; alternativa futura `/auth/step-up`. → registrado.
- B4 — rotación de `MFA_ENC_KEY` invalida secretos: **documentado en RUNBOOK** (re-enrolar).

## Decisiones declaradas — veredicto de Kimi
E-1 aceptable CON M1 (single-use) ✓ · E-2 correcto (catálogo; hueco vía M3) ✓ ·
E-3 HIBP fail-open aceptado ✓ · E-4 reset admin diferido aceptado ✓ ·
E-5 gap audit "bien detectado, mal diferido → corregido ahora (M2)" ✓.

**Camino al GO:** M1+M2+M3+B1 aplicados → re-presentación PR2-R. Estimación ≥ 9.4.
