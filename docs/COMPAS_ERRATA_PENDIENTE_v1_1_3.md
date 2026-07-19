# Errata documental pendiente → baseline v1.1.3 (CR-002 — PROPUESTA, pendiente firma CEO)

**Origen:** auditorías Kimi de la Sesión 2 — I-PLAN (A-01, A-06, M-03) + R-PLAN (H3: 5 drift extra).
**Naturaleza:** reconciliación documental. **No cambia decisiones, mecanismos, costos ni criterios** —
alinea los `.docx` certificados v1.1.2 con lo ya decidido en CR-001, CLAUDE.md, el tracker y el RUNBOOK,
y precisa lo que la Sesión 2 construye.
**Registro:** CR-002 en el tracker (hoja CRs), estado Borrador hasta la firma. **No se regeneran los
`.docx` ni se firma el re-baseline ahora**; se foldea en el próximo re-baseline natural (v1.1.3 / v1.2,
como ya previó CR-001 §metadata). Mientras tanto, este documento + CR-001 son normativos.

## E-1 — Catálogo de auditoría: 29 → 30 (ya normativo)
Spec §1.11, DoD #6, PRD §5, INFO-000 dicen "29"; deben decir **"30"**. Autoridad: CR-001 §2.1
(exhibido en `docs/cambios/CR-001.md`), CLAUDE.md regla 11, hoja DoD #6 del tracker. `extracto.cargado`
(extracto mensual, `POST /extractos`, S4) es **distinto** de `carga.completada` (carga diaria M7).

## E-2 — Cookie de refresh: `Path=/auth` → `Path=/api/v1/auth`  (Spec §4 **y** STACK §3 — H3-1)
Endpoints `POST /api/v1/auth/*`; con `Path=/auth` el navegador nunca envía la cookie a
`/api/v1/auth/refresh` (RFC 6265 §5.1.4) → refresh roto al 100%. Valor correcto:
`Path=/api/v1/auth` (+ `HttpOnly; Secure; SameSite=Strict; Max-Age=2592000`). **El mismo path viejo
está en dos lugares:** Spec §4 y STACK §3.

## E-3 — Dominio del API: `api.compas.roddos.com` + verificación de Origin
RUNBOOK §5 **ya** lo define. Se confirma como requisito de la cookie same-site (eTLD+1 con
`compas.roddos.com`; con `*.onrender.com` `SameSite=Strict` no viajaría). Añadir explícito: CORS
`Allow-Origin: https://compas.roddos.com` + `Allow-Credentials: true`; verificación de `Origin` en mutaciones.

## E-4 — Convención de tiempo para persistencia (precisa regla 2 / Spec §1.1 — H3-4)
Persistencia / TTL de Mongo / claims JWT: **UTC aware**; `now_bogota()` (aware) solo para presentación.
Un `datetime` naive Bogotá se lee como UTC (−5 h) en Mongo/PyMongo/PyJWT → TTL y `exp` desfasados
(un `exp` naive-Bogotá queda ~5 h **en el pasado**: el access nacería muerto). No contradice la zona
única Bogotá para dominio/UI; precisa la capa de almacenamiento. Precisa el literal "now_bogota() en
toda marca temporal" de Spec §1.1.

## E-5 — Colección `refresh_sessions` ausente del contrato (H3-2)
No existe en Spec §2.3 ni STACK §4.2 (colecciones/índices). Añadir: `refresh_sessions
{jti único, usuario_id, family_id, family_created_at, ultimo_uso, rotado, revocado}`, índice
`(family_id)`, TTL `family_created_at + 30 d`. Necesaria para "idle 12 h / máx 30 d" (imposible con
JWT stateless puro) y para la detección de reuso.

## E-6 — TTL de `jwt_denylist` por tipo de token (precisa Spec §2.3 — H3-3)
Spec §2.3 dice "TTL 30 días" plano. Precisar: **por tipo** (access 15 min / refresh 30 d), con
mecanismo `expires_at` (UTC-aware) + índice `expireAfterSeconds: 0`.

## E-7 — Nuevo secreto `MONGODB_URI_AUDIT` (H2 / H3-5)
La inmutabilidad del audit usa una **segunda cadena de conexión a la MISMA database `compas`** con
usuario exclusivo (`audit_writer`). Añadir `MONGODB_URI_AUDIT` por entorno a STACK §5.1 (Render/Actions).
**No** es database separada (evita sacar `audit_log` del dump/restore/archivado).

## E-8 — Rotación de refresh: reuso estricto sin replay de leeway (desviación PR-2, Kimi L7)
El PLAN v2/v3 especificaba un **replay de 10 s** dentro del leeway para que un doble-submit
legítimo (2 pestañas) no revocara la familia. **PR-2 implementa reuso ESTRICTO** (fail-closed:
el doble-submit revoca la familia → re-login), sin replay server-side. Es seguro para Fase 0–1
(degrada UX, no seguridad); mitigado por el single-flight del SPA. El test de concurrencia ya
codifica el criterio estricto. **Compromiso:** implementar el replay server-side en **Sprint 0b/1**.

## E-9 — Catálogo de auditoría: 30 → 32 · eventos de ciclo de vida de MFA (Kimi M3, PR-2)
Habilitar y resetear MFA son **eventos de seguridad forense** y hoy son invisibles (el catálogo
cerrado de 30 se respetó — regla 11 — pero queda el hueco). Añadir **`mfa.habilitado`** (tras
`/auth/mfa/activate`) y **`mfa.reset`** (tras `/auth/mfa/reset` y el reset admin futuro) →
catálogo **32**. Mientras no se firme: el mapeo actual (`user.login` solo tras el 2º factor;
`user.login_fallido{factor:'mfa'}`) es aceptable (Kimi lo acepta como puente). Al firmar: agregar
los 2 a `AuditEvento`/`CATALOGO_EVENTOS`, emitirlos en `service.mfa_activate`/`mfa_reset`, y
actualizar Spec §1.11 / DoD #6 / regla 11 (30 → 32).

---
**Firma CEO:** ☐ Aprobada — se folda en v1.1.3 en el próximo re-baseline.  Fecha: ________
