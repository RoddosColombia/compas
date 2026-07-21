# SOLICITUD DE AUDITORÍA — sprint3-ciclo PR1-I: apertura del mes (US-01)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-21
**Docs contrato:** Spec §1.3 (MesControl), §2.2, §2.4 (autoridad), US-01; CLAUDE.md reglas 1, 2, 3, 9, 11
**Rama:** `feat/ciclo-abrir-mes` · commit `274f47e` · **SIN mergear — gate antes del merge**

## Qué hace
1. **POST /api/v1/meses** (US-01): crea el `MesControl` del mes (estado inicial `sugerido`) con `saldo_inicial_caja` y `saldos_banco` (los 3 bancos reales; `manual` rechazado, §1.3). Emite **`mes.creado`** (regla 11, evento existente).
2. **Audit fail-closed con compensación** (política O1 tuya): si `emit_audit` falla, la apertura se REVIERTE (`delete` del mes) y el error se propaga — no queda un mes operable sin rastro. Test que lo prueba.
3. **Unicidad:** verificación previa + `DuplicateKeyError` del índice `mes_unico` → **409** (carrera cubierta por el índice).
4. **RBAC §2.4:** `ciclo:abrir` = financiero/directivo/admin (consulta 403, test). `GET /meses` con `dashboard:leer` (todos) para el selector de la UI.
5. Reglas: montos string (number → 422, test) · mes normalizado al día 1 (422, test) · Pydantic strict + extra=forbid.

## Decisiones declaradas (auditar)
1. **Sin Idempotency-Key**: la §1.12 lista "cargas, aprobaciones, cierres, transacciones manuales" — apertura no está y su dedup natural es el índice único del mes (doble-submit → 409, inocuo). ¿De acuerdo?
2. **Sin transacción multi-doc**: la regla 8 exige transacciones en aprobación/finalización-de-carga/cierre — la apertura es 1 insert + 1 evento; la compensación cubre el fallo del audit. ¿Suficiente, o exiges transacción también aquí?
3. **La apertura NO genera el sugerido**: el §2.4 dice "Abrir mes / generar sugerido" en una fila; el motor del sugerido (Spec §1.4.1) es el siguiente incremento (Sprint 3). Hoy abre el mes sin líneas de presupuesto. Declarado como alcance parcial de la fila.
4. **`saldos_banco` opcional (default [])**: el Excel real a veces no tiene el corte de todos los bancos al abrir. ¿O exiges ≥1 saldo?

## Semántica preservada
Nada existente cambia: cargas/manual/parsers/auth intactos (solo se agrega el router `ciclo` al api_router). El saldo inicial NO es editable por esta vía (eso será `ciclo:config` + step-up, incremento futuro).

## Contexto de proceso (desde tu último certificado)
- CI de `main` VERDE de nuevo: se corrigió el mongod del CI a **replica set 1-nodo con keyFile** (las transacciones de la regla 8 no existen en standalone — 9 tests de carga lo exigían), `ruff format` aplicado, y **pip-audit atrapó 3 CVEs** en `python-multipart 0.0.27` → 0.0.31 (el gate DoD #8 funcionando).
- Ese pin (0.0.27) venía del incidente post-merge anterior: el deploy falló porque `python-multipart` no estaba en requirements (drift local/CI) — detectado con el log de Render, corregido y desplegado.

## Evidencia local (EVIDENCIA.md: diff completo + salidas)
pytest: **248 passed / 23 skipped** (10 nuevos) · ruff check + format limpios · greps protocolo 0 · CI main run `29861083363` success.
