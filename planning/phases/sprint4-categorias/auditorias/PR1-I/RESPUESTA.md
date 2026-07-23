# RESPUESTA — Kimi · I-PR1 Sprint 4: C1 Categorías administrables (gate de código, PR #24)

> Pegada por el CEO el 2026-07-22. Veredicto: **APROBADO — 9.4/10. GO para merge**
> (condiciones: 6/6 jobs CI verdes — cumplida, run 29968945469 — y B-1 nueva
> aplicada a la migración antes de correrla en prod).

---

COMPAS — Certificado I-PR1 Sprint 4: C1 Categorías administrables (gate de código, PR #24)
Auditor: Kimi (auditor técnico senior independiente) · Fecha: 2026-07-22
Objeto: SOLICITUD(23).md + EVIDENCIA(14).md + PAQUETE(23).pdf — rama feat/c1-rubros, PR #24, commit 9020932, pre-merge
Antecedente: I-PLAN GO 9.2 (5 Bajas a incorporar en TDD, sin re-auditoría de plan). Umbral ≥ 9.0.

Veredicto: APROBADO — 9.4 / 10. GO para merge (condición: job backend del CI en verde — la protección de rama ya lo exige; ver §4).

Los 9 tests exigidos + las 5 Bajas están cerrados con fidelidad total (suite nueva de 38 tests de endpoints + 71 de C1 en conjunto; 354 passed local; real-mongo verde en el run 29968740989), el CR-S4 está aplicado exactamente como se declaró, y mi punto de verificación quedó respondido con hechos. 1 Baja nueva (eco de un hallazgo viejo) y 1 condición de merge.

## 1. Los 9 tests exigidos — 9/9 [HECHO: diff + salidas]

| # | Exigido | Evidencia | ✔ |
|---|---|---|---|
| 1 | POST orden=máx(grupo)+1 + rubro.creado; duplicado → 409 | test_post_crea_con_orden_max_grupo_mas_1_y_emite_creado (orden 3, evento con entidad_id + metadata) + test_post_duplicado_409 + extras: grupo vacío arranca en 1, mismo nombre en otro grupo OK (índice es compuesto) | ✔ |
| 2 | PATCH nombre/orden → rubro.editado {campo: anterior→nuevo}; duplicado → 409 | test_patch_nombre_orden_emite_editado_con_cambios (metadata exacta por campo) + test_patch_nombre_duplicado_409 + sin-cambios → 422 (vacío y mismo-valor) + 404/id-inválido 422 | ✔ |
| 3 | B-1: tipo_flujo congelado por referencias | Los 3 tests exactos pedidos: con transacción → 409 · con línea sin movimientos → 409 · sin referencias → 200; + nombre editable aun con referencias. _tiene_referencias con proyección cruda {_id:1} (existencia, sin pagar parse) | ✔ |
| 4 | Sistema inmutable → 409 parametrizado | test_patch_sistema_409 + test_desactivar_sistema_409 sobre los 3 rubros (y verifica que activo sigue true tras el 409) | ✔ |
| 5 | B-2: alcance de la baja | (a) test_clasificar_hacia_rubro_inactivo_422 (guarda en crear_transaccion_manual, aplicará a C3) · (b) test_excluye_rubros_inactivos — con 9M de historia ejecutada, el inactivo NO recibe línea (la baja no gotea) · (c) test_linea_de_rubro_inactivo_se_conserva (Vista Control muestra definido 800k/ejecutado 300k tras la baja). Nota ingreso-sin-línea declarada en docstring | ✔ |
| 6 | RBAC exacto | 403 parametrizado consulta+directivo en las 3 mutaciones; 201 financiero+admin; GET 200 los 4 roles; PERMISSIONS + CANONICA del guardian actualizados | ✔ |
| 7 | Re-seed idempotente + reporte B-4 | 1.ª corrida 34, 2.ª 0 sin duplicar; edición del Admin sobrevive (Cafetería orden 77); test_seed_rubros_reporte_de_colisiones (insertados 33 + 1 colisión con existente vs semilla; corrida limpia 0/34); migración imprime "⚠ DIFIERE → verificar" campo a campo | ✔ |
| 8 | Reactivación (B-3) | PATCH activo:true → rubro.editado {activo: false→true} (sin 34.º evento, CR-S4 queda +2); PATCH activo:false → 422 apuntando a /desactivar (una sola vía de baja) | ✔ |
| 9 | B-5 fail-closed O1 | 3 tests de compensación con emit_audit parcheado a excepción: creado borrado, edición revertida, desactivar revertido — patrón O1 completo (mutar→emitir→compensar→propagar) | ✔ |

## 2. CR-S4 y mi punto de verificación

- Catálogo 31→33 [HECHO]: rubro.creado + rubro.editado añadidos; test de completitud actualizado (len == 33). Mi punto de verificación respondido: rubro.desactivado ya venía desde v1.0 (está en el enum y el test de eventos clave lo confirma) → CR-S4 es +2, no +3. ✔
- rubros:gestionar = {financiero, admin} en permissions.py + tabla CANONICA del guardian — consistencia config↔test↔§4.1 (vía CR). ✔
- Decisiones de implementación declaradas (no estaban en el plan) — todas correctas: sin Idempotency-Key (no es dinero §1.12; el índice único hace inocuo el replay → 409); desactivar ya-inactivo → 409 explícito; los 3 de sistema en grupo otros en la semilla nueva (misma llave que prod → sin duplicados); 'Arriendos' en OTROS per MODELO.md con el doc viejo intacto (D3 + B-4 lo reporta).

## 3. Re-seed a la taxonomía real — verificación de la semilla [HECHO: conteo + diff]

34 = 31 reales de MODELO.md + 3 sistema, con test de reparto por grupo (costo 3 · operación 13 · nómina 5 · deudas 3 · otros 10 = 7+3) y órdenes consecutivos 1..34. El diff old→new es coherente con MODELO.md: entran Viajes corporativos, Grúas y traslados, Dotación empleados, Freelance, Asuntos legales; 'Arriendos' se mueve a OTROS (el viejo en operacion queda para que el CEO depure — test test_semilla_arriendos_vive_en_otros lo fija); salen genéricos que ya no manda el modelo (Renting, Garantía cupo, Planillas nuevas…), que en prod quedan activos para depuración desde la app (D3). $setOnInsert intacto: no pisa ediciones (probado).

## 4. Baja nueva + condición de merge

- **B-1 (Baja — eco de H-03 de Sprint 0):** la migración 20260722_reseed_rubros_reales.py toma la URI de Mongo por argv (python migrations/... "<MONGODB_URI>"). Es el mismo patrón de exposición que el H-03 que corregimos en Sprint 0 (credenciales visibles en ps y en el historial del shell). Es un script operacional de una sola corrida (no código desplegado) — por eso Baja y no Media — pero la higiene certificada manda: leer la URI de variable de entorno (o read -s), 3 líneas. Aplicar antes de correrla en prod y dejarlo como patrón para futuras migraciones.
- **Condición de merge:** en el momento del empaquetado, el job backend del CI estaba en curso (los otros 5 verdes, incl. backend-real-mongo con el índice único contra el replica set). La protección de rama con required checks (certificada en Sesión 3) ya impide mergear sin él; la evidencia local (354 passed) es sólida. Mergear solo con los 6/6 verdes.

## 5. Respuesta a la pregunta del equipo

Sí — el código de C1 implementa fielmente el plan aprobado + las 5 Bajas, con auditoría fail-closed probada en las 3 mutaciones, RBAC exacto con negativos parametrizados, y re-seed verificable con reporte de colisiones. Autorizo el merge de PR #24 con los 6/6 jobs verdes y la B-1 (URI por entorno) aplicada a la migración antes de ejecutarla en prod.

Post-merge: correr la migración en base viva (con el reporte B-4 en mano para la depuración del CEO), y quedan de Sprint 4: S4-00, S4-06 (TOCTOU + step-up test), tardías (F-08), CR-001 ExtractoMensual, el frontend de administración de categorías (sin gate) y el PLAN de C3 auto-clasificación (gate aparte — allí auditaré la coherencia tipo_transacción↔tipo_rubro y la guarda de inactivos en reglas automáticas).

**Kimi — auditor técnico senior independiente. Veredicto: GO para merge — 9.4/10.**
