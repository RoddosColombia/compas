# RESPUESTA KIMI — sprint0b · PR1-I

**Certificado — I-PR1 · Sprint 0b: dominio base (Rubro, MesControl, Configuracion)**
**9.4 / 10 — GO (merge autorizado)** · RODDOS S.A.S. · 2026-07-19 · Commit `203e23f`

Salidas: pytest 129 passed, 9 skipped (placeholders `@requires_real_mongo` honestos, CI S3) ·
ruff limpio · self-check de semilla consistente (32 rubros; 2 de sistema; órdenes 1..32).

## Verificación (4/4 puntos de lupa + 3/3 hallazgos del I-PLAN)
- **Money/Decimal128:** `_coerce_decimal` acepta Decimal, coerciona Decimal128→Decimal, rechaza
  float/bool (bool subclase de int — bien cazado) y str/int/None; `_a_bson` Decimal→Decimal128 en
  Motor crudo; `money_str` HALF_EVEN. Tests completos. **D-4 aceptada.**
- **Semilla real (M-02):** 32 rubros = 31 del Excel (3+11+6+5+6) + 'Ajuste de conciliación';
  agrupación fiel a PRD M1; 2 de sistema inmutables; índice único (grupo,nombre) con test
  DuplicateKeyError en mongo real. **D-3 aceptada.**
- **Configuracion (M-03):** valor tipado por clave + model_validator exactamente-uno-del-tipo;
  semilla real (UMBRAL $50.000, CALENDARIO_DIAN 3 fechas del NIT, DIAS_CREDITO vacío). **D-2 aceptada.**
- **init_beanie (M-04):** DOCUMENT_MODELS = [Rubro, MesControl, Configuracion]; AuditLog/User/
  RefreshSession FUERA; `ensure_beanie` no-fatal + reintento con 3 tests. Patrón sólido.
- **Inmutabilidad meses cerrados (regla 4):** `assert_editable()` → MesCerradoError; tardías
  diferidas al cierre (Sprint 4).
- **Fechas como string (D-1):** aceptada — justificación técnica correcta (BSON no tiene
  date-sin-hora; string ISO cumple §0.2 y ordena lexicográficamente).

## Bajas (follow-ups, no bloquean el merge)
- **B-1 — Rubro de ingreso ausente:** la semilla es 100% egreso; la regla PRD M7
  ('Abono' → ingreso recaudo) no tiene rubro destino. **Decidir ANTES del Sprint 2**: añadir
  rubro Recaudo (tipo ingreso) a la semilla, o declarar que lo crea el Admin — pero debe existir
  antes de la clasificación automática de ingresos. → seguimiento S0B-05.
- **B-2 — SaldoBanco.banco como str libre:** usar enum `bancolombia|bbva|global66`. → **APLICADO**
  en esta ronda (post-GO): `app/domain/bancos.py` + validador + tests de rechazo.

## Gobernanza (no de este PR)
A-01 (mecanismo Gate G1) → **resuelto por el CEO vía CR-003** (aprobador = CEO + evidencia Kimi).
Bloque M-01 (MFA) es insumo del PLAN de PR-2.

**Declaración:** dominio base fiel al contrato. **GO — merge autorizado.**
