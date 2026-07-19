# PLAN v3 — Sprint 0 · Sesión 2: portar auth + RBAC + audit log desde SISMO-V3

**Fase:** `sprint0-auth-rbac-audit` · **Fecha:** 2026-07-18 · **Rev:** v3 (post R-PLAN 9.1 GO condicionado — precisiones H1–H7 aplicadas; v2 tras I-PLAN 7.8)
**Base de rama:** commit `61048ac` (Sesión 1, verde). Si Sesión 1 se mueve → rebase + suite verde antes de cada gate (Kimi Baja-6).
**Rama:** `sprint0/sesion2-auth-rbac-audit` (apilada sobre `sprint0/sesion1-esqueleto`).
**Contrato:** Spec §1.1, §1.11, §2.2.6, §2.4, §4, §4.1, §5 (DoD #1/#6/#11) · CR-001 (catálogo=30) · RUNBOOK §2/§5.
**Fuente a portar:** `../SISMO-V3/backend/app/`: `core/security.py`, `models/user.py`, `models/audit_log.py`, `routers/auth.py`, `schemas/auth.py`, `services/audit/`.

## Objetivo
Portar de SISMO-V3 la estructura de auth JWT, RBAC por dependencia y audit log append-only,
**adaptada al Spec de COMPAS**, y **construir** lo que SISMO no tiene (token_version, estado
server-side de refresh con rotación atómica + detección de reuso). Documentar en
`docs/PORTADO_DE_SISMO.md` (tabla por archivo: portado / adaptado / construido — mitiga bus-factor).

## Porta vs. construye (verificado con grep sobre SISMO, no asumido)
- **Se porta:** patrón `get_current_user` + `require_role`; `AuditLog` model + router/service; hashing bcrypt; estructura de `routers/auth.py`.
- **Se construye (NO existe en SISMO):** `token_version` + su validación por request y en refresh; colección `refresh_sessions` (familia); rotación atómica con detección de reuso; `jwt_denylist`; `require_permission` + config único ≡ matriz §4.1; roles COMPAS `admin|directivo|financiero|consulta`.

---

## Convenciones de la fase (correcciones Kimi A-04, Q6)

### Tiempo (A-04 — crítico)
- **Persistencia, TTL de Mongo y claims JWT (`exp`, `iat`): SIEMPRE UTC aware** (`datetime.now(timezone.utc)`). Mongo TTL usa reloj UTC del servidor; PyMongo interpreta *naive* como UTC; PyJWT convierte `exp` como UTC. **Corrección de sentido (Kimi H7-4):** un `exp` *naive*-Bogotá leído como UTC queda ~5 h **en el pasado** → el access **nace muerto** (exp ya vencido al emitirse), y los TTL quedan desfasados. En ambos sentidos la convención UTC-aware es la correcta.
- `now_bogota()` (aware, ZoneInfo) **solo para presentación** (Spec §0.2).
- **Prohibido `datetime` naive** en el backend → guardián de lint en CI (Sesión 3).

### Frontera mongomock / Mongo real (Q6)
Van **contra Mongo real** con `@requires_real_mongo` (y el marker **FALLA, no skip**, si no hay mongod con auth): índices únicos parciales, TTL, permisos de BD, transacciones multi-documento, agregaciones, montos Decimal128 y **tests de concurrencia** (doble submit del mismo refresh).

### Cripto del port (Kimi Bajas 3/4)
`algorithms=['HS256']` explícito en `decode`; `leeway=30s`; `jti` uuid4 (≥128 bits) en access **y** refresh; `JWT_SECRET` ≥32 bytes por entorno con plan de rotación; bcrypt `rounds=12` + test de latencia < 1 s (la política "12/10 chars" es longitud, no costo).

---

## Desglose en PRs (REORDENADO por A-05; cada PR = gate Kimi ≥ 9.0)

### PR-1 — Audit base (antes que auth, para que el login pueda emitir eventos)
- `AuditLog` (Beanie, **append-only**), **catálogo cerrado de 30 eventos** como enum (§1.11: 29 + `extracto.cargado` de CR-001 — normativo; ver §Errata). `emit_audit(evento, entidad, entidad_id, actor_id, metadata)`.
  - **`extracto.cargado` — flujo dueño (Kimi H5):** evento reservado por CR-001 para la carga de extracto mensual oficial (entidad `ExtractoMensual`); **emisor: `POST /extractos`, Sprint 4** (CR-001 §2.3). No es huérfano: se declara en el enum ahora y su emisor llega en S4.
- **Inmutabilidad por privilegios de servidor (M-06, Q4, H2):** **`compas_audit` = una SEGUNDA cadena de conexión (`MONGODB_URI_AUDIT`) a la MISMA database `compas`**, con usuario exclusivo (rol `audit_writer` = insert+find sobre `audit_log`, **sin update/remove**). **NO es database separada** (evitarlo: dejaría `audit_log` fuera del dump nocturno, del restore DoD-10 y del archivado — pérdida forense). El **usuario general de la app NO tiene update/remove** sobre `audit_log`. `MONGODB_URI_AUDIT` se añade a STACK §5.1 vía CR-002 y al script idempotente. `$jsonSchema` como defensa en profundidad (Spec §2.2.6): valida forma pero **no sustituye** privilegios.
- Script idempotente de creación de rol/usuario en el repo (local + CI); documentado en RUNBOOK §2.
- **Tests (@requires_real_mongo, mongod con auth):** negativo (update/remove → error 13) **y positivo** (insert/find como `compas_audit` funcionan — sin él, un rol roto sin insert pasaría el negativo y el audit moriría en silencio).
- Residual declarado: el admin de Atlas siempre puede alterar la colección (mitigar: least-privilege + Activity Feed + backups).

### PR-2 — Núcleo de auth (JWT endurecido, emite eventos desde el primer commit)
- `User` (Beanie): `email` único **normalizado** (`strip().lower()`), `password_hash` (bcrypt rounds=12), `rol`, `token_version` (default 1), `activo`, timestamps UTC-aware.
- **Login:** respuesta **uniforme** (mensaje/timing/lockout sin oráculo; bcrypt dummy si el email no existe → anti-enumeración, M-04). Emite `user.login` / `user.login_fallido` / `user.bloqueado` vía `emit_audit` (de PR-1).
- **Rate limit doble (M-05):** por **IP** (del baseline, ausente del PLAN v1) **+ por cuenta** (backoff 5 fallos → 15 min); reset en login exitoso; flujo de desbloqueo por admin/break-glass; evento `user.bloqueado` + alerta. Evita el DoS selectivo contra el CEO.
- **JWT:** access 15 min (memoria SPA) + refresh en cookie. **`token_version` validado en cada request Y en `/auth/refresh`** (M-01/Q2): un usuario desactivado NO renueva access. Bump de `token_version` **atómico** con desactivar/cambiar contraseña/re-activar (una sola operación). No cachear el usuario en el camino de auth (5–10 usuarios → lectura por request viable).
- **Cookie (A-01/M-03):** `Set-Cookie: refresh=<jwt>; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth; Max-Age=2592000` + test de integración del Set-Cookie. API en **`api.compas.roddos.com`** (same-site por eTLD+1 con `compas.roddos.com`; con `*.onrender.com` la cookie nunca viaja). CORS `Allow-Origin: https://compas.roddos.com` exacto + `Allow-Credentials: true`; `fetch(credentials:'include')`; **verificación de Origin en mutaciones** (Spec §4).
- **Estado server-side del refresh — colección `refresh_sessions` (A-03):** `{jti único, usuario_id, family_id, family_created_at, ultimo_uso, rotado, revocado}`, TTL en `family_created_at + 30 d`. En `/auth/refresh` validar: `exp`, `ultimo_uso + 12h` (idle), `family_created_at + 30d` (máx), `token_version`, `activo`. **Índices/invariantes (Kimi H7-1/2):** índice `(family_id)` (la revocación hace `update_many` por ese campo); `family_created_at` es **inmutable** y **se hereda** en cada rotación (el TTL de la familia depende de ello).
- **Rotación atómica + detección de reuso (A-02, reformulado H4):** `findOneAndUpdate({jti, rotado:false} → {rotado:true})`; el **ganador** rota (emite un único par de tokens nuevo); el **perdedor** concurrente recibe, **dentro del leeway de 10 s**, el *replay* de la respuesta original (200) — single-flight en la SPA lo hace raro. **Fuera del leeway**, un `jti` ya rotado ⇒ **reuso** ⇒ `update_many({family_id},{revocado:true})` + `user.bloqueado` `metadata={motivo:'reuso_refresh'}` (Baja-1, sin inventar evento). **Tests TDD (@requires_real_mongo):** (a) dos refresh simultáneos → **exactamente una rotación** (un solo par nuevo); el perdedor obtiene el replay 200 dentro del leeway; (b) reuso **fuera** del leeway → familia revocada + `user.bloqueado`.
- **Logout (M-02, H6):** deniega el `jti` del refresh **y** del access (TTL ≤ 15 min en denylist); `get_current_user` consulta la denylist. Para operar con access expirado, se decodifica con firma válida y `options={'verify_exp': False}` **solo** para extraer `jti`/`exp` y denegarlo hasta su expiración natural (un implementador literal, sin esto, rechazaría el logout con 401).
- **`jwt_denylist`:** índice `(jti)` único + **TTL por tipo de token** (access 15 min / refresh 30 d — M-11). **Mecanismo (H7-3):** campo `expires_at` (UTC-aware) + índice `expireAfterSeconds: 0` sobre él (no un TTL plano de 30 d).

### PR-3 — RBAC por dependencia (matriz §4.1 como fuente única)
- `Role(StrEnum)`: `admin | directivo | financiero | consulta`.
- `get_current_user` (valida token_version, activo, denylist), `require_permission("<cap>")`.
- **Config único de permisos ≡ matriz §4.1** (una sola fuente). **§2.4 se codifica como capacidades `ciclo:aprobar|cerrar|reabrir|config`** dentro del mismo config (M-09). **Regla (Kimi H1):** endpoints de negocio usan solo `require_permission`; **`require_role` queda SOLO para endpoints de administración de identidad (`/users`) si se construyen; prohibido en endpoints de negocio.** (No hay 5º rol "superadmin": el enum certificado tiene 4 roles — Spec §1.1.)
- **Navbar sin drift (M-07):** `GET /api/v1/auth/capabilities` devuelve las capacidades efectivas del usuario; el frontend renderiza desde ahí (M13.1 #6 prohíbe mapas rol→ítems en el front).
- **Tests (DoD #1):** routers de prueba **solo-test** (uno por capacidad) para ejercitar negativos por rol, incl. **export de Consulta denegado** (`export:*`) (M-08).
- **Test de completitud del config (M-10):** triple — (a) toda capacidad usada en decoradores ∈ config; (b) config ≡ §4.1 canónica (lista congelada en el test); (c) sin capacidades huérfanas ni roles vacíos. (Coherente con exigir catálogo cerrado testeado para eventos.)

---

## Errata documental — CR-002 ampliado (A-06, M-03, H3) — antes del merge de PR-1
**CR-001 exhibido** en `docs/cambios/CR-001.md` (firmado CEO 18-jul, tracker CRs fila 2 "Aprobado y firmado"): el **catálogo = 30** es normativo (CR-001 §2.1 + CLAUDE.md regla 11 + hoja DoD #6). `extracto.cargado` (extracto mensual, `POST /extractos` S4) ≠ `carga.completada` (carga diaria M7). Lo desincronizado son los `.docx` certificados; se foldea en el re-baseline (CR-001 §metadata ya lo previó como v1.2). **CR-002** registra los 8 ítems (no se firma el re-baseline ni se regeneran los `.docx` ahora; ver `docs/COMPAS_ERRATA_PENDIENTE_v1_1_3.md`):
1. Spec §1.11 / DoD #6 / PRD §5 / INFO-000: "29" → **"30"**.
2. Spec §4: cookie refresh `Path=/auth` → **`Path=/api/v1/auth`**.
3. `api.compas.roddos.com` (RUNBOOK §5) + verificación de Origin en mutaciones.
4. **(H3-1)** STACK §3 tiene el MISMO cookie path viejo `path /auth` → `/api/v1/auth`.
5. **(H3-2)** `refresh_sessions` no existe en Spec §2.3 ni STACK §4.2 (colecciones/índices) → añadirla.
6. **(H3-3)** TTL denylist **por tipo** (access 15 min / refresh 30 d) precisa el Spec §2.3 ("TTL 30 días" plano).
7. **(H3-4)** convención UTC-aware en persistencia precisa el literal "now_bogota() en toda marca temporal" (Spec §1.1 / regla 2) — sin contradecir la zona única para dominio/UI.
8. **(H2/H3-5)** nuevo secreto `MONGODB_URI_AUDIT` por entorno → STACK §5.1.

## Reglas innegociables aplicables
Pydantic `strict=True` (r3); tiempo UTC-aware en persistencia + `now_bogota()` en presentación (r2); audit append-only (r4); catálogo cerrado de 30, no inventar eventos (r11); `JWT_SECRET` por env, sin secretos en repo (r12); access en memoria, refresh en cookie HttpOnly (no localStorage).

## Fuera de alcance (sin scope creep)
MFA TOTP + respaldo + step-up (Sprint 0b) · HIBP k-anonymity (0b) · cabeceras CSP/HSTS (0b) · workflows CI (Sesión 3) · aplicar `require_permission` a endpoints de negocio inexistentes. **G1 (0b) debe verificar que el PLAN de 0b incluye TOTP + respaldo + step-up + HIBP + CSP** (Q5).

## DoD cubierto por esta sesión
Parcial #1 (RBAC + negativos), parcial #6 (audit inmutable + tests neg/pos; el CI real lo recoge en Sesión 3 — marker `@requires_real_mongo`, mongod de CI **con auth**), parcial #11 (auth endurecida: logout revoca, token_version, backoff IP+cuenta). MFA de #11 → 0b.

## Riesgos (ampliado, Baja-5)
1. Deriva de semántica al portar (SISMO usa otros roles, sin token_version) → construir el endurecimiento fresco con TDD; PORTADO_DE_SISMO.md.
2. **Concurrencia de rotación** → rotación atómica + test de carrera obligatorio.
3. **A-05 orden de PRs** → mitigado (audit primero).
4. **Errata baseline (A-06)** → CR-002 antes del merge de PR-1; si no se firma, se construye con 30 igual (ya normativo por CR-001) pero se deja la nota de erratum.
5. **Drift config↔§4.1** → test de completitud (M-10).
6. **Dependencia `audit_writer`↔CI** → mongod de CI con auth habilitada; markers fallan (no skip) sin él.
7. Base de rama sobre Sesión 1 no mergeada → pin `61048ac` + rebase si se mueve.

## Gate
- **I-PLAN:** 7.8/10 NO-GO (6A+11M+6B). **R-PLAN:** **9.1/10 GO CONDICIONADO** (≥9.0). Condiciones cumplidas: (1) CR-001 exhibido en `docs/cambios/CR-001.md`; (2) CR-002 ampliado a 8 ítems; (3) H1–H7 aplicados en este PLAN v3 → **GO pleno**.
- Siguiente: construir **PR-1 (audit base) → PR-2 (auth) → PR-3 (RBAC)**, cada uno con su gate Kimi ≥ 9.0 antes de merge.
