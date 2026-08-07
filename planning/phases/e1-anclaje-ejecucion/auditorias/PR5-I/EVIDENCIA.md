# EVIDENCIA — E1 PR5-I (PR #72, commit `bca43a4`)

Diff real + salidas de tests locales. Rama `feat/e1-p5-exposicion-shape` sobre `main`.

## 1. Regresión completa del backend

```
$ cd backend && python -m pytest -q
910 passed, 95 skipped, 5301 warnings in 480.47s (0:08:00)
```

Los 95 skipped son las suites `requires_real_mongo` (no hay Mongo real en local; CI las corre). Antes de P5: 901 passed. Los 9 nuevos son de P5.

## 2. Subconjunto E1 focalizado (los archivos tocados por P5)

```
$ python -m pytest tests/test_e1_guarda.py tests/test_e1_loader.py \
    tests/test_e1_loader_realmongo.py tests/test_e1_pipeline.py \
    tests/test_proyeccion_endpoints.py -q
36 passed, 3 skipped, 437 warnings in 16.51s
```

Desglose de los tests NUEVOS de P5:
- **`test_e1_guarda.py` (+3):** `rubros_sin_mapear` reporta rubro con movimiento sin concepto (R-2/4040); `[]` cuando todo mapea; dedup/orden entre meses.
- **`test_e1_loader.py` (+2, mongomock):** completitud toma la fecha máxima; `None` sin mes en ejecución.
- **`test_e1_loader_realmongo.py` (+1, `requires_real_mongo`):** `sort(-fecha).limit(1)` da la fecha máxima real.
- **`test_e1_pipeline.py` (+2):** `_resultado_con` expone `AnclajeMeta` (meses_anclados + sin_mapear); meta vacía sin anclaje.
- **`test_proyeccion_endpoints.py` (+2):** foto sin ciclo → 3 claves vacías + resto presente; B13 → `mes_en_curso` con completitud + fórmula y `meses_anclados["2026-08"]=="en_ejecucion"`.

## 3. TDD rojo→verde (documentado por pieza)

1. **`rubros_sin_mapear`** — RED: `ImportError: cannot import name 'rubros_sin_mapear'`. GREEN: 9 passed en `test_e1_guarda.py`.
2. **`cargar_completitud_mes_en_curso`** — RED: `ImportError: cannot import name 'cargar_completitud_mes_en_curso'`. GREEN: 10 passed (mongomock) + real-mongo skip.
3. **`AnclajeMeta` + cableado** — RED: `ImportError: cannot import name 'AnclajeMeta'`. GREEN: 6 passed en `test_e1_pipeline.py`.
4. **Endpoint** — el test de foto sin ciclo pasó de una; el de B13 verde por construcción (Task 3 ya cableó las claves). 2 passed.

## 4. R0 y perímetro (git diff --stat vs main)

```
$ git diff --stat origin/main -- backend/app/proyeccion/motor.py
   (vacío — motor.py CERO diffs)

$ git diff --stat origin/main -- backend/app/proyeccion/ejecucion/service.py \
    backend/app/proyeccion/ejecucion/lectura.py backend/app/obligaciones/reconciliacion.py
   (vacío — anclar/lectura/reconciliacion INTACTOS)
```

Diff total del PR (solo P5):

```
 backend/app/proyeccion/ejecucion/guarda.py | 25 ++++++++-
 backend/app/proyeccion/ejecucion/loader.py | 33 ++++++++++++
 backend/app/proyeccion/service.py          | 80 +++++++++++++++++++--------
 backend/tests/test_e1_guarda.py            | 54 +++++++++++++++++++
 backend/tests/test_e1_loader.py            | 37 ++++++++++++-
 backend/tests/test_e1_loader_realmongo.py  | 37 ++++++++++++-
 backend/tests/test_e1_pipeline.py          | 46 ++++++++++++++--
 backend/tests/test_proyeccion_endpoints.py | 87 ++++++++++++++++++++++++++++++
 8 files changed, 369 insertions(+), 30 deletions(-)
```

## 5. Lint

```
$ python -m ruff check .            → All checks passed!
$ python -m ruff format --check .   → 246 files already formatted
```

## 6. Diff de CÓDIGO (real)

