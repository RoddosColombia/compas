# RESPUESTA KIMI — sprint0b · PR3-I

**Certificado I-PR3 · Sprint 0b: cabeceras de seguridad (DoD #12)**
**9.2 / 10 — GO** (merge autorizado con 2 ajustes menores) · 2026-07-19 · `40e760f`

4/4 puntos de lupa verificados. **DoD #12: CUMPLIDO** (CSP estricta, HSTS, nosniff,
Referrer-Policy, frame-ancestors 'none', X-Frame-Options DENY + test CI).

## Ajustes aplicados en el mismo pase (Kimi los pidió sin re-auditoría)
- **B-1 — orden de middleware:** Security ahora se añade DESPUÉS de CORS → es la capa MÁS
  EXTERNA y cubre también las respuestas de CORS (preflight OPTIONS, rechazos). **Test nuevo**
  `test_cabeceras_en_preflight_cors`.
- **B-2 — `style-src` de la SPA:** cambiado a `'self' 'unsafe-inline'`. Radix/floating-ui
  (popovers/dropdowns) y Recharts inyectan **atributos** `style` inline, y el hash/nonce NO
  aplica a atributos style. El vector real de XSS queda cerrado por `script-src 'self'`.
  Decisión documentada; verificar en el Vercel preview y relajar SOLO `style-src` si algo se
  rompe (nunca `script-src`).

## Notas menores (checklist de deploy)
- HSTS en Cloudflare + origen puede duplicarse (benigno). `includeSubDomains` en
  `compas.roddos.com` es seguro; cuidado si se prelodea el apex `roddos.com`.
- Añadido al checklist: `curl -I https://compas.roddos.com` y
  `curl -I https://api.compas.roddos.com/health` como evidencia de cabeceras vivas.

**Declaración:** PR-3 cierra DoD #12. GO. **Sprint 0b completo** (PR-1 ✓ PR-2 ✓ PR-3 ✓).
Siguiente y último: **Gate G1** (A-01 resuelto por CR-003; prerrequisitos: Sesión 3 CI + §9).
