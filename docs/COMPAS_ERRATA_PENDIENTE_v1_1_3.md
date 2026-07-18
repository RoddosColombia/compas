# Errata documental pendiente → baseline v1.1.3 (PROPUESTA — pendiente firma CEO)

**Origen:** auditoría Kimi I-PLAN de la Sesión 2 (7.8/10), hallazgos A-01, A-06, M-03.
**Naturaleza:** reconciliación documental. **No cambia decisiones, mecanismos, costos ni criterios** —
alinea los `.docx` certificados v1.1.2 con lo ya decidido en CR-001, CLAUDE.md, el tracker y el RUNBOOK.
**Registro:** CR-002 en el tracker (hoja CRs), estado Borrador hasta la firma.

> Regla del proyecto: "cambio = nueva versión con impacto explícito" y "declarar ANTES de construir".
> Esta errata se declara aquí; se folda en los `.docx` en el próximo re-baseline natural (v1.1.3 / v1.2,
> como ya previó CR-001 §metadata). Mientras tanto, este documento + CR-001 son normativos.

## E-1 — Catálogo de auditoría: 29 → 30 (ya normativo)
- **Dónde:** Spec §1.11, DoD #6, PRD §5, INFO-000 dicen "29"; deben decir **"30"**.
- **Autoridad ya existente:** CR-001 §2.1 ("catálogo pasa de 29 a 30"), CLAUDE.md regla 11, hoja DoD #6 del tracker — todos dicen 30.
- **Aclaración:** `extracto.cargado` (carga de extracto mensual oficial de ExtractoMensual, CR-001) es **distinto** de `carga.completada` (carga diaria de movimientos, M7). Sujetos distintos → 30, no sustitución.
- **Impacto:** ninguno de decisión; el test de completitud del catálogo (DoD #6) valida 30.

## E-2 — Cookie de refresh: `Path=/auth` → `Path=/api/v1/auth`
- **Dónde:** Spec §4 ("refresh en cookie … path /auth").
- **Motivo (RFC 6265 §5.1.4):** los endpoints son `POST /api/v1/auth/*`; con `Path=/auth` el navegador **nunca** envía la cookie a `/api/v1/auth/refresh` → flujo de refresh roto al 100%.
- **Valor correcto:** `Path=/api/v1/auth` (+ `HttpOnly; Secure; SameSite=Strict; Max-Age=2592000`).
- **Impacto:** corrige un defecto que, de construirse literal, rompería la sesión.

## E-3 — Dominio del API: confirmar `api.compas.roddos.com` + verificación de Origin
- **Dónde:** RUNBOOK §5 **ya** define `api.compas.roddos.com → Render`. Se confirma como requisito de la cookie same-site (eTLD+1 con `compas.roddos.com`; con `*.onrender.com` sería cross-site y `SameSite=Strict` no viajaría).
- **Añadir explícito:** CORS `Allow-Origin: https://compas.roddos.com` exacto + `Allow-Credentials: true`; verificación de `Origin` en mutaciones (mandato del Spec §4).
- **Impacto:** ninguno nuevo (ya estaba en RUNBOOK); se hace explícito en el contrato de auth.

## E-4 — Convención de tiempo para persistencia (aclaración de la regla 2)
- Persistencia / TTL de Mongo / claims JWT: **UTC aware**. `now_bogota()` (aware) solo para presentación.
- **Motivo:** un `datetime` naive Bogotá se interpreta como UTC (−5 h) en Mongo/PyMongo/PyJWT → TTL y `exp` desfasados. No contradice la regla 2 (zona única Bogotá para el dominio/UI); la precisa para la capa de almacenamiento.

---
**Firma CEO:** ☐ Aprobada — se folda en v1.1.3 en el próximo re-baseline.  Fecha: ________
