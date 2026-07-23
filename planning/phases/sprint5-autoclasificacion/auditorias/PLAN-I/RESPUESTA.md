# RESPUESTA — Kimi · I-PLAN Sprint 5: C3 Auto-clasificación de movimientos

> Pegada por el CEO el 2026-07-22. Veredicto: **APROBADO — 9.3/10. GO para construir con TDD.**

---

COMPAS — Auditoría I-PLAN Sprint 5: C3 Auto-clasificación de movimientos
Auditor: Kimi (auditor técnico senior independiente) · Fecha: 2026-07-22
Objeto: SOLICITUD(24).md + PAQUETE(24).pdf — sprint5-autoclasificacion · I-PLAN C3 (PLAN, pre-código)
Base: main con C1 mergeada (I-PR1 GO 9.4, merge 126ac29) + re-seed en prod (39 rubros, solo difs de orden). Contrato: COMPAS_NORTE, PROJECT (C3), MODELO §C3, Spec §1.9 / §1.5 (regla_id) / §319, CR-S5 declarado. Umbral ≥ 9.0.

Veredicto: APROBADO — 9.3 / 10. GO para construir con TDD.

El diseño es fiel a Spec §1.9/§319, los dos puntos que anuncié auditar (D1 coherencia de tipos, D2 guarda de inactivos) están bien resueltos por construcción, la precedencia es determinista, la semilla es PII-aware (Ley 1581), y CR-S5 sigue la gobernanza correcta. Sin hallazgos Medios/Altos. 2 Bajas a incorporar en TDD (sin re-auditoría de plan).

## 1. Los dos puntos anunciados en el certificado de C1

**D1 — coherencia tipo_transacción ↔ tipo_rubro por construcción ✔ RESUELTO.**
Tres capas que se cierran mutuamente: (i) la regla exige regla.tipo_flujo == rubro.tipo_flujo al crear/editar (409); (ii) la evaluación en carga está particionada por tipo_flujo — una regla de ingreso jamás se evalúa contra un egreso (así 'Abono' de ingreso no puede colarse a un egreso ni por patrón coincidente); (iii) si el rubro cambiara de tipo después, la B-1 de C1 ya lo impide (congelado al tener referencias — y la transacción clasificada ES una referencia). Es imposible clasificar un egreso en rubro de ingreso por regla, por carrera o por deriva posterior. Correcto.

**D2 — guarda de inactivos en reglas automáticas ✔ RESUELTO — y la decisión de NO desactivar en cascada es la correcta.**
Regla activa con rubro inactivo → se salta, la fila cae a 'Por clasificar' (regla 7: no se adivina) y la carga reporta reglas_con_rubro_inactivo (fail-loud informativo, patrón B-4). La alternativa (desactivar la regla en cascada al desactivar el rubro) destruiría configuración sin orden explícita y sorprendería al reactivar el rubro; el skip-and-report mantiene el sistema consistente y reversible. De acuerdo sin reservas.

## 2. Respuesta a D3 y D4

**D3 — sin evento por transacción en clasificación masiva: SUFICIENTE para el forense ✔.**
El rastro completo queda: regla_id persistido en cada Transaccion (qué regla) + carga_id (en qué lote) + regla.creada (quién y cuándo la creó) + contadores {clasificadas, por_clasificar} en carga.completada. La pregunta forense "¿por qué esta transacción está en este rubro?" tiene respuesta completa por documento. Un evento por transacción sería ruido duplicado (cientos por carga) sin información adicional. La clasificación manual sí emite transaccion.clasificada (v1.0, sin CR) — asimetría correcta: el acto humano individual se audita; el automático masivo se audita por lote + por regla.

**D4 — aplicar-pendientes sin evento propio: ACEPTABLE SOLO CON UNA CONDICIÓN (B-2).**
A diferencia de la carga (que tiene su ancla agregada carga.completada), aplicar-pendientes es una mutación masiva sin ancla: si solo queda regla_id, el forense sabe qué regla aplicó pero no quién disparó el lote ni cuándo. La respuesta con contadores es efímera. Condición para no exigir el evento agregado: que cada transacción reclasificada quede sellada con clasificada_por + clasificada_at (además de regla_id) — con eso el rastro por documento es completo (quién/cuándo/qué regla) y reglas.aplicadas sobra. Si no se sellan, exijo el evento agregado (CR-S5 pasaría a +4). Mi recomendación: sellar clasificada_por/at — más barato y más granular.

**D5 — aprendidas solo-propuesta + aprobación: de acuerdo ✔.** Fiel a §1.9 ("requiere aprobación, nunca auto-activada"): la única vía de creación de aprendidas fuerza activa=false, y la activación exige reglas:gestionar (vía /aprobar o PATCH activa:true — misma autoridad, el invariante "nunca auto-activada" se sostiene porque ninguna vía automática la activa). Diferir la minería de reclasificaciones repetidas es correcto: no es la capa predictiva del norte y aún no hay datos.

## 3. Verificación del resto de los puntos "con lupa"

