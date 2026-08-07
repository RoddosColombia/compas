# EVIDENCIA — E1 PR3-I + P3.1 (código real + salidas de tests)

Acompaña a `SOLICITUD.md` y `ADDENDUM-P3.1.md`. Incluye el **diff completo** contra
`origin/main` (ya con la corrección C-1) y las **salidas reales** de tests/ruff/R0.
PR #70 · commits `f8e21d1` (P3) + `18cbdb0` (C-1/P3.1).

## 1. Resumen de verificación (P3.1)

- **pytest E1 + relacionados:** 45 passed, 1 skipped (variante real-mongo del loader).
- **Regresión completa del backend:** 890 passed, 93 skipped, 0 fallos (12m12s).
- **ruff:** `All checks passed!` + `format --check` limpio.
- **R0:** `git diff origin/main -- backend/app/proyeccion/motor.py` → 0 líneas.
- **Test C-1 (nuevo):** `test_c1_d2_aplica_pago_real_en_mes_anclado_no_cerrado`
  [en_ejecucion, presupuesto] — RED (−10.000 paramétrico) → GREEN (−1.000.000 real).

---

# ADDENDUM P3.1 — corrección del hallazgo C-1 (re-gate)

**Gate previo:** Kimi 8.7/10 NO-GO (2026-08-07) · **Hallazgo:** C-1 (bloqueante, arquitectónico — del plan §3/B7 aprobado por el propio auditor, no de la implementación) · **Este addendum:** aplica C-1 con TDD y re-pide gate.

## Qué encontró C-1

`_resultado_con` pasaba a D2 `meses_anclados = frozenset(anclas)` (TODOS los regímenes: `cerrado`, `en_ejecucion`, `presupuesto`). Como E1 **nunca ancla Auteco** (sus 5 conceptos son `gastos_fijos/gps/costo_nueva/int_deuda/iva`; en el delta de flujo el `pago_inventario`/`fondeo` paramétrico se cancela), excluir de D2 los meses **no cerrados** no evitaba ningún doble conteo — solo hacía **desaparecer** los pagos reales de FIX-K de esos meses (p. ej. al acotar el presupuesto de septiembre, sus $123.392.031 reales quedaban reemplazados por el paramétrico). Regresión de FIX-K sobre la exigencia #1 del CEO.

## El fix (quirúrgico, Regla B — NO refactor)

1. **`backend/app/proyeccion/service.py` `_resultado_con`:**
   ```python
   meses_anclados = frozenset(m for m, a in anclas.items() if a.estado == CERRADO)
   ```
   Solo los meses **cerrados** se excluyen de D2 (el pasado es del libro; sus facturas ya no están pendientes). En `en_ejecucion`/`presupuesto`, D2 aplica el pago real — compone limpio con E1 (campos disjuntos: E1 escribe los 5 conceptos no-Auteco, D2 escribe `pago_inventario`/`fondeo`; deltas aditivos vía `reacumular`). El conjunto completo (`frozenset(anclas)`) se reserva para las marcas de origen de la UI en **P5** — NO se alimenta a D2. `CERRADO` se importa de `ejecucion.service`.

2. **`backend/app/obligaciones/reconciliacion.py`:** corregido el docstring — la exclusión aplica SOLO a meses cerrados; en no-cerrados D2 aplica el pago real sin doble conteo. (El paréntesis previo "esa realidad ya la puso E1" era falso para Auteco.)

3. **Test de regresión NUEVO** (`test_e1_pipeline.py::test_c1_d2_aplica_pago_real_en_mes_anclado_no_cerrado`, parametrizado `en_ejecucion` + `presupuesto`): mes anclado no-cerrado con factura que paga ahí → D2 aplica el pago real (`pago_inventario == −capital`, `fondeo == −interés`) Y el concepto que E1 ancló por Regla A (`int_deuda == −800.00`) se conserva en la misma fila; el mes no anclado (2026-12) reconcilia normal. **Rojo antes del fix** (daba el Auteco paramétrico `−10.000,00` en vez del real `−1.000.000,00`), **verde después**.

## Lo que NO se tocó (por exigencia del re-gate)

`motor.py` (R0), `ejecucion/service.py`, `lectura.py`, `loader.py`, y `reconciliacion.py` salvo el docstring del punto 2. Los tests existentes (pipeline con 2026-10 `cerrado`, B7 puro con set explícito) siguen **verdes sin modificarlos** — la capa de reconciliación y el candado no cambian.

## Baja B-1 (diferida a P4, con visto de Kimi)

`cargar_anclas` corre dentro de `_resultado_con`, que se invoca por escenario (base/optimista/pesimista) → el mismo trabajo Mongo (depende solo de `mes_inicio`/`horizonte`) se repite hasta 3× por carga de página. Correctitud intacta. Kimi la dejó a criterio ("puede ir en P4"); se difiere a P4 para mantener este re-gate quirúrgico.

## Evidencia (ver EVIDENCIA.md actualizada)

- Test C-1 nuevo: **2 passed** (en_ejecucion + presupuesto). Pipeline existente + B7 puro: verdes sin cambios.
- Regresión completa del backend: ver EVIDENCIA.md (§1).
- ruff check + format: limpios. R0: `motor.py` 0 diffs.
- Diff del fix: `_resultado_con` (1 línea efectiva + comentario), docstring de `reconciliar`, y el test nuevo.


---

## 2. Diff completo (`git diff origin/main...HEAD -- backend/`)

