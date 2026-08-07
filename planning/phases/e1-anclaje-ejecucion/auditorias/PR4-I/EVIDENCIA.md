# EVIDENCIA — E1 PR4-I (código real + salidas de tests)

Acompaña a `SOLICITUD.md`. Diff completo contra `origin/main` + salidas reales.
PR #71 · commit `a71a787`.

## 1. Resumen de verificación

- **pytest E1 + relacionados:** 51 passed, 2 skipped (variantes real-mongo del loader).
- **Regresión completa del backend:** 901 passed, 94 skipped, 0 fallos (13m31s).
- **ruff:** `All checks passed!` + `format --check` limpio.
- **R0:** `git diff origin/main -- backend/app/proyeccion/motor.py` → 0 líneas.
- **Perímetro intacto:** `anclar`/`ejecucion.service`, `lectura.py`, `reconciliacion.py`,
  `MesControl` sin tocar; catálogo de eventos sin crecer.

## 2. Diff completo (`git diff origin/main...HEAD -- backend/`)

```diff
diff --git a/backend/app/proyeccion/ejecucion/guarda.py b/backend/app/proyeccion/ejecucion/guarda.py
new file mode 100644
index 0000000..3c23efb
--- /dev/null
+++ b/backend/app/proyeccion/ejecucion/guarda.py
@@ -0,0 +1,68 @@
+# backend/app/proyeccion/ejecucion/guarda.py
+"""E1 · P4 — guarda B10: marca de anomalía del mes cerrado (función PURA).
+
+Un mes CERRADO cuya ejecución quedó muy por debajo de lo definido probablemente está
+mal cargado (faltan movimientos). Decisión CEO 2026-08-05: NO se bloquea el anclaje —la
+confirmación del cierre ES la validación (FIX-J)—; el mes se ancla igual y solo se MARCA
+`cerrado_sospechoso` para la UI. Sin flag en MesControl, sin evento nuevo.
+
+Regla (tunable): sobre los 5 conceptos que E1 ancla (`gastos_fijos`, `gps`,
+`costo_nueva`, `int_deuda`, `iva` — sin Auteco, sin `neto`), sea E = Σ ejecutado y
+D = Σ definido. El mes es sospechoso si `D > 0` y `E < UMBRAL × D` (estricto:
+`E == UMBRAL×D` NO marca; `D == 0` NO marca —no hay base de juicio—).
+
+**Protege el fix C-1:** la marca NO cambia `AnclaMes.estado` (un sospechoso sigue siendo
+`"cerrado"`, así el filtro de D2 lo sigue excluyendo). Vive solo en el mapa de marcas.
+"""
+
+from __future__ import annotations
+
+from decimal import Decimal
+
+from app.proyeccion.ejecucion.lectura import RubroInfo
+from app.proyeccion.ejecucion.service import CERRADO, AnclaMes, _conceptos_egreso
+
+UMBRAL_SOSPECHA_EJECUTADO = Decimal("0.5")
+
+
+def es_ejecutado_anomalo(
+    ejecutado_por_rubro_id: dict[str, Decimal],
+    definido_por_rubro_id: dict[str, Decimal],
+    *,
+    rubros: list[RubroInfo],
+    neutros_ids: set[str],
+) -> bool:
+    """True si el ejecutado del mes cerrado quedó sospechosamente bajo vs el definido
+    (Σ de los 5 conceptos anclados). `D == 0` o `E >= UMBRAL×D` → no anómalo."""
+    ejec = _conceptos_egreso(
+        ejecutado_por_rubro_id, rubros=rubros, neutros_ids=neutros_ids
+    )
+    defi = _conceptos_egreso(
+        definido_por_rubro_id, rubros=rubros, neutros_ids=neutros_ids
+    )
+    e_total = sum(ejec.values(), Decimal("0"))
+    d_total = sum(defi.values(), Decimal("0"))
+    return d_total > 0 and e_total < UMBRAL_SOSPECHA_EJECUTADO * d_total
+
+
+def marcas_origen(
+    anclas: dict[str, AnclaMes],
+    *,
+    rubros: list[RubroInfo],
+    neutros_ids: set[str],
+) -> dict[str, str]:
+    """Marca de origen por mes anclado (vocabulario del shape de P5):
+    `"cerrado"` | `"cerrado_sospechoso"` | `"en_ejecucion"` | `"presupuesto"`. Solo el
+    régimen cerrado puede volverse sospechoso; los demás conservan su estado."""
+    marcas: dict[str, str] = {}
+    for mes, a in anclas.items():
+        if a.estado == CERRADO and es_ejecutado_anomalo(
+            a.ejecutado_por_rubro_id,
+            a.definido_por_rubro_id,
+            rubros=rubros,
+            neutros_ids=neutros_ids,
+        ):
+            marcas[mes] = "cerrado_sospechoso"
+        else:
+            marcas[mes] = a.estado
+    return marcas
diff --git a/backend/app/proyeccion/ejecucion/loader.py b/backend/app/proyeccion/ejecucion/loader.py
index ee4fc76..49c6b7d 100644
--- a/backend/app/proyeccion/ejecucion/loader.py
+++ b/backend/app/proyeccion/ejecucion/loader.py
@@ -18,6 +18,7 @@ reinventar agregaciones.
 
 from __future__ import annotations
 
+import logging
 from decimal import Decimal
 
 from beanie import PydanticObjectId
@@ -26,8 +27,9 @@ from beanie.operators import In
 from app.control.service import _egresos_por_rubro
 from app.domain.mes_control import EstadoMes, MesControl
 from app.domain.presupuesto import PresupuestoLinea
-from app.domain.rubro import Rubro
+from app.domain.rubro import RUBROS_SISTEMA_CLASIFICABLES, Rubro
 from app.domain.rubros_neutros import _ids_rubros_neutros
+from app.domain.transaccion import Transaccion
 from app.metas_ingreso.service import ingreso_real
 from app.proyeccion.ejecucion.lectura import RubroInfo
 from app.proyeccion.ejecucion.service import (
@@ -39,6 +41,7 @@ from app.proyeccion.ejecucion.service import (
 from app.proyeccion.motor import _meses_del_horizonte
 
 _CERO = Decimal("0")
+_log = logging.getLogger(__name__)
 
 
 async def _rubros_info() -> list[RubroInfo]:
@@ -69,15 +72,40 @@ async def _definido_por_rubro(mes_id: PydanticObjectId) -> dict[str, Decimal]:
     }
 
 
+async def _rubros_ofensores(
+    mes_id: PydanticObjectId, dirty_ids: frozenset[str]
+) -> list[str]:
+    """PASO 0 (A2): rubros de sistema "sucios" (ids en `dirty_ids`) con al menos una
+    transacción en el mes. `[]` si el mes está limpio."""
+    oids = [PydanticObjectId(x) for x in dirty_ids]
+    txs = await Transaccion.find(
+        Transaccion.mes_id == mes_id, In(Transaccion.rubro_id, oids)
+    ).to_list()
+    return sorted({str(t.rubro_id) for t in txs})
+
+
 async def cargar_anclas(
     mes_inicio: tuple[int, int], horizonte: int
 ) -> tuple[dict[str, AnclaMes], list[RubroInfo], set[str]]:
-    """Arma `(anclas, rubros, neutros_ids)` para `anclar`. Los meses sin MesControl o
-    futuros sin presupuesto definido quedan fuera de `anclas` (el motor los cubre)."""
+    """Arma `(anclas, rubros, neutros_ids)` para `anclar`. Los meses sin MesControl,
+    futuros sin presupuesto definido, o con higiene sucia (PASO 0/A2) quedan fuera de
+    `anclas` (el motor los cubre). El `definido` se trae también para los cerrados: no
+    lo usa `anclar` (lo ignora en cerrado), solo alimenta la marca B10 (`guarda`)."""
     meses = [f"{a:04d}-{m:02d}" for a, m in _meses_del_horizonte(mes_inicio, horizonte)]
     rubros = await _rubros_info()
     neutros_ids = {str(i) for i in await _ids_rubros_neutros()}
 
+    # PASO 0 (higiene A2): rubros de SISTEMA que no deberían mover dinero en un mes
+    # anclable (es_sistema, NO clasificable, NO neutro). Si aparecen en un mes → ese mes
+    # no se ancla (cae al motor). Set derivado de la taxonomía ya cargada (sin query).
+    dirty_ids = frozenset(
+        r.id
+        for r in rubros
+        if r.es_sistema
+        and r.nombre not in RUBROS_SISTEMA_CLASIFICABLES
+        and r.id not in neutros_ids
+    )
+
     # un solo query para los MesControl del horizonte
     claves = [f"{m}-01" for m in meses]
     por_mes = {
@@ -90,11 +118,22 @@ async def cargar_anclas(
         mc = por_mes.get(m)
         if mc is None:
             continue  # sin ciclo → motor intacto
+        ofensores = await _rubros_ofensores(mc.id, dirty_ids) if dirty_ids else []
+        if ofensores:
+            # A2: mes mal higienizado → no se ancla (por-mes, no tumba los demás).
+            _log.warning(
+                "E1 PASO 0: el mes %s no se ancla (cae al motor): %d rubro(s) de "
+                "sistema no clasificables con movimiento: %s",
+                m,
+                len(ofensores),
+                ofensores,
+            )
+            continue
         if mc.estado == EstadoMes.CERRADO:
             anclas[m] = AnclaMes(
                 estado=CERRADO,
                 ejecutado_por_rubro_id=await _egresos_por_rubro(mc.id),
-                definido_por_rubro_id={},
+                definido_por_rubro_id=await _definido_por_rubro(mc.id),
                 ingreso_real=await ingreso_real(m),
             )
         elif mc.estado == EstadoMes.EN_EJECUCION:
diff --git a/backend/app/proyeccion/service.py b/backend/app/proyeccion/service.py
index 714e0bd..8d6fe99 100644
--- a/backend/app/proyeccion/service.py
+++ b/backend/app/proyeccion/service.py
@@ -6,6 +6,7 @@ Carga los parámetros VIGENTES + el catálogo de modelos ACTIVOS, arma un
 `motor.proyectar()`. Serializa a JSON con montos como string (regla 1). No escribe
 estado: es una lectura pura sobre la configuración vigente."""
 
+import logging
 from dataclasses import replace
 from decimal import Decimal
 
@@ -30,6 +31,7 @@ from app.obligaciones.reconciliacion import (
     reconciliar,
 )
 from app.parametros_proyeccion import service as parametros_service
+from app.proyeccion.ejecucion.guarda import marcas_origen
 from app.proyeccion.ejecucion.lectura import RubroInfo
 from app.proyeccion.ejecucion.loader import cargar_anclas
 from app.proyeccion.ejecucion.service import CERRADO, AnclaMes, anclar
@@ -49,6 +51,7 @@ from app.proyeccion.solvers import goal_seek, punto_de_quiebre, techo_gasto
 from app.proyeccion.valles import Valle, detectar_valles
 
 HORIZONTE_MAX = 180  # 15 años (tope de infraestructura)
+_log = logging.getLogger(__name__)
 
 
 class ProyeccionError(Exception):
@@ -370,6 +373,21 @@ async def _resultado_con(
         # (campos disjuntos, deltas aditivos). El set completo de anclados queda como
         # `frozenset(anclas)` para las marcas de origen de la UI en P5 — no se da a D2.
         meses_anclados = frozenset(m for m, a in anclas.items() if a.estado == CERRADO)
+        # B10 (P4): marca de origen por mes + log de los cerrados sospechosos (ejecutado
+        # << definido). Solo observabilidad — la exposición en la respuesta es P5, y la
+        # marca NUNCA cambia el régimen (un sospechoso sigue anclado y excluido de D2).
+        sospechosos = sorted(
+            m
+            for m, marca in marcas_origen(
+                anclas, rubros=rubros_e1, neutros_ids=neutros_e1
+            ).items()
+            if marca == "cerrado_sospechoso"
+        )
+        if sospechosos:
+            _log.warning(
+                "E1 B10: mes(es) cerrado(s) sospechoso(s) (ejecutado << definido): %s",
+                sospechosos,
+            )
 
     facturas = (
         facturas_override
diff --git a/backend/tests/test_e1_anclaje.py b/backend/tests/test_e1_anclaje.py
index b9de47b..04b9e39 100644
--- a/backend/tests/test_e1_anclaje.py
+++ b/backend/tests/test_e1_anclaje.py
@@ -373,3 +373,40 @@ def test_a3_fixture_julio_real_b2_y_b6():
     # B6: invariante al peso sobre la realidad.
     assert jul.neto + jul.egresos == jul.flujo
     assert _invariante_ok(out)
+
+
+# ───────── P4: inercia — anclar IGNORA el definido en régimen cerrado ─────────
+def test_cerrado_ignora_definido_inercia():
+    """P4: el loader ahora trae `definido` también para meses cerrados (alimenta la
+    marca B10), pero `anclar` lo IGNORA en cerrado (ancla el ejecutado real). La salida
+    debe ser idéntica con definido {} o poblado — protege el contrato de P2."""
+    res = _serie_coherente(
+        Decimal("1000000.00"),
+        [("2026-09", {"neto": Decimal("500000.00")})],
+    )
+    base = dict(
+        estado=CERRADO,
+        ejecutado_por_rubro_id={"2010": Decimal("350000")},
+        ingreso_real=Decimal("300000"),
+    )
+    sin_def = anclar(
+        resultado=res,
+        caja_minima=_CAJA_MIN,
+        anclas={"2026-09": AnclaMes(definido_por_rubro_id={}, **base)},
+        rubros=_rubros(),
+        neutros_ids=set(),
+    )
+    con_def = anclar(
+        resultado=res,
+        caja_minima=_CAJA_MIN,
+        anclas={
+            "2026-09": AnclaMes(
+                definido_por_rubro_id={"2010": Decimal("999999")}, **base
+            )
+        },
+        rubros=_rubros(),
+        neutros_ids=set(),
+    )
+    assert (
+        con_def.meses == sin_def.meses
+    )  # el definido no cambia el anclaje del cerrado
diff --git a/backend/tests/test_e1_guarda.py b/backend/tests/test_e1_guarda.py
new file mode 100644
index 0000000..79c5fea
--- /dev/null
+++ b/backend/tests/test_e1_guarda.py
@@ -0,0 +1,110 @@
+# backend/tests/test_e1_guarda.py
+"""E1 · P4 — guarda B10 (marca `cerrado_sospechoso`), función pura.
+
+Un mes CERRADO con ejecución muy por debajo de lo definido probablemente está mal
+cargado. NO se bloquea el anclaje (la confirmación ES el cierre — FIX-J); solo se MARCA
+para la UI. Regla (tunable UMBRAL_SOSPECHA_EJECUTADO): sobre los 5 conceptos anclados
+(sin Auteco, sin neto) E = Σ ejecutado, D = Σ definido; sospechoso si D>0 y E < 0.5×D
+(estricto: E==0.5×D NO marca; D==0 NO marca). El régimen (AnclaMes.estado) NO cambia —
+un sospechoso sigue siendo "cerrado" (así D2 lo sigue excluyendo, protege C-1); la marca
+vive solo en el mapa."""
+
+from decimal import Decimal
+
+from app.proyeccion.ejecucion.guarda import (
+    UMBRAL_SOSPECHA_EJECUTADO,
+    es_ejecutado_anomalo,
+    marcas_origen,
+)
+from app.proyeccion.ejecucion.lectura import RubroInfo
+from app.proyeccion.ejecucion.service import AnclaMes
+
+# Los 9 códigos del mapeo presentes (B12 no dispara). 4010 → int_deuda.
+_PLAN = [
+    ("0110", "ingresos_operativos", "Recaudo de cartera"),
+    ("1010", "costo_producto", "Producto"),
+    ("1020", "costo_producto", "SOAT"),
+    ("1030", "costo_producto", "GPS"),
+    ("4010", "deudas_obligaciones", "Préstamos"),
+    ("4020", "deudas_obligaciones", "Tarjetas"),
+    ("4030", "deudas_obligaciones", "Garantía cupo"),
+    ("4050", "deudas_obligaciones", "Proveedores"),
+    ("5060", "otros", "Impuestos"),
+]
+
+
+def _rubros():
+    return [
+        RubroInfo(id=c, codigo=c, grupo=g, nombre=n, es_sistema=False)
+        for (c, g, n) in _PLAN
+    ]
+
+
+def _anomalo(ejec, defi):
+    return es_ejecutado_anomalo(
+        {"4010": Decimal(ejec)} if ejec is not None else {},
+        {"4010": Decimal(defi)} if defi is not None else {},
+        rubros=_rubros(),
+        neutros_ids=set(),
+    )
+
+
+def test_umbral_por_defecto_es_medio():
+    assert UMBRAL_SOSPECHA_EJECUTADO == Decimal("0.5")
+
+
+def test_ejecutado_muy_bajo_es_anomalo():
+    # E = 40, D = 100 → 40 < 50 → sospechoso
+    assert _anomalo("40", "100") is True
+
+
+def test_ejecutado_alto_es_limpio():
+    # E = 80, D = 100 → 80 !< 50 → limpio
+    assert _anomalo("80", "100") is False
+
+
+def test_frontera_exacta_no_marca():
+    # E = 50, D = 100 → 50 < 50 es falso (comparación estricta) → NO marca
+    assert _anomalo("50", "100") is False
+
+
+def test_sin_definido_no_marca():
+    # D = 0 → no hay base de juicio → no marca (aunque E sea 0)
+    assert _anomalo("0", None) is False
+    assert _anomalo(None, None) is False
+
+
+def test_marcas_origen_marca_solo_cerrado_anomalo():
+    anclas = {
+        "2026-05": AnclaMes(
+            estado="cerrado",
+            ejecutado_por_rubro_id={"4010": Decimal("40")},
+            definido_por_rubro_id={"4010": Decimal("100")},
+            ingreso_real=Decimal("0"),
+        ),  # anómalo → cerrado_sospechoso
+        "2026-06": AnclaMes(
+            estado="cerrado",
+            ejecutado_por_rubro_id={"4010": Decimal("90")},
+            definido_por_rubro_id={"4010": Decimal("100")},
+            ingreso_real=Decimal("0"),
+        ),  # sano → cerrado
+        "2026-07": AnclaMes(
+            estado="en_ejecucion",
+            ejecutado_por_rubro_id={"4010": Decimal("1")},
+            definido_por_rubro_id={"4010": Decimal("100")},
+            ingreso_real=None,
+        ),  # en ejecución: nunca sospechoso
+        "2026-08": AnclaMes(
+            estado="presupuesto",
+            ejecutado_por_rubro_id={},
+            definido_por_rubro_id={"4010": Decimal("100")},
+            ingreso_real=None,
+        ),
+    }
+    marcas = marcas_origen(anclas, rubros=_rubros(), neutros_ids=set())
+    assert marcas == {
+        "2026-05": "cerrado_sospechoso",
+        "2026-06": "cerrado",
+        "2026-07": "en_ejecucion",
+        "2026-08": "presupuesto",
+    }
diff --git a/backend/tests/test_e1_loader.py b/backend/tests/test_e1_loader.py
index 6d8d603..97bbe5b 100644
--- a/backend/tests/test_e1_loader.py
+++ b/backend/tests/test_e1_loader.py
@@ -42,8 +42,15 @@ async def _mes(mes7: str, estado: EstadoMes) -> MesControl:
     return mc
 
 
-async def _rubro(grupo, nombre, flujo, codigo=None) -> Rubro:
-    r = Rubro(grupo=grupo, nombre=nombre, tipo_flujo=flujo, orden=1, codigo=codigo)
+async def _rubro(grupo, nombre, flujo, codigo=None, es_sistema=False) -> Rubro:
+    r = Rubro(
+        grupo=grupo,
+        nombre=nombre,
+        tipo_flujo=flujo,
+        orden=1,
+        codigo=codigo,
+        es_sistema=es_sistema,
+    )
     await r.insert()
     return r
 
@@ -169,3 +176,50 @@ async def test_rubros_info_y_neutros_ids_se_arman(escenario):
     assert {"Arriendos", "Producto", "Recaudo de cartera"} <= nombres
     # el único neutro presente es la reversa
     assert neutros_ids == {str(escenario["neutro"].id)}
+
+
+# ── P4 · PASO 0 (higiene A2): un mes con tx a rubro de SISTEMA "sucio" (es_sistema, no
+# clasificable, no neutro) no se ancla — cae al motor. Alcance por-mes. ──
+
+
+@pytest.mark.asyncio
+async def test_paso0_mes_con_rubro_sistema_sucio_no_se_ancla(db):
+    gasto = await _rubro(RubroGrupo.OPERACION, "Arriendos", TipoFlujo.EGRESO, "2010")
+    sucio = await _rubro(
+        RubroGrupo.OTROS, "Sistema no clasificable", TipoFlujo.EGRESO, es_sistema=True
+    )
+    jul = await _mes("2026-07", EstadoMes.CERRADO)
+    await _tx(jul, gasto, "5000", TipoFlujo.EGRESO, 1)
+    await _tx(
+        jul, sucio, "9", TipoFlujo.EGRESO, 2
+    )  # 1 tx sucia → PASO 0 excluye el mes
+    anclas, _, _ = await cargar_anclas(_MES_INICIO, _HORIZONTE)
+    assert "2026-07" not in anclas  # cae al motor
+
+
+@pytest.mark.asyncio
+async def test_paso0_clasificables_y_neutros_no_disparan(db):
+    gasto = await _rubro(RubroGrupo.OPERACION, "Arriendos", TipoFlujo.EGRESO, "2010")
+    porclas = await _rubro(
+        RubroGrupo.OTROS, "Por clasificar", TipoFlujo.EGRESO, es_sistema=True
+    )
+    neutro = await _rubro(
+        RubroGrupo.OTROS, "Reversas y devoluciones", TipoFlujo.INGRESO, es_sistema=True
+    )
+    jul = await _mes("2026-07", EstadoMes.CERRADO)
+    await _tx(jul, gasto, "5000", TipoFlujo.EGRESO, 1)
+    await _tx(jul, porclas, "3", TipoFlujo.EGRESO, 2)  # clasificable → NO dispara
+    await _tx(jul, neutro, "7", TipoFlujo.INGRESO, 3)  # neutro → NO dispara
+    anclas, _, _ = await cargar_anclas(_MES_INICIO, _HORIZONTE)
+    assert "2026-07" in anclas  # el mes se ancla igual
+
+
+@pytest.mark.asyncio
+async def test_cerrado_trae_definido_para_la_marca(db):
+    gasto = await _rubro(RubroGrupo.OPERACION, "Arriendos", TipoFlujo.EGRESO, "2010")
+    jul = await _mes("2026-07", EstadoMes.CERRADO)
+    await _tx(jul, gasto, "5000", TipoFlujo.EGRESO, 1)
+    await _linea(jul, gasto, Decimal("12000"))  # presupuesto definido del mes cerrado
+    anclas, _, _ = await cargar_anclas(_MES_INICIO, _HORIZONTE)
+    # el loader trae el definido también para cerrado (alimenta la marca B10)
+    assert anclas["2026-07"].definido_por_rubro_id == {str(gasto.id): Decimal("12000")}
diff --git a/backend/tests/test_e1_loader_realmongo.py b/backend/tests/test_e1_loader_realmongo.py
index 2ee0c33..22a35b9 100644
--- a/backend/tests/test_e1_loader_realmongo.py
+++ b/backend/tests/test_e1_loader_realmongo.py
@@ -110,3 +110,48 @@ class TestLoaderReal:
         assert anclas["2026-08"].definido_por_rubro_id == {
             str(gasto.id): Decimal("6000")
         }
+
+    @pytest.mark.asyncio
+    async def test_paso0_rubro_sistema_sucio_excluye_el_mes_real(self, db):
+        """P4/A2 contra Mongo real: la query de PASO 0 (find In sobre rubro_id) detecta
+        la tx a un rubro de sistema no clasificable → el mes cae al motor."""
+        gasto = await Rubro(
+            grupo=RubroGrupo.OPERACION,
+            nombre="Arriendos",
+            tipo_flujo=TipoFlujo.EGRESO,
+            orden=1,
+            codigo="2010",
+        ).insert()
+        sucio = await Rubro(
+            grupo=RubroGrupo.OTROS,
+            nombre="Sistema no clasificable",
+            tipo_flujo=TipoFlujo.EGRESO,
+            orden=2,
+            es_sistema=True,
+        ).insert()
+        jul = await MesControl(
+            mes="2026-07-01", saldo_inicial_caja=Decimal("0"), estado=EstadoMes.CERRADO
+        ).insert()
+        await Transaccion(
+            fecha="2026-07-10",
+            descripcion="ok",
+            valor=Decimal("5000"),
+            tipo_flujo=TipoFlujo.EGRESO,
+            rubro_id=gasto.id,
+            mes_id=jul.id,
+            banco=Banco.GLOBAL66,
+            id_banco="REF-OK|1",
+        ).insert()
+        await Transaccion(
+            fecha="2026-07-11",
+            descripcion="sucia",
+            valor=Decimal("9"),
+            tipo_flujo=TipoFlujo.EGRESO,
+            rubro_id=sucio.id,
+            mes_id=jul.id,
+            banco=Banco.GLOBAL66,
+            id_banco="REF-SUCIA|1",
+        ).insert()
+
+        anclas, _rubros, _neutros = await cargar_anclas((2026, 7), 1)
+        assert "2026-07" not in anclas  # PASO 0 lo sacó (cae al motor)
diff --git a/backend/tests/test_e1_pipeline.py b/backend/tests/test_e1_pipeline.py
index 4eca849..2870bcc 100644
--- a/backend/tests/test_e1_pipeline.py
+++ b/backend/tests/test_e1_pipeline.py
@@ -243,3 +243,24 @@ async def test_c1_d2_aplica_pago_real_en_mes_anclado_no_cerrado(db, estado):
 
     # 2026-12 (no anclado) reconcilia normal.
     assert a["2026-12"].pago_inventario == Decimal(f"-{cap_dic.capital}")
+
+
+@pytest.mark.asyncio
+async def test_b10_loguea_mes_cerrado_sospechoso(db, caplog):
+    """P4/B10: un mes CERRADO con ejecutado << definido se ancla igual (no se bloquea)
+    pero se registra en log estructurado. La marca no cambia el régimen (sigue anclado y
+    excluido de D2 por ser cerrado)."""
+    import logging
+
+    anclas = {
+        "2026-10": AnclaMes(
+            estado="cerrado",
+            ejecutado_por_rubro_id={"4010": Decimal("40")},  # E=40
+            definido_por_rubro_id={"4010": Decimal("100")},  # D=100 → 40<50 sospechoso
+            ingreso_real=Decimal("0"),
+        )
+    }
+    with caplog.at_level(logging.WARNING):
+        res = await _correr((anclas, _rubros(), set()), [])
+    assert "2026-10" in res  # se ancla igual (no se bloquea)
+    assert any("B10" in r.getMessage() for r in caplog.records)

```

