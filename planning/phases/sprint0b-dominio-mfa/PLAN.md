# PLAN — Sprint 0b: dominio base + MFA + cabeceras + Gate G1

**Fase:** `sprint0b-dominio-mfa` · **Fecha:** 2026-07-19 · **Base:** `main` (Sesión 2 mergeada, `28f0bdd`)
**Contrato:** Spec §1.2 (Rubro), §1.3 (MesControl), §1.10 (Configuracion), §1.11, §8.1 (MFA/HIBP), §8.3 (cabeceras) · PLAN §3 (Sprint 0b) · DoD #6/#11/#12 · RUNBOOK §9 (G1)
**Fuente a portar:** `../SISMO-V3` (MFA/TOTP y cabeceras si existen; verificar con grep como en Sesión 2).

## Objetivo
Cerrar el andamiaje de Fase 0–1: modelos de dominio base (Rubro/MesControl/Configuracion) con Beanie + init_beanie cableado, MFA TOTP + step-up + HIBP (completar DoD #11), cabeceras de seguridad (DoD #12), y armar el **checklist del Gate G1 (bloqueante)**.

## Desglose en PRs (cada uno gate Kimi ≥ 9.0)

### PR-1 — Dominio base (Rubro, MesControl, Configuracion) + init_beanie
- **Rubro** (Beanie Document, Spec §1.2): `grupo` (5: costo_producto|operacion|nomina|deudas_obligaciones|otros), `nombre` único por grupo, `tipo_flujo`, `orden`, `activo`, `es_sistema`. **Semilla** (Kimi M-02): los 5 grupos + las **~30 categorías del Excel congelado** (PRD M1), cada una con `grupo`, `tipo_flujo` y `orden`; más los rubros de sistema 'Por clasificar' y 'Ajuste de conciliación' (`es_sistema`, inmutables). `migrations/20260901_seed_rubros.py` idempotente. Si alguna categoría del Excel no se puede fijar en esta semilla, se registra explícitamente en el migration por qué se difiere y dónde se cargará.
- **MesControl** (§1.3): `mes` (YYYY-MM-01 único), `estado` (sugerido…cerrado), `saldo_inicial_caja` (Decimal), `saldos_banco[]`, trazabilidad. Regla: meses cerrados inmutables.
- **Configuracion** (§1.10): `{clave, vigente_desde, modificado_por}` + valor **tipado por clave** (Kimi M-03): `valor_decimal` (COP como `Decimal`, p.ej. `UMBRAL_DIF_BANCO_CIERRE`), `valor_fecha` (p.ej. entradas de `CALENDARIO_DIAN`), `valor_json` (p.ej. `DIAS_CREDITO_POR_PROVEEDOR`) — nada de `valor` genérico que rompa "dinero=Decimal". Evento `config.actualizada`; semilla **CALENDARIO_DIAN** desde `docs/Calendario_DIAN_2026.md`, `UMBRAL_DIF_BANCO_CIERRE`, `DIAS_CREDITO_POR_PROVEEDOR`.
- **init_beanie** cableado en el lifespan (Kimi M-04): lista explícita de Documents = `[Rubro, MesControl, Configuracion, User, RefreshSession]`; **`AuditLog` queda FUERA** (escritura por conexión dedicada `compas_audit`; lecturas futuras del query service con modelo explícito).
- **Dinero = Decimal** (regla 1): montos como `Decimal` en backend, string en API. TDD contra Mongo real para índices únicos (`@requires_real_mongo`).

### PR-2 — MFA TOTP + step-up + HIBP (completa DoD #11)
- **TOTP** obligatorio para `admin` y `directivo` antes del go-live; `mfa_secret`/`mfa_habilitado` en User; códigos de respaldo de un solo uso; endpoint `POST /auth/mfa/verify`.
- **Step-up** para `ciclo:reabrir`, `ciclo:config`, editar saldo inicial (dependencia que exige MFA reciente).
- **HIBP k-anonymity** en la política de contraseñas (rango SHA-1, sin enviar el hash completo).
- Break-glass documentado (RUNBOOK); eventos de auditoría existentes.

#### Diseño MFA (Kimi M-01 — los 6 puntos)
1. **Enrolamiento TOTP:** `POST /auth/mfa/setup` genera `mfa_secret` (cifrado en reposo, ver pt.5) y devuelve `otpauth://` para QR; **protegido por contraseña + step-up** (re-verificar credencial). `POST /auth/mfa/activate` confirma con un código TOTP válido antes de marcar `mfa_habilitado=true` y emite los códigos de respaldo (una sola vez, en claro en la respuesta).
2. **"MFA reciente" (step-up):** claim `mfa_at` (epoch UTC) en el access token, escrito al superar `/auth/mfa/verify`. La dependencia `require_step_up` exige `now_utc() - mfa_at ≤ MFA_STEPUP_WINDOW_MIN` (config, default 5 min); si no, `403 step_up_required`. Sin token de step-up separado — el claim en el access es la fuente.
3. **Códigos de respaldo:** N=10, **hasheados con bcrypt** (nunca texto plano en DB), **un solo uso** (se elimina/marca al consumir). Regenerar invalida los anteriores.
4. **Throttle `/auth/mfa/verify`:** 6 dígitos = fuerza bruta factible → **reusar el patrón IP+cuenta de auth** (`login_throttle` TTL) con su propio scope `mfa_verify`.
5. **`mfa_secret` en reposo:** cifrado simétrico (Fernet/AES-GCM) con clave `MFA_ENC_KEY` (secret, fail-fast fuera de dev); nunca en claro ni en logs/audit metadata.
6. **Reset de MFA:** `POST /auth/mfa/reset` (admin sobre otro usuario, o self con step-up) → limpia `mfa_secret`/códigos y **bump `token_version`** (revoca todas las sesiones). Evento de auditoría existente.
- **Tests obligatorios:** TOTP inválido repetido → throttle 429; código de respaldo un-solo-uso (segundo intento falla); step-up expirado → 403; enrolamiento sin contraseña → 401.

### PR-3 — Cabeceras de seguridad (DoD #12)
- Middleware API: **CSP estricta** (sin unsafe-inline), **HSTS** (vía Cloudflare + header), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `frame-ancestors 'none'`. Test en CI que verifica su presencia.
- **SPA (Kimi B-01):** las mismas cabeceras en la SPA vía `frontend/vercel.json` (`headers`) — DoD #12 es del sistema, no solo de la API. Test/verificación de que Vercel las sirve.

## Gate G1 (BLOQUEANTE) — checklist de seguridad
Al cierre de 0b: auth endurecida (✓ Sesión 2) + audit inmutable (test real en CI) + MFA activo + cabeceras + CI con pip-audit/gitleaks.

**Prerrequisitos duros del gate (Kimi B-02/B-03):**
- **Sesión 3 (S0-05):** CI con pip-audit/gitleaks **y mongod real** (para los `@requires_real_mongo` de índices únicos de PR-1). No es "en paralelo": es prerrequisito duro de G1.
- **Break-glass (S0-07):** custodio nombrado y documentado antes de evaluar G1.

**Mecanismo de aprobación (Kimi A-01 — RESUELTO por el CEO, `CR-003`):** la única autoridad de COMPAS es el CEO (Andrés) ([[revisor-solo-andres]]); Iván no aprueba (rol nominal, derogado). Se adopta la vía (b): **G1 lo aprueba el CEO Andrés (decisión) + auditoría adversarial Kimi ≥ 9.0 (evidencia independiente del ejecutor)**. Formalizado en `docs/cambios/CR-003-gate-g1-aprobador.md` (re-baseline v1.1.3). Se reconoce que debilita el segundo-par-humano; aceptado por el CEO, compensado por el gate Kimi.

## Micro-ítems de arrastre (Sesión 2) — YA en repo, se exhiben aquí
- **B-1**: `cookie`/`set-cookie` en `_PII_KEYS` (`app/main.py`, commit `c34f9c9`).
- **P-1**: `tz_aware=True` en `app/db/mongo.py:27`.
- **P-2**: tests de validadores de audit (`tests/test_audit_models.py`, commit `5d5ae41`).

## Reglas / DoD
Dinero=Decimal (r1); TZ Bogotá + UTC-aware en persistencia; Pydantic strict (r3); histórico inmutable (r4); catálogo cerrado 30 (r11); transacciones multi-doc donde aplique (r8). Cierra DoD #11 (MFA) y #12 (cabeceras); prepara G1.

## Fuera de alcance
Parsers/cargas (Sprint 1) · errata v1.1.3 (CR-002, firma CEO).
> CI workflows (Sesión 3, S0-05) NO son fuera de alcance de 0b: son **prerrequisito duro del Gate G1** (Kimi B-02).

## Gate
Auditoría Kimi del PLAN (esta) ≥ 9.0 → construir PR-1 → PR-2 → PR-3, cada uno con gate ≥ 9.0 → **Gate G1 bloqueante**.
