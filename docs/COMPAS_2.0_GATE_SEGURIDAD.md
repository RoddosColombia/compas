# G-SEC · Gate de seguridad bloqueante antes de liberar (COMPAS 2.0)

> **Qué es:** el ÚNICO gate de los 6 que **no es un job de CI** — es una
> segunda revisión de seguridad **externa al equipo** que se cumple ANTES
> de liberar. Los otros 5 (G-GM · G-SEMGREP · G-TRIVY · G-PIXEL · G-AXE)
> corren automáticos en cada PR; G-SEC corre una sola vez, contra el
> release-candidate.
>
> **Alcance:** el sistema completo desde la última liberación. No es un
> code review de un PR: es una auditoría de superficie (auth, RBAC, CSRF,
> secretos, endpoints públicos, dependencias, IaC de Render).
>
> **Gate del CEO:** el release no sale a producción hasta que G-SEC
> firme. Sin firma = no despliegue.

## 1 · Cuándo se activa

- **Antes de cada liberación** que toque:
  - `backend/app/auth/` (login, tokens, cookies, refresh)
  - `backend/app/audit/` (catálogo de eventos, escritura fail-closed)
  - `backend/app/cargas/` (parsers bancarios, hash/dedup)
  - RBAC o `require_permission` (permisos nuevos)
  - Rutas `/api/v1/*` públicas (sin `require_permission`)
  - `render.yaml`, `.gitleaks.toml`, `docs/INVENTARIO-SECRETOS.xlsx`
- **Antes del go-live** de COMPAS 2.0 — obligatorio, no negociable.
- **Cuando el CEO decida** por incidente o cambio de perímetro.

## 2 · Quién lo firma

**Revisor externo al equipo de desarrollo** — no es Claude, no es el CEO
(que también desarrolla). El revisor puede ser:

- **Kimi** (auditor arquitectónico) en modo "gate de seguridad" — cuando
  esté disponible.
- **Fabián** (contador · perímetro contable/DIAN) — para el subset de
  reglas DIAN, no para todo G-SEC.
- **Auditor externo contratado** — la vía por defecto cuando Kimi
  ausente y el release exige G-SEC.

**Regla actual (2026-08-30):** Kimi ausente ~semanas ⇒ **G-SEC queda
diferido hasta que Kimi vuelva** o el CEO contrate un revisor externo
para el go-live. Todo merge crítico hasta entonces va con gate-waiver
GO CEO + auditoría Kimi retroactiva pendiente.

## 3 · Qué revisa (checklist)

**Auth**
- [ ] `access_token` en memoria (nunca localStorage) — regla del stack.
- [ ] `refresh_token` en cookie `HttpOnly` + `SameSite=Strict`.
- [ ] Cookie `Secure` en producción (verificar `COOKIE_SECURE=True` en Render).
- [ ] `JWT_SECRET` de al menos 40 chars, rotable, no en repo.
- [ ] Password hash con `argon2id` o `bcrypt >= 12` rounds.
- [ ] `verify_origin` cubre TODOS los POST/PUT/PATCH/DELETE sensibles.

**RBAC**
- [ ] Cada ruta declara `Depends(require_permission("<cap>"))` — G-SEMGREP
      ya lo enforcea automáticamente, G-SEC verifica que la capacidad
      coincida con la matriz del Spec §4.1.
- [ ] Rutas de auth (login/refresh/logout) NO requieren autenticación
      (documentado en `paths.exclude` de `.semgrep.yml`).
- [ ] `require_role` NO se usa (regla H-1: solo por capacidad,
      `require_permission`).

**Audit log**
- [ ] `audit_log` NUNCA se actualiza ni borra (regla 4 · G-SEMGREP lo
      enforcea).
- [ ] Catálogo cerrado: `AuditEvento` no crece sin CR aprobada (regla 11).
- [ ] Emit fail-closed: si el emit falla, la mutación se compensa (saga O1).

**Secretos**
- [ ] `gitleaks` en CI (ya corre).
- [ ] `INVENTARIO-SECRETOS.xlsx` allowlist en gitleaks (repo privado, no
      pública, decisión CEO 2026-07-20).
- [ ] Ningún token/API-key en el historial de git no allowlisted.
- [ ] Rotación de `JWT_SECRET` documentada en `docs/RUNBOOK-INFRA.md`.

**Dependencias**
- [ ] `pip-audit` verde (ya corre en CI).
- [ ] `G-TRIVY` verde para npm + pip + IaC (ya corre en CI).
- [ ] Ninguna dependencia con CVE HIGH/CRITICAL sin fix.

**Perímetro público**
- [ ] `verify_origin` en TODOS los POST/PUT/PATCH/DELETE sensibles.
- [ ] CORS: sólo el frontend de COMPAS en la lista.
- [ ] Rate-limit en `/api/v1/auth/login` (contra brute-force).
- [ ] IaC de Render: `RUN_SCHEDULER=false` en el servicio web (regla 6);
      jobs solo en `compas-jobs`.

**Repo público hoy**
- [ ] Antes del go-live: **privatizar repo + rotar credenciales** (parte
      de G-SEC — memoria `kimi-auditoria-plan-maestro`).

## 4 · Salida esperada

Un archivo firmado en `planning/phases/gates/G-SEC/RESPUESTA.md` con:

- Fecha, revisor, alcance.
- Cada ítem del §3: ✅ o hallazgo.
- Nota ≥ 9.0 (mismo umbral que auditorías Kimi de PR crítico).
- GO / NO-GO.

Sin RESPUESTA.md firmado ≥ 9.0 = no despliegue de producción.
