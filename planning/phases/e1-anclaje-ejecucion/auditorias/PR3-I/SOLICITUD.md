# SOLICITUD DE AUDITORÍA — E1 PR3-I: precedencia motor→E1→D2 + loader + exclusión D2

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-08-06
**Plan padre:** `docs/COMPAS_PLAN_E1_Anclaje_a_la_Ejecucion.md` (pieza **P3**, §6) · **Contratos:** plan §3 (precedencia + composición COCK-09×E1), spec ejecución Parte V (B7/B8/B11 + candado de no-regresión)
**Rama / PR:** `feat/e1-p3-precedencia-ventana-d2` · **PR #70** · commit `f8e21d1`

## Qué hace

P3 **activa E1 en producción**: enchufa la capa de anclaje (P2) en la tubería de proyección **antes** de la reconciliación de obligaciones (D2), y hace que la ventana de D2 **excluya** los meses que E1 ya ancló, para que ningún peso se cuente dos veces. Incorpora las **2 precisiones del arquitecto** (mover el resolver de neutros al dominio; probar el régimen "presupuesto").

1. **`backend/app/proyeccion/ejecucion/loader.py` (nuevo — la ÚNICA capa Mongo de E1).** `cargar_anclas(mes_inicio, horizonte) -> (anclas, rubros, neutros_ids)`. Traduce el estado del ciclo (`MesControl.estado`) al **régimen de anclaje** del plan §1:
   - `CERRADO` → `'cerrado'`: ejecutado real por rubro (`_egresos_por_rubro`) + `ingreso_real` (excluye neutros).
   - `EN_EJECUCION` → `'en_ejecucion'`: ejecutado real + presupuesto definido vigente (Regla A la resuelve `anclar`).
   - otro estado con líneas `vigente` y `monto_definido > 0` → `'presupuesto'`: solo el definido.
   - sin `MesControl` / futuro sin definido → **omitido** (motor intacto).
   - Reusa queries ya probadas (`control._egresos_por_rubro`, `PresupuestoLinea` vigente, `metas_ingreso.ingreso_real`); `lectura.py`/`service.py` siguen puros.

2. **`backend/app/proyeccion/service.py` `_resultado_con` (cableado).** Orden `motor → EJECUCIÓN (E1) → OBLIGACIONES (D2) → IMPACTOS (D1)`: tras `proyectar()`, si hay `anclas` → `r = _kpis_a_resultado(anclar(...))` y `meses_anclados = frozenset(anclas)`; luego `reconciliar(r, facturas, caja_min, meses_anclados=meses_anclados)`. Nuevo `anclas_override` (espejo de `facturas_override`) para tests deterministas. Docstrings de composición COCK-09×E1.

3. **`backend/app/obligaciones/reconciliacion.py` (exclusión).** `reconciliar(..., *, meses_anclados: frozenset[str] = frozenset())`: los pagos reales que caen en meses anclados se excluyen de la ventana; el neteo y la reescritura por concepto **saltan** los meses anclados. **Default vacío ⇒ serie idéntica a hoy** (candado de no-regresión de D2, gratis).

4. **`backend/app/domain/rubros_neutros.py` (precisión 1 del arquitecto).** Se **mueve** el resolver `_ids_rubros_neutros` aquí (junto al set `RUBROS_NEUTROS_INGRESO_REAL`): una verdad, un lugar. `metas_ingreso.service` lo **re-exporta** (no rompe importadores; el script y `ingreso_real` siguen funcionando).

## Cambios de valores esperados (verificados)

| Caso | Antes | Después |
|---|---|---|
| Proyección sin anclaje ni facturas | base del motor | **idéntica bit a bit** (E1 no-op con `anclas` vacío; candado) |
| Mes anclado + factura que paga ahí | D2 neteaba/aplicaba | **D2 lo salta**; E1 fija ese mes; Auteco = paramétrico del motor |
| Mes NO anclado + factura | D2 reconcilia | **igual que hoy** (pago real) |
| `_ids_rubros_neutros` | vivía en `metas_ingreso` | **movido a `domain/rubros_neutros`**; metas re-exporta (mismo objeto) |