```diff
diff --git a/backend/app/proyeccion/ejecucion/guarda.py b/backend/app/proyeccion/ejecucion/guarda.py
index 3c23efb..61cfc7d 100644
--- a/backend/app/proyeccion/ejecucion/guarda.py
+++ b/backend/app/proyeccion/ejecucion/guarda.py
@@ -19,7 +19,7 @@ from __future__ import annotations
 
 from decimal import Decimal
 
-from app.proyeccion.ejecucion.lectura import RubroInfo
+from app.proyeccion.ejecucion.lectura import RubroInfo, mapear_a_conceptos
 from app.proyeccion.ejecucion.service import CERRADO, AnclaMes, _conceptos_egreso
 
 UMBRAL_SOSPECHA_EJECUTADO = Decimal("0.5")
@@ -66,3 +66,26 @@ def marcas_origen(
         else:
             marcas[mes] = a.estado
     return marcas
+
+
+def rubros_sin_mapear(
+    anclas: dict[str, AnclaMes],
+    *,
+    rubros: list[RubroInfo],
+    neutros_ids: set[str],
+) -> list[str]:
+    """Nombres de rubro con movimiento REAL y sin concepto del motor (unión ordenada y
+    deduplicada sobre los meses con ejecutado). Reusa `mapear_a_conceptos` sobre el
+    snapshot del ejecutado —aquí afloran R-1/R-2 parqueados—; función PURA (sin Mongo).
+    `[]` si todo mapea. NO altera el anclaje: solo lectura para exponer en el shape."""
+    nombres: set[str] = set()
+    for a in anclas.values():
+        if not a.ejecutado_por_rubro_id:
+            continue
+        res = mapear_a_conceptos(
+            rubros=rubros,
+            valor_por_rubro_id=a.ejecutado_por_rubro_id,
+            neutros_ids=neutros_ids,
+        )
+        nombres.update(res.sin_mapear)
+    return sorted(nombres)
diff --git a/backend/app/proyeccion/ejecucion/loader.py b/backend/app/proyeccion/ejecucion/loader.py
index 49c6b7d..ace0761 100644
--- a/backend/app/proyeccion/ejecucion/loader.py
+++ b/backend/app/proyeccion/ejecucion/loader.py
@@ -42,6 +42,7 @@ from app.proyeccion.motor import _meses_del_horizonte
 
 _CERO = Decimal("0")
 _log = logging.getLogger(__name__)
+_FORMULA_MES_EN_CURSO = "ejecutado + max(0, definido - ejecutado) por concepto"
 
 
 async def _rubros_info() -> list[RubroInfo]:
@@ -154,3 +155,35 @@ async def cargar_anclas(
                 )
             # futuro sin definido → omitido (motor)
     return anclas, rubros, neutros_ids
+
+
+async def cargar_completitud_mes_en_curso(
+    mes_inicio: tuple[int, int], horizonte: int
+) -> dict | None:
+    """B13 — completitud del mes EN EJECUCIÓN del horizonte: hasta qué día está cargado
+    (fecha máxima de transacción) y con qué fórmula se arma (Regla A/D-08). `None` si
+    ningún mes del horizonte está en ejecución. `cargado_hasta`/`dia` son `None` si el
+    mes existe pero aún no tiene transacciones. Consulta aparte de `cargar_anclas` (no
+    altera su contrato); corre 1× por request (ver B-1)."""
+    meses = [f"{a:04d}-{m:02d}" for a, m in _meses_del_horizonte(mes_inicio, horizonte)]
+    claves = [f"{m}-01" for m in meses]
+    en_curso = await MesControl.find(
+        In(MesControl.mes, claves),
+        MesControl.estado == EstadoMes.EN_EJECUCION,
+    ).to_list()
+    if not en_curso:
+        return None
+    mc = min(en_curso, key=lambda x: x.mes)  # el más temprano, por determinismo
+    ultima = (
+        await Transaccion.find(Transaccion.mes_id == mc.id)
+        .sort(-Transaccion.fecha)
+        .limit(1)
+        .to_list()
+    )
+    cargado_hasta = ultima[0].fecha if ultima else None
+    return {
+        "mes": mc.mes[:7],
+        "cargado_hasta": cargado_hasta,
+        "dia": int(cargado_hasta[8:10]) if cargado_hasta else None,
+        "formula": _FORMULA_MES_EN_CURSO,
+    }
diff --git a/backend/app/proyeccion/service.py b/backend/app/proyeccion/service.py
index 8d6fe99..5dfafa3 100644
--- a/backend/app/proyeccion/service.py
+++ b/backend/app/proyeccion/service.py
@@ -7,7 +7,7 @@ Carga los parámetros VIGENTES + el catálogo de modelos ACTIVOS, arma un
 estado: es una lectura pura sobre la configuración vigente."""
 
 import logging
-from dataclasses import replace
+from dataclasses import dataclass, field, replace
 from decimal import Decimal
 
 from app.cartera_previa import service as cartera_previa_service
@@ -31,9 +31,12 @@ from app.obligaciones.reconciliacion import (
     reconciliar,
 )
 from app.parametros_proyeccion import service as parametros_service
-from app.proyeccion.ejecucion.guarda import marcas_origen
+from app.proyeccion.ejecucion.guarda import marcas_origen, rubros_sin_mapear
 from app.proyeccion.ejecucion.lectura import RubroInfo
-from app.proyeccion.ejecucion.loader import cargar_anclas
+from app.proyeccion.ejecucion.loader import (
+    cargar_anclas,
+    cargar_completitud_mes_en_curso,
+)
 from app.proyeccion.ejecucion.service import CERRADO, AnclaMes, anclar
 from app.proyeccion.impactos import Ajuste, aplicar_impactos
 from app.proyeccion.motor import (
@@ -145,16 +148,34 @@ def _armar_parametros(
     )
 
 
+@dataclass(frozen=True)
+class AnclajeMeta:
+    """Metadato de origen de la proyección para el shape de P5 (aditivo). Vacío cuando
+    no hay anclaje → la respuesta queda byte-idéntica a la de antes de P5."""
+
+    meses_anclados: dict[str, str] = field(default_factory=dict)
+    sin_mapear: list[str] = field(default_factory=list)
+    mes_en_curso: dict | None = None
+
+
 def _serializar(
     r: ResultadoProyeccion,
     escenario: str,
     caja_minima,
     fondo: list,
     rec: ResultadoReconciliado | None = None,
+    *,
+    meta: "AnclajeMeta | None" = None,
 ) -> dict:
     meses_ym = [f.mes for f in r.meses]
+    meta = meta or AnclajeMeta()
     return {
         "escenario": escenario,
+        # P5 — origen de cada cifra (aditivo): marcas por mes, rubros sin concepto del
+        # motor, y completitud del mes en curso (B13). Vacíos si no hay anclaje.
+        "meses_anclados": dict(meta.meses_anclados),
+        "sin_mapear": list(meta.sin_mapear),
+        "mes_en_curso": meta.mes_en_curso,
         # D2 §4: ventana donde las facturas reales netean el Auteco paramétrico + el
         # interés de obligaciones separado por mes (None/{} si no hay facturas activas).
         "ventana_reconciliada": (
@@ -315,7 +336,9 @@ async def _resultado_con(
     facturas_override: list[FacturaReconciliar] | None = None,
     anclas_override: tuple[dict[str, AnclaMes], list[RubroInfo], set[str]]
     | None = None,
-) -> tuple[ResultadoProyeccion, object, list, ResultadoReconciliado | None]:
+) -> tuple[
+    ResultadoProyeccion, object, list, ResultadoReconciliado | None, AnclajeMeta
+]:
     """La tubería completa sobre un set de parámetros DADO, en el orden de precedencia
     `motor → EJECUCIÓN (E1) → OBLIGACIONES (D2) → IMPACTOS (D1)`:
 
@@ -358,6 +381,8 @@ async def _resultado_con(
         else await cargar_anclas(mes_inicio, horizonte)
     )
     meses_anclados: frozenset[str] = frozenset()
+    marcas: dict[str, str] = {}
+    sin_mapear: list[str] = []
     if anclas:
         aj = anclar(
             resultado=r,
@@ -370,18 +395,16 @@ async def _resultado_con(
         # D2 solo excluye los meses CERRADOS (el pasado es del libro; su factura ya no
         # está pendiente). E1 NO ancla Auteco (sus 5 conceptos no incluyen el Auteco),
         # así que en meses no-cerrados D2 SÍ aplica el pago real, sin doble conteo
-        # (campos disjuntos, deltas aditivos). El set completo de anclados queda como
-        # `frozenset(anclas)` para las marcas de origen de la UI en P5 — no se da a D2.
+        # (campos disjuntos, deltas aditivos).
         meses_anclados = frozenset(m for m, a in anclas.items() if a.estado == CERRADO)
-        # B10 (P4): marca de origen por mes + log de los cerrados sospechosos (ejecutado
-        # << definido). Solo observabilidad — la exposición en la respuesta es P5, y la
-        # marca NUNCA cambia el régimen (un sospechoso sigue anclado y excluido de D2).
+        # P5 — marcas de origen (todas) + rubros sin concepto, para el shape aditivo.
+        marcas = marcas_origen(anclas, rubros=rubros_e1, neutros_ids=neutros_e1)
+        sin_mapear = rubros_sin_mapear(anclas, rubros=rubros_e1, neutros_ids=neutros_e1)
+        # B10 (P4): log de los cerrados sospechosos (ejecutado << definido). Solo
+        # observabilidad — la marca NUNCA cambia el régimen (un sospechoso sigue anclado
+        # y excluido de D2, protege C-1).
         sospechosos = sorted(
-            m
-            for m, marca in marcas_origen(
-                anclas, rubros=rubros_e1, neutros_ids=neutros_e1
-            ).items()
-            if marca == "cerrado_sospechoso"
+            m for m, mk in marcas.items() if mk == "cerrado_sospechoso"
         )
         if sospechosos:
             _log.warning(
@@ -389,6 +412,14 @@ async def _resultado_con(
                 sospechosos,
             )
 
+    # P5/B13 — completitud del mes en curso (Mongo). None con anclas_override (tests) o
+    # cuando ningún mes del horizonte está en ejecución. Independiente del anclaje.
+    completitud = (
+        None
+        if anclas_override is not None
+        else await cargar_completitud_mes_en_curso(mes_inicio, horizonte)
+    )
+
     facturas = (
         facturas_override
         if facturas_override is not None
@@ -400,7 +431,10 @@ async def _resultado_con(
             r, facturas, params.caja_minima, meses_anclados=meses_anclados
         )
         r = _kpis_a_resultado(rec.ajustado)
-    return r, params.caja_minima, fondo, rec
+    meta = AnclajeMeta(
+        meses_anclados=marcas, sin_mapear=sin_mapear, mes_en_curso=completitud
+    )
+    return r, params.caja_minima, fondo, rec, meta
 
 
 async def _proyectar_con(
@@ -414,7 +448,7 @@ async def _proyectar_con(
 ) -> dict:
     """Serializa la proyección de `_resultado_con` (mismo shape que GET /proyeccion),
     marcando la ventana reconciliada y el interés de obligaciones (§4)."""
-    r, caja_min, fondo, rec = await _resultado_con(
+    r, caja_min, fondo, rec, meta = await _resultado_con(
         params,
         modelos,
         escenario=escenario,
@@ -422,7 +456,7 @@ async def _proyectar_con(
         horizonte_meses=horizonte_meses,
         caja_inicial_override=caja_inicial_override,
     )
-    return _serializar(r, escenario, caja_min, fondo, rec)
+    return _serializar(r, escenario, caja_min, fondo, rec, meta=meta)
 
 
 async def proyectar_vigente(
@@ -511,7 +545,7 @@ async def valles_vigente(
     """D1 §3 — los valles (hitos) de la proyección vigente: mínimos de caja relevantes
     con sus causas. Lectura pura sobre la config vigente."""
     params, modelos = await _cargar_config_vigente()
-    r, caja_min, _, _ = await _resultado_con(
+    r, caja_min, _, _, _ = await _resultado_con(
         params,
         modelos,
         escenario=escenario,
@@ -537,7 +571,7 @@ async def proyectar_impactos(
     ESCRIBE). Devuelve ambas series con el shape de GET /proyeccion, los valles de cada
     una y el delta de flujo por mes. Con `ajustes` vacío, ajustada == base bit a bit."""
     params, modelos = await _cargar_config_vigente()
-    r, caja_min, fondo, _ = await _resultado_con(
+    r, caja_min, fondo, _, meta = await _resultado_con(
         params,
         modelos,
         escenario=escenario,
@@ -548,8 +582,8 @@ async def proyectar_impactos(
     r_aj = _kpis_a_resultado(ajustado)
     return {
         "escenario": escenario,
-        "base": _serializar(r, escenario, caja_min, fondo),
-        "ajustada": _serializar(r_aj, escenario, caja_min, fondo),
+        "base": _serializar(r, escenario, caja_min, fondo, meta=meta),
+        "ajustada": _serializar(r_aj, escenario, caja_min, fondo, meta=meta),
         "valles_base": [
             _serializar_valle(v) for v in detectar_valles(r.meses, caja_min)
         ],
@@ -574,7 +608,7 @@ async def resolver(
     """D1 §5 — solvers por bisección sobre la proyección vigente + los `ajustes` en
     pantalla. Compute-only. `objetivo` ∈ {techo_gasto, goal_seek, punto_quiebre}."""
     params, modelos = await _cargar_config_vigente()
-    r, caja_min, _, _ = await _resultado_con(
+    r, caja_min, _, _, _ = await _resultado_con(
         params,
         modelos,
         escenario=escenario,
@@ -644,7 +678,7 @@ async def simular_plazo(
         replace(f, plazo_elegido_dias=max(plazo_dias, f.plazo_base_dias))
         for f in reales
     ]
-    r, _caja, _fondo, rec = await _resultado_con(
+    r, _caja, _fondo, rec, _ = await _resultado_con(
         params,
         modelos,
         escenario=escenario,
```

