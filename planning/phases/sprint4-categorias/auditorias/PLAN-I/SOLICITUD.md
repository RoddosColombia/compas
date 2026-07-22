# SOLICITUD DE AUDITORÍA — sprint4-categorias · I-PLAN: C1 categorías administrables

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-22
**Docs contrato:** `docs/COMPAS_NORTE.md`, `.planning/PROJECT.md` (C1), `docs/modelo/MODELO.md` (taxonomía real), **CR-S4** (catálogo +2 eventos, permiso `rubros:gestionar`); Spec §1.2/§2.2/§4.1; CLAUDE.md reglas 1,2,3,4,9,11.
**Base:** `main` con Vista Control mergeada (GO 9.4). **Nivel:** PLAN (pre-código).
**Alcance:** SOLO **C1** (categorías administrables + re-seed real). La auto-clasificación (C3) va en PLAN aparte.

> Contexto de norte: COMPAS es predictivo, NO contable. Las categorías son la estructura
> sobre la que se controla el presupuesto por categoría y cuenta (molde: `Base real egresos`
> del Excel). C1 permite crear/administrarlas desde la app.

## Qué se propone

**Nuevo módulo `rubros`** (router + service):
1. `GET /rubros` (RBAC `dashboard:leer`) — lista con filtros `activo`/`grupo`.
2. `POST /rubros` (RBAC `rubros:gestionar`, CR-S4) — crea `{grupo (uno de 5), nombre, tipo_flujo egreso|ingreso}`; `orden` = máx del grupo + 1. Emite **`rubro.creado`** (CR-S4). 409 si (grupo,nombre) duplicado.
3. `PATCH /rubros/{id}` (`rubros:gestionar`) — edita `nombre`/`orden`/`tipo_flujo`. Emite **`rubro.editado`** con {campo: anterior→nuevo}. 409 en rubro de sistema o nombre duplicado.
4. `POST /rubros/{id}/desactivar` (`rubros:gestionar`) — `activo=false`. Emite `rubro.desactivado` (ya existe). 409 en rubro de sistema.

**Guardas de dominio (§2.2):**
- Rubros de **sistema** ('Por clasificar','Ajuste de conciliación','Recaudo') **inmutables** → 409.
- **No se borra**: solo baja lógica. Reactivar = `PATCH activo` (o endpoint simétrico) — a decidir (ver D2).
- Único (grupo, nombre) — índice existente.

**Re-seed de la taxonomía real (migración idempotente):** alinear la semilla de rubros a las
**31 categorías reales** del `Base real egresos` (Transporte/peajes, Cafetería, Bonificaciones,
Sueldos directivos, SOAT/Matrículas, Gastos de representación, etc.) agrupadas en los 5 grupos
(mapeo en `docs/modelo/MODELO.md`). `$setOnInsert` por (grupo,nombre) → no duplica ni pisa.

**CR-S4 (declarado):** catálogo 31→33 (`rubro.creado`, `rubro.editado`); test de completitud
CI actualizado; permiso `rubros:gestionar` = {financiero, admin}.

## Decisiones declaradas (auditar)
1. **`tipo_flujo` editable:** una categoría es egreso o ingreso. ¿Permito cambiarlo por PATCH si ya tiene transacciones, o lo congelo tras el primer movimiento? Propongo **congelar `tipo_flujo` si el rubro ya tiene transacciones** (evita voltear el signo del histórico) — nombre/orden sí editables siempre.
2. **Desactivar con movimientos:** un rubro con transacciones **sí** se puede desactivar (baja lógica; las transacciones quedan en la categoría inactiva, visibles en el histórico); solo se impide **crear nuevas** clasificaciones hacia él. ¿De acuerdo?
3. **Re-seed:** como prod solo tiene la semilla vieja (sin transacciones reales aún), el re-seed a la taxonomía real es seguro. Las categorías viejas genéricas que no estén en la taxonomía real quedan `activo=true` igualmente (no se borran) — ¿o las desactivo? Propongo dejarlas activas y que el CEO las depure desde la app.

## Semántica preservada
Nada de dinero/tiempo cambia; es estructura + CRUD. Motor/acotar/aprobar/cierre/control intactos. Pydantic strict. Índice único (grupo,nombre) intacto. `es_sistema` protege los 3 rubros de sistema.

## Puntos a auditar con lupa
1. Inmutabilidad de rubros de sistema (409 en editar/desactivar).
2. Emisión correcta de `rubro.creado`/`rubro.editado` (CR-S4) + RBAC `rubros:gestionar` exacto (financiero/admin sí; consulta/directivo → 403 en gestionar).
3. Congelar `tipo_flujo` con transacciones (D1) — no voltear el signo del histórico (regla 4).
4. Re-seed idempotente sin pisar ediciones ni duplicar.
5. Único (grupo,nombre) → 409.

## Evidencia
- Sin código aún (PLAN). `main` con Sprint 3 + cierre + Vista Control; CI verde; deploy sano.

## Pregunta al auditor
¿El diseño de C1 (CRUD de categorías con guardas de sistema/inmutabilidad, CR-S4 para los 2 eventos + permiso, re-seed a la taxonomía real) es correcto para construir con TDD? En particular D1 (congelar tipo_flujo con movimientos) y D3 (qué hacer con las categorías viejas genéricas en el re-seed).
