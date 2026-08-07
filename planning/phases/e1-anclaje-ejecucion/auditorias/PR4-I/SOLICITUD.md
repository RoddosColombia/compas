# SOLICITUD DE AUDITORÍA — E1 PR4-I: guarda B10 + PASO 0 (A2) + B-1

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-08-07
**Plan padre:** `docs/COMPAS_PLAN_E1_Anclaje_a_la_Ejecucion.md` (pieza **P4**, §6) · **Brief:** etapa59 (CEO 2026-08-05: la confirmación ES el cierre — FIX-J; el mes anómalo se ancla igual, solo se MARCA) · **Contratos:** spec ejecución Parte V (B10, A2) + candados C-1/B1
**Rama / PR:** `feat/e1-p4-guarda-b10` · **PR #71** · commit `a71a787`

## Qué hace

P4 añade la **guarda anti-mes-mal-cargado** sobre E1 (ya activo en prod tras P3), sin bloquear el anclaje y sin tocar el catálogo/MesControl.

1. **`backend/app/proyeccion/ejecucion/guarda.py` (nuevo, PURO).** Marca B10:
   - `UMBRAL_SOSPECHA_EJECUTADO = Decimal("0.5")`.
   - `es_ejecutado_anomalo(ejecutado, definido, *, rubros, neutros_ids) -> bool`: sobre los 5 conceptos anclados (`_conceptos_egreso`, sin Auteco ni `neto`), E = Σ ejecutado, D = Σ definido; True si `D > 0 and E < 0.5×D` (estricto; `E==0.5×D` y `D==0` → False).
   - `marcas_origen(anclas, *, rubros, neutros_ids) -> dict[str,str]`: `"cerrado" | "cerrado_sospechoso" | "en_ejecucion" | "presupuesto"` (vocabulario del shape P5). Solo el régimen cerrado puede volverse sospechoso.

2. **`backend/app/proyeccion/ejecucion/loader.py` (PASO 0 A2 + definido-para-cerrado).**
   - **PASO 0:** `dirty_ids` = rubros `es_sistema` que NO son clasificables (`RUBROS_SISTEMA_CLASIFICABLES`) ni neutros (set derivado de la taxonomía ya cargada, sin query extra). Para cada mes candidato, `_rubros_ofensores(mes_id, dirty_ids)` (find `In` sobre `rubro_id`) cuenta txs a esos rubros; si ≥1 → el mes **NO se ancla** (cae al motor) + log estructurado. Alcance **por-mes**.
   - **definido para cerrados:** el loader ahora trae `definido_por_rubro_id` también para meses cerrados. `anclar` lo **IGNORA** en cerrado (test de inercia); solo alimenta la marca B10.

3. **`backend/app/proyeccion/service.py` `_resultado_con` (observabilidad B10).** Tras `anclar`, computa `marcas_origen` y loguea los `cerrado_sospechoso` (WARNING estructurado). **No expone nada en la respuesta** (eso es P5).

## Hallazgo sobre la Pieza 3 (B-1) — NO implementada, con causa raíz

El brief pedía subir `cargar_anclas` a una vez por request y pasar `anclas_override` a "cada `_resultado_con`". Verifiqué **todos** los call-sites: en la arquitectura actual **cada request llama `_resultado_con`/`cargar_anclas` exactamente una vez** (`proyectar_vigente`, `valles_vigente`, `proyectar_impactos`, `resolver`, `simular_plazo`, `comparar_vigente`; los solvers `techo_gasto`/`goal_seek`/`punto_de_quiebre` bisectan **en memoria** sobre el `r` ya calculado, no re-llaman). No existe la vía "varios `_resultado_con` por request" que el hoisting arreglaría → sería un **no-op**. El 3× real es **entre requests HTTP** (el front pide base/optimista/pesimista por separado), que solo se resolvería con un **cache de proceso con TTL** (con su riesgo de staleness — decisión aparte). **B-1 se difiere** con esta causa raíz declarada; queda a decisión del CEO/arquitecto si se quiere el cache TTL como ítem de perf separado.

## Semántica preservada (NO cambia)

- **R0 · `motor.py` cero diffs.** `anclar`, `lectura.py`, `reconciliacion.py` **sin tocar**. `MesControl` sin flag nuevo. **Catálogo de eventos sin crecer** (P4 no emite eventos; solo log).
- **Protege C-1:** la marca `cerrado_sospechoso` NO cambia `AnclaMes.estado` (sigue `"cerrado"` → D2 lo sigue excluyendo). La marca vive solo en el mapa.
- **Candado B1:** sin anclas, todo sigue bit a bit. **Inercia:** `anclar` en cerrado ignora el `definido` (salida idéntica con `{}` o poblado).
- **Dinero = Decimal.**

## Puntos a auditar con lupa

1. **La regla B10 y sus fronteras.** `D>0 and E<0.5×D` estricto; `E==0.5×D` y `D==0` → no marca. E,D sobre los 5 conceptos anclados vía `_conceptos_egreso` (sin Auteco ni neto). ¿Correcta la comparación estricta y el caso `D==0`?
2. **PASO 0: el set `dirty_ids`.** `es_sistema and nombre ∉ RUBROS_SISTEMA_CLASIFICABLES and id ∉ neutros`. ¿Cubre exactamente "sistema sucio"? Verificar que 'Por clasificar'/'Recaudo de cartera'/'Tránsito Wava'/neutros NO disparan y que el alcance es por-mes (un mes sucio no tumba los demás).
3. **La marca NO contamina el régimen (protege C-1).** `AnclaMes.estado` intacto; `meses_anclados` de D2 sigue = solo cerrados (incl. sospechosos). Verificar que un sospechoso sigue excluido de D2 y anclado.
4. **Inercia del `definido` en cerrado.** El loader lo trae, `anclar` lo ignora. Test de igualdad bit a bit.
5. **Observabilidad sin efecto.** El log B10 vive en `_resultado_con` (donde ya corre la taxonomía completa, evita acoplar B12 al loader); PASO 0 loguea en el loader (pre-anclaje, sin B12). ¿Separación correcta?

## Evidencia local

- **pytest E1 + relacionados:** ver `EVIDENCIA.md`. Nuevos: guarda (6), loader PASO 0/definido-cerrado (3), pipeline B10 log (1), inercia (1), loader real-mongo PASO 0 (1, `requires_real_mongo`).
- **Regresión completa del backend:** ver `EVIDENCIA.md` (§1).
- **ruff:** `All checks passed!` + `format --check` limpio. **R0:** `motor.py` 0 diffs.
- Dos capas Mongo para la query nueva de PASO 0 (mongomock + real-mongo).

## Cumplimiento del DoD / reglas de CLAUDE.md

- Regla 1 (Decimal): ✅. Regla 4 (histórico inmutable): P4 no escribe. Regla 11 (catálogo cerrado): ✅ no emite eventos. Regla 10/motor: ✅ R0.
- Plan E1 §6-P4 (guarda + PASO 0): ✅. Decisión CEO 2026-08-05 (marca, sin flag ni evento): ✅.
- TDD rojo→verde por pieza (documentado). B-1 diferida con causa raíz declarada.
