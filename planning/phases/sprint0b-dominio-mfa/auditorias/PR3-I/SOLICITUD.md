# SOLICITUD DE AUDITORÍA — sprint0b-dominio-mfa · PR3-I (código)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-19
**Base:** rama `sprint0b-pr3-cabeceras` · **Commit:** `40e760f`
**Docs contrato:** Spec §8.3 · DoD #12 · PLAN §PR-3 · Kimi B-01 (SPA) del I-PLAN
**Nivel:** PR (código). Diff + tests en `EVIDENCIA.md`.

## Qué hace PR-3 (cabeceras de seguridad — DoD #12)
- **`app/security.py`**: `SecurityHeadersMiddleware` (ASGI puro) fija en **TODA** respuesta
  (incluye errores 4xx/5xx, verificado con test en 404):
  - **CSP estricta**: `default-src 'none'; frame-ancestors 'none'; base-uri 'none'` — **sin
    `unsafe-inline` ni `unsafe-eval`** (la API sirve JSON, no HTML → `'none'` es correcto).
  - **HSTS** (`max-age=31536000; includeSubDomains; preload`) **solo fuera de dev** (en http
    local sería inútil y podría pinnear localhost).
  - `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`.
- **`frontend/vercel.json`** (Kimi B-01): las mismas cabeceras en la SPA; CSP `'self'` sin
  `unsafe-inline` (Vite prod emite JS/CSS externos; se tunea con hash/nonce si hiciera falta).
- **Test CI** (`tests/test_security_headers.py`, 5): presencia, CSP sin unsafe-inline,
  HSTS ausente en dev / presente fuera de dev, cabeceras también en 404.

## Puntos a auditar con lupa
1. **CSP realmente estricta**: ¿`default-src 'none'` + `frame-ancestors 'none'` es correcto
   para una API JSON? ¿sin `unsafe-inline/eval`?
2. **Cabeceras en respuestas de error**: el middleware ASGI las pone en `http.response.start`
   → cubre 404/500 (no solo 200). ¿Sólido?
3. **HSTS gating por entorno**: ¿bien no fijarlo en dev? ¿el valor (1 año + includeSubDomains
   + preload) es correcto para prod tras Cloudflare?
4. **Paridad SPA (B-01)**: ¿`vercel.json` cubre lo mismo? ¿la CSP de la SPA es defendible?

## Decisiones declaradas
- **F-1** El middleware NO pisa cabeceras ya presentes (respeta las que ponga la app/CORS).
- **F-2** CSP de la SPA permite `connect-src` al API (`api.compas.roddos.com`) y `img-src data:`;
  todo lo demás `'self'`/`'none'`. Sin `unsafe-inline`; si el build lo exigiera, se usará
  hash/nonce (no se relajará a unsafe-inline).
- **F-3** El test CI del DoD #12 es del lado API (pytest). La verificación de la SPA en vivo
  (que Vercel sirve las cabeceras) queda para el e2e/deploy check.

## Evidencia (en EVIDENCIA.md)
Código de `security.py` + `vercel.json` + diff de `main.py`, y salida de `pytest`
(**171 passed, 9 skipped** @requires_real_mongo) + ruff limpio.

## Pregunta al auditor
¿Las cabeceras de seguridad (API + SPA) son correctas y cierran el DoD #12 para GO, dejando
Sprint 0b listo para el Gate G1?
