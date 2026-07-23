# SOLICITUD DE AUDITORÍA — sprint4-categorias · I-PR1: C1 categorías administrables (código)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-22
**Objeto:** PR #24 `feat/c1-rubros` (gate de CÓDIGO). Plan aprobado por ti: **PLAN-I GO 9.2** (misma carpeta padre, ronda PLAN-I) — construido con TDD incorporando **B-1..B-5** tal como lo pediste; "sin re-auditoría de plan".
**Docs contrato:** `docs/COMPAS_NORTE.md`, `.planning/PROJECT.md` (C1), `docs/modelo/MODELO.md` (taxonomía real), CR-S4; Spec §1.2/§2.2/§4.1; CLAUDE.md reglas 3, 4, 9, 11.
**Base:** `main` con Vista Control (tu GO I-PR1 9.4). **Alcance:** SOLO C1 backend + re-seed (C3 va en PLAN aparte; pantalla frontend de administración va después, sin gate).

## Qué hace el PR (20 archivos, +1349/−76; código en EVIDENCIA.md)

1. **CR-S4 aplicado:** `app/audit/events.py` 31→**33** (`rubro.creado`, `rubro.editado`; confirmado tu punto de verificación: **`rubro.desactivado` ya estaba en v1.0**, CR-S4 es +2). `app/auth/permissions.py`: `rubros:gestionar` = {financiero, admin}.
2. **Módulo nuevo `app/rubros/`** (router + service):
   - `GET /rubros` (`dashboard:leer`) — filtros `activo`/`grupo`, ordenado por `orden`.
   - `POST /rubros` (`rubros:gestionar` + `verify_origin`) — `orden = máx(grupo)+1`; emite `rubro.creado`; duplicado (grupo,nombre) → 409 (pre-check + `DuplicateKeyError` del índice → nunca 500).
   - `PATCH /rubros/{id}` — nombre/orden/`tipo_flujo`/reactivar; emite `rubro.editado` con `{campo: {anterior, nuevo}}`; sin cambios efectivos → 422.
   - `POST /rubros/{id}/desactivar` — baja lógica (D2); emite `rubro.desactivado`.
3. **Re-seed a la taxonomía real de MODELO.md:** `SEMILLA_RUBROS` = 31 reales + 3 sistema = **34** (antes 33 de la hoja 'Presupuesto'). Migración `migrations/20260722_reseed_rubros_reales.py` con **reporte de colisiones** (B-4).

## Cómo quedaron tus 5 Bajas (verificar con lupa)

- **B-1 (tipo_flujo congelado por REFERENCIAS):** `service._tiene_referencias()` = ∃ `Transaccion(rubro_id)` **∨** ∃ `PresupuestoLinea(rubro_id)` (consulta cruda proyección `{_id:1}`). Los 3 tests que pediste: con transacción → 409; con línea sin movimientos → 409; sin referencias → 200. Nombre/orden editables siempre (test con referencias → 200).
- **B-2 (alcance de la baja, declarado en el docstring del service y FIJADO con tests):**
  (a) clasificar hacia inactivo → 422 — la guarda vive en `transacciones/service.py::crear_transaccion_manual` (`rubro is None or not rubro.activo`; aplicará igual a C3); test nuevo en `test_transacciones_manual.py`.
  (b) el sugerido omite inactivos — el filtro `Rubro.activo == True` ya existía en `generar_sugerido`; test nuevo `test_excluye_rubros_inactivos` (la baja NO "gotea").
  (c) Vista Control conserva las líneas existentes del rubro inactivo — test nuevo `test_linea_de_rubro_inactivo_se_conserva`.
  Nota declarada: categoría INGRESO no recibe línea de presupuesto (§1.4 es de egresos).
- **B-3 (reactivación):** tu recomendación tal cual — PATCH `activo:true` → `rubro.editado {activo: false→true}` (catálogo queda en 33, sin 34.º evento). PATCH `activo:false` → 422 apuntando a `/desactivar` (una sola vía de baja, con su evento propio).
- **B-4 (reporte de colisiones):** `seed_rubros_reporte()` devuelve `(insertados, colisiones)`; cada colisión trae `existente` vs `semilla`; la migración imprime "⚠ DIFIERE → verificar" campo a campo (tipo_flujo/orden/activo/es_sistema). `$setOnInsert` intacto (test: edición del Admin sobrevive al re-seed).
- **B-5 (política de emisión, declarada):** **fail-closed estilo O1** en las 3 mutaciones — mutar → emitir → si el emit falla, COMPENSAR (delete del creado / revert de campos editados / revert del desactivar) y propagar. 3 tests de compensación con `emit_audit` parcheado a excepción.

## Decisiones de implementación declaradas (no estaban explícitas en el plan)

1. **Sin Idempotency-Key en POST /rubros:** no es movimiento de dinero (§1.12); el índice único (grupo,nombre) hace inocuo el replay (→ 409). Declarado en el docstring del router.
2. **Desactivar un rubro ya inactivo → 409** (explícito, no silencioso).
3. **Los 3 rubros de sistema viven en grupo `otros` en la semilla nueva** — misma llave (grupo,nombre) que los docs ya sembrados en prod → el re-seed NO los duplica.
4. **'Arriendos' queda en OTROS** (MODELO.md); el doc viejo (operación, si existe) no se toca — D3: el CEO depura desde la app, y B-4 lo reporta.

## Semántica preservada

Cero cambios en dinero/tiempo/motor/cierre/control: el PR no toca `presupuesto/motor.py`, `cierre/`, `control/`, `cargas/`, `ciclo/`. Los tests B-2 sobre generar/control/manual solo AÑADEN casos (fijan comportamiento que ya existía). Pydantic strict en los 2 bodies nuevos. `es_sistema` inmutable (409 parametrizado en los 3). El índice `(grupo,nombre)` único intacto.

## Evidencia local (salidas reales en EVIDENCIA.md)

- `pytest -q`: **354 passed, 34 skipped** (los skipped son los `requires_real_mongo` — corren en CI con replica set; run del PR #24 referenciado en EVIDENCIA).
- Suite nueva `test_rubros_endpoints.py`: **38 passed** (tu lista del §5 completa).
- `ruff check` + `ruff format --check`: limpios. Greps del protocolo: 0 resultados. gitleaks/pip-audit/frontend/runtime-imports verdes en CI.

## Pregunta al auditor

¿El código de C1 implementa fielmente el plan aprobado + tus 5 Bajas, con la auditoría fail-closed, el RBAC exacto y el re-seed verificable, para mergear a `main`?
