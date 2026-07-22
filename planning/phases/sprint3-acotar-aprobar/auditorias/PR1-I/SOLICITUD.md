# SOLICITUD DE AUDITORÍA — sprint3-acotar-aprobar · I-PR1: acotamiento + aprobación

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-21
**Docs contrato:** Spec §1.4/§2.2 (multi-doc F-09, versionado nit-12)/§2.4 (autoridad)/§1.11/§1.12; CLAUDE.md reglas 1,2,3,4,8,9,11
**Rama / PR:** `feat/acotar-aprobar` / **#21** · commit `2277d32` · **SIN mergear — gate pre-merge**
**Antecedente:** GO PLAN I-PLAN 9.2 (M-1/M-2 incorporados). Este es el gate de CÓDIGO.

> En el PLAN anunciaste que en el gate de código auditarías: **la transacción real contra el replica set (regla 8)**, **el test de convergencia en ambos puntos de fallo**, **el flip de estado en acotar (M-1)**, y **la saga completa (M-2)**. La EVIDENCIA trae el diff real + las salidas de tests (incl. CI real-mongo).

## Qué hace (implementado)

1. **`acotar_linea`** (`app/presupuesto/service.py`) + **`PATCH /meses/{mes}/presupuesto/{rubro_id}`** (`presupuesto:acotar`): fija `monto_definido` en la línea vigente + `Ajuste` append-only con `comentario`. **M-1:** `sugerido → propuesto` en el primer acotamiento. **M-2:** saga fail-closed O1 — captura estado previo, escribe línea (+ estado), emite `presupuesto.acotado`; si el emit falla, **compensa** (revierte ajuste + `monto_definido` + estado del mes). NO usa transacción Mongo (pocos docs secuenciales).

2. **`aprobar_presupuesto`** + **`POST /meses/{mes}/presupuesto/aprobar`** (`ciclo:aprobar` = **solo Admin**, header **Idempotency-Key**): **TRANSACCIÓN MULTI-DOC (regla 8)** `with_transaction` en la conexión principal — fija `monto_definido` (null → `monto_sugerido`, D2) en las líneas vigentes + `MesControl → definido` (+`definido_por/at`), atómico, reintento automático de `with_transaction`. Auditoría `presupuesto.definido` **tras el commit** (conexión dedicada); si falla → **transacción compensatoria** (saga O1). Idempotency-Key para replay/convergencia.

3. **Modelo:** `Ajuste.comentario: str|None` (Baja #3); `PresupuestoLinea.creada_por: str|None` (Baja #1).

4. **Baja #4 (`$group`):** `_ejecutados_por_rubro_mes` reemplaza el loop de ~90 queries por UNA agregación. El **test dorado 48/61/75M → 84.033.333,33 pasa con la agregación** (equivalencia probada, como pediste). **Baja #5:** fechas del helper de tests dentro de su mes.

## Decisiones (ya avaladas en el PLAN, reconfirmar en código)
- **D1** primera aprobación in-place (sin versión nueva; flip nit-12 → Sprint 4). **D2** líneas sin acotar toman el sugerido. **D3** saga de auditoría por conexión dedicada. **D4** resuelta por M-1 (sin verbo `proponer`).

## Semántica preservada (NO cambia)
Motor §1.4.1 y su dorado intactos; índice `{vigente:true}` intacto; histórico inmutable (mes `cerrado`/`definido` rechaza acotar/aprobar); dinero Decimal/string; Pydantic strict; catálogo de eventos cerrado (se usan `presupuesto.acotado`/`presupuesto.definido`, sin inventar).

## Puntos a auditar con lupa
1. **Transacción multi-doc real:** atomicidad de ~30 líneas + MesControl; el test `test_convergencia_abort_datos` prueba que un fallo en la ÚLTIMA escritura revierte también las líneas ya escritas en la sesión (rollback total).
2. **Saga de auditoría (M-2 en acotar, O1 en aprobar):** `test_acotar_compensa_si_falla_auditoria` y `test_convergencia_falla_emit_compensa` — la compensación preserva el dato legítimo (la línea acotada NO se toca) y solo revierte lo generado (null→sugerido).
3. **Convergencia:** ambos tests re-ejecutan tras el fallo y CONVERGEN a `definido`.
4. **RBAC §2.4:** acotar Financiero/Directivo/Admin; aprobar solo Admin (403 para Financiero/Directivo/Consulta — test parametrizado).
5. **`$group`:** equivalencia con el loop certificado vía el dorado end-to-end.

## Evidencia (ver EVIDENCIA.md)
- **Local:** 286 passed / 27 skipped (los skipped = real-mongo). Presupuesto: 32 passed. ruff limpio. Greps del protocolo en 0.
- **CI (PR #21, run 29883289498):** TODOS los jobs verdes — `backend`, `backend-real-mongo` (**27 passed**, incluye los 4 de la transacción + convergencia contra replica set 1-nodo), `gitleaks`, `pip-audit`, `runtime-imports`, `frontend`.

## Pregunta al auditor
¿La transacción multi-doc, la saga de auditoría (acotar y aprobar) y la convergencia en ambos puntos de fallo están correctamente implementadas y probadas para merge, o hay un hallazgo a resolver?