```diff
diff --git a/backend/app/domain/rubros_neutros.py b/backend/app/domain/rubros_neutros.py
index 1c4a92e..9658d36 100644
--- a/backend/app/domain/rubros_neutros.py
+++ b/backend/app/domain/rubros_neutros.py
@@ -12,7 +12,14 @@ El set:
   • 'Ajuste de conciliación'     — CR-WAVA: contra-asiento de una reapertura de cierre.
 
 Promovido desde `metas_ingreso.service` (donde nació con FIX-B) para que E1 y metas
-compartan exactamente el mismo conjunto — no dos copias que puedan divergir."""
+compartan exactamente el mismo conjunto — no dos copias que puedan divergir. El set Y su
+resolver nombre→id viven aquí (una verdad, un lugar); `metas_ingreso` los re-exporta
+y el loader E1 los importa de aquí."""
+
+from beanie import PydanticObjectId
+from beanie.operators import In
+
+from app.domain.rubro import Rubro
 
 RUBROS_NEUTROS_INGRESO_REAL: frozenset[str] = frozenset(
     {
@@ -21,3 +28,13 @@ RUBROS_NEUTROS_INGRESO_REAL: frozenset[str] = frozenset(
         "Ajuste de conciliación",
     }
 )
+
+
+async def _ids_rubros_neutros() -> set[PydanticObjectId]:
+    """IDs de los rubros neutros (por nombre) presentes en la BD. Vacío si ninguno
+    existe todavía (p. ej. antes de FIX-B) → la exclusión es inocua. La exclusión se
+    resuelve SIEMPRE por `rubro_id` (una verdad compartida por E1 y metas)."""
+    return {
+        r.id
+        async for r in Rubro.find(In(Rubro.nombre, list(RUBROS_NEUTROS_INGRESO_REAL)))
+    }
diff --git a/backend/app/metas_ingreso/service.py b/backend/app/metas_ingreso/service.py
index a61121d..44f7495 100644
--- a/backend/app/metas_ingreso/service.py
+++ b/backend/app/metas_ingreso/service.py
@@ -8,7 +8,6 @@ meta activa por mes."""
 from decimal import Decimal
 
 from beanie import PydanticObjectId
-from beanie.operators import In
 
 from app.audit.events import AuditEvento
 from app.audit.service import emit_audit
@@ -16,13 +15,16 @@ from app.core.money import Money
 from app.core.time import now_bogota
 from app.domain.mes_control import MesControl
 from app.domain.obligacion import LineaMeta, MetaIngreso
-from app.domain.rubro import Rubro
 
-# El set de neutros vive en `app.domain.rubros_neutros` (E1 lo comparte — una verdad,
-# un lugar); se re-exporta aquí para no romper los importadores existentes.
+# El set de neutros Y su resolver nombre→id viven en `app.domain.rubros_neutros` (E1 lo
+# comparte — una verdad, un lugar); se re-exportan aquí para no romper los importadores
+# existentes (metas_ingreso.service._ids_rubros_neutros sigue disponible).
 from app.domain.rubros_neutros import (
     RUBROS_NEUTROS_INGRESO_REAL as RUBROS_NEUTROS_INGRESO_REAL,
 )
+from app.domain.rubros_neutros import (
+    _ids_rubros_neutros as _ids_rubros_neutros,
+)
 from app.domain.transaccion import TipoFlujo, Transaccion
 
 
@@ -142,15 +144,6 @@ async def eliminar_meta(*, meta_id: str, usuario_id: str) -> None:
         raise
 
 
-async def _ids_rubros_neutros() -> set[PydanticObjectId]:
-    """IDs de los rubros neutros (por nombre) presentes en la BD. Vacío si ninguno
-    existe todavía (p. ej. antes de FIX-B) → la exclusión es inocua."""
-    return {
-        r.id
-        async for r in Rubro.find(In(Rubro.nombre, list(RUBROS_NEUTROS_INGRESO_REAL)))
-    }
-
-
 async def ingreso_real(mes: str) -> Decimal | None:
     """Ingreso ejecutado del mes = Σ de las transacciones de INGRESO, EXCLUIDOS los
     rubros neutros (reversas/devoluciones; a futuro tránsito Wava y ajuste). None si el
diff --git a/backend/app/obligaciones/reconciliacion.py b/backend/app/obligaciones/reconciliacion.py
index 000c6ea..0bac75d 100644
--- a/backend/app/obligaciones/reconciliacion.py
+++ b/backend/app/obligaciones/reconciliacion.py
@@ -54,7 +54,17 @@ def reconciliar(
     resultado: ResultadoProyeccion,
     facturas: list[FacturaReconciliar],
     caja_minima: Decimal,
+    *,
+    meses_anclados: frozenset[str] = frozenset(),
 ) -> ResultadoReconciliado:
+    """`meses_anclados` (E1·P3): SOLO los meses CERRADOS quedan fuera de esta
+    reconciliación — el pasado es del libro (sus facturas ya no están pendientes). En
+    los meses NO cerrados D2 SÍ aplica el pago real: E1 no ancla Auteco (sus 5
+    conceptos excluyen pago_inventario/fondeo y en su delta el paramétrico se cancela),
+    así que aplicar la factura ahí compone limpio, sin doble conteo (campos disjuntos,
+    deltas aditivos). Por eso el llamador solo pasa los meses cerrados, no todos los
+    anclados. Precedencia `motor → EJECUCIÓN (E1) → OBLIGACIONES (D2) → IMPACTOS (D1)`.
+    Con `meses_anclados` vacío la serie es idéntica a hoy (candado de no-regresión)."""
     base = resultado.meses
     n = len(base)
     idx = {fila.mes: i for i, fila in enumerate(base)}
@@ -73,8 +83,8 @@ def reconciliar(
         cap[p.mes] = _cop(cap.get(p.mes, _CERO) + p.capital)
         interes[p.mes] = _cop(interes.get(p.mes, _CERO) + p.interes)
 
-    # solo los pagos que caen DENTRO del horizonte proyectado cuentan para la ventana
-    meses_pago = sorted(m for m in cap if m in idx)
+    # solo los pagos DENTRO del horizonte y NO anclados por E1 cuentan para la ventana
+    meses_pago = sorted(m for m in cap if m in idx and m not in meses_anclados)
     if not meses_pago:
         return ResultadoReconciliado(
             ajustado=reacumular(resultado, [_CERO] * n, caja_minima),
@@ -90,6 +100,8 @@ def reconciliar(
     deltas = [_CERO] * n
     for m in range(i_desde, i_hasta + 1):
         fila = base[m]
+        if fila.mes in meses_anclados:
+            continue  # anclado por E1 → D2 no lo toca (evita doble conteo)
         # pago_inventario y fondeo son NEGATIVOS (egresos); netearlos = sumar su opuesto
         deltas[m] = _cop(deltas[m] - fila.pago_inventario - fila.fondeo)
     for mes in meses_pago:
@@ -109,6 +121,8 @@ def reconciliar(
     filas = list(ajustado.meses)
     for m in range(i_desde, i_hasta + 1):
         mes = base[m].mes
+        if mes in meses_anclados:
+            continue  # anclado por E1 → conserva lo que E1 escribió, D2 no reescribe
         filas[m] = replace(
             filas[m],
             pago_inventario=_cop(-cap.get(mes, _CERO)),
diff --git a/backend/app/proyeccion/ejecucion/loader.py b/backend/app/proyeccion/ejecucion/loader.py
new file mode 100644
index 0000000..ee4fc76
--- /dev/null
+++ b/backend/app/proyeccion/ejecucion/loader.py
@@ -0,0 +1,117 @@
+# backend/app/proyeccion/ejecucion/loader.py
+"""E1 · P3 — loader de anclaje (la ÚNICA capa Mongo de E1).
+
+Dado `(mes_inicio, horizonte)`, arma los insumos que `ejecucion.service.anclar` consume:
+el dict `anclas: {'YYYY-MM': AnclaMes}`, la lista de `RubroInfo` y el set `neutros_ids`.
+Traduce el estado del ciclo (`MesControl`) al régimen de anclaje del plan §1:
+
+    CERRADO       → 'cerrado'      : ejecutado por rubro + ingreso_real (sin neutros)
+    EN_EJECUCION  → 'en_ejecucion' : ejecutado real + presupuesto definido (Regla A)
+    otro estado con definido vigente > 0 → 'presupuesto' : solo el definido
+    sin MesControl / futuro sin definido → OMITIDO (el motor queda intacto)
+
+`lectura.py` (P1) y `service.py` (P2) siguen PUROS (sin Mongo): esta es la capa que los
+alimenta. Reusa las queries ya probadas —`_egresos_por_rubro`, `PresupuestoLinea`
+vigente, `metas_ingreso.ingreso_real`, `rubros_neutros._ids_rubros_neutros`— sin
+reinventar agregaciones.
+"""
+
+from __future__ import annotations
+
+from decimal import Decimal
+
+from beanie import PydanticObjectId
+from beanie.operators import In
+
+from app.control.service import _egresos_por_rubro
+from app.domain.mes_control import EstadoMes, MesControl
+from app.domain.presupuesto import PresupuestoLinea
+from app.domain.rubro import Rubro
+from app.domain.rubros_neutros import _ids_rubros_neutros
+from app.metas_ingreso.service import ingreso_real
+from app.proyeccion.ejecucion.lectura import RubroInfo
+from app.proyeccion.ejecucion.service import (
+    CERRADO,
+    EN_EJECUCION,
+    PRESUPUESTO,
+    AnclaMes,
+)
+from app.proyeccion.motor import _meses_del_horizonte
+
+_CERO = Decimal("0")
+
+
+async def _rubros_info() -> list[RubroInfo]:
+    """Snapshot de la taxonomía → `RubroInfo` (id como str, grupo como valor plano)."""
+    return [
+        RubroInfo(
+            id=str(r.id),
+            codigo=r.codigo,
+            grupo=r.grupo.value,
+            nombre=r.nombre,
+            es_sistema=r.es_sistema,
+        )
+        for r in await Rubro.find_all().to_list()
+    ]
+
+
+async def _definido_por_rubro(mes_id: PydanticObjectId) -> dict[str, Decimal]:
+    """Presupuesto DEFINIDO vigente por rubro (magnitud POSITIVA). `{}` si aún no hay
+    definido (líneas con `monto_definido` nulo o no positivas)."""
+    lineas = await PresupuestoLinea.find(
+        PresupuestoLinea.mes_id == mes_id,
+        PresupuestoLinea.vigente == True,  # noqa: E712 — Beanie exige la comparación
+    ).to_list()
+    return {
+        str(ln.rubro_id): ln.monto_definido
+        for ln in lineas
+        if ln.monto_definido is not None and ln.monto_definido > _CERO
+    }
+
+
+async def cargar_anclas(
+    mes_inicio: tuple[int, int], horizonte: int
+) -> tuple[dict[str, AnclaMes], list[RubroInfo], set[str]]:
+    """Arma `(anclas, rubros, neutros_ids)` para `anclar`. Los meses sin MesControl o
+    futuros sin presupuesto definido quedan fuera de `anclas` (el motor los cubre)."""
+    meses = [f"{a:04d}-{m:02d}" for a, m in _meses_del_horizonte(mes_inicio, horizonte)]
+    rubros = await _rubros_info()
+    neutros_ids = {str(i) for i in await _ids_rubros_neutros()}
+
+    # un solo query para los MesControl del horizonte
+    claves = [f"{m}-01" for m in meses]
+    por_mes = {
+        mc.mes[:7]: mc
+        for mc in await MesControl.find(In(MesControl.mes, claves)).to_list()
+    }
+
+    anclas: dict[str, AnclaMes] = {}
+    for m in meses:
+        mc = por_mes.get(m)
+        if mc is None:
+            continue  # sin ciclo → motor intacto
+        if mc.estado == EstadoMes.CERRADO:
+            anclas[m] = AnclaMes(
+                estado=CERRADO,
+                ejecutado_por_rubro_id=await _egresos_por_rubro(mc.id),
+                definido_por_rubro_id={},
+                ingreso_real=await ingreso_real(m),
+            )
+        elif mc.estado == EstadoMes.EN_EJECUCION:
+            anclas[m] = AnclaMes(
+                estado=EN_EJECUCION,
+                ejecutado_por_rubro_id=await _egresos_por_rubro(mc.id),
+                definido_por_rubro_id=await _definido_por_rubro(mc.id),
+                ingreso_real=None,
+            )
+        else:
+            definido = await _definido_por_rubro(mc.id)
+            if definido:  # futuro con presupuesto definido vigente
+                anclas[m] = AnclaMes(
+                    estado=PRESUPUESTO,
+                    ejecutado_por_rubro_id={},
+                    definido_por_rubro_id=definido,
+                    ingreso_real=None,
+                )
+            # futuro sin definido → omitido (motor)
+    return anclas, rubros, neutros_ids
diff --git a/backend/app/proyeccion/service.py b/backend/app/proyeccion/service.py
index 6500821..714e0bd 100644
--- a/backend/app/proyeccion/service.py
+++ b/backend/app/proyeccion/service.py
@@ -30,6 +30,9 @@ from app.obligaciones.reconciliacion import (
     reconciliar,
 )
 from app.parametros_proyeccion import service as parametros_service
+from app.proyeccion.ejecucion.lectura import RubroInfo
+from app.proyeccion.ejecucion.loader import cargar_anclas
+from app.proyeccion.ejecucion.service import CERRADO, AnclaMes, anclar
 from app.proyeccion.impactos import Ajuste, aplicar_impactos
 from app.proyeccion.motor import (
     PRESETS_ESCENARIO,
@@ -307,12 +310,24 @@ async def _resultado_con(
     horizonte_meses: int | None,
     caja_inicial_override: object | None = None,
     facturas_override: list[FacturaReconciliar] | None = None,
+    anclas_override: tuple[dict[str, AnclaMes], list[RubroInfo], set[str]]
+    | None = None,
 ) -> tuple[ResultadoProyeccion, object, list, ResultadoReconciliado | None]:
-    """La tubería completa (cartera previa + IVA + motor + reconciliación D2) sobre un
-    set de parámetros DADO. Devuelve el ResultadoProyeccion CRUDO ya RECONCILIADO (las
-    facturas reales netean el Auteco paramétrico, §4) + umbral + fondo + la meta de
-    reconciliación (ventana/interés). Sin facturas activas la reconciliación es no-op
-    (base bit a bit): preview/vigente siguen idénticos por test."""
+    """La tubería completa sobre un set de parámetros DADO, en el orden de precedencia
+    `motor → EJECUCIÓN (E1) → OBLIGACIONES (D2) → IMPACTOS (D1)`:
+
+    1. `proyectar` — el motor paramétrico (R0, nunca se toca).
+    2. **E1 (anclaje):** sobre-escribe las líneas de los meses cerrados/en ejecución con
+       la ejecución real y re-acumula la caja (`ejecucion.service.anclar`). Composición
+       con COCK-09: COCK-09 ancla la caja inicial; E1 ancla las LÍNEAS y re-acumula
+       desde ahí — no hay doble anclaje. Con `anclas` vacío, la base bit a bit.
+    3. **D2 (reconciliación):** netea el Auteco paramétrico contra las facturas reales,
+       EXCLUYENDO los meses que E1 ya ancló (`meses_anclados`) para no contar dos veces.
+
+    Devuelve el ResultadoProyeccion crudo (anclado + reconciliado) + umbral + fondo + la
+    meta de reconciliación. Sin anclaje ni facturas es la base bit a bit (preview y
+    vigente idénticos por test). `anclas_override`/`facturas_override` inyectan insumos
+    deterministas en los tests (evitan Mongo)."""
     horizonte = horizonte_meses or params.horizonte_meses
     if horizonte < 1 or horizonte > HORIZONTE_MAX:
         raise ProyeccionError(
@@ -332,6 +347,30 @@ async def _resultado_con(
         caja_inicial_override,
     )
     r = proyectar(pm)
+
+    # E1 (P3) — anclar a la ejecución real ANTES de la reconciliación D2.
+    anclas, rubros_e1, neutros_e1 = (
+        anclas_override
+        if anclas_override is not None
+        else await cargar_anclas(mes_inicio, horizonte)
+    )
+    meses_anclados: frozenset[str] = frozenset()
+    if anclas:
+        aj = anclar(
+            resultado=r,
+            caja_minima=params.caja_minima,
+            anclas=anclas,
+            rubros=rubros_e1,
+            neutros_ids=neutros_e1,
+        )
+        r = _kpis_a_resultado(aj)
+        # D2 solo excluye los meses CERRADOS (el pasado es del libro; su factura ya no
+        # está pendiente). E1 NO ancla Auteco (sus 5 conceptos no incluyen el Auteco),
+        # así que en meses no-cerrados D2 SÍ aplica el pago real, sin doble conteo
+        # (campos disjuntos, deltas aditivos). El set completo de anclados queda como
+        # `frozenset(anclas)` para las marcas de origen de la UI en P5 — no se da a D2.
+        meses_anclados = frozenset(m for m, a in anclas.items() if a.estado == CERRADO)
+
     facturas = (
         facturas_override
         if facturas_override is not None
@@ -339,7 +378,9 @@ async def _resultado_con(
     )
     rec: ResultadoReconciliado | None = None
     if facturas:
-        rec = reconciliar(r, facturas, params.caja_minima)
+        rec = reconciliar(
+            r, facturas, params.caja_minima, meses_anclados=meses_anclados
+        )
         r = _kpis_a_resultado(rec.ajustado)
     return r, params.caja_minima, fondo, rec
 
diff --git a/backend/tests/test_e1_loader.py b/backend/tests/test_e1_loader.py
new file mode 100644
index 0000000..6d8d603
--- /dev/null
+++ b/backend/tests/test_e1_loader.py
@@ -0,0 +1,171 @@
+# backend/tests/test_e1_loader.py
+"""E1 · P3 — loader de anclaje (única capa Mongo). `cargar_anclas` traduce el estado del
+ciclo (MesControl) al régimen de anclaje del plan §1 y arma los insumos que consume
+`ejecucion.service.anclar` (dict `anclas`, `RubroInfo`, `neutros_ids`) reusando las
+queries ya probadas — sin reinventar agregaciones.
+
+    CERRADO       → 'cerrado'      : ejecutado por rubro + ingreso_real (sin neutros)
+    EN_EJECUCION  → 'en_ejecucion' : ejecutado + definido (Regla A la resuelve anclar)
+    otro estado con definido vigente > 0 → 'presupuesto' : solo el definido
+    sin MesControl / futuro sin definido → OMITIDO (motor intacto)
+"""
+
+from decimal import Decimal
+
+import pytest
+import pytest_asyncio
+from app.domain import DOMAIN_DOCUMENTS
+from app.domain.bancos import Banco
+from app.domain.mes_control import EstadoMes, MesControl
+from app.domain.presupuesto import PresupuestoLinea
+from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
+from app.domain.transaccion import Transaccion
+from app.proyeccion.ejecucion.lectura import RubroInfo
+from app.proyeccion.ejecucion.loader import cargar_anclas
+from beanie import init_beanie
+from mongomock_motor import AsyncMongoMockClient
+
+_MES_INICIO = (2026, 7)
+_HORIZONTE = 6  # 2026-07 .. 2026-12
+
+
+@pytest_asyncio.fixture
+async def db():
+    c = AsyncMongoMockClient(tz_aware=True)
+    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
+    yield c
+
+
+async def _mes(mes7: str, estado: EstadoMes) -> MesControl:
+    mc = MesControl(mes=f"{mes7}-01", saldo_inicial_caja=Decimal("0"), estado=estado)
+    await mc.insert()
+    return mc
+
+
+async def _rubro(grupo, nombre, flujo, codigo=None) -> Rubro:
+    r = Rubro(grupo=grupo, nombre=nombre, tipo_flujo=flujo, orden=1, codigo=codigo)
+    await r.insert()
+    return r
+
+
+async def _tx(mc, rubro, valor, flujo, ordinal) -> None:
+    await Transaccion(
+        fecha=f"{mc.mes[:7]}-10",
+        descripcion="mov",
+        valor=Decimal(valor),
+        tipo_flujo=flujo,
+        rubro_id=rubro.id,
+        mes_id=mc.id,
+        banco=Banco.GLOBAL66,
+        id_banco=f"REF-{mc.mes}-{ordinal}|1",
+    ).insert()
+
+
+async def _linea(mc, rubro, definido) -> None:
+    await PresupuestoLinea(
+        mes_id=mc.id,
+        rubro_id=rubro.id,
+        monto_sugerido=Decimal("0"),
+        prom_3m=Decimal("0"),
+        tendencia_mes=Decimal("0"),
+        crec_pct=Decimal("0"),
+        historia_incompleta=False,
+        monto_definido=definido,
+        vigente=True,
+    ).insert()
+
+
+@pytest_asyncio.fixture
+async def escenario(db):
+    """Un horizonte con los cuatro regímenes representados."""
+    gasto_a = await _rubro(RubroGrupo.OPERACION, "Arriendos", TipoFlujo.EGRESO, "2010")
+    gasto_b = await _rubro(
+        RubroGrupo.COSTO_PRODUCTO, "Producto", TipoFlujo.EGRESO, "1010"
+    )
+    recaudo = await _rubro(
+        RubroGrupo.INGRESOS_OPERATIVOS, "Recaudo de cartera", TipoFlujo.INGRESO, "0110"
+    )
+    neutro = await _rubro(
+        RubroGrupo.OTROS, "Reversas y devoluciones", TipoFlujo.INGRESO
+    )
+
+    # 2026-07 CERRADO: egreso real + ingreso (recaudo real + una reversa neutra)
+    jul = await _mes("2026-07", EstadoMes.CERRADO)
+    await _tx(jul, gasto_a, "5000", TipoFlujo.EGRESO, 1)
+    await _tx(jul, recaudo, "8000", TipoFlujo.INGRESO, 2)
+    await _tx(jul, neutro, "300", TipoFlujo.INGRESO, 3)  # neutro → excluido
+
+    # 2026-08 EN_EJECUCION: ejecutado real + presupuesto definido (Regla A)
+    ago = await _mes("2026-08", EstadoMes.EN_EJECUCION)
+    await _tx(ago, gasto_a, "2000", TipoFlujo.EGRESO, 1)
+    await _linea(ago, gasto_a, Decimal("6000"))
+    await _linea(ago, gasto_b, Decimal("3000"))
+
+    # 2026-09 PROPUESTO con definido vigente > 0 → régimen 'presupuesto'
+    sep = await _mes("2026-09", EstadoMes.PROPUESTO)
+    await _linea(sep, gasto_a, Decimal("4000"))
+
+    # 2026-10 SUGERIDO con línea SIN definido (monto_definido None) → omitido
+    oct_ = await _mes("2026-10", EstadoMes.SUGERIDO)
+    await _linea(oct_, gasto_a, None)
+
+    # 2026-11 y 2026-12 SIN MesControl → omitidos
+    return {
+        "gasto_a": gasto_a,
+        "gasto_b": gasto_b,
+        "recaudo": recaudo,
+        "neutro": neutro,
+    }
+
+
+@pytest.mark.asyncio
+async def test_mes_cerrado_ancla_ejecutado_e_ingreso_real_sin_neutros(escenario):
+    anclas, _, _ = await cargar_anclas(_MES_INICIO, _HORIZONTE)
+    a = anclas["2026-07"]
+    assert a.estado == "cerrado"
+    assert a.ejecutado_por_rubro_id == {str(escenario["gasto_a"].id): Decimal("5000")}
+    assert a.definido_por_rubro_id == {}
+    assert a.ingreso_real == Decimal("8000")  # 8000 recaudo, la reversa (300) excluida
+
+
+@pytest.mark.asyncio
+async def test_mes_en_ejecucion_ancla_ejecutado_y_definido(escenario):
+    anclas, _, _ = await cargar_anclas(_MES_INICIO, _HORIZONTE)
+    a = anclas["2026-08"]
+    assert a.estado == "en_ejecucion"
+    assert a.ejecutado_por_rubro_id == {str(escenario["gasto_a"].id): Decimal("2000")}
+    assert a.definido_por_rubro_id == {
+        str(escenario["gasto_a"].id): Decimal("6000"),
+        str(escenario["gasto_b"].id): Decimal("3000"),
+    }
+    assert a.ingreso_real is None
+
+
+@pytest.mark.asyncio
+async def test_mes_propuesto_con_definido_es_regimen_presupuesto(escenario):
+    """El régimen 'presupuesto' (plan §1) NO está dormido: un mes propuesto con
+    monto_definido > 0 se ancla con el definido, sin ejecutado ni ingreso."""
+    anclas, _, _ = await cargar_anclas(_MES_INICIO, _HORIZONTE)
+    a = anclas["2026-09"]
+    assert a.estado == "presupuesto"
+    assert a.definido_por_rubro_id == {str(escenario["gasto_a"].id): Decimal("4000")}
+    assert a.ejecutado_por_rubro_id == {}
+    assert a.ingreso_real is None
+
+
+@pytest.mark.asyncio
+async def test_futuro_sin_definido_y_sin_mescontrol_se_omiten(escenario):
+    anclas, _, _ = await cargar_anclas(_MES_INICIO, _HORIZONTE)
+    assert set(anclas) == {"2026-07", "2026-08", "2026-09"}
+    assert "2026-10" not in anclas  # SUGERIDO sin definido
+    assert "2026-11" not in anclas and "2026-12" not in anclas  # sin MesControl
+
+
+@pytest.mark.asyncio
+async def test_rubros_info_y_neutros_ids_se_arman(escenario):
+    _, rubros, neutros_ids = await cargar_anclas(_MES_INICIO, _HORIZONTE)
+    assert all(isinstance(r, RubroInfo) for r in rubros)
+    nombres = {r.nombre for r in rubros}
+    assert {"Arriendos", "Producto", "Recaudo de cartera"} <= nombres
+    # el único neutro presente es la reversa
+    assert neutros_ids == {str(escenario["neutro"].id)}
diff --git a/backend/tests/test_e1_loader_realmongo.py b/backend/tests/test_e1_loader_realmongo.py
new file mode 100644
index 0000000..2ee0c33
--- /dev/null
+++ b/backend/tests/test_e1_loader_realmongo.py
@@ -0,0 +1,112 @@
+# backend/tests/test_e1_loader_realmongo.py
+"""E1 · P3 — loader de anclaje contra Mongo REAL.
+
+La clasificación del loader se cubre en mongomock (`test_e1_loader.py`); esta capa
+verifica lo único sensible a mongomock-vs-real: la agregación `$group` de
+`_egresos_por_rubro` (Σ egresos por rubro) que alimenta el ejecutado del mes cerrado.
+@requires_real_mongo; CI lo provee (local con COMPAS_TEST_MONGO_URI)."""
+
+import os
+from decimal import Decimal
+
+import pytest
+import pytest_asyncio
+from app.domain import DOMAIN_DOCUMENTS
+from app.domain.bancos import Banco
+from app.domain.mes_control import EstadoMes, MesControl
+from app.domain.presupuesto import PresupuestoLinea
+from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
+from app.domain.transaccion import Transaccion
+from app.proyeccion.ejecucion.loader import cargar_anclas
+from beanie import init_beanie
+from motor.motor_asyncio import AsyncIOMotorClient
+
+
+@pytest.mark.requires_real_mongo
+class TestLoaderReal:
+    @pytest_asyncio.fixture
+    async def db(self):
+        uri = os.environ.get("COMPAS_TEST_MONGO_URI")
+        if not uri:
+            pytest.skip("COMPAS_TEST_MONGO_URI no configurado")
+        client = AsyncIOMotorClient(uri, tz_aware=True)
+        dbname = "compas_test_e1_loader"
+        await client.drop_database(dbname)
+        await init_beanie(database=client[dbname], document_models=DOMAIN_DOCUMENTS)
+        yield client
+        await client.drop_database(dbname)
+
+    @pytest.mark.asyncio
+    async def test_cerrado_agrega_egresos_y_en_ejecucion_lee_definido(self, db):
+        gasto = await Rubro(
+            grupo=RubroGrupo.OPERACION,
+            nombre="Arriendos",
+            tipo_flujo=TipoFlujo.EGRESO,
+            orden=1,
+            codigo="2010",
+        ).insert()
+        recaudo = await Rubro(
+            grupo=RubroGrupo.INGRESOS_OPERATIVOS,
+            nombre="Recaudo de cartera",
+            tipo_flujo=TipoFlujo.INGRESO,
+            orden=2,
+            codigo="0110",
+        ).insert()
+
+        jul = await MesControl(
+            mes="2026-07-01",
+            saldo_inicial_caja=Decimal("0"),
+            estado=EstadoMes.CERRADO,
+        ).insert()
+        # dos egresos del MISMO rubro → el $group real debe sumarlos (5000)
+        for i, v in enumerate(("3000", "2000")):
+            await Transaccion(
+                fecha="2026-07-10",
+                descripcion="egreso",
+                valor=Decimal(v),
+                tipo_flujo=TipoFlujo.EGRESO,
+                rubro_id=gasto.id,
+                mes_id=jul.id,
+                banco=Banco.GLOBAL66,
+                id_banco=f"REF-E-{i}|1",
+            ).insert()
+        await Transaccion(
+            fecha="2026-07-11",
+            descripcion="ingreso",
+            valor=Decimal("8000"),
+            tipo_flujo=TipoFlujo.INGRESO,
+            rubro_id=recaudo.id,
+            mes_id=jul.id,
+            banco=Banco.GLOBAL66,
+            id_banco="REF-I|1",
+        ).insert()
+
+        ago = await MesControl(
+            mes="2026-08-01",
+            saldo_inicial_caja=Decimal("0"),
+            estado=EstadoMes.EN_EJECUCION,
+        ).insert()
+        await PresupuestoLinea(
+            mes_id=ago.id,
+            rubro_id=gasto.id,
+            monto_sugerido=Decimal("0"),
+            prom_3m=Decimal("0"),
+            tendencia_mes=Decimal("0"),
+            crec_pct=Decimal("0"),
+            historia_incompleta=False,
+            monto_definido=Decimal("6000"),
+            vigente=True,
+        ).insert()
+
+        anclas, _rubros, _neutros = await cargar_anclas((2026, 7), 2)
+
+        assert anclas["2026-07"].estado == "cerrado"
+        # el $group real sumó los dos egresos del rubro
+        assert anclas["2026-07"].ejecutado_por_rubro_id == {
+            str(gasto.id): Decimal("5000")
+        }
+        assert anclas["2026-07"].ingreso_real == Decimal("8000")
+        assert anclas["2026-08"].estado == "en_ejecucion"
+        assert anclas["2026-08"].definido_por_rubro_id == {
+            str(gasto.id): Decimal("6000")
+        }
diff --git a/backend/tests/test_e1_pipeline.py b/backend/tests/test_e1_pipeline.py
new file mode 100644
index 0000000..4eca849
--- /dev/null
+++ b/backend/tests/test_e1_pipeline.py
@@ -0,0 +1,245 @@
+# backend/tests/test_e1_pipeline.py
+"""E1 · P3 — composición en `_resultado_con` (integración: motor → E1 → D2 → IMPACTOS).
+
+Verifica el ORDEN efectivo y la no-colisión E1×D2 leyendo `_resultado_con`, con
+`anclas_override`/`facturas_override` para determinismo. Tres corridas sobre el mismo
+motor:
+
+    A = anclar 2026-10 + facturas que pagan 2026-10 y 2026-12
+    B = anclar 2026-10 + SIN facturas   (Auteco de 2026-10 = paramétrico del motor)
+    C = SIN anclaje    + las mismas facturas
+
+B8  — orden efectivo: en A, 2026-10 lo fija E1 y D2 lo SALTA (≠ C, que lo reconcilia).
+B11 — E1 no toca Auteco (A[2026-10] == B[2026-10], el paramétrico), y D2 solo toca los
+      NO anclados (A[2026-12] = pago real).
+Candado — sin anclaje (C) D2 reconcilia todo como hoy (2026-10 con su pago real)."""
+
+from decimal import Decimal
+
+import pytest
+import pytest_asyncio
+from app.domain import DOMAIN_DOCUMENTS
+from app.domain.modelo_moto import ModeloMoto
+from app.domain.parametros_proyeccion import ParametrosProyeccion
+from app.obligaciones.calculadora import pago_factura
+from app.obligaciones.reconciliacion import FacturaReconciliar
+from app.proyeccion.ejecucion.lectura import RubroInfo
+from app.proyeccion.ejecucion.service import AnclaMes
+from app.proyeccion.service import _resultado_con
+from beanie import init_beanie
+from mongomock_motor import AsyncMongoMockClient
+
+_MES_INICIO = (2026, 7)
+_HORIZONTE = 12
+
+# Plan con los 9 códigos del mapeo presentes (B12 no dispara). Sin ejecutado, E1 solo
+# ancla ingreso_real y CONSERVA el Auteco del motor — justo lo que B11 mide.
+_PLAN = [
+    ("0110", "ingresos_operativos", "Recaudo de cartera"),
+    ("1010", "costo_producto", "Producto"),
+    ("1020", "costo_producto", "SOAT/Matrículas"),
+    ("1030", "costo_producto", "Seguros"),
+    ("4010", "deudas_obligaciones", "Préstamos"),
+    ("4020", "deudas_obligaciones", "Tarjetas"),
+    ("4030", "deudas_obligaciones", "Garantía cupo"),
+    ("4050", "deudas_obligaciones", "Proveedores"),
+    ("5060", "otros", "Impuestos"),
+]
+
+
+def _rubros() -> list[RubroInfo]:
+    return [
+        RubroInfo(id=cod, codigo=cod, grupo=gr, nombre=nom, es_sistema=False)
+        for (cod, gr, nom) in _PLAN
+    ]
+
+
+def _params() -> ParametrosProyeccion:
+    return ParametrosProyeccion(
+        vigente_desde="2026-07-01",
+        caja_inicial=Decimal("500000"),
+        caja_minima=Decimal("10000"),
+        motos_base=2,
+        crec_pct_mensual=Decimal("0"),
+        horizonte_meses=_HORIZONTE,
+        adelanto_auteco=Decimal("0"),
+        plazo_auteco_dias=60,
+        base_auteco_dias=30,
+        tasa_auteco=Decimal("0.016"),
+        gastos_fijos=Decimal("1000"),
+        gps_moto=Decimal("0"),
+        costo_moto_nueva=Decimal("0"),
+        deuda=Decimal("0"),
+        tasa_deuda=Decimal("0"),
+        mes_inicio_deuda=0,
+        meses_deuda=0,
+        pct_mora=Decimal("0"),
+        pct_recuperacion=Decimal("0"),
+        pct_default=Decimal("0"),
+        pct_provision=Decimal("0"),
+    )
+
+
+def _modelos() -> list[ModeloMoto]:
+    return [
+        ModeloMoto(
+            nombre="Raider",
+            costo_auteco=Decimal("5000"),
+            precio_venta_con_iva=Decimal("6000"),
+            cuota_inicial=Decimal("1000"),
+            cuota_semanal=Decimal("100"),
+            plazo_semanas=6,
+            matricula=Decimal("0"),
+            participacion_mix=Decimal("1"),
+            orden=1,
+        )
+    ]
+
+
+def _facturas() -> list[FacturaReconciliar]:
+    # pagan 2026-10 (plazo 60) y 2026-12 (plazo 120)
+    return [
+        FacturaReconciliar(
+            fecha_factura="2026-08-15",
+            valor=Decimal("1000000"),
+            plazo_elegido_dias=60,
+            plazo_base_dias=30,
+            tasa_excedente_mensual=Decimal("0.016"),
+        ),
+        FacturaReconciliar(
+            fecha_factura="2026-08-15",
+            valor=Decimal("2000000"),
+            plazo_elegido_dias=120,
+            plazo_base_dias=30,
+            tasa_excedente_mensual=Decimal("0.016"),
+        ),
+    ]
+
+
+def _anclas_oct():
+    """Ancla 2026-10 como CERRADO con solo ingreso_real (ejecutado vacío) → E1 conserva
+    el Auteco del motor en ese mes."""
+    anclas = {
+        "2026-10": AnclaMes(
+            estado="cerrado",
+            ejecutado_por_rubro_id={},
+            definido_por_rubro_id={},
+            ingreso_real=Decimal("123456.00"),
+        )
+    }
+    return anclas, _rubros(), set()
+
+
+@pytest_asyncio.fixture
+async def db():
+    c = AsyncMongoMockClient(tz_aware=True)
+    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
+    yield c
+
+
+async def _correr(anclas_override, facturas_override):
+    r, _cm, _fondo, _rec = await _resultado_con(
+        _params(),
+        _modelos(),
+        escenario="base",
+        mes_inicio=_MES_INICIO,
+        horizonte_meses=_HORIZONTE,
+        anclas_override=anclas_override,
+        facturas_override=facturas_override,
+    )
+    return {m.mes: m for m in r.meses}
+
+
+@pytest.mark.asyncio
+async def test_b8_b11_candado_composicion(db):
+    a = await _correr(_anclas_oct(), _facturas())  # A
+    b = await _correr(_anclas_oct(), [])  # B
+    c = await _correr(({}, [], set()), _facturas())  # C
+
+    cap_oct = pago_factura(
+        fecha_factura="2026-08-15",
+        valor=Decimal("1000000"),
+        plazo_elegido_dias=60,
+        plazo_base_dias=30,
+        tasa_excedente_mensual=Decimal("0.016"),
+    )
+    cap_dic = pago_factura(
+        fecha_factura="2026-08-15",
+        valor=Decimal("2000000"),
+        plazo_elegido_dias=120,
+        plazo_base_dias=30,
+        tasa_excedente_mensual=Decimal("0.016"),
+    )
+
+    # B11 — E1 no toca Auteco: 2026-10 anclado conserva el paramétrico (A == B), aun
+    # cuando una factura paga ahí (D2 lo excluyó).
+    assert a["2026-10"].pago_inventario == b["2026-10"].pago_inventario
+    assert a["2026-10"].fondeo == b["2026-10"].fondeo
+
+    # B11 — D2 solo toca los NO anclados: 2026-12 lleva el pago real.
+    assert a["2026-12"].pago_inventario == Decimal(f"-{cap_dic.capital}")
+    assert a["2026-12"].fondeo == Decimal(f"-{cap_dic.interes}")
+
+    # B8 — orden efectivo: sin anclaje (C) D2 SÍ reconcilia 2026-10; con anclaje (A) NO.
+    assert c["2026-10"].pago_inventario == Decimal(f"-{cap_oct.capital}")
+    assert c["2026-10"].pago_inventario != a["2026-10"].pago_inventario
+
+    # E1 corrió: el mes anclado tomó el ingreso real anclado.
+    assert a["2026-10"].neto == Decimal("123456.00")
+
+
+def _anclas_no_cerrado(estado):
+    """Ancla 2026-10 en un régimen NO cerrado con un egreso NO-Auteco (int_deuda vía
+    4010). en_ejecucion usa Regla A (ejec+max(0,def-ejec)); presupuesto solo definido.
+    Ambos → int_deuda anclado = 800 (→ -800.00). E1 NO toca Auteco en ningún caso."""
+    if estado == "en_ejecucion":
+        ancla = AnclaMes(
+            estado="en_ejecucion",
+            ejecutado_por_rubro_id={"4010": Decimal("500")},
+            definido_por_rubro_id={"4010": Decimal("800")},
+            ingreso_real=None,
+        )
+    else:  # presupuesto
+        ancla = AnclaMes(
+            estado="presupuesto",
+            ejecutado_por_rubro_id={},
+            definido_por_rubro_id={"4010": Decimal("800")},
+            ingreso_real=None,
+        )
+    return {"2026-10": ancla}, _rubros(), set()
+
+
+@pytest.mark.asyncio
+@pytest.mark.parametrize("estado", ["en_ejecucion", "presupuesto"])
+async def test_c1_d2_aplica_pago_real_en_mes_anclado_no_cerrado(db, estado):
+    """C-1 (gate PR3-I): E1 no ancla Auteco, así que en un mes anclado NO cerrado D2 SÍ
+    debe aplicar el pago real de la factura (sin doble conteo — campos disjuntos) y
+    conservar los campos que E1 ancló. Antes del fix, meses_anclados=frozenset(anclas)
+    excluía estos meses y el pago real de FIX-K desaparecía de la proyección."""
+    a = await _correr(_anclas_no_cerrado(estado), _facturas())  # con facturas
+    b = await _correr(_anclas_no_cerrado(estado), [])  # sin facturas (referencia)
+    cap_oct = pago_factura(
+        fecha_factura="2026-08-15",
+        valor=Decimal("1000000"),
+        plazo_elegido_dias=60,
+        plazo_base_dias=30,
+        tasa_excedente_mensual=Decimal("0.016"),
+    )
+    cap_dic = pago_factura(
+        fecha_factura="2026-08-15",
+        valor=Decimal("2000000"),
+        plazo_elegido_dias=120,
+        plazo_base_dias=30,
+        tasa_excedente_mensual=Decimal("0.016"),
+    )
+
+    # EL FIX — D2 aplica el pago REAL en el mes anclado no-cerrado (antes: excluido).
+    assert a["2026-10"].pago_inventario == Decimal(f"-{cap_oct.capital}")
+    assert a["2026-10"].fondeo == Decimal(f"-{cap_oct.interes}")
+
+    # E1 ancló int_deuda (=800 → -800.00) y D2 NO lo tocó (campos disjuntos).
+    assert a["2026-10"].int_deuda == Decimal("-800.00")
+    assert a["2026-10"].int_deuda == b["2026-10"].int_deuda
+
+    # 2026-12 (no anclado) reconcilia normal.
+    assert a["2026-12"].pago_inventario == Decimal(f"-{cap_dic.capital}")
diff --git a/backend/tests/test_e1_precedencia.py b/backend/tests/test_e1_precedencia.py
new file mode 100644
index 0000000..733ff21
--- /dev/null
+++ b/backend/tests/test_e1_precedencia.py
@@ -0,0 +1,122 @@
+# backend/tests/test_e1_precedencia.py
+"""E1 · P3 — precedencia y no-colisión con D2 (capa pura de reconciliación).
+
+La reconciliación D2 (Auteco) debe EXCLUIR los meses que E1 ya ancló: no netea su
+paramétrico ni aplica pagos reales ahí (esa realidad ya la puso E1; tocarla sería doble
+conteo). `meses_anclados` es aditivo: vacío ⇒ la serie es idéntica a hoy (candado de
+no-regresión de D2).
+
+B7  — factura que paga en un mes anclado → D2 la SALTA; en un mes no-anclado → normal.
+Candado — `meses_anclados=frozenset()` ⇒ resultado idéntico al de hoy."""
+
+from decimal import Decimal
+
+from app.obligaciones.reconciliacion import FacturaReconciliar, reconciliar
+from app.proyeccion.motor import ModeloProyeccion, ParametrosMotor, proyectar
+
+
+def _params(**over):
+    base = dict(
+        mes_inicio=(2026, 7),
+        horizonte_meses=12,
+        modelos=[
+            ModeloProyeccion(
+                "Raider",
+                cuota_semanal=Decimal("100"),
+                cuota_inicial=Decimal("1000"),
+                plazo_semanas=6,
+                mix=Decimal("1"),
+                costo_moto=Decimal("5000"),
+            )
+        ],
+        motos_base=2,
+        crec_pct_mensual=Decimal("0"),
+        rampa=None,
+        adelanto_auteco=Decimal("0"),
+        plazo_auteco_dias=60,
+        base_auteco_dias=30,
+        tasa_auteco=Decimal("0.016"),
+        gastos_fijos=Decimal("1000"),
+        gps_moto=Decimal("0"),
+        costo_moto_nueva=Decimal("0"),
+        deuda=Decimal("0"),
+        tasa_deuda=Decimal("0"),
+        mes_inicio_deuda=0,
+        meses_deuda=0,
+        pct_mora=Decimal("0"),
+        pct_recuperacion=Decimal("0"),
+        pct_default=Decimal("0"),
+        pct_provision=Decimal("0"),
+        overrides_mora=None,
+        overrides_default=None,
+        caja_inicial=Decimal("500000"),
+        caja_minima=Decimal("10000"),
+    )
+    base.update(over)
+    return ParametrosMotor(**base)
+
+
+def _base():
+    p = _params()
+    return proyectar(p), p.caja_minima
+
+
+def _dos_facturas():
+    # una paga 2026-10 (plazo 60), otra 2026-12 (plazo 120)
+    return [
+        FacturaReconciliar(
+            fecha_factura="2026-08-15",
+            valor=Decimal("1000000"),
+            plazo_elegido_dias=60,
+            plazo_base_dias=30,
+            tasa_excedente_mensual=Decimal("0.016"),
+        ),
+        FacturaReconciliar(
+            fecha_factura="2026-08-15",
+            valor=Decimal("2000000"),
+            plazo_elegido_dias=120,
+            plazo_base_dias=30,
+            tasa_excedente_mensual=Decimal("0.016"),
+        ),
+    ]
+
+
+def test_candado_vacio_identico_a_hoy():
+    """`meses_anclados=frozenset()` ⇒ serie idéntica a hoy (candado no-regresión D2)."""
+    r, cm = _base()
+    facturas = _dos_facturas()
+    hoy = reconciliar(r, facturas, cm)
+    con_default = reconciliar(r, facturas, cm, meses_anclados=frozenset())
+    assert con_default.ventana == hoy.ventana
+    assert con_default.capital_por_mes == hoy.capital_por_mes
+    assert con_default.interes_por_mes == hoy.interes_por_mes
+    for a, b in zip(con_default.ajustado.meses, hoy.ajustado.meses, strict=True):
+        assert a.flujo == b.flujo
+        assert a.caja == b.caja
+        assert a.pago_inventario == b.pago_inventario
+        assert a.fondeo == b.fondeo
+
+
+def test_b7_d2_salta_el_mes_anclado_y_reconcilia_el_resto():
+    """B7: 2026-10 anclado por E1 → D2 no lo netea ni aplica su pago (queda como el
+    motor lo dejó, para que E1 lo reescriba); 2026-12 (no anclado) → reconcilia normal.
+    Ningún peso contado dos veces."""
+    r, cm = _base()
+    facturas = _dos_facturas()
+    idx = {m.mes: i for i, m in enumerate(r.meses)}
+    oct_i, dic_i = idx["2026-10"], idx["2026-12"]
+
+    rec = reconciliar(r, facturas, cm, meses_anclados=frozenset({"2026-10"}))
+
+    # el pago de octubre queda FUERA de la reconciliación (es territorio de E1)
+    assert rec.capital_por_mes == {"2026-12": "2000000.00"}
+    assert rec.interes_por_mes == {"2026-12": "96000.00"}  # 2M × 1,6% × 3 meses
+    assert rec.ventana == ("2026-12", "2026-12")
+
+    # octubre (anclado): D2 NO lo tocó → Auteco paramétrico intacto (== base del motor)
+    assert rec.ajustado.meses[oct_i].pago_inventario == r.meses[oct_i].pago_inventario
+    assert rec.ajustado.meses[oct_i].fondeo == r.meses[oct_i].fondeo
+
+    # diciembre (no anclado): reconciliado con el pago REAL
+    assert rec.ajustado.meses[dic_i].pago_inventario == Decimal("-2000000.00")
+    assert rec.ajustado.meses[dic_i].fondeo == Decimal("-96000.00")
diff --git a/backend/tests/test_proyeccion_endpoints.py b/backend/tests/test_proyeccion_endpoints.py
index 0da90ca..35c4e9a 100644
--- a/backend/tests/test_proyeccion_endpoints.py
+++ b/backend/tests/test_proyeccion_endpoints.py
@@ -185,6 +185,23 @@ async def _seed_mes_cerrado_con_ingreso():
     porclas = await Rubro(
         grupo="otros", nombre="Por clasificar", orden=97, es_sistema=True
     ).insert()
+    # E1·P3: al anclar el mes cerrado, la taxonomía debe traer los 9 códigos del mapeo
+    # (B12 fail-loud; en PROD existen por C1). Sin esto la proyección anclada rompería.
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
     mc = await MesControl(
         mes="2026-06-01",
         estado="cerrado",
diff --git a/backend/tests/test_rubros_neutros.py b/backend/tests/test_rubros_neutros.py
new file mode 100644
index 0000000..6a09570
--- /dev/null
+++ b/backend/tests/test_rubros_neutros.py
@@ -0,0 +1,49 @@
+# backend/tests/test_rubros_neutros.py
+"""E1 · P3 — el resolver nombre→id de rubros neutros vive en `domain.rubros_neutros`
+(una verdad, un lugar, junto al set). `metas_ingreso` lo re-exporta para no romper
+importadores y el loader E1 lo importa de ahí — sin dos copias que puedan divergir."""
+
+from decimal import Decimal  # noqa: F401  (paridad con el resto de tests del dominio)
+
+import pytest
+import pytest_asyncio
+from app.domain import DOMAIN_DOCUMENTS
+from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
+from app.domain.rubros_neutros import _ids_rubros_neutros
+from beanie import init_beanie
+from mongomock_motor import AsyncMongoMockClient
+
+
+@pytest_asyncio.fixture
+async def db():
+    c = AsyncMongoMockClient(tz_aware=True)
+    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
+    yield c
+
+
+async def _rubro(grupo: RubroGrupo, nombre: str, orden: int) -> Rubro:
+    r = Rubro(grupo=grupo, nombre=nombre, tipo_flujo=TipoFlujo.INGRESO, orden=orden)
+    await r.insert()
+    return r
+
+
+@pytest.mark.asyncio
+async def test_resuelve_solo_los_neutros_presentes(db):
+    n1 = await _rubro(RubroGrupo.OTROS, "Reversas y devoluciones", 1)
+    n2 = await _rubro(RubroGrupo.OTROS, "Ajuste de conciliación", 2)
+    _normal = await _rubro(RubroGrupo.INGRESOS_OPERATIVOS, "Recaudo de cartera", 3)
+    ids = await _ids_rubros_neutros()
+    assert ids == {n1.id, n2.id}
+
+
+@pytest.mark.asyncio
+async def test_vacio_si_no_existen(db):
+    assert await _ids_rubros_neutros() == set()
+
+
+@pytest.mark.asyncio
+async def test_metas_ingreso_reexporta_el_mismo_resolver(db):
+    """El re-export no rompe importadores y apunta al MISMO objeto (una verdad)."""
+    from app.metas_ingreso.service import _ids_rubros_neutros as reexport
+
+    assert reexport is _ids_rubros_neutros

```