## 7. Diff de TESTS (real)

```diff
diff --git a/backend/tests/test_e1_guarda.py b/backend/tests/test_e1_guarda.py
index 79c5fea..262e52a 100644
--- a/backend/tests/test_e1_guarda.py
+++ b/backend/tests/test_e1_guarda.py
@@ -15,6 +15,7 @@ from app.proyeccion.ejecucion.guarda import (
     UMBRAL_SOSPECHA_EJECUTADO,
     es_ejecutado_anomalo,
     marcas_origen,
+    rubros_sin_mapear,
 )
 from app.proyeccion.ejecucion.lectura import RubroInfo
 from app.proyeccion.ejecucion.service import AnclaMes
@@ -108,3 +109,56 @@ def test_marcas_origen_marca_solo_cerrado_anomalo():
         "2026-07": "en_ejecucion",
         "2026-08": "presupuesto",
     }
+
+
+def _rubros_con_4040():
+    # los 9 del mapeo + un rubro no-sistema sin concepto (4040 = R-2, grupo
+    # deudas_obligaciones no está en _GRUPOS_GASTOS_FIJOS → _concepto_de = None)
+    return _rubros() + [
+        RubroInfo(
+            id="4040",
+            codigo="4040",
+            grupo="deudas_obligaciones",
+            nombre="Ajuste raro 4040",
+            es_sistema=False,
+        )
+    ]
+
+
+def test_rubros_sin_mapear_reporta_rubro_con_movimiento_sin_concepto():
+    anclas = {
+        "2026-05": AnclaMes(
+            estado="cerrado",
+            ejecutado_por_rubro_id={"4010": Decimal("100"), "4040": Decimal("500")},
+            definido_por_rubro_id={},
+            ingreso_real=Decimal("0"),
+        ),
+    }
+    assert rubros_sin_mapear(anclas, rubros=_rubros_con_4040(), neutros_ids=set()) == [
+        "Ajuste raro 4040"
+    ]
+
+
+def test_rubros_sin_mapear_vacio_cuando_todo_mapea():
+    anclas = {
+        "2026-05": AnclaMes(
+            estado="cerrado",
+            ejecutado_por_rubro_id={"4010": Decimal("100")},
+            definido_por_rubro_id={},
+            ingreso_real=Decimal("0"),
+        ),
+    }
+    assert rubros_sin_mapear(anclas, rubros=_rubros(), neutros_ids=set()) == []
+
+
+def test_rubros_sin_mapear_dedup_y_ordena_entre_meses():
+    a = AnclaMes(
+        estado="cerrado",
+        ejecutado_por_rubro_id={"4040": Decimal("500")},
+        definido_por_rubro_id={},
+        ingreso_real=Decimal("0"),
+    )
+    anclas = {"2026-05": a, "2026-06": a}  # mismo rubro en dos meses → una entrada
+    assert rubros_sin_mapear(anclas, rubros=_rubros_con_4040(), neutros_ids=set()) == [
+        "Ajuste raro 4040"
+    ]
diff --git a/backend/tests/test_e1_loader.py b/backend/tests/test_e1_loader.py
index 97bbe5b..e318103 100644
--- a/backend/tests/test_e1_loader.py
+++ b/backend/tests/test_e1_loader.py
@@ -21,7 +21,10 @@ from app.domain.presupuesto import PresupuestoLinea
 from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
 from app.domain.transaccion import Transaccion
 from app.proyeccion.ejecucion.lectura import RubroInfo
-from app.proyeccion.ejecucion.loader import cargar_anclas
+from app.proyeccion.ejecucion.loader import (
+    cargar_anclas,
+    cargar_completitud_mes_en_curso,
+)
 from beanie import init_beanie
 from mongomock_motor import AsyncMongoMockClient
 
@@ -223,3 +226,35 @@ async def test_cerrado_trae_definido_para_la_marca(db):
     anclas, _, _ = await cargar_anclas(_MES_INICIO, _HORIZONTE)
     # el loader trae el definido también para cerrado (alimenta la marca B10)
     assert anclas["2026-07"].definido_por_rubro_id == {str(gasto.id): Decimal("12000")}
+
+
+@pytest.mark.asyncio
+async def test_completitud_mes_en_curso_toma_la_fecha_maxima(db):
+    """P5/B13: para el mes EN_EJECUCION, completitud = fecha máxima de tx + fórmula."""
+    ago = await _mes("2026-08", EstadoMes.EN_EJECUCION)
+    gasto = await _rubro(RubroGrupo.OPERACION, "Arriendos", TipoFlujo.EGRESO, "2010")
+    for f in ("2026-08-03", "2026-08-06", "2026-08-01"):
+        await Transaccion(
+            fecha=f,
+            descripcion="x",
+            valor=Decimal("1"),
+            tipo_flujo=TipoFlujo.EGRESO,
+            rubro_id=gasto.id,
+            mes_id=ago.id,
+            banco=Banco.GLOBAL66,
+            id_banco=f"REF-{f}|1",
+        ).insert()
+
+    comp = await cargar_completitud_mes_en_curso((2026, 8), 1)
+    assert comp == {
+        "mes": "2026-08",
+        "cargado_hasta": "2026-08-06",
+        "dia": 6,
+        "formula": "ejecutado + max(0, definido - ejecutado) por concepto",
+    }
+
+
+@pytest.mark.asyncio
+async def test_completitud_none_sin_mes_en_ejecucion(db):
+    await _mes("2026-08", EstadoMes.CERRADO)
+    assert await cargar_completitud_mes_en_curso((2026, 8), 1) is None
diff --git a/backend/tests/test_e1_loader_realmongo.py b/backend/tests/test_e1_loader_realmongo.py
index 22a35b9..340e64c 100644
--- a/backend/tests/test_e1_loader_realmongo.py
+++ b/backend/tests/test_e1_loader_realmongo.py
@@ -17,7 +17,10 @@ from app.domain.mes_control import EstadoMes, MesControl
 from app.domain.presupuesto import PresupuestoLinea
 from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
 from app.domain.transaccion import Transaccion
-from app.proyeccion.ejecucion.loader import cargar_anclas
+from app.proyeccion.ejecucion.loader import (
+    cargar_anclas,
+    cargar_completitud_mes_en_curso,
+)
 from beanie import init_beanie
 from motor.motor_asyncio import AsyncIOMotorClient
 
@@ -155,3 +158,35 @@ class TestLoaderReal:
 
         anclas, _rubros, _neutros = await cargar_anclas((2026, 7), 1)
         assert "2026-07" not in anclas  # PASO 0 lo sacó (cae al motor)
+
+    @pytest.mark.asyncio
+    async def test_completitud_fecha_maxima_real(self, db):
+        """P5/B13 contra Mongo real: sort(-fecha).limit(1) devuelve la fecha máxima de
+        transacción del mes en ejecución (fecha ISO ordena cronológicamente)."""
+        rubro = await Rubro(
+            grupo=RubroGrupo.OPERACION,
+            nombre="Arriendos",
+            tipo_flujo=TipoFlujo.EGRESO,
+            orden=1,
+            codigo="2010",
+        ).insert()
+        ago = await MesControl(
+            mes="2026-08-01",
+            saldo_inicial_caja=Decimal("0"),
+            estado=EstadoMes.EN_EJECUCION,
+        ).insert()
+        for f in ("2026-08-02", "2026-08-09", "2026-08-05"):
+            await Transaccion(
+                fecha=f,
+                descripcion="x",
+                valor=Decimal("1"),
+                tipo_flujo=TipoFlujo.EGRESO,
+                rubro_id=rubro.id,
+                mes_id=ago.id,
+                banco=Banco.GLOBAL66,
+                id_banco=f"REF-{f}|1",
+            ).insert()
+
+        comp = await cargar_completitud_mes_en_curso((2026, 8), 1)
+        assert comp["cargado_hasta"] == "2026-08-09"
+        assert comp["dia"] == 9
diff --git a/backend/tests/test_e1_pipeline.py b/backend/tests/test_e1_pipeline.py
index 2870bcc..910b105 100644
--- a/backend/tests/test_e1_pipeline.py
+++ b/backend/tests/test_e1_pipeline.py
@@ -25,7 +25,7 @@ from app.obligaciones.calculadora import pago_factura
 from app.obligaciones.reconciliacion import FacturaReconciliar
 from app.proyeccion.ejecucion.lectura import RubroInfo
 from app.proyeccion.ejecucion.service import AnclaMes
-from app.proyeccion.service import _resultado_con
+from app.proyeccion.service import AnclajeMeta, _resultado_con
 from beanie import init_beanie
 from mongomock_motor import AsyncMongoMockClient
 
@@ -137,8 +137,8 @@ async def db():
     yield c
 
 
-async def _correr(anclas_override, facturas_override):
-    r, _cm, _fondo, _rec = await _resultado_con(
+async def _correr(anclas_override, facturas_override, *, con_meta=False):
+    r, _cm, _fondo, _rec, meta = await _resultado_con(
         _params(),
         _modelos(),
         escenario="base",
@@ -147,7 +147,8 @@ async def _correr(anclas_override, facturas_override):
         anclas_override=anclas_override,
         facturas_override=facturas_override,
     )
-    return {m.mes: m for m in r.meses}
+    filas = {m.mes: m for m in r.meses}
+    return (filas, meta) if con_meta else filas
 
 
 @pytest.mark.asyncio
@@ -264,3 +265,40 @@ async def test_b10_loguea_mes_cerrado_sospechoso(db, caplog):
         res = await _correr((anclas, _rubros(), set()), [])
     assert "2026-10" in res  # se ancla igual (no se bloquea)
     assert any("B10" in r.getMessage() for r in caplog.records)
+
+
+@pytest.mark.asyncio
+async def test_meta_marcas_y_sin_mapear(db):
+    """P5: _resultado_con expone AnclajeMeta — meses_anclados (marcas) y sin_mapear
+    (rubro con movimiento sin concepto). mes_en_curso es None (db vacía, sin ciclo)."""
+    rubros_4040 = _rubros() + [
+        RubroInfo(
+            id="4040",
+            codigo="4040",
+            grupo="deudas_obligaciones",
+            nombre="Ajuste raro 4040",
+            es_sistema=False,
+        )
+    ]
+    anclas = {
+        "2026-10": AnclaMes(
+            estado="cerrado",
+            ejecutado_por_rubro_id={"4010": Decimal("40"), "4040": Decimal("9")},
+            definido_por_rubro_id={"4010": Decimal("100")},  # 40<50 → sospechoso
+            ingreso_real=Decimal("0"),
+        )
+    }
+    _filas, meta = await _correr((anclas, rubros_4040, set()), [], con_meta=True)
+    assert isinstance(meta, AnclajeMeta)
+    assert meta.meses_anclados == {"2026-10": "cerrado_sospechoso"}
+    assert meta.sin_mapear == ["Ajuste raro 4040"]
+    assert meta.mes_en_curso is None
+
+
+@pytest.mark.asyncio
+async def test_meta_vacia_sin_anclaje(db):
+    """Candado 'foto sin ciclo': sin anclas la meta queda totalmente vacía."""
+    _filas, meta = await _correr(({}, [], set()), [], con_meta=True)
+    assert meta.meses_anclados == {}
+    assert meta.sin_mapear == []
+    assert meta.mes_en_curso is None
diff --git a/backend/tests/test_proyeccion_endpoints.py b/backend/tests/test_proyeccion_endpoints.py
index 35c4e9a..911f243 100644
--- a/backend/tests/test_proyeccion_endpoints.py
+++ b/backend/tests/test_proyeccion_endpoints.py
@@ -287,3 +287,90 @@ async def test_modelo_baja_logica_y_reactivar(api):
         f"/api/v1/modelos-moto/{mid}", json={"activo": False}, headers=h
     )
     assert r.status_code == 422
+
+
+async def _seed_mes_en_ejecucion():
+    # E1·P5/B13: un mes EN_EJECUCION con transacciones cargadas hasta el día 6.
+    # Trae los 9 códigos del mapeo (B12 fail-loud al anclar) + un rubro de gasto.
+    from decimal import Decimal
+
+    from app.domain.bancos import Banco
+    from app.domain.mes_control import MesControl
+    from app.domain.rubro import Rubro, TipoFlujo
+    from app.domain.transaccion import Transaccion
+
+    _plan = [
+        ("0110", "ingresos_operativos", TipoFlujo.INGRESO),
+        ("1010", "costo_producto", TipoFlujo.EGRESO),
+        ("1020", "costo_producto", TipoFlujo.EGRESO),
+        ("1030", "costo_producto", TipoFlujo.EGRESO),
+        ("4010", "deudas_obligaciones", TipoFlujo.EGRESO),
+        ("4020", "deudas_obligaciones", TipoFlujo.EGRESO),
+        ("4030", "deudas_obligaciones", TipoFlujo.EGRESO),
+        ("4050", "deudas_obligaciones", TipoFlujo.EGRESO),
+        ("5060", "otros", TipoFlujo.EGRESO),
+    ]
+    for i, (cod, grupo, flujo) in enumerate(_plan):
+        await Rubro(
+            grupo=grupo, nombre=f"Rubro {cod}", codigo=cod, tipo_flujo=flujo, orden=i
+        ).insert()
+    arriendos = await Rubro(
+        grupo="operacion",
+        nombre="Arriendos",
+        codigo="2010",
+        tipo_flujo=TipoFlujo.EGRESO,
+        orden=99,
+    ).insert()
+    mc = await MesControl(
+        mes="2026-08-01",
+        estado="en_ejecucion",
+        saldo_inicial_caja=Decimal("10000000"),
+    ).insert()
+    for j, f in enumerate(("2026-08-02", "2026-08-06", "2026-08-04")):
+        await Transaccion(
+            fecha=f,
+            descripcion="gasto",
+            valor=Decimal("100000"),
+            tipo_flujo=TipoFlujo.EGRESO,
+            rubro_id=arriendos.id,
+            mes_id=mc.id,
+            banco=Banco.MANUAL,
+            id_banco=f"MAN-P5B13TEST0000000000000000{j}",
+        ).insert()
+
+
+@pytest.mark.asyncio
+async def test_proyeccion_expone_claves_aditivas_sin_ciclo(api):
+    """Foto sin ciclo: las 3 claves nuevas salen en su forma vacía; el resto del payload
+    conserva sus claves (aditivo, no rompe consumidores)."""
+    await _setup_config(api)
+    h = await _token(api, "consulta@roddos.com")
+    r = await api.get("/api/v1/proyeccion", headers=h)
+    assert r.status_code == 200
+    data = r.json()
+    assert data["meses_anclados"] == {}
+    assert data["sin_mapear"] == []
+    assert data["mes_en_curso"] is None
+    for k in ("escenario", "meses", "caja_final", "caja_minima", "piso_caja"):
+        assert k in data
+
+
+@pytest.mark.asyncio
+async def test_proyeccion_mes_en_curso_b13(api):
+    """B13: con un mes EN_EJECUCION cargado, mes_en_curso trae completitud + fórmula, y
+    meses_anclados lo marca 'en_ejecucion'."""
+    await _setup_config(api)
+    await _seed_mes_en_ejecucion()
+    h = await _token(api, "consulta@roddos.com")
+    r = await api.get(
+        "/api/v1/proyeccion?mes_inicio=2026-08&horizonte_meses=3", headers=h
+    )
+    assert r.status_code == 200
+    data = r.json()
+    assert data["meses_anclados"]["2026-08"] == "en_ejecucion"
+    mec = data["mes_en_curso"]
+    assert mec is not None
+    assert mec["mes"] == "2026-08"
+    assert mec["cargado_hasta"] == "2026-08-06"
+    assert mec["dia"] == 6
+    assert mec["formula"] == "ejecutado + max(0, definido - ejecutado) por concepto"
```
