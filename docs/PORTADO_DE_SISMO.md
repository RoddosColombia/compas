# Portado de SISMO-V3 → COMPAS (entregable para el par revisor)

Tabla por artefacto: **portado** (traído casi igual), **adaptado** (traído y modificado al
Spec de COMPAS) o **construido** (nuevo, no existe en SISMO). Mitiga bus-factor (riesgo #1/#8).

## Sesión 2 · PR-1 — Audit base

| Artefacto COMPAS | Origen SISMO | Clasif. | Notas |
|---|---|---|---|
| `app/audit/events.py` (`AuditEvento`, 30) | `models/audit_log.py` (tenía su propio set de eventos) | **construido** | Catálogo CERRADO de 30 del Spec §1.11 + `extracto.cargado` (CR-001). Distinto al de SISMO. |
| `app/audit/models.py` (`AuditLog` Pydantic) | `models/audit_log.py` (Beanie Document) | **adaptado** | En COMPAS es Pydantic plano: las escrituras van por conexión dedicada, no por el ODM general. |
| `app/audit/service.py` (`emit_audit`) | `services/audit/` | **adaptado** | Escribe por `compas_audit` (audit_writer); valida contra el catálogo cerrado. |
| Inmutabilidad por privilegios + `compas_audit` | (SISMO usa readWrite) | **construido** | 2ª conexión a la MISMA db `compas`; app general sin update/remove; test neg+pos (@requires_real_mongo, CI S3). |
| `scripts/create_audit_role.py` | — | **construido** | Rol/usuario idempotente para el gate de inmutabilidad. |
| `app/core/time.py::now_utc` | `utils/time.py::now_bogota` | **construido** | Convención A-04: UTC-aware en persistencia; `now_bogota` solo presentación. |

## Sesión 2 · PR-2 — auth (JWT endurecido)

| Artefacto COMPAS | Origen SISMO | Clasif. | Notas |
|---|---|---|---|
| `app/auth/tokens.py` (JWT) | `core/security.py` (JWT básico) | **construido** | HS256 explícito, jti uuid4 en ambos, family_id, verify_exp para logout. |
| `app/auth/service.py` (login/refresh/logout) | `routers/auth.py` (estructura) | **construido** | token_version, rotación atómica + reuso, backoff IP+cuenta, anti-enumeración. SISMO no tenía nada de esto. |
| `app/auth/repository.py` | — | **construido** | Motor crudo; rotación findOneAndUpdate; TTL/índices. |
| `app/auth/passwords.py` | `core/security.py` (bcrypt) | **adaptado** | bcrypt rounds=12 + política por rol + DUMMY_HASH. |
| `app/auth/roles.py` | `models/user.py::Role` | **adaptado** | Roles COMPAS (admin/directivo/financiero/consulta), distintos de SISMO. |
| `app/auth/deps.py::get_current_user` | `core/security.py::get_current_user` | **adaptado** | + denylist + token_version por request. |
| `scripts/create_auth_indexes.py` | — | **construido** | Índices idempotentes (email/jti únicos, TTL). |

## Sesión 2 · PR-3 (RBAC)
_(se completará al construir PR-3)_

## Sprint 1 — Parsers bancarios + Transaccion + carga (GO Kimi R-PR1 9.3, merge 72034a0)

| Artefacto COMPAS | Origen SISMO | Clasif. | Notas |
|---|---|---|---|
| `app/parsers/bank_parsers.py` (3 bancos + auto-detect) | **SISMO-V2** `backend/services/bank_parsers.py` (5 bancos, float, silencioso) | **adaptado** | Conocimiento de formatos reusado (Bancolombia hoja 'Extracto' fila 15, BBVA fila 14, Global66 hoja COP fila 4); reescrito por TDD para las reglas COMPAS: Decimal/`Money` (regla 1), fail-loud `ErrorFila` (regla 7), FX Global66 (`moneda_original`/`tasa_cambio`). Se descartaron Davivienda y Nequi (no son bancos de RODDOS) → sin pandas/pdfplumber. |
| `app/domain/transaccion.py` (`derivar_id_banco`) | **SISMO-V2** `services/anti_duplicados.py::hash_movimiento` (MD5 fecha\|desc\|monto) | **adaptado** | Huella determinista con banco+tipo en la clave y **ordinal de ocurrencia por archivo** (Kimi A-01: dos movimientos legítimos idénticos no colapsan). Global66 usa su referencia nativa. |
| `Transaccion` (§1.5) + índice único parcial (banco, id_banco) | — | **construido** | Dedup como restricción de BD (regla 5); probado contra Mongo real (solape→0, 2 manuales coexisten). |
| `CargaBancaria` (§1.6) + `app/cargas/service.py` | (V2 hacía conciliación por colecciones de hashes) | **construido** | Ciclo procesando→completada/fallida, F-02, transacción multi-doc real (pre-filtro + `with_transaction`; se refutó con evidencia el catch-and-commit), preservación del original (M-04), eventos `carga.completada/fallida`. |
| `app/cargas/mapper.py` | — | **construido** | MovimientoBancario→Transaccion ('Por clasificar', debito→egreso/credito→ingreso). |

## Infra (20-jul-2026) — no es porte de código, pero cierra el ciclo
Base `compas` en el **cluster de SISMO-V3** (decisión CEO: facilita integraciones futuras); usuarios `compas_app`/`compas_audit` + rol `audit_writer` creados por **Atlas UI** (Atlas bloquea createUser/createRole por driver en todos los tiers — corrección a la nota H-01, ver RUNBOOK §2). API live: `https://compas-api-von1.onrender.com` (auto-deploy desde main, fase desarrollo).
