# RESPUESTA — Kimi · I-PR1 Sprint 5: C3 Auto-clasificación (gate de código, PR #25)

> Pegada por el CEO el 2026-07-22. Veredicto: **APROBADO — 9.4/10. GO para merge**
> (6/6 jobs verdes — cumplido, run tras fix 823c343). 1 Baja no bloqueante
> (simetría D2 en aplicar-pendientes) — aplicada pre-merge.

---

COMPAS — Certificado I-PR1 Sprint 5: C3 Auto-clasificación (gate de código, PR #25)
Auditor: Kimi (auditor técnico senior independiente) · Fecha: 2026-07-22
Objeto: SOLICITUD(25).md + EVIDENCIA(15).md + PAQUETE(25).pdf — rama feat/c3-clasificacion, PR #25, commits e08f252+823c343, pre-merge
Antecedente: I-PLAN GO 9.3 (B-1/B-2 a incorporar). Umbral ≥ 9.0.

Veredicto: APROBADO — 9.4 / 10. GO para merge.

Los 11 tests exigidos + B-1/B-2 están cerrados con fidelidad total (412 passed local, +58; suite C3 de 77; real-mongo en CI con clasificación en carga real e índice parcial), la "normalización única" quedó garantizada estructuralmente (no solo por test), y el equipo volvió a mostrar honestidad de proceso: el run inicial de CI real-mongo falló porque el test de re-corrida usaba dos archivos idénticos y F-02 correctamente rechazó el hash — corrigieron el test (solape con archivo distinto, 823c343) y lo declararon abiertamente. 1 Baja menor (simetría D2 en aplicar-pendientes).

## 1. Los 11 tests exigidos — 11/11 [HECHO: diff + salidas]

| # | Exigido | Evidencia | ✔ |
|---|---|---|---|
| 1 | Normalización ambas direcciones + patrón 2 chars → 422 | normalizar_texto (NFD + sin diacríticos + lower + trim) es LA única función — usada por coincide() en AMBOS lados y por patron_normalizado (model_validator siempre derivado, no acepta valor divergente). Tests tilde↔sin-tilde y case en ambas direcciones + 422 por <3 (incl. post-normalización: "éé"→"ee" rechazado) | ✔ estructural |
| 2 | Precedencia determinista | elegir_regla puro, sorted((prioridad, str(_id))); tests menor-prioridad-gana, empate-por-id, re-corrida idéntica (real-mongo; solape→duplicado sin cambiar la asignación del original; contadores solo sobre nuevas) | ✔ |
| 3 | Unicidad patrón activo | Índice único parcial (patron_normalizado, tipo_flujo) con activa=true probado contra Mongo real: inactiva NO bloquea, segunda ACTIVA 'CAFÉ' contra 'cafe' → DuplicateKeyError. mongomock pierde partialFilterExpression — documentado; pre-check en service + índice real para la carrera (mismo criterio certificado del dedup de Sprint 1) | ✔ |
| 4 | D1 crear/editar + B-1 activar | _validar_rubro_destino (404/422/409) en crear y editar-destino; _validar_rubro_destino_para_activar (409) en AMBOS puntos de activación + re-chequeo de unicidad. Tests: otro-tipo 409, inactivo 422, reactivar-con-rubro-inactivo 409, aprobar-con-rubro-inactivo 409 | ✔ |
| 5 | D2 en carga + sin match + con match | Regla activa con rubro inactivo → fila a 'Por clasificar' + reglas_con_rubro_inactivo == ["cafeteria"] reportado; sin match → PC + regla_id=None; con match → rubro_id + regla_id escritos. Partición D1-ii probada: 'ABONO CUOTA SEMANAL' (ingreso) → Recaudo; 'PAGO ABONO PROVEEDOR' (egreso) → PC (la regla de ingreso jamás ve egresos) | ✔ |
| 6 | Reclasificación manual | mes cerrado → 409 (regla 4); inmutables §2.2 con assert explícito (fecha/valor/banco/id_banco intactos); evento transaccion.clasificada {anterior→nuevo}; inactivo 422 / tipo incoherente 409 / 404s; O1 con compensación (rubro revertido si el emit falla) | ✔ |
| 7 | proponer_regla + aprobar | Aprendida con activa=False forzado + regla.creada; la propuesta se valida ANTES de mutar (si es inválida, nada cambia); aprobar → regla.editada {activa: false→true, via:'aprobacion'}; manual→409, ya-activa→409 | ✔ |
| 8 | aplicar-pendientes | B-2 exacto como lo prescribí: docs sellados con clasificada_por + clasificada_at + regla_id; no toca meses cerrados (regla 4); idempotente (2.ª corrida 0/0); sin_match queda en PC | ✔ |
| 9 | RBAC + catálogo 36 + guardián | GET 200 los 4 roles; mutaciones 403 consulta/directivo; len == 36; PERMISSIONS + CANONICA actualizados | ✔ |
| 10 | Semilla | Lista congelada testeada (solo 'Abono'/'Recibido de' → Recaudo, origen=manual, creada_por='semilla' — PII-free por construcción); idempotente; fail-loud LookupError sin rubro destino; colisiones reportadas; URI por variable de entorno (patrón corregido de C1 aplicado) | ✔ |
| 11 | O1 fail-closed | Compensación probada en crear / aprobar / desactivar / clasificar (4 tests con emit parcheado) | ✔ |

## 2. Decisiones de implementación declaradas — todas aceptadas

- Semilla de egresos diferida: el mapeo real de comercios vive fuera del repo (dato real); en vez de inventar patrones (regla 7) o arriesgar PII, la semilla trae solo las 2 genéricas de ingreso y los comercios se crean desde la app (o extensión cuando el CEO comparta el mapeo). Reducción de alcance conservadora y declarada — entrega el valor inmediato (Recaudo, PRD M7) sin fabricar datos. ✔
- Reclasificación sin Idempotency-Key: naturalmente idempotente y no crea dinero ✔. aplicar-pendientes con reglas:gestionar (efecto masivo) vs reclasificación individual con cargas:gestionar — separación de autoridad sensata ✔.
- Contadores solo sobre las NUEVAS insertadas (los duplicados no se reclasifican) ✔ — la lectura correcta del ciclo F-02.
- tz_aware=True alineado en fixtures (regla 2) ✔.

## 3. Pasada adversarial sobre el código — notas

- La clasificación en carga carga reglas y rubros activos una vez por carga (no por fila) ✔; el reporte reglas_con_rubro_inactivo lista TODAS las reglas activas con rubro inactivo (estado de configuración, no solo filas afectadas) — fail-loud correcto ✔.
- reclasificar valida la propuesta antes de mutar; si la propuesta fallara después por carrera, la reclasificación ya quedó (con su evento) y el error es explícito — semántica aceptable (la acción primaria es legítima y trazada).
- Sin polizontes: motor/cierre/control/ciclo intactos (0 líneas); dedup/mes/valor/signo jamás tocados por la clasificación.

## 4. Baja (no bloqueante — 1 línea + assert)

**B-1 (simetría D2):** aplicar-pendientes salta correctamente las reglas con rubro inactivo (mismo elegir_regla), pero su respuesta solo trae {clasificadas, sin_match} — un operador que ve sin_match=50 no distingue "no hay regla" de "hay regla pero su rubro está inactivo". Incluir reglas_con_rubro_inactivo en la respuesta (como hace la carga). Puede ir en el primer follow-up; no amerita re-gate.

## 5. Respuesta a la pregunta del equipo

Sí — el código de C3 implementa fielmente el plan 9.3 + B-1/B-2: normalización única garantizada por construcción, precedencia determinista probada de punta a punta, D1/D2 en todas las vías (carga, CRUD, activación, reclasificación, aplicar-pendientes), rastro forense completo por documento, semilla sin PII y CR-S5 aplicado. Autorizo el merge de PR #25 con los 6/6 jobs verdes (la protección de rama lo exige; el run final tras el fix 823c343 debe quedar visible).

Post-merge: correr la migración de reglas en base viva (tras la de rubros, por el fail-loud); pendientes del programa: S4-00, S4-06, tardías (F-08), CR-001, pantalla de reglas (sin gate), la extensión de la semilla de egresos cuando el CEO comparta el mapeo real, C4 (ajuste de caja) en PLAN aparte — y el operativo hacia G3.

**Kimi — auditor técnico senior independiente. Veredicto: GO para merge — 9.4/10.**