## 3. Salida de tests (E1 + reconciliación + metas + endpoints, `-v`)

```
tests/test_rubros_neutros.py::test_resuelve_solo_los_neutros_presentes PASSED [  2%]
tests/test_rubros_neutros.py::test_vacio_si_no_existen PASSED            [  4%]
tests/test_rubros_neutros.py::test_metas_ingreso_reexporta_el_mismo_resolver PASSED [  6%]
tests/test_e1_precedencia.py::test_candado_vacio_identico_a_hoy PASSED   [  8%]
tests/test_e1_precedencia.py::test_b7_d2_salta_el_mes_anclado_y_reconcilia_el_resto PASSED [ 10%]
tests/test_e1_loader.py::test_mes_cerrado_ancla_ejecutado_e_ingreso_real_sin_neutros PASSED [ 13%]
tests/test_e1_loader.py::test_mes_en_ejecucion_ancla_ejecutado_y_definido PASSED [ 15%]
tests/test_e1_loader.py::test_mes_propuesto_con_definido_es_regimen_presupuesto PASSED [ 17%]
tests/test_e1_loader.py::test_futuro_sin_definido_y_sin_mescontrol_se_omiten PASSED [ 19%]
tests/test_e1_loader.py::test_rubros_info_y_neutros_ids_se_arman PASSED  [ 21%]
tests/test_e1_loader_realmongo.py::TestLoaderReal::test_cerrado_agrega_egresos_y_en_ejecucion_lee_definido SKIPPED [ 23%]
tests/test_e1_pipeline.py::test_b8_b11_candado_composicion PASSED        [ 26%]
tests/test_e1_pipeline.py::test_c1_d2_aplica_pago_real_en_mes_anclado_no_cerrado[en_ejecucion] PASSED [ 28%]
tests/test_e1_pipeline.py::test_c1_d2_aplica_pago_real_en_mes_anclado_no_cerrado[presupuesto] PASSED [ 30%]
tests/test_e1_anclaje.py::test_b1_sin_ancla_es_base_bit_a_bit PASSED     [ 32%]
tests/test_e1_anclaje.py::test_b2_cerrado_ejecutado_real_y_reacumula PASSED [ 34%]
tests/test_e1_anclaje.py::test_b3_regla_a_incluye_ejecutado_mayor_que_definido PASSED [ 36%]
tests/test_e1_anclaje.py::test_b4_futuro_con_presupuesto_usa_definido PASSED [ 39%]
tests/test_e1_anclaje.py::test_b5_futuro_sin_presupuesto_es_el_motor PASSED [ 41%]
tests/test_e1_anclaje.py::test_a3_fixture_julio_real_b2_y_b6 PASSED      [ 43%]
tests/test_e1_lectura.py::test_b9_suma_rubros_igual_concepto PASSED      [ 45%]
tests/test_e1_lectura.py::test_r1_1010_entero_a_pago_inventario_no_costo_nueva PASSED [ 47%]
tests/test_e1_lectura.py::test_r2_4040_en_sin_mapear PASSED              [ 50%]
tests/test_e1_lectura.py::test_a1_neutros_excluidos_por_id PASSED        [ 52%]
tests/test_e1_lectura.py::test_b12_codigo_del_mapeo_ausente_es_ruidoso PASSED [ 54%]
tests/test_reconciliacion.py::test_sin_facturas_es_base_bit_a_bit PASSED [ 56%]
tests/test_reconciliacion.py::test_pagos_fuera_del_horizonte_no_reconcilian PASSED [ 58%]
tests/test_reconciliacion.py::test_una_factura_netea_el_parametrico_y_suma_el_real PASSED [ 60%]
tests/test_reconciliacion.py::test_meses_fuera_de_la_ventana_intactos PASSED [ 63%]
tests/test_reconciliacion.py::test_coherencia_concepto_a_concepto_toda_la_serie PASSED [ 65%]
tests/test_reconciliacion.py::test_ventana_reescribe_conceptos_con_el_pago_real PASSED [ 67%]
tests/test_reconciliacion.py::test_hueco_en_ventana_netea_el_parametrico_a_cero PASSED [ 69%]
tests/test_ingreso_real_neutros.py::test_reversas_no_suma_pero_recaudo_si PASSED [ 71%]
tests/test_ingreso_real_neutros.py::test_recaudo_solo_cuenta_completo PASSED [ 73%]
tests/test_ingreso_real_neutros.py::test_sin_mes_control_es_none PASSED  [ 76%]
tests/test_ingreso_real_neutros.py::test_transito_wava_no_suma_ingreso_real PASSED [ 78%]
tests/test_ingreso_real_neutros.py::test_ajuste_conciliacion_no_suma_ingreso_real PASSED [ 80%]
tests/test_proyeccion_endpoints.py::test_proyeccion_sin_config_es_409 PASSED [ 82%]
tests/test_proyeccion_endpoints.py::test_flujo_completo_ingreso_discriminado_y_kpis PASSED [ 84%]
tests/test_proyeccion_endpoints.py::test_operacion_cartera_por_anada_y_colocacion PASSED [ 86%]
tests/test_proyeccion_endpoints.py::test_operacion_sin_config_es_409 PASSED [ 89%]
tests/test_proyeccion_endpoints.py::test_comparar_actuals_vs_forecast_rolling PASSED [ 91%]
tests/test_proyeccion_endpoints.py::test_comparar_ancla_modo_invalido_es_422 PASSED [ 93%]
tests/test_proyeccion_endpoints.py::test_escenario_pesimista_menos_caja_que_optimista PASSED [ 95%]
tests/test_proyeccion_endpoints.py::test_rbac_mutaciones_solo_gestionar PASSED [ 97%]
tests/test_proyeccion_endpoints.py::test_modelo_baja_logica_y_reactivar PASSED [100%]
SKIPPED [1] tests\test_e1_loader_realmongo.py:39: requiere Mongo real; correr con: pytest -m requires_real_mongo
================ 45 passed, 1 skipped, 383 warnings in 14.29s =================

```

## 4. Prueba R0 (motor.py cero diffs)

```
$ git diff origin/main...HEAD -- backend/app/proyeccion/motor.py | wc -l
0
```

## 5. ruff

```
$ python -m ruff check app/ tests/
All checks passed!
$ python -m ruff format --check app/ tests/
244 files already formatted
```
