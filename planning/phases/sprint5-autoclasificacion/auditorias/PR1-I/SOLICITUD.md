# SOLICITUD DE AUDITORÍA — sprint5-autoclasificacion · I-PR1: C3 auto-clasificación (código)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-22
**Objeto:** PR #25 `feat/c3-clasificacion` (gate de CÓDIGO). Plan aprobado por ti: **PLAN-I GO 9.3** — construido con TDD incorporando **B-1 y B-2** tal como lo pediste; "sin re-auditoría de plan".
**Docs contrato:** Spec §1.9 / §1.5 / §319; MODELO §C3; CR-S5; CLAUDE.md reglas 3, 4, 7, 9, 11.
**Base:** `main` con C1 completa (GO 9.4 + re-seed + pantalla Categorías). **Alcance:** C3 backend; la pantalla frontend va aparte sin gate.

## Qué hace el PR (código real + salidas en EVIDENCIA.md)

1. **CR-S5 aplicado:** catálogo 33→**36** (`regla.creada`, `regla.editada`, `regla.desactivada`) + `reglas:gestionar`={financiero,admin}; completitud + guardián + CANONICA actualizados.
2. **`app/domain/regla_clasificacion.py`** (Spec §1.9 fiel): patron 3..120, **`normalizar_texto` = LA única normalización** (case + tildes) usada por `patron_normalizado` (model_validator, SIEMPRE derivado — no acepta valor divergente) y por `coincide()` al matchear. Índice único **parcial** `(patron_normalizado, tipo_flujo)` con `activa=true`. Registrada en `DOMAIN_DOCUMENTS` (8).
3. **`app/reglas/`** (service+router): GET (filtros) · POST · PATCH (patron/prioridad/rubro/reactivar) · POST /desactivar · POST /{id}/aprobar · POST /aplicar-pendientes. `elegir_regla()` puro: orden `(prioridad, str(_id))`, salta rubros inactivos (D2).
4. **Carga:** `procesar_carga` clasifica cada fila con las reglas activas particionadas por tipo (D1-ii, cargadas UNA vez por carga); mapper recibe `rubro_id` decidido + `regla_id` (rastro §1.5); `CargaBancaria` suma `clasificadas/por_clasificar/reglas_con_rubro_inactivo`; metadata de `carga.completada` extendida (D3 — sin CR: metadata de evento existente, como validaste).
5. **`PATCH /transacciones/{id}/clasificar`**: regla 4 (mes cerrado → 409); inmutables §2.2 intactos; `transaccion.clasificada` {rubro_anterior→rubro_nuevo} fail-closed con compensación; `proponer_regla` → aprendida `activa=False` forzado + `regla.creada` (validación de la propuesta ANTES de mutar).
6. **Semilla** (`SEMILLA_REGLAS`, congelada y testeada): SOLO `'Abono'`/`'Recibido de'` → 'Recaudo' (ingreso, prioridad 1-2, `origen='manual'`, `creada_por='semilla'`). **Fail-loud** `LookupError` si falta el rubro destino. Migración `20260722_seed_reglas_clasificacion.py` con URI por entorno (patrón B-1 de C1) + reporte de colisiones.

## Cómo quedaron tus 2 Bajas

- **B-1 (activación revalida D1):** `_validar_rubro_destino_para_activar` corre en los DOS puntos — `POST /{id}/aprobar` y `PATCH activa:true` — exigiendo rubro existente + activo + tipo coherente → 409; además re-chequea unicidad de patrón activo. Tests: `test_patch_reactivar_revalida_rubro_b1`, `test_aprobar_con_rubro_inactivo_409_b1`.
- **B-2 (sellado en aplicar-pendientes):** cada doc reclasificado queda con `clasificada_por` (quién disparó el lote) + `clasificada_at` (cuándo) + `regla_id` (qué regla) — rastro forense completo por documento, sin evento agregado (tu recomendación). Test: `test_aplicar_pendientes_clasifica_y_sella_b2`.

## Tu lista §5 → tests (todos en verde)

