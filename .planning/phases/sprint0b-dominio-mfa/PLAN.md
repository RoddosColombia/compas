# PLAN — Sprint 0b: dominio base + MFA + cabeceras + Gate G1

**Fase:** `sprint0b-dominio-mfa` · **Fecha:** 2026-07-19 · **Base:** `main` (Sesión 2 mergeada, `28f0bdd`)
**Contrato:** Spec §1.2 (Rubro), §1.3 (MesControl), §1.10 (Configuracion), §1.11, §8.1 (MFA/HIBP), §8.3 (cabeceras) · PLAN §3 (Sprint 0b) · DoD #6/#11/#12 · RUNBOOK §9 (G1)
**Fuente a portar:** `../SISMO-V3` (MFA/TOTP y cabeceras si existen; verificar con grep como en Sesión 2).

## Objetivo
Cerrar el andamiaje de Fase 0–1: modelos de dominio base (Rubro/MesControl/Configuracion) con Beanie + init_beanie cableado, MFA TOTP + step-up + HIBP (completar DoD #11), cabeceras de seguridad (DoD #12), y armar el **checklist del Gate G1 (bloqueante)**.

## Desglose en PRs (cada uno gate Kimi ≥ 9.0)

### PR-1 — Dominio base (Rubro, MesControl, Configuracion) + init_beanie
- **Rubro** (Beanie Document, Spec §1.2): `grupo` (5: costo_producto|operacion|nomina|deudas_obligaciones|otros), `nombre` único por grupo, `tipo_flujo`, `orden`, `activo`, `es_sistema`. **Semilla** de los 5 grupos + rubros 'Por clasificar' y 'Ajuste de conciliación' (es_sistema, inmutables). `migrations/20260901_seed_rubros.py` idempotente.
- **MesControl** (§1.3): `mes` (YYYY-MM-01 único), `estado` (sugerido…cerrado), `saldo_inicial_caja` (Decimal), `saldos_banco[]`, trazabilidad. Regla: meses cerrados inmutables.
- **Configuracion** (§1.10): `{clave, valor, vigente_desde, modificado_por}` + evento `config.actualizada`; semilla **CALENDARIO_DIAN** desde `docs/Calendario_DIAN_2026.md`, `UMBRAL_DIF_BANCO_CIERRE`, `DIAS_CREDITO_POR_PROVEEDOR`.
- **init_beanie** cableado en el lifespan (ahora sí hay Documents); `AuditLog` sigue por conexión dedicada.
- **Dinero = Decimal** (regla 1): montos como `Decimal` en backend, string en API. TDD contra Mongo real para índices únicos (`@requires_real_mongo`).

### PR-2 — MFA TOTP + step-up + HIBP (completa DoD #11)
- **TOTP** obligatorio para `admin` y `directivo` antes del go-live; `mfa_secret`/`mfa_habilitado` en User; códigos de respaldo de un solo uso; endpoint `POST /auth/mfa/verify`.
- **Step-up** para `ciclo:reabrir`, `ciclo:config`, editar saldo inicial (dependencia que exige MFA reciente).
- **HIBP k-anonymity** en la política de contraseñas (rango SHA-1, sin enviar el hash completo).
- Break-glass documentado (RUNBOOK); eventos de auditoría existentes.

### PR-3 — Cabeceras de seguridad (DoD #12)
- Middleware: **CSP estricta** (sin unsafe-inline), **HSTS** (vía Cloudflare + header), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `frame-ancestors 'none'`. Test en CI que verifica su presencia.

## Gate G1 (BLOQUEANTE) — checklist de seguridad
Al cierre de 0b: auth endurecida (✓ Sesión 2) + audit inmutable (test real en CI) + MFA activo + cabeceras + CI con pip-audit/gitleaks (Sesión 3). Aprobador **distinto del ejecutor** (RUNBOOK): con la política actual **solo Andrés revisa** ([[revisor-solo-andres]]) — el gate adversarial Kimi + Andrés cubren la revisión; la segregación formal "aprobador≠ejecutor" queda como decisión del CEO (señalada, no bloqueada).

## Micro-ítems de arrastre (Sesión 2) — YA en repo, se exhiben aquí
- **B-1**: `cookie`/`set-cookie` en `_PII_KEYS` (`app/main.py`, commit `c34f9c9`).
- **P-1**: `tz_aware=True` en `app/db/mongo.py:27`.
- **P-2**: tests de validadores de audit (`tests/test_audit_models.py`, commit `5d5ae41`).

## Reglas / DoD
Dinero=Decimal (r1); TZ Bogotá + UTC-aware en persistencia; Pydantic strict (r3); histórico inmutable (r4); catálogo cerrado 30 (r11); transacciones multi-doc donde aplique (r8). Cierra DoD #11 (MFA) y #12 (cabeceras); prepara G1.

## Fuera de alcance
Parsers/cargas (Sprint 1) · CI workflows (Sesión 3, en paralelo) · errata v1.1.3 (CR-002, firma CEO).

## Gate
Auditoría Kimi del PLAN (esta) ≥ 9.0 → construir PR-1 → PR-2 → PR-3, cada uno con gate ≥ 9.0 → **Gate G1 bloqueante**.