## 3. Salida de tests (E1 + relacionados, `-v`)

```
tests/test_e1_guarda.py::test_umbral_por_defecto_es_medio PASSED         [  1%]
tests/test_e1_guarda.py::test_ejecutado_muy_bajo_es_anomalo PASSED       [  3%]
tests/test_e1_guarda.py::test_ejecutado_alto_es_limpio PASSED            [  5%]
tests/test_e1_guarda.py::test_frontera_exacta_no_marca PASSED            [  7%]
tests/test_e1_guarda.py::test_sin_definido_no_marca PASSED               [  9%]
tests/test_e1_guarda.py::test_marcas_origen_marca_solo_cerrado_anomalo PASSED [ 11%]
tests/test_e1_loader.py::test_mes_cerrado_ancla_ejecutado_e_ingreso_real_sin_neutros PASSED [ 13%]
tests/test_e1_loader.py::test_mes_en_ejecucion_ancla_ejecutado_y_definido PASSED [ 15%]
tests/test_e1_loader.py::test_mes_propuesto_con_definido_es_regimen_presupuesto PASSED [ 16%]
tests/test_e1_loader.py::test_futuro_sin_definido_y_sin_mescontrol_se_omiten PASSED [ 18%]
tests/test_e1_loader.py::test_rubros_info_y_neutros_ids_se_arman PASSED  [ 20%]
tests/test_e1_loader.py::test_paso0_mes_con_rubro_sistema_sucio_no_se_ancla PASSED [ 22%]
tests/test_e1_loader.py::test_paso0_clasificables_y_neutros_no_disparan PASSED [ 24%]
tests/test_e1_loader.py::test_cerrado_trae_definido_para_la_marca PASSED [ 26%]
tests/test_e1_loader_realmongo.py::TestLoaderReal::test_cerrado_agrega_egresos_y_en_ejecucion_lee_definido SKIPPED [ 28%]
tests/test_e1_loader_realmongo.py::TestLoaderReal::test_paso0_rubro_sistema_sucio_excluye_el_mes_real SKIPPED [ 30%]
tests/test_e1_pipeline.py::test_b8_b11_candado_composicion PASSED        [ 32%]
tests/test_e1_pipeline.py::test_c1_d2_aplica_pago_real_en_mes_anclado_no_cerrado[en_ejecucion] PASSED [ 33%]
tests/test_e1_pipeline.py::test_c1_d2_aplica_pago_real_en_mes_anclado_no_cerrado[presupuesto] PASSED [ 35%]
tests/test_e1_pipeline.py::test_b10_loguea_mes_cerrado_sospechoso PASSED [ 37%]
tests/test_e1_anclaje.py::test_b1_sin_ancla_es_base_bit_a_bit PASSED     [ 39%]
tests/test_e1_anclaje.py::test_b2_cerrado_ejecutado_real_y_reacumula PASSED [ 41%]
tests/test_e1_anclaje.py::test_b3_regla_a_incluye_ejecutado_mayor_que_definido PASSED [ 43%]
tests/test_e1_anclaje.py::test_b4_futuro_con_presupuesto_usa_definido PASSED [ 45%]
tests/test_e1_anclaje.py::test_b5_futuro_sin_presupuesto_es_el_motor PASSED [ 47%]
tests/test_e1_anclaje.py::test_a3_fixture_julio_real_b2_y_b6 PASSED      [ 49%]
tests/test_e1_anclaje.py::test_cerrado_ignora_definido_inercia PASSED    [ 50%]
tests/test_e1_precedencia.py::test_candado_vacio_identico_a_hoy PASSED   [ 52%]
tests/test_e1_precedencia.py::test_b7_d2_salta_el_mes_anclado_y_reconcilia_el_resto PASSED [ 54%]
tests/test_reconciliacion.py::test_sin_facturas_es_base_bit_a_bit PASSED [ 56%]
tests/test_reconciliacion.py::test_pagos_fuera_del_horizonte_no_reconcilian PASSED [ 58%]
tests/test_reconciliacion.py::test_una_factura_netea_el_parametrico_y_suma_el_real PASSED [ 60%]
tests/test_reconciliacion.py::test_meses_fuera_de_la_ventana_intactos PASSED [ 62%]
tests/test_reconciliacion.py::test_coherencia_concepto_a_concepto_toda_la_serie PASSED [ 64%]
tests/test_reconciliacion.py::test_ventana_reescribe_conceptos_con_el_pago_real PASSED [ 66%]
tests/test_reconciliacion.py::test_hueco_en_ventana_netea_el_parametrico_a_cero PASSED [ 67%]
tests/test_rubros_neutros.py::test_resuelve_solo_los_neutros_presentes PASSED [ 69%]
tests/test_rubros_neutros.py::test_vacio_si_no_existen PASSED            [ 71%]
tests/test_rubros_neutros.py::test_metas_ingreso_reexporta_el_mismo_resolver PASSED [ 73%]
tests/test_ingreso_real_neutros.py::test_reversas_no_suma_pero_recaudo_si PASSED [ 75%]
tests/test_ingreso_real_neutros.py::test_recaudo_solo_cuenta_completo PASSED [ 77%]
tests/test_ingreso_real_neutros.py::test_sin_mes_control_es_none PASSED  [ 79%]
tests/test_ingreso_real_neutros.py::test_transito_wava_no_suma_ingreso_real PASSED [ 81%]
tests/test_ingreso_real_neutros.py::test_ajuste_conciliacion_no_suma_ingreso_real PASSED [ 83%]
tests/test_proyeccion_endpoints.py::test_proyeccion_sin_config_es_409 PASSED [ 84%]
tests/test_proyeccion_endpoints.py::test_flujo_completo_ingreso_discriminado_y_kpis PASSED [ 86%]
tests/test_proyeccion_endpoints.py::test_operacion_cartera_por_anada_y_colocacion PASSED [ 88%]
tests/test_proyeccion_endpoints.py::test_operacion_sin_config_es_409 PASSED [ 90%]
tests/test_proyeccion_endpoints.py::test_comparar_actuals_vs_forecast_rolling PASSED [ 92%]
tests/test_proyeccion_endpoints.py::test_comparar_ancla_modo_invalido_es_422 PASSED [ 94%]
tests/test_proyeccion_endpoints.py::test_escenario_pesimista_menos_caja_que_optimista PASSED [ 96%]
tests/test_proyeccion_endpoints.py::test_rbac_mutaciones_solo_gestionar PASSED [ 98%]
tests/test_proyeccion_endpoints.py::test_modelo_baja_logica_y_reactivar PASSED [100%]
SKIPPED [1] tests\test_e1_loader_realmongo.py:39: requiere Mongo real; correr con: pytest -m requires_real_mongo
SKIPPED [1] tests\test_e1_loader_realmongo.py:114: requiere Mongo real; correr con: pytest -m requires_real_mongo
================ 51 passed, 2 skipped, 431 warnings in 27.46s =================

```

## 4. R0

```
$ git diff origin/main...HEAD -- backend/app/proyeccion/motor.py | wc -l
0
```

## 5. ruff

```
$ python -m ruff check app/ tests/
All checks passed!
$ python -m ruff format --check app/ tests/
246 files already formatted
```