- Precedencia determinista ✔: prioridad ascendente + desempate por _id (estable); misma carga → misma asignación, re-corrida idempotente. Unicidad de patrón activo ✔: índice parcial único (patron_normalizado, tipo_flujo) con activa=true — dos activas idénticas = ambigüedad = regla 7; duplicados desactivados permitidos (correcto). patron mínimo 3 caracteres ✔ (guarda contra match-all).
- Normalización única compartida ✔ declarada — es EL punto delicado de la pieza: la misma función (case-insensitive + sin tildes) debe normalizar el patrón al escribir la regla y la descripción al matchear; si divergieran, fallo silencioso. Test exigido en el gate: tilde↔sin-tilde y mayúsculas↔minúsculas en ambas direcciones.
- Regla 4 en reclasificación ✔: mes cerrado → 409 (el histórico congelado no se reclasifica); solo mutan rubro_id/clasificada_por/at — fecha, valor, banco, id_banco intocables, que es exactamente la cláusula de inmutabilidad de Spec §2.2 ("solo cambia su rubro_id y sus vínculos de conciliación"). El dedup no se toca.
- Semilla sin PII ✔: solo patrones de comercios/servicios, NUNCA nombres de personas (Ley 1581) — los abonos de clientes los cubren las genéricas de ingreso ('Abono', 'Recibido de' → 'Recaudo', prioridad alta — coherente con PRD M7). $setOnInsert + reporte de colisiones + URI por entorno (patrón corregido en C1). Punto de verificación para el gate: reglas de la semilla con origen=manual (son curaduría, no aprendizaje) y fail-loud si un rubro destino del mapeo no existe.
- CR-S5 ✔: catálogo 33→36 (regla.creada/editada/desactivada) + reglas:gestionar={financiero, admin} — simetría exacta con CR-S4; completitud y guardián actualizados. Los contadores nuevos en carga.completada son metadata de un evento existente: no requieren CR.
- Semántica preservada ✔: la clasificación solo asigna rubro_id/regla_id; motor §1.4.1, cierre, conciliación y Vista Control no cambian — reciben mejor insumo.

## 4. Bajas (incorporar en TDD; las verifico en I-PR1)

- **B-1 (activación):** re-validar D1 en los dos puntos de activación — POST /{id}/aprobar y PATCH activa:true: el rubro pudo desactivarse ENTRE la creación/propuesta de la regla y su activación. Hoy D2 contiene el efecto (skip-and-report), pero la activación debería exigir rubro existente + activo + tipo coherente y devolver 409 si no — así el estado "regla activa → rubro inactivo" solo existe por desactivación posterior del rubro, nunca por decisión de activación. 3 líneas + 1 test.
- **B-2 (D4):** aplicar-pendientes sella clasificada_por + clasificada_at por documento (ver §2-D4); si no, evento agregado (CR-S5 +4).

## 5. Tests que el gate de código (I-PR1) esperará ver

- Normalización: patrón "Café" matchea "CAFETERIA LA 14" y viceversa (tildes/case, ambas direcciones); patrón de 2 caracteres → 422.
- Precedencia: dos reglas que matchean la misma descripción → gana la de menor prioridad; empate → _id; re-corrida de la misma carga → asignación idéntica.
- Unicidad: segunda regla activa con mismo (patron_normalizado, tipo_flujo) → 409; desactivada no cuenta.
- D1: crear/editar regla con rubro de otro tipo → 409; con rubro inactivo → 409/422; B-1: aprobar/activar con rubro inactivo → 409.
- D2 en carga: regla activa con rubro inactivo → la fila cae a 'Por clasificar' + la carga reporta reglas_con_rubro_inactivo; sin match → 'Por clasificar'; con match → rubro_id + regla_id escritos.
- Reclasificación manual: mes cerrado → 409; rubro inactivo o tipo incoherente → 409/422; OK → transaccion.clasificada con {rubro_anterior→nuevo}; fecha/valor/banco/id_banco intactos (assert explícito).
- proponer_regla:true → aprendida con activa=false forzado + regla.creada; aprobar → regla.editada {activa: false→true, via:'aprobacion'} (sin evento extra).
- aplicar-pendientes: solo 'Por clasificar' de meses NO cerrados; idempotente; B-2: docs sellados con clasificada_por/at + regla_id; contadores en la respuesta.
- RBAC: GET 200 los 4 roles; mutaciones 403 consulta/directivo, OK financiero/admin; guardián + completitud del catálogo en 36.
- Semilla: idempotente, sin PII (aserción explícita sobre la lista), origen=manual, reporte de colisiones, fail-loud si falta un rubro destino.
- O1 fail-closed (estándar C1/B-5): compensación al fallar el emit en crear/editar/desactivar/aprobar.

**Camino: construir con TDD incorporando B-1/B-2 → I-PR1 con esos tests → merge. Sin re-auditoría de plan.** Nota de gobernanza sana que registro sin puntuar: S4-07/S4-08 ya están en el tracker con ID propio y G3 intacto.

**Kimi — auditor técnico senior independiente. Veredicto: GO — 9.3/10.**
