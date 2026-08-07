# SOLICITUD DE AUDITORÍA — E1 PR5-I: exposición del shape (meses_anclados + sin_mapear + mes_en_curso)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-08-07
**Plan padre:** `docs/COMPAS_PLAN_E1_Anclaje_a_la_Ejecucion.md` (pieza **P5**, §6) · **Criterio:** spec ejecución Parte V (**B13**) · **Decisión de shape (CEO 2026-08-07):** objeto rico para `mes_en_curso` (día + fecha + fórmula)
**Rama / PR:** `feat/e1-p5-exposicion-shape` · **PR #72** · commit `bca43a4`
**Spec/Plan:** `docs/superpowers/specs/2026-08-07-e1-p5-exposicion-shape-design.md` · `docs/superpowers/plans/2026-08-07-e1-p5-exposicion-shape.md`

## Qué hace

P5 expone en la respuesta de `GET /proyeccion` (compartida por `/preview` y `/impactos`) **el origen de cada cifra**, de forma **aditiva**: tres claves nuevas que el backend ya conocía pero no devolvía. Es el penúltimo eslabón de E1 antes del frontend (P6). No toca el catálogo, ni `MesControl`, ni el motor.

### Contrato (3 claves top-level nuevas)

```jsonc
"meses_anclados": { "2026-07": "cerrado", "2026-08": "en_ejecucion" }, // {} sin anclaje
"sin_mapear": ["Rubro sin concepto X"],                               // [] si nada
"mes_en_curso": {                                                     // null si no hay mes en_ejecucion
  "mes": "2026-08", "cargado_hasta": "2026-08-06", "dia": 6,
  "formula": "ejecutado + max(0, definido - ejecutado) por concepto"
}
```

### De dónde sale cada dato (perímetro intacto)

1. **`backend/app/proyeccion/ejecucion/guarda.py` — `rubros_sin_mapear` (nuevo, PURO).** Recorre los meses con ejecutado (cerrado + en ejecución), reusa `mapear_a_conceptos` sobre el snapshot del ejecutado y une (ordenado, dedup) los `.sin_mapear`. Aquí afloran R-1/R-2 parqueados. Sin Mongo. Antes esta información se computaba dentro de `_conceptos_egreso` y se **descartaba** (solo se tomaba `.conceptos`).
2. **`backend/app/proyeccion/ejecucion/loader.py` — `cargar_completitud_mes_en_curso` (nuevo, Mongo).** Para el mes `EN_EJECUCION` del horizonte: `cargado_hasta` = fecha máxima de transacción (`Transaccion.find(mes_id).sort(-fecha).limit(1)`; `fecha` ISO ordena cronológicamente por lexicografía), `dia` = su día, `formula` = constante (Regla A/D-08). `None` si ningún mes está en ejecución; `cargado_hasta`/`dia` en `None` si el mes existe pero aún no tiene tx. **Función aparte** de `cargar_anclas`: NO altera su contrato 3-tuple (los tests con `anclas_override` no cambian).
3. **`backend/app/proyeccion/service.py` — `AnclajeMeta` + cableado.** `_resultado_con` deja de descartar el dict de `marcas_origen`, computa `rubros_sin_mapear` y (si `anclas_override is None`) la completitud, y devuelve un `AnclajeMeta(meses_anclados, sin_mapear, mes_en_curso)` como 5º elemento. `_serializar(..., *, meta=None)` emite las 3 claves (vacías si `meta is None`). Propagada a `/impactos` (base + ajustada).

## Semántica preservada (candados)

- **R0 · `motor.py` cero diffs.** `anclar`, `lectura.py`, `reconciliacion.py` **sin tocar** (verificado `git diff --stat`). `MesControl` sin flag nuevo. **Catálogo de eventos sin crecer** (P5 no emite eventos).
- **Protege C-1:** las marcas (`meses_anclados`) son lectura pura; NO cambian `AnclaMes.estado`; el filtro D2 (`meses_anclados = frozenset(m for m,a in anclas.items() if a.estado == CERRADO)`) queda **literalmente inalterado**. Un sospechoso sigue anclado y excluido de D2.
- **Aditivo / foto sin ciclo:** sin `MesControl` → `meses_anclados={}`, `sin_mapear=[]`, `mes_en_curso=null` y el resto del payload byte-idéntico; los consumidores viejos ignoran las claves nuevas.
- **Dinero = Decimal** (los montos ya viajan como string vía `money_str`; las 3 claves nuevas son metadato, no montos crudos).

## Puntos a auditar con lupa

1. **`sin_mapear` sobre el snapshot correcto.** ¿Recorre bien los meses con ejecutado y reusa `mapear_a_conceptos` sin recomputar el mapeo dos veces ni disparar B12 fuera de sitio? (La llamada vive en `_resultado_con`, donde la taxonomía completa ya corrió; en el loader NO, para no acoplar B12 a los seeds mínimos.) Dedup/orden correctos.
2. **`mes_en_curso` (B13).** `sort(-fecha).limit(1)` da la fecha máxima (ISO); `dia = int(fecha[8:10])`. ¿Correcto el caso "mes en ejecución sin tx" (`cargado_hasta`/`dia` = None) y el `None` global sin mes en ejecución? ¿La función separada evita tocar el contrato de `cargar_anclas`?
3. **La marca NO contamina el régimen (C-1).** Verificar que `meses_anclados` (marcas) es solo lectura y que el `frozenset(... estado == CERRADO)` que alimenta D2 quedó igual; un sospechoso sigue excluido de D2.
4. **Aditividad real.** `_serializar` emite las 3 claves en TODAS sus llamadas (GET, preview, impactos base+ajustada) y en su forma vacía cuando no hay meta → foto sin ciclo idéntica salvo las 3 claves vacías.
5. **`anclas_override` y determinismo de tests.** Con override, la completitud se fija en `None` (evita Mongo); marcas y sin_mapear salen del override. ¿Coherente con los tests de pipeline?

## Evidencia local (ver `EVIDENCIA.md`)

- **Regresión completa:** 910 passed, 95 skipped, 0 fallos (§1).
- **Nuevos P5:** guarda 3 (sin_mapear) · loader mongomock 2 + real-mongo 1 (completitud) · pipeline 2 (meta) · endpoint 2 (foto sin ciclo + B13).
- **R0:** `motor.py` 0 diffs; perímetro `anclar`/`lectura`/`reconciliacion` 0 diffs (§4).
- **ruff:** `check` + `format --check` limpios (246 archivos).
- Dos capas Mongo para la consulta nueva (mongomock + real-mongo).

## Cumplimiento del DoD / reglas de CLAUDE.md

- Regla 1 (Decimal): ✅. Regla 4 (histórico inmutable): P5 no escribe. Regla 10 (motor): ✅ R0. Regla 11 (catálogo cerrado): ✅ no emite eventos.
- Plan E1 §6-P5 (shape aditivo + B13): ✅. Decisión CEO 2026-08-07 (objeto rico): ✅.
- TDD rojo→verde por pieza (documentado en `EVIDENCIA.md`).