## Semántica preservada (NO cambia en este PR)

- **R0 · `motor.py` cero diffs** (verificable: no aparece en el diff).
- **Golden-master intacto** · **compuerta IVA** sin tocar · **catálogo de eventos** sin crecer (E1 lee, no emite).
- **Auteco 100% en D2:** E1 NO toca `pago_inventario`/`fondeo`/`adelanto` (los conserva del motor); D2 solo reconcilia los meses NO anclados. Verificado en B11.
- **Dinero = Decimal** en todo.

## Puntos a auditar con lupa

1. **No-colisión E1×D2 (el riesgo #1 del plan).** Con facturas + pagos + meses anclados simultáneos, ningún peso doble: la ventana de D2 excluye los anclados (`meses_pago` filtra `m not in meses_anclados`; el neteo y el paso-3 saltan los anclados). Verificar que `meses_anclados = frozenset(anclas)` cubre exactamente lo que `anclar` ancló (mismos meses del horizonte, regímenes anclables) — B7 (puro) + B8/B11 (integración).
2. **El candado de no-regresión.** `meses_anclados` vacío ⇒ D2 idéntico a hoy (mismo default). Verificar que el parámetro es aditivo y que sin anclaje la serie no cambia (candado puro + integración).
3. **La traducción estado→régimen (loader).** `EstadoMes.CERRADO/EN_EJECUCION` → régimen directo; otro estado con `monto_definido>0` vigente → `'presupuesto'` (el definido se llena al acotar, ANTES de aprobar → el régimen NO está dormido); sin definido → omitido. Verificar que se reusan las queries de prod (`_egresos_por_rubro` `$group`, `PresupuestoLinea` vigente) sin agregaciones nuevas.
4. **La composición COCK-09×E1 (sin doble anclaje).** COCK-09 ancla la caja inicial (escalar); E1 ancla las LÍNEAS y re-acumula desde ahí. Verificar que el orden en `_resultado_con` es motor→E1→D2 y que E1 corre antes de D2.
5. **El movimiento del resolver de neutros (precisión 1).** `_ids_rubros_neutros` ahora en `domain/rubros_neutros`; `metas_ingreso` re-exporta el MISMO objeto (test lo verifica). Sin `In`/`Rubro` colgando en metas (ruff limpio). ¿Inocuo para `ingreso_real` y el script?

## Evidencia local

- **pytest E1 + relacionados:** **43 passed, 1 skipped** (el skip es la variante real-mongo del loader; corre en CI `backend-real-mongo`). Ver `EVIDENCIA.md`.
- **Regresión completa del backend:** **888 passed, 92 skipped, 0 fallos**.
- **ruff:** `All checks passed!` + `format --check` limpio sobre `app/` y `tests/`.
- **R0:** `git diff origin/main -- backend/app/proyeccion/motor.py` → **0 líneas**.

## Cambio a un módulo ya auditado (declarado)

`test_proyeccion_endpoints.py::_seed_mes_cerrado_con_ingreso` ahora siembra los **9 códigos del mapeo** (rubros de C1). Motivo: al activar E1, `anclar` valida la taxonomía completa (**B12 fail-loud**, aprobado en P1) para el mes cerrado del rolling forecast; la semilla mínima previa (2 rubros sin código) hacía 500. En PROD los 9 códigos existen (commit 7ed35a2). Es un ajuste de **semilla de test**, no de lógica.

## Cumplimiento del DoD / reglas de CLAUDE.md

- Regla 1 (Decimal): ✅. Regla 4 (histórico inmutable): E1 no escribe, solo lee/proyecta. Regla 8 (transacciones): no aplica (lectura pura). Regla 10/motor (fórmula intacta): ✅ R0. Regla 11 (catálogo cerrado): ✅ no emite eventos.
- Plan E1 §3 (precedencia + composición): ✅. §4 (garantías): ✅ R0, golden intacto, IVA apagada.
- Dos capas de test: mongomock (`test_e1_loader`) + real-mongo (`test_e1_loader_realmongo`, `$group` de `_egresos_por_rubro`).
- TDD: cada pieza rojo→verde (documentado en la sesión); el diff no trae código sin test previo.