| Exigido | Test |
|---|---|
| Normalización ambas direcciones + patrón 2 chars → 422 | `test_match_tilde_patron_contra_descripcion_sin_tilde` / `..._sin_tilde_patron_contra_descripcion_con_tilde` / `test_match_case_ambas_direcciones` / `test_post_patron_2_chars_422` |
| Precedencia (prioridad, empate _id, re-corrida idéntica) | `test_precedencia_gana_menor_prioridad` / `test_precedencia_empate_desempata_por_id` / `test_carga_recorrida_identica` (real-mongo) |
| Unicidad patrón activo; desactivada no cuenta | `test_post_patron_activo_duplicado_409` / `test_precheck_duplicado_desactivado_no_cuenta` + **índice parcial real**: `test_regla_patron_activo_unico_parcial` (real-mongo; mongomock PIERDE el partialFilterExpression — documentado en el test) |
| D1 crear/editar; B-1 activar | `test_post_rubro_de_otro_tipo_409_d1` / `test_post_rubro_inactivo_422_d1` / `test_patch_rubro_de_otro_tipo_409_d1` / los 2 tests B-1 |
| D2 en carga + sin match + con match | `test_carga_d2_rubro_inactivo_salta_y_reporta` / `test_carga_sin_match_cae_a_por_clasificar` / `test_carga_clasifica_con_match` (real-mongo) + `test_carga_ingreso_clasifica_a_recaudo` (partición D1-ii) |
| Reclasificación manual (regla 4, inmutables, evento) | `test_clasificar_mes_cerrado_409` / `test_clasificar_inmutables_intactos` (assert explícito §2.2) / `test_clasificar_ok_emite_evento_con_anterior_y_nuevo` / inactivo 422 / tipo 409 |
| proponer_regla + aprobar | `test_proponer_regla_crea_aprendida_inactiva` / `test_aprobar_aprendida_emite_editada_via_aprobacion` / `test_aprobar_manual_409` / `test_aprobar_ya_activa_409` |
| aplicar-pendientes | `..._clasifica_y_sella_b2` / `..._no_toca_mes_cerrado` / `..._idempotente_y_no_toca_clasificadas` / `..._sin_match_queda_por_clasificar` |
| RBAC + catálogo 36 + guardián | `test_get_200_los_cuatro_roles` / `test_mutaciones_403_consulta_y_directivo` / `test_catalogo_tiene_exactamente_36_eventos` / guardián verde |
| Semilla (sin PII, manual, fail-loud, colisiones) | `test_semilla_reglas_sin_pii_y_origen_manual` (lista congelada) / `test_seed_reglas_idempotente_y_resuelve_rubro` / `test_seed_reglas_fail_loud_sin_rubro_destino` |
| O1 fail-closed | `test_fail_closed_crear_compensa` / `..._aprobar_compensa` / `..._desactivar_compensa` / `test_fail_closed_clasificar_compensa` |

## Decisiones de implementación declaradas (no explícitas en el plan)

1. **Semilla de egresos diferida:** el mapeo real descripción→categoría de `Base real egresos` vive fuera del repo (OneDrive, dato real). La semilla congelada trae SOLO las 2 genéricas de ingreso; los patrones de comercios se crean desde la app (o extensión de la semilla cuando el CEO comparta el mapeo). Evita inventar patrones (regla 7) y cualquier riesgo PII.
2. **Reclasificación sin Idempotency-Key:** idempotente por naturaleza (re-aplicar el mismo rubro no cambia nada) y no crea dinero.
3. **`aplicar-pendientes` con permiso `reglas:gestionar`** (dispara efecto masivo de reglas); la reclasificación individual usa `cargas:gestionar` (misma autoridad del POST manual).
4. **mongomock pierde `partialFilterExpression`** al crear índices vía Beanie (verificado con `index_information()`): el pre-check se prueba en mongomock (tumbando el índice falso, documentado) y el índice parcial REAL en `test_domain_indexes.py` (real-mongo, corre en CI) — mismo criterio del dedup de Sprint 1.

## Semántica preservada

La clasificación solo asigna `rubro_id`/`regla_id` (+ sellos B-2): nunca toca valor, fecha, signo, dedup ni mes. Motor §1.4.1 / cierre / conciliación / Vista Control intactos (0 líneas cambiadas en esos módulos). Mes cerrado inmutable en TODAS las vías (carga ya lo omitía; reclasificación 409; aplicar-pendientes filtra). Pydantic strict en los 3 bodies nuevos.

## Evidencia local (salidas en EVIDENCIA.md)

`pytest -q`: **412 passed, 40 skipped** (los real-mongo corren en CI — run del PR #25 referenciado). `ruff check` + `format --check`: limpios. Greps: 0.

## Pregunta al auditor

¿El código de C3 implementa fielmente el plan 9.3 + B-1/B-2, con la normalización única, la precedencia determinista, las guardas D1/D2 en todas las vías y el rastro forense completo, para mergear a `main`?
