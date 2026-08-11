# EVIDENCIA — FABS Incremento 1 (PR1-I)

Rama `feat/fabs-inc1`, commits `588a300..0a8f0ca`. Todo verificado en local.

## 1. Motor intocable (regla motor-cero-diffs)
```
$ git diff --stat 588a300..0a8f0ca -- '**/motor.py'
(vacío = motor.py sin cambios)
```

## 2. Aislamiento S1 (imports de cfo/calc y cfo/goldens)
```
$ grep -rnE '^(from|import) ' backend/app/cfo/calc backend/app/cfo/goldens | grep -v '__init__'
backend/app/cfo/calc/caja.py:6:from decimal import Decimal
backend/app/cfo/calc/caja.py:8:from app.caja import service as caja_service
backend/app/cfo/calc/caja.py:9:from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
backend/app/cfo/calc/caja.py:10:from app.core.time import today_bogota
backend/app/cfo/calc/caja.py:11:from app.parametros_proyeccion import service as params_service
backend/app/cfo/calc/evidencia.py:5:from pydantic import BaseModel, ConfigDict, Field
backend/app/cfo/calc/evidencia.py:7:from app.core.money import Money
backend/app/cfo/calc/iva.py:5:from decimal import Decimal
backend/app/cfo/calc/iva.py:7:from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
backend/app/cfo/calc/iva.py:8:from app.core.time import now_bogota
backend/app/cfo/calc/iva.py:9:from app.facturas import service as fact_service
backend/app/cfo/calc/runway.py:4:from decimal import Decimal
backend/app/cfo/calc/runway.py:6:from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
backend/app/cfo/calc/runway.py:7:from app.core.time import now_bogota
backend/app/cfo/calc/runway.py:8:from app.proyeccion import service as proy_service
backend/app/cfo/calc/runway.py:9:from app.proyeccion.service import ProyeccionError
backend/app/cfo/goldens/modelo.py:7:from datetime import datetime
backend/app/cfo/goldens/modelo.py:9:from beanie import Document
backend/app/cfo/goldens/modelo.py:10:from pydantic import ConfigDict, Field
backend/app/cfo/goldens/modelo.py:12:from app.core.money import Money
backend/app/cfo/goldens/runner.py:5:from decimal import Decimal
backend/app/cfo/goldens/runner.py:7:from app.cfo.calc.caja import caja_hoy
backend/app/cfo/goldens/runner.py:8:from app.cfo.calc.iva import iva_cuatrimestre
backend/app/cfo/goldens/runner.py:9:from app.cfo.calc.runway import runway
backend/app/cfo/goldens/runner.py:10:from app.cfo.goldens.modelo import CFOGolden
backend/app/cfo/goldens/semilla.py:7:from decimal import Decimal
backend/app/cfo/goldens/semilla.py:9:from app.cfo.datos.repositorios import upsert_golden
backend/app/cfo/goldens/semilla.py:10:from app.cfo.goldens.modelo import CFOGolden
backend/app/cfo/goldens/semilla.py:11:from app.core.time import now_bogota
```

## 3. cfo/ no importa app.domain ni el driver de Mongo (salvo modelo.py)
```
$ grep -rnE 'app\.domain|get_pymongo_collection|AsyncIOMotor|import motor' backend/app/cfo/calc backend/app/cfo/goldens/runner.py backend/app/cfo/goldens/semilla.py backend/app/cfo/datos
(sin coincidencias — limpio)
```

## 4. cfo router NO registrado (flag-off; api/v1)
```
$ grep -n 'cfo' backend/app/api/v1/__init__.py
(sin coincidencias — cfo no está cableado)
```

## 5. Salidas de tests
```
$ pytest tests/cfo/ -q

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
17 passed, 48 warnings in 0.37s

$ pytest tests/ -k 'factura or iva' -q  (endpoint idéntico tras el refactor DRY)
........................................................................ [ 47%]
................
## 5. Salidas de tests
```
$ pytest tests/cfo/ -q
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
17 passed, 48 warnings in 0.21s
```
- Facturas/IVA tras el refactor DRY: **153 passed** (endpoint idéntico; verificado en Task 5 y en el review final).
- Suite COMPAS COMPLETA: **940 passed / 95 skipped / 0 failed** con el flag apagado (verificado en el cierre — Task 11).
- `ruff check app/cfo/`: limpio.

## 6. Diff completo de la rama (`588a300..0a8f0ca`, 13 commits)
```diff
# Review package: 588a300b8996ed3fc4e7d000236c801a5dea54bf..HEAD

## Commits
0a8f0ca docs(fabs): roadmap — incremento 1 cerrado (SDD, suite 940 verde, flag-off idéntico)
bbe2c3b chore(cfo): semilla real de goldens (snapshot 2026-08-11)
096a3ea test(cfo): salvaguarda S1 (aislamiento de cfo/ respecto al driver y al dominio ajeno)
73ce549 feat(cfo): repositorio cfo_* + semilla idempotente de goldens
f464e7f feat(cfo): runner de goldens (tolerancia + abstencion)
d96bb66 feat(cfo): modelo cfo_goldens registrado en Beanie
d26b561 feat(cfo): concepto iva_cuatrimestre (neto del periodo vigente + fecha DIAN)
523863b refactor(facturas): extraer liquidacion_iva() a servicio (DRY; endpoint idéntico)
8ff70b5 feat(cfo): concepto runway desde la proyeccion vigente
8b226da feat(cfo): concepto caja_hoy con evidencia y fecha de corte
fa0d49d feat(cfo): flag CFO_ENABLED (apagado por defecto)
bcfb6ef style(cfo): ordenar imports del test (ruff I001)
63f8ef3 feat(cfo): contrato de evidencia ResultadoCFO/Evidencia (FABS inc1)

## Files changed
 backend/app/cfo/__init__.py               |   0
 backend/app/cfo/calc/__init__.py          |   0
 backend/app/cfo/calc/caja.py              |  59 ++++++++++++++
 backend/app/cfo/calc/evidencia.py         |  26 ++++++
 backend/app/cfo/calc/iva.py               |  51 ++++++++++++
 backend/app/cfo/calc/runway.py            |  48 +++++++++++
 backend/app/cfo/config.py                 |   8 ++
 backend/app/cfo/datos/__init__.py         |   0
 backend/app/cfo/datos/repositorios.py     |  16 ++++
 backend/app/cfo/goldens/__init__.py       |   0
 backend/app/cfo/goldens/modelo.py         |  30 +++++++
 backend/app/cfo/goldens/runner.py         |  48 +++++++++++
 backend/app/cfo/goldens/semilla.py        |  63 +++++++++++++++
 backend/app/domain/__init__.py            |   3 +
 backend/app/facturas/router.py            |  49 +-----------
 backend/app/facturas/service.py           |  37 ++++++++-
 backend/app/iva/liquidacion.py            |  22 ++++++
 backend/tests/cfo/__init__.py             |   0
 backend/tests/cfo/test_calc_caja.py       | 127 ++++++++++++++++++++++++++++++
 backend/tests/cfo/test_calc_iva.py        |  42 ++++++++++
 backend/tests/cfo/test_calc_runway.py     |  30 +++++++
 backend/tests/cfo/test_config.py          |  11 +++
 backend/tests/cfo/test_evidencia.py       |  36 +++++++++
 backend/tests/cfo/test_goldens_modelo.py  |  38 +++++++++
 backend/tests/cfo/test_goldens_runner.py  |  73 +++++++++++++++++
 backend/tests/cfo/test_goldens_semilla.py |  25 ++++++
 backend/tests/cfo/test_s1_aislamiento.py  |  42 ++++++++++
 backend/tests/test_db.py                  |   5 +-
 docs/COMPAS_FABS_ROADMAP.md               |  11 ++-
 29 files changed, 849 insertions(+), 51 deletions(-)

## Diff
diff --git a/backend/app/cfo/__init__.py b/backend/app/cfo/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/backend/app/cfo/calc/__init__.py b/backend/app/cfo/calc/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/backend/app/cfo/calc/caja.py b/backend/app/cfo/calc/caja.py
new file mode 100644
index 0000000..b943090
--- /dev/null
+++ b/backend/app/cfo/calc/caja.py
@@ -0,0 +1,59 @@
+# backend/app/cfo/calc/caja.py
+"""FABS · concepto 'caja disponible hoy'. Lee la serie diaria real de COMPAS
+(caja.service.caja_diaria) desde el ancla de caja inicial vigente hasta hoy (Bogotá) y
+toma el último saldo, con su fecha de corte. Sin parámetros vigentes → abstención."""
+
+from decimal import Decimal
+
+from app.caja import service as caja_service
+from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
+from app.core.time import today_bogota
+from app.parametros_proyeccion import service as params_service
+
+_CONCEPTO = "caja_hoy"
+_UNIDAD = "COP"
+_FUENTE = "caja.service.caja_diaria"
+
+
+async def caja_hoy() -> ResultadoCFO:
+    """Caja disponible HOY: corre la serie diaria real desde `vigente_desde` (el
+    ancla `caja_inicial` de los parámetros de proyección vigentes) hasta hoy
+    (Bogotá) y toma el último saldo. Sin parámetros vigentes → abstención
+    (`disponible=False`, `valor=None`). Sin movimientos en el rango → cae al
+    ancla (`caja_inicial`), con `fecha_corte=vigente_desde`. Nunca inventa un
+    número: toda cifra viaja con su Evidencia (fuente + fecha de corte + ref)."""
+    vig = await params_service.obtener_vigente()
+    if vig is None:
+        return ResultadoCFO(
+            concepto=_CONCEPTO,
+            valor=None,
+            unidad=_UNIDAD,
+            disponible=False,
+            evidencia=Evidencia(fuente=_FUENTE, fecha_corte=None, ref="sin-parametros"),
+        )
+
+    hasta = today_bogota().isoformat()
+    data = await caja_service.caja_diaria(
+        desde=vig.vigente_desde, hasta=hasta, caja_inicial=vig.caja_inicial
+    )
+    dias = data["dias"]
+    if not dias:
+        return ResultadoCFO(
+            concepto=_CONCEPTO,
+            valor=vig.caja_inicial,
+            unidad=_UNIDAD,
+            disponible=True,
+            evidencia=Evidencia(
+                fuente=_FUENTE, fecha_corte=vig.vigente_desde, ref="sin-movimientos"
+            ),
+        )
+
+    ultimo = dias[-1]
+    return ResultadoCFO(
+        concepto=_CONCEPTO,
+        valor=Decimal(ultimo["caja"]),
+        unidad=_UNIDAD,
+        disponible=True,
+        evidencia=Evidencia(fuente=_FUENTE, fecha_corte=ultimo["fecha"], ref=hasta[:7]),
+        detalle={"desde": vig.vigente_desde, "hasta": hasta},
+    )
diff --git a/backend/app/cfo/calc/evidencia.py b/backend/app/cfo/calc/evidencia.py
new file mode 100644
index 0000000..e3cc89a
--- /dev/null
+++ b/backend/app/cfo/calc/evidencia.py
@@ -0,0 +1,26 @@
+"""FABS · contrato de evidencia. Toda cifra que FABS publica viaja envuelta en
+ResultadoCFO con su Evidencia (fuente + fecha de corte + ref reproducible). Sin
+evidencia no hay cifra; sin dato, `disponible=False` y `valor=None` (abstención)."""
+
+from pydantic import BaseModel, ConfigDict, Field
+
+from app.core.money import Money
+
+
+class Evidencia(BaseModel):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    fuente: str
+    fecha_corte: str | None  # 'YYYY-MM-DD' del dato más reciente (None si no aplica)
+    ref: str  # identificador reproducible: mes de control, cuatrimestre, etc.
+
+
+class ResultadoCFO(BaseModel):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    concepto: str
+    valor: Money | None
+    unidad: str
+    disponible: bool
+    evidencia: Evidencia
+    detalle: dict = Field(default_factory=dict)
diff --git a/backend/app/cfo/calc/iva.py b/backend/app/cfo/calc/iva.py
new file mode 100644
index 0000000..49f53c6
--- /dev/null
+++ b/backend/app/cfo/calc/iva.py
@@ -0,0 +1,51 @@
+"""FABS · concepto 'IVA del cuatrimestre'. Toma el neto a pagar del período fiscal
+VIGENTE (el que contiene hoy) de la liquidación de COMPAS, con su fecha DIAN como
+evidencia. Sin período vigente en la liquidación → abstención."""
+
+from decimal import Decimal
+
+from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
+from app.core.time import now_bogota
+from app.facturas import service as fact_service
+
+
+async def _liquidacion() -> dict:
+    return await fact_service.liquidacion_iva()
+
+
+def _periodo_vigente_idx() -> tuple[int, int]:
+    ahora = now_bogota()
+    idx = (ahora.month - 1) // 4 + 1  # 1..3 (cuatrimestral: ene-abr/may-ago/sep-dic)
+    return (ahora.year, idx)
+
+
+async def iva_cuatrimestre() -> ResultadoCFO:
+    fuente = "facturas.service.liquidacion_iva"
+    anio, idx = _periodo_vigente_idx()
+    ref = f"{anio}-C{idx}"
+    data = await _liquidacion()
+    vig = next(
+        (p for p in data["periodos"] if p["anio"] == anio and p["periodo"] == idx),
+        None,
+    )
+    if vig is None:
+        return ResultadoCFO(
+            concepto="iva_cuatrimestre",
+            valor=None,
+            unidad="COP",
+            disponible=False,
+            evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref=ref),
+        )
+    pago = vig.get("proximo_pago")
+    fecha_dian = pago["fecha"] if pago else None
+    return ResultadoCFO(
+        concepto="iva_cuatrimestre",
+        valor=Decimal(vig["neto_a_pagar"]),
+        unidad="COP",
+        disponible=True,
+        evidencia=Evidencia(fuente=fuente, fecha_corte=fecha_dian, ref=vig["etiqueta"]),
+        detalle={
+            "generado": vig.get("generado"),
+            "descontable": vig.get("descontable"),
+        },
+    )
diff --git a/backend/app/cfo/calc/runway.py b/backend/app/cfo/calc/runway.py
new file mode 100644
index 0000000..5e4dfbd
--- /dev/null
+++ b/backend/app/cfo/calc/runway.py
@@ -0,0 +1,48 @@
+"""FABS · concepto 'runway' (meses de caja al ritmo actual). Lee el KPI runway_meses
+de la proyección vigente de COMPAS. Sin config (ProyeccionError) → abstención."""
+
+from decimal import Decimal
+
+from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
+from app.core.time import now_bogota
+from app.proyeccion import service as proy_service
+from app.proyeccion.service import ProyeccionError
+
+
+async def _proyectar(**kw) -> dict:
+    return await proy_service.proyectar_vigente(**kw)
+
+
+async def runway() -> ResultadoCFO:
+    fuente = "proyeccion.service.proyectar_vigente"
+    ahora = now_bogota()
+    ref = f"{ahora.year:04d}-{ahora.month:02d}"
+    try:
+        data = await _proyectar(
+            escenario="base", mes_inicio=(ahora.year, ahora.month), horizonte_meses=None
+        )
+    except ProyeccionError:
+        return ResultadoCFO(
+            concepto="runway",
+            valor=None,
+            unidad="meses",
+            disponible=False,
+            evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref="sin-config"),
+        )
+    rm = data.get("runway_meses")
+    if rm is None:
+        return ResultadoCFO(
+            concepto="runway",
+            valor=None,
+            unidad="meses",
+            disponible=False,
+            evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref=ref),
+            detalle={"nota": "sin quema neta: runway no aplica"},
+        )
+    return ResultadoCFO(
+        concepto="runway",
+        valor=Decimal(rm),
+        unidad="meses",
+        disponible=True,
+        evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref=ref),
+    )
diff --git a/backend/app/cfo/config.py b/backend/app/cfo/config.py
new file mode 100644
index 0000000..77d0f9c
--- /dev/null
+++ b/backend/app/cfo/config.py
@@ -0,0 +1,8 @@
+"""FABS · feature flag. Apagado por defecto ⇒ COMPAS byte-idéntico. La doble barrera
+(router condicional + guard 404) aterriza con el primer endpoint (incremento 2)."""
+
+import os
+
+
+def cfo_enabled() -> bool:
+    return os.environ.get("CFO_ENABLED", "false").strip().lower() == "true"
diff --git a/backend/app/cfo/datos/__init__.py b/backend/app/cfo/datos/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/backend/app/cfo/datos/repositorios.py b/backend/app/cfo/datos/repositorios.py
new file mode 100644
index 0000000..d878946
--- /dev/null
+++ b/backend/app/cfo/datos/repositorios.py
@@ -0,0 +1,16 @@
+"""FABS · única puerta de escritura del módulo. SOLO colecciones cfo_*. (S1: ninguna
+otra subruta de cfo/ toca el driver de Mongo.)"""
+
+from app.cfo.goldens.modelo import CFOGolden
+
+
+async def upsert_golden(g: CFOGolden) -> bool:
+    """Inserta el golden si no existe uno con el mismo (concepto, nota). Devuelve True
+    si insertó, False si ya existía. Idempotente."""
+    existe = await CFOGolden.find_one(
+        CFOGolden.concepto == g.concepto, CFOGolden.nota == g.nota
+    )
+    if existe is not None:
+        return False
+    await g.insert()
+    return True
diff --git a/backend/app/cfo/goldens/__init__.py b/backend/app/cfo/goldens/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/backend/app/cfo/goldens/modelo.py b/backend/app/cfo/goldens/modelo.py
new file mode 100644
index 0000000..08aa36e
--- /dev/null
+++ b/backend/app/cfo/goldens/modelo.py
@@ -0,0 +1,30 @@
+# backend/app/cfo/goldens/modelo.py
+"""FABS · caso dorado. Un valor esperado (calculado a mano desde COMPAS) para
+un concepto de cfo/calc, con su tolerancia. El runner compara el resultado
+real contra esto. `valor_esperado=None` ⇒ caso de ABSTENCIÓN (el concepto
+debe dar disponible=False)."""
+
+from datetime import datetime
+
+from beanie import Document
+from pydantic import ConfigDict, Field
+
+from app.core.money import Money
+
+CFO_GOLDENS_COLLECTION = "cfo_goldens"
+
+
+class CFOGolden(Document):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    concepto: str
+    filtros: dict = Field(default_factory=dict)
+    valor_esperado: Money | None
+    tolerancia: Money  # Decimal; COP para montos, 0.1 para "meses"
+    unidad: str
+    origen: str  # 'semilla' | 'fabian'
+    nota: str | None = None
+    creado_at: datetime
+
+    class Settings:
+        name = CFO_GOLDENS_COLLECTION
diff --git a/backend/app/cfo/goldens/runner.py b/backend/app/cfo/goldens/runner.py
new file mode 100644
index 0000000..12ed005
--- /dev/null
+++ b/backend/app/cfo/goldens/runner.py
@@ -0,0 +1,48 @@
+"""FABS · runner de evaluación. Corre cada golden contra su concepto de cfo/calc y
+compara dentro de tolerancia. Los goldens con valor_esperado=None son de ABSTENCIÓN:
+pasan solo si el concepto devuelve disponible=False. No imprime: devuelve un reporte."""
+
+from decimal import Decimal
+
+from app.cfo.calc.caja import caja_hoy
+from app.cfo.calc.iva import iva_cuatrimestre
+from app.cfo.calc.runway import runway
+from app.cfo.goldens.modelo import CFOGolden
+
+CONCEPTOS = {
+    "caja_hoy": caja_hoy,
+    "runway": runway,
+    "iva_cuatrimestre": iva_cuatrimestre,
+}
+
+
+async def correr_goldens() -> dict:
+    total = ok = abst_ok = 0
+    fallos: list[dict] = []
+    async for g in CFOGolden.find_all():
+        fn = CONCEPTOS.get(g.concepto)
+        if fn is None:
+            fallos.append({"concepto": g.concepto, "esperado": None,
+                           "obtenido": None, "delta": "concepto desconocido"})
+            total += 1
+            continue
+        r = await fn()
+        total += 1
+        if g.valor_esperado is None:  # caso de abstención
+            if r.disponible is False and r.valor is None:
+                abst_ok += 1
+            else:
+                fallos.append({"concepto": g.concepto, "esperado": "abstención",
+                               "obtenido": str(r.valor), "delta": "no abstuvo"})
+            continue
+        if r.valor is None:
+            fallos.append({"concepto": g.concepto, "esperado": str(g.valor_esperado),
+                           "obtenido": None, "delta": "sin dato"})
+            continue
+        delta = (Decimal(r.valor) - Decimal(g.valor_esperado)).copy_abs()
+        if delta <= Decimal(g.tolerancia):
+            ok += 1
+        else:
+            fallos.append({"concepto": g.concepto, "esperado": str(g.valor_esperado),
+                           "obtenido": str(r.valor), "delta": str(delta)})
+    return {"total": total, "ok": ok, "fallos": fallos, "abstenciones_ok": abst_ok}
diff --git a/backend/app/cfo/goldens/semilla.py b/backend/app/cfo/goldens/semilla.py
new file mode 100644
index 0000000..318760e
--- /dev/null
+++ b/backend/app/cfo/goldens/semilla.py
@@ -0,0 +1,63 @@
+"""FABS · lote semilla de goldens (origen='semilla'). Valores editables/corregibles por
+el CEO. El set completo (240+60, con Fabián) llega en un incremento posterior.
+
+Task 11: los 3 casos de abajo son valores reales, calculados a mano desde PROD
+(solo lectura) por el controlador — snapshot 2026-08-11. Ya no son placeholder."""
+
+from decimal import Decimal
+
+from app.cfo.datos.repositorios import upsert_golden
+from app.cfo.goldens.modelo import CFOGolden
+from app.core.time import now_bogota
+
+# Snapshot PROD 2026-08-11 (Task 11). Editables/corregibles por el CEO; el set
+# completo (240+60, con Fabián) llega en un incremento posterior.
+SEMILLA: list[dict] = [
+    {
+        "concepto": "caja_hoy",
+        "valor_esperado": Decimal("704722003"),
+        "tolerancia": Decimal("1"),
+        "unidad": "COP",
+        "nota": (
+            "snapshot 2026-08-11: caja anclada a caja_inicial (params vigentes "
+            "2026-08-10, sin movimientos en la ventana)"
+        ),
+    },
+    {
+        "concepto": "runway",
+        "valor_esperado": None,  # ABSTENCIÓN
+        "tolerancia": Decimal("0.1"),
+        "unidad": "meses",
+        "nota": (
+            "snapshot 2026-08-11: sin quema neta en PROD -> runway N/A (abstención)"
+        ),
+    },
+    {
+        "concepto": "iva_cuatrimestre",
+        "valor_esperado": Decimal("36204698.10"),
+        "tolerancia": Decimal("1"),
+        "unidad": "COP",
+        "nota": "snapshot 2026-08-11: C2-2026, vence DIAN 2026-09-10",
+    },
+]
+
+
+async def sembrar_semilla() -> tuple[int, int]:
+    now = now_bogota()
+    insertados = duplicados = 0
+    for c in SEMILLA:
+        g = CFOGolden(
+            concepto=c["concepto"],
+            filtros=c.get("filtros", {}),
+            valor_esperado=c["valor_esperado"],
+            tolerancia=c["tolerancia"],
+            unidad=c["unidad"],
+            origen="semilla",
+            nota=c.get("nota"),
+            creado_at=now,
+        )
+        if await upsert_golden(g):
+            insertados += 1
+        else:
+            duplicados += 1
+    return insertados, duplicados
diff --git a/backend/app/domain/__init__.py b/backend/app/domain/__init__.py
index ae8fc97..2e1e605 100644
--- a/backend/app/domain/__init__.py
+++ b/backend/app/domain/__init__.py
@@ -1,19 +1,20 @@
 # backend/app/domain/__init__.py
 """Modelos de dominio base (Beanie Documents) + registro para init_beanie.
 
 `DOMAIN_DOCUMENTS` es la lista EXPLÍCITA de Documents que se registran en Beanie
 (Kimi M-04). `AuditLog`, `User` y `RefreshSession` NO están aquí: sus escrituras van
 por repositorios con Motor crudo/conexión dedicada (decisión de la Sesión 2), no por
 el ODM general.
 """
 
+from app.cfo.goldens.modelo import CFOGolden
 from app.domain.carga import CargaBancaria
 from app.domain.cartera_previa import CarteraPreviaRecaudo
 from app.domain.configuracion import Configuracion
 from app.domain.escenario_impacto import EscenarioImpacto
 from app.domain.factura import Factura
 from app.domain.gasto_recurrente import GastoRecurrente
 from app.domain.idempotency import IdempotencyKey
 from app.domain.loantape import LoanTapeCredito
 from app.domain.mes_control import MesControl
 from app.domain.modelo_moto import ModeloMoto
@@ -38,20 +39,21 @@ DOMAIN_DOCUMENTS: list[type] = [
     ModeloMoto,
     ParametrosProyeccion,
     CarteraPreviaRecaudo,
     Factura,
     LoanTapeCredito,
     GastoRecurrente,
     EscenarioImpacto,
     Obligacion,
     FacturaObligacion,
     MetaIngreso,
+    CFOGolden,
 ]
 
 __all__ = [
     "Rubro",
     "MesControl",
     "Configuracion",
     "Transaccion",
     "CargaBancaria",
     "IdempotencyKey",
     "PresupuestoLinea",
@@ -60,12 +62,13 @@ __all__ = [
     "ModeloMoto",
     "ParametrosProyeccion",
     "CarteraPreviaRecaudo",
     "Factura",
     "LoanTapeCredito",
     "GastoRecurrente",
     "EscenarioImpacto",
     "Obligacion",
     "FacturaObligacion",
     "MetaIngreso",
+    "CFOGolden",
     "DOMAIN_DOCUMENTS",
 ]
diff --git a/backend/app/facturas/router.py b/backend/app/facturas/router.py
index a271a5b..3e9a8f3 100644
--- a/backend/app/facturas/router.py
+++ b/backend/app/facturas/router.py
@@ -1,42 +1,40 @@
 # backend/app/facturas/router.py
 """/api/v1/facturas — carga de facturas (compra/venta) para IVA + liquidación
 cuatrimestral (C11, CR "Fidelidad de caja").
 
 RBAC: GET con `dashboard:leer`; mutaciones con `iva:gestionar` = {financiero, admin}
 + `verify_origin` (anti-CSRF). Montos como string (regla 1): el body los parsea a
 Decimal antes de construir la factura; la respuesta los serializa con `money_str`. Sin
 Idempotency-Key: no es un movimiento de dinero; el índice único (tercero_nit, numero)
 hace inocuo el replay (→ 409). La liquidación se calcula en el backend."""
 
-from datetime import date
 from decimal import Decimal, InvalidOperation
 
 from beanie import PydanticObjectId
 from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
 from pydantic import BaseModel, ConfigDict, Field
 
 from app.auth.deps import require_permission
 from app.auth.models import User
 from app.auth.permissions import has_permission
 from app.auth.router import verify_origin
 from app.core.money import money_str
-from app.core.time import today_bogota
 from app.domain.factura import (
     TARIFAS_IVA_VALIDAS,
     Factura,
     OrigenFactura,
     TipoFactura,
 )
 from app.facturas import ingesta, service
 from app.facturas.extraccion import PERSONA_JURIDICA
-from app.iva.liquidacion import Periodicidad, clave_dian, liquidar, periodo_de
+from app.iva.liquidacion import Periodicidad, etiqueta_periodo, periodo_de
 
 router = APIRouter(prefix="/facturas", tags=["facturas"])
 
 
 def _dec(valor: str, campo: str) -> Decimal:
     try:
         v = Decimal(valor)
         if not v.is_finite():
             raise InvalidOperation
         return v
@@ -63,39 +61,20 @@ class FacturaCrearBody(BaseModel):
 
 class FacturaEditarBody(BaseModel):
     # CR-E2-EDITAR: SOLO los campos no fiscales. `extra=forbid` → un intento de tocar
     # un monto/fecha/tipo (factura inmutable en lo fiscal) responde 422.
     model_config = ConfigDict(strict=True, extra="forbid")
 
     deducible: bool | None = None
     origen: str | None = None
 
 
-def _etiqueta_periodo(anio: int, idx: int, periodicidad: Periodicidad) -> str:
-    # 'C' cuatrimestral (2026-C1) · 'B' bimestral (2026-B1)
-    prefijo = "C" if periodicidad == Periodicidad.cuatrimestral else "B"
-    return f"{anio}-{prefijo}{idx}"
-
-
-def _proximo_pago(
-    anio: int, idx: int, periodicidad: Periodicidad, calendario: dict
-) -> dict | None:
-    """Fecha DIAN del período (de `CALENDARIO_DIAN`) + días desde hoy (Bogotá). Sin
-    fecha en el calendario → None: la UI omite la línea, no se inventa (R5, §3③)."""
-    anio_cal = calendario.get(str(anio))
-    fecha = anio_cal.get(clave_dian(idx, periodicidad)) if anio_cal else None
-    if not fecha:
-        return None
-    y, m, d = (int(x) for x in fecha.split("-"))
-    return {"fecha": fecha, "dias": (date(y, m, d) - today_bogota()).days}
-
-
 def _serializar(
     f: Factura, periodicidad: Periodicidad, *, ver_pii: bool = True
 ) -> dict:
     anio, idx = periodo_de(f.fecha, periodicidad)
     # A17 (Ley 1581): la Ley protege a la PERSONA NATURAL. La razón social de una
     # persona jurídica (Auteco, Éxito, Hunter) NO es PII y debe verla el directivo.
     # Se enmascara SOLO si la contraparte es natural o su tipo es desconocido
     # (manual / PDF sin dato → por precaución) y el usuario no tiene ver_detalle.
     es_juridica = f.tipo_contribuyente == PERSONA_JURIDICA
     ver_contraparte = ver_pii or es_juridica
@@ -115,63 +94,41 @@ def _serializar(
         "total_bruto": money_str(f.total_bruto) if f.total_bruto is not None else None,
         # None = ingesta DIAN (tarifas mezcladas; manda iva_valor, D-13)
         "tarifa_iva": str(f.tarifa_iva) if f.tarifa_iva is not None else None,
         "iva_valor": money_str(f.iva_valor),
         "total": money_str(f.total),
         "deducible": f.deducible,
         # 3 estados en la UI: decidido+True=Sí, decidido+False=No, no decidido=Sin
         # decidir. El §2 cuenta las compras activas con deducible_decidido=False.
         "deducible_decidido": f.deducible_decidido,
         "activo": f.activo,
-        "periodo": _etiqueta_periodo(anio, idx, periodicidad),  # derivado de la fecha
+        "periodo": etiqueta_periodo(anio, idx, periodicidad),  # derivado de la fecha
     }
 
 
 @router.get("")
 async def listar(
     activo: bool | None = Query(default=None),
     user: User = Depends(require_permission("dashboard:leer")),
 ):
     periodicidad = await service.obtener_periodicidad()
     facturas = await service.listar_facturas(activo=activo)
     ver_pii = has_permission(user.rol, "facturas:ver_detalle")
     return [_serializar(f, periodicidad, ver_pii=ver_pii) for f in facturas]
 
 
 @router.get("/liquidacion")
 async def liquidacion(_: User = Depends(require_permission("dashboard:leer"))):
     """Liquidación por período (cuatrimestral o bimestral, según `PERIODICIDAD_IVA`) de
     las facturas activas: generado − descontable con arrastre de saldo a favor. Montos
     como string (regla 1)."""
-    periodicidad = await service.obtener_periodicidad()
-    items = await service.obtener_facturas_iva()
-    calendario = await service.obtener_calendario_dian()
-    return {
-        "periodicidad": periodicidad.value,
-        "periodos": [
-            {
-                "anio": c.anio,
-                "periodo": c.periodo,
-                "etiqueta": _etiqueta_periodo(c.anio, c.periodo, periodicidad),
-                "generado": money_str(c.generado),
-                "descontable": money_str(c.descontable),
-                "saldo": money_str(c.saldo),
-                "saldo_favor_previo": money_str(c.saldo_favor_previo),
-                "neto_a_pagar": money_str(c.neto_a_pagar),
-                "saldo_favor_nuevo": money_str(c.saldo_favor_nuevo),
-                "proximo_pago": _proximo_pago(
-                    c.anio, c.periodo, periodicidad, calendario
-                ),
-            }
-            for c in liquidar(items, periodicidad)
-        ],
-    }
+    return await service.liquidacion_iva()
 
 
 @router.get("/{factura_id}")
 async def detalle(
     factura_id: str,
     _: User = Depends(require_permission("facturas:ver_detalle")),
 ):
     """Detalle de una factura con PII completa (A17 / Ley 1581): solo
     facturas:ver_detalle = {financiero, admin}. La ruta va DESPUÉS de /liquidacion
     para que ese literal no caiga en {factura_id}."""
diff --git a/backend/app/facturas/service.py b/backend/app/facturas/service.py
index 98c6f3a..c16dda4 100644
--- a/backend/app/facturas/service.py
+++ b/backend/app/facturas/service.py
@@ -9,23 +9,31 @@ falla, COMPENSAR). El IVA se calcula AQUÍ (regla 1): `iva_valor = base × tarif
 `FacturaIva` para el liquidador (puente C11↔liquidación)."""
 
 import re
 from decimal import Decimal
 
 from beanie import PydanticObjectId
 from pymongo.errors import DuplicateKeyError
 
 from app.audit.events import AuditEvento
 from app.audit.service import emit_audit
+from app.core.money import money_str
 from app.domain.configuracion import ClaveConfig, Configuracion
 from app.domain.factura import Factura, OrigenFactura, TipoFactura
-from app.iva.liquidacion import FacturaIva, Periodicidad, iva_desde_base
+from app.iva.liquidacion import (
+    FacturaIva,
+    Periodicidad,
+    etiqueta_periodo,
+    iva_desde_base,
+    liquidar,
+    proximo_pago,
+)
 
 _MES = re.compile(r"^\d{4}-\d{2}$")
 
 
 class FacturasError(Exception):
     def __init__(self, detalle: str, status: int = 422) -> None:
         super().__init__(detalle)
         self.detalle = detalle
         self.status = status
 
@@ -332,10 +340,37 @@ async def obtener_facturas_iva() -> list[FacturaIva]:
     activas = await listar_facturas(activo=True)
     return [
         FacturaIva(
             tipo=f.tipo.value,
             fecha=f.fecha,
             iva_valor=f.iva_valor,
             deducible=f.deducible,
         )
         for f in activas
     ]
+
+
+async def liquidacion_iva() -> dict:
+    """Liquidación de IVA por período (misma forma que GET /facturas/liquidacion)."""
+    periodicidad = await obtener_periodicidad()
+    items = await obtener_facturas_iva()
+    calendario = await obtener_calendario_dian()
+    return {
+        "periodicidad": periodicidad.value,
+        "periodos": [
+            {
+                "anio": c.anio,
+                "periodo": c.periodo,
+                "etiqueta": etiqueta_periodo(c.anio, c.periodo, periodicidad),
+                "generado": money_str(c.generado),
+                "descontable": money_str(c.descontable),
+                "saldo": money_str(c.saldo),
+                "saldo_favor_previo": money_str(c.saldo_favor_previo),
+                "neto_a_pagar": money_str(c.neto_a_pagar),
+                "saldo_favor_nuevo": money_str(c.saldo_favor_nuevo),
+                "proximo_pago": proximo_pago(
+                    c.anio, c.periodo, periodicidad, calendario
+                ),
+            }
+            for c in liquidar(items, periodicidad)
+        ],
+    }
diff --git a/backend/app/iva/liquidacion.py b/backend/app/iva/liquidacion.py
index 4db373a..84f5d88 100644
--- a/backend/app/iva/liquidacion.py
+++ b/backend/app/iva/liquidacion.py
@@ -4,23 +4,26 @@
 Réplica del diseño de docs/modelo/AUDITORIA-IVA-ARTIFACT-V2.md §5.2. Todo Decimal
 (regla 1). El PERÍODO es CONFIGURABLE (decisión CEO 2026-07-25): default CUATRIMESTRAL
 (ene-abr / may-ago / sep-dic — realidad actual de RODDOS), y bimestral (ene-feb /
 mar-abr / … / nov-dic) habilitable cuando la DIAN lo exija por volumen de facturas.
 Tarifa general 19%; el IVA descontable cuenta SOLO compras deducibles (incluye Auteco
 —autorretenedor, pero su IVA SÍ es descontable— y otras compras). El saldo a favor se
 ARRASTRA al siguiente período.
 """
 
 from dataclasses import dataclass
+from datetime import date
 from decimal import ROUND_HALF_EVEN, Decimal
 from enum import StrEnum
 
+from app.core.time import today_bogota
+
 _CENTAVO = Decimal("0.01")
 
 _MESES_ABBR = (
     "ene",
     "feb",
     "mar",
     "abr",
     "may",
     "jun",
     "jul",
@@ -72,20 +75,39 @@ def periodo_de(
 def clave_dian(idx: int, periodicidad: Periodicidad) -> str:
     """Clave del período en `CALENDARIO_DIAN` = 'mesInicio_mesFin' (p. ej. 'ene_abr',
     'may_ago' cuatrimestral; 'ene_feb', 'mar_abr' bimestral). Derivada del rango de
     meses del período → una sola fuente de verdad, sin listas hardcodeadas."""
     meses = _meses_por_periodo(periodicidad)
     ini = (idx - 1) * meses
     fin = idx * meses - 1
     return f"{_MESES_ABBR[ini]}_{_MESES_ABBR[fin]}"
 
 
+def etiqueta_periodo(anio: int, idx: int, periodicidad: Periodicidad) -> str:
+    # 'C' cuatrimestral (2026-C1) · 'B' bimestral (2026-B1)
+    prefijo = "C" if periodicidad == Periodicidad.cuatrimestral else "B"
+    return f"{anio}-{prefijo}{idx}"
+
+
+def proximo_pago(
+    anio: int, idx: int, periodicidad: Periodicidad, calendario: dict
+) -> dict | None:
+    """Fecha DIAN del período (de `CALENDARIO_DIAN`) + días desde hoy (Bogotá). Sin
+    fecha en el calendario → None: la UI omite la línea, no se inventa (R5, §3③)."""
+    anio_cal = calendario.get(str(anio))
+    fecha = anio_cal.get(clave_dian(idx, periodicidad)) if anio_cal else None
+    if not fecha:
+        return None
+    y, m, d = (int(x) for x in fecha.split("-"))
+    return {"fecha": fecha, "dias": (date(y, m, d) - today_bogota()).days}
+
+
 def cuatrimestre_de(fecha: str) -> tuple[int, int]:
     """Compat: `periodo_de` con periodicidad cuatrimestral (el default histórico)."""
     return periodo_de(fecha, Periodicidad.cuatrimestral)
 
 
 @dataclass(frozen=True)
 class FacturaIva:
     """Subconjunto de `Factura` que afecta la liquidación (compute-only). `deducible`
     solo aplica a compras (si su IVA es descontable)."""
 
diff --git a/backend/tests/cfo/__init__.py b/backend/tests/cfo/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/backend/tests/cfo/test_calc_caja.py b/backend/tests/cfo/test_calc_caja.py
new file mode 100644
index 0000000..764c7cf
--- /dev/null
+++ b/backend/tests/cfo/test_calc_caja.py
@@ -0,0 +1,127 @@
+# backend/tests/cfo/test_calc_caja.py
+"""Task 3 FABS inc1 — concepto `caja_hoy`: lee la serie diaria real de COMPAS
+(`caja.service.caja_diaria`) desde el ancla `caja_inicial`/`vigente_desde` de los
+parámetros de proyección vigentes hasta hoy (Bogotá), y toma el último saldo con
+su fecha de corte. Abstención sin parámetros vigentes; cae al ancla sin
+movimientos en el rango. mongomock; patrón de la suite: init_beanie con
+DOMAIN_DOCUMENTS (ver tests/test_control.py, tests/test_facturas.py)."""
+
+from datetime import date
+from decimal import Decimal
+
+import pytest_asyncio
+from app.domain import DOMAIN_DOCUMENTS
+from app.domain.mes_control import MesControl
+from app.domain.parametros_proyeccion import ParametrosProyeccion
+from app.domain.rubro import Rubro
+from app.domain.transaccion import Transaccion
+from beanie import init_beanie
+from mongomock_motor import AsyncMongoMockClient
+
+
+def _parametros_completos(**overrides) -> ParametrosProyeccion:
+    """Fixture COMPLETA y válida del modelo real (todos los campos obligatorios
+    de `app/domain/parametros_proyeccion.py`), en cero salvo lo que el test
+    necesite — mismo patrón que `tests/test_facturas.py`."""
+    campos = {
+        "vigente_desde": "2026-08-01",
+        "caja_inicial": Decimal("0"),
+        "caja_minima": Decimal("0"),
+        "motos_base": 0,
+        "crec_pct_mensual": Decimal("0"),
+        "horizonte_meses": 8,
+        "adelanto_auteco": Decimal("0"),
+        "plazo_auteco_dias": 0,
+        "base_auteco_dias": 0,
+        "tasa_auteco": Decimal("0"),
+        "gastos_fijos": Decimal("0"),
+        "gps_moto": Decimal("0"),
+        "costo_moto_nueva": Decimal("0"),
+        "deuda": Decimal("0"),
+        "tasa_deuda": Decimal("0"),
+        "mes_inicio_deuda": 0,
+        "meses_deuda": 0,
+        "pct_mora": Decimal("0"),
+        "pct_recuperacion": Decimal("0"),
+        "pct_default": Decimal("0"),
+        "pct_provision": Decimal("0"),
+    }
+    campos.update(overrides)
+    return ParametrosProyeccion(**campos)
+
+
+@pytest_asyncio.fixture
+async def db():
+    """DB con parámetros vigentes (caja_inicial=700M desde 2026-08-01) + un
+    MesControl y un Rubro reales para poder insertar Transaccion válidas."""
+    c = AsyncMongoMockClient(tz_aware=True)
+    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
+    mc = MesControl(mes="2026-08-01", saldo_inicial_caja=Decimal("0"))
+    await mc.insert()
+    rubro = Rubro(grupo="ingresos_operativos", nombre="Cuotas iniciales", orden=1)
+    await rubro.insert()
+    await _parametros_completos(caja_inicial=Decimal("700000000")).insert()
+    yield {"mc_id": mc.id, "rubro_id": rubro.id}
+
+
+async def _tx(ids: dict, fecha: str, valor: str, tipo: str = "ingreso") -> None:
+    await Transaccion(
+        fecha=fecha,
+        descripcion="ingreso real",
+        valor=Decimal(valor),
+        tipo_flujo=tipo,
+        rubro_id=ids["rubro_id"],
+        mes_id=ids["mc_id"],
+        banco="global66",
+        id_banco=f"ING-{fecha}-{valor}",
+    ).insert()
+
+
+async def test_caja_hoy_devuelve_ultimo_saldo_con_fecha_corte(db, monkeypatch):
+    import app.cfo.calc.caja as caja_mod
+
+    # Ancla hoy=2026-08-04 (patch en el NOMBRE importado dentro de caja.py, no en
+    # app.core.time — mismo idioma que tests/test_bank_parsers.py::TestFronteraAnio).
+    monkeypatch.setattr(caja_mod, "today_bogota", lambda: date(2026, 8, 4))
+    await _tx(db, "2026-08-02", "5000000")
+    await _tx(db, "2026-08-04", "3000000")
+    # Movimiento POSTERIOR al "hoy" simulado: si el patch no tomara efecto (se
+    # usara la fecha real del sistema, muy posterior), este movimiento SÍ entraría
+    # al rango y cambiaría valor/fecha_corte — es la prueba de que el patch aplica.
+    await _tx(db, "2026-08-06", "999000000")
+
+    r = await caja_mod.caja_hoy()
+    assert r.concepto == "caja_hoy"
+    assert r.unidad == "COP"
+    assert r.disponible is True
+    assert r.valor == Decimal("708000000.00")  # 700M + 5M + 3M (el 08-06 excluido)
+    assert r.evidencia.fuente == "caja.service.caja_diaria"
+    assert r.evidencia.fecha_corte == "2026-08-04"
+    assert r.evidencia.ref == "2026-08"
+    assert r.detalle == {"desde": "2026-08-01", "hasta": "2026-08-04"}
+
+
+async def test_caja_hoy_sin_movimientos_cae_al_ancla(db, monkeypatch):
+    import app.cfo.calc.caja as caja_mod
+
+    monkeypatch.setattr(caja_mod, "today_bogota", lambda: date(2026, 8, 4))
+    # Sin transacciones insertadas: caja_diaria() devuelve dias=[] (serie_diaria
+    # solo emite días CON movimiento) → cae al ancla caja_inicial/vigente_desde.
+    r = await caja_mod.caja_hoy()
+    assert r.disponible is True
+    assert r.valor == Decimal("700000000")
+    assert r.evidencia.fecha_corte == "2026-08-01"
+    assert r.evidencia.ref == "sin-movimientos"
+
+
+async def test_caja_hoy_sin_parametros_abstiene():
+    c = AsyncMongoMockClient(tz_aware=True)
+    await init_beanie(database=c["compas_vacio"], document_models=DOMAIN_DOCUMENTS)
+
+    from app.cfo.calc.caja import caja_hoy
+
+    r = await caja_hoy()
+    assert r.disponible is False
+    assert r.valor is None
+    assert r.evidencia.fecha_corte is None
+    assert r.evidencia.ref == "sin-parametros"
diff --git a/backend/tests/cfo/test_calc_iva.py b/backend/tests/cfo/test_calc_iva.py
new file mode 100644
index 0000000..48df9fc
--- /dev/null
+++ b/backend/tests/cfo/test_calc_iva.py
@@ -0,0 +1,42 @@
+from decimal import Decimal
+
+import pytest
+
+
+@pytest.mark.asyncio
+async def test_iva_toma_neto_del_periodo_vigente(monkeypatch):
+    from app.cfo.calc import iva as mod
+
+    async def _liq():
+        return {
+            "periodicidad": "cuatrimestral",
+            "periodos": [
+                {
+                    "anio": 2026,
+                    "periodo": 2,
+                    "etiqueta": "2026-C2",
+                    "neto_a_pagar": "26000000.00",
+                    "proximo_pago": {"fecha": "2026-09-10", "dias": 31},
+                },
+            ],
+        }
+
+    monkeypatch.setattr(mod, "_liquidacion", _liq)
+    # hoy dentro de C2 (may-ago): 2026-08-10
+    monkeypatch.setattr(mod, "_periodo_vigente_idx", lambda: (2026, 2))
+    r = await mod.iva_cuatrimestre()
+    assert r.disponible is True and r.valor == Decimal("26000000.00")
+    assert r.evidencia.fecha_corte == "2026-09-10" and r.evidencia.ref == "2026-C2"
+
+
+@pytest.mark.asyncio
+async def test_iva_sin_periodo_vigente_abstiene(monkeypatch):
+    from app.cfo.calc import iva as mod
+
+    async def _liq():
+        return {"periodicidad": "cuatrimestral", "periodos": []}
+
+    monkeypatch.setattr(mod, "_liquidacion", _liq)
+    monkeypatch.setattr(mod, "_periodo_vigente_idx", lambda: (2026, 3))
+    r = await mod.iva_cuatrimestre()
+    assert r.disponible is False and r.valor is None
diff --git a/backend/tests/cfo/test_calc_runway.py b/backend/tests/cfo/test_calc_runway.py
new file mode 100644
index 0000000..86e5273
--- /dev/null
+++ b/backend/tests/cfo/test_calc_runway.py
@@ -0,0 +1,30 @@
+from decimal import Decimal
+
+import pytest
+
+
+@pytest.mark.asyncio
+async def test_runway_sin_config_abstiene(monkeypatch):
+    from app.cfo.calc import runway as mod
+
+    async def _boom(**kw):
+        from app.proyeccion.service import ProyeccionError
+
+        raise ProyeccionError("no hay parametros", 409)
+
+    monkeypatch.setattr(mod, "_proyectar", _boom)
+    r = await mod.runway()
+    assert r.disponible is False and r.valor is None and r.unidad == "meses"
+
+
+@pytest.mark.asyncio
+async def test_runway_toma_runway_meses(monkeypatch):
+    from app.cfo.calc import runway as mod
+
+    async def _ok(**kw):
+        return {"runway_meses": "18.0", "meses": []}
+
+    monkeypatch.setattr(mod, "_proyectar", _ok)
+    r = await mod.runway()
+    assert r.disponible is True and r.valor == Decimal("18.0")
+    assert r.evidencia.fuente.startswith("proyeccion")
diff --git a/backend/tests/cfo/test_config.py b/backend/tests/cfo/test_config.py
new file mode 100644
index 0000000..2759043
--- /dev/null
+++ b/backend/tests/cfo/test_config.py
@@ -0,0 +1,11 @@
+from app.cfo.config import cfo_enabled
+
+
+def test_flag_apagado_por_defecto(monkeypatch):
+    monkeypatch.delenv("CFO_ENABLED", raising=False)
+    assert cfo_enabled() is False
+
+
+def test_flag_encendible_por_env(monkeypatch):
+    monkeypatch.setenv("CFO_ENABLED", "true")
+    assert cfo_enabled() is True
diff --git a/backend/tests/cfo/test_evidencia.py b/backend/tests/cfo/test_evidencia.py
new file mode 100644
index 0000000..ec61df7
--- /dev/null
+++ b/backend/tests/cfo/test_evidencia.py
@@ -0,0 +1,36 @@
+from decimal import Decimal
+
+import pytest
+from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
+from pydantic import ValidationError
+
+
+def test_resultado_ok_con_evidencia():
+    r = ResultadoCFO(
+        concepto="caja_hoy",
+        valor=Decimal("704722003.00"),
+        unidad="COP",
+        disponible=True,
+        evidencia=Evidencia(
+            fuente="caja.service.caja_diaria", fecha_corte="2026-08-04", ref="2026-08"
+        ),
+    )
+    assert r.valor == Decimal("704722003.00")
+    assert r.evidencia.fecha_corte == "2026-08-04"
+    assert r.detalle == {}
+
+
+def test_abstencion_valor_none_disponible_false():
+    r = ResultadoCFO(
+        concepto="runway",
+        valor=None,
+        unidad="meses",
+        disponible=False,
+        evidencia=Evidencia(fuente="proyeccion", fecha_corte=None, ref="sin-config"),
+    )
+    assert r.valor is None and r.disponible is False
+
+
+def test_rechaza_campo_extra_strict():
+    with pytest.raises(ValidationError):
+        Evidencia(fuente="x", fecha_corte=None, ref="y", inventado=1)
diff --git a/backend/tests/cfo/test_goldens_modelo.py b/backend/tests/cfo/test_goldens_modelo.py
new file mode 100644
index 0000000..ee29f1d
--- /dev/null
+++ b/backend/tests/cfo/test_goldens_modelo.py
@@ -0,0 +1,38 @@
+# backend/tests/cfo/test_goldens_modelo.py
+"""Task 7 FABS inc1 — modelo `CFOGolden` (Beanie Document, colección `cfo_goldens`)
+registrado en Beanie vía `DOMAIN_DOCUMENTS`. Persiste y relee un caso dorado."""
+
+from decimal import Decimal
+
+import pytest
+import pytest_asyncio
+from app.domain import DOMAIN_DOCUMENTS
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
+@pytest.mark.asyncio
+async def test_persistir_y_leer_golden(db):
+    from app.cfo.goldens.modelo import CFOGolden
+    from app.core.time import now_bogota
+
+    g = CFOGolden(
+        concepto="runway",
+        filtros={},
+        valor_esperado=Decimal("18.0"),
+        tolerancia=Decimal("0.1"),
+        unidad="meses",
+        origen="semilla",
+        nota="al 2026-08",
+        creado_at=now_bogota(),
+    )
+    await g.insert()
+    leido = await CFOGolden.find_one(CFOGolden.concepto == "runway")
+    assert leido is not None and leido.valor_esperado == Decimal("18.0")
diff --git a/backend/tests/cfo/test_goldens_runner.py b/backend/tests/cfo/test_goldens_runner.py
new file mode 100644
index 0000000..5ff003d
--- /dev/null
+++ b/backend/tests/cfo/test_goldens_runner.py
@@ -0,0 +1,73 @@
+from decimal import Decimal
+
+import pytest
+import pytest_asyncio
+from app.domain import DOMAIN_DOCUMENTS
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
+@pytest.mark.asyncio
+async def test_runner_ok_fallo_y_abstencion(db, monkeypatch):
+    from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
+    from app.cfo.goldens import runner
+    from app.cfo.goldens.modelo import CFOGolden
+    from app.core.time import now_bogota
+
+    def _res(concepto, valor, unidad, disp=True):
+        return ResultadoCFO(
+            concepto=concepto, valor=valor, unidad=unidad, disponible=disp,
+            evidencia=Evidencia(fuente="x", fecha_corte=None, ref="r"),
+        )
+
+    async def _runway():
+        return _res("runway", Decimal("18.05"), "meses")
+
+    async def _caja():
+        return _res("caja_hoy", Decimal("700000000"), "COP")
+
+    async def _iva():
+        return _res("iva_cuatrimestre", None, "COP", disp=False)  # abstención
+
+    monkeypatch.setattr(
+        runner,
+        "CONCEPTOS",
+        {"runway": _runway, "caja_hoy": _caja, "iva_cuatrimestre": _iva},
+    )
+
+    now = now_bogota()
+    await CFOGolden(
+        concepto="runway",
+        valor_esperado=Decimal("18.0"),
+        tolerancia=Decimal("0.1"),
+        unidad="meses",
+        origen="semilla",
+        creado_at=now,
+    ).insert()  # OK (delta 0.05<0.1)
+    await CFOGolden(
+        concepto="caja_hoy",
+        valor_esperado=Decimal("500000000"),
+        tolerancia=Decimal("1"),
+        unidad="COP",
+        origen="semilla",
+        creado_at=now,
+    ).insert()  # FALLO
+    await CFOGolden(
+        concepto="iva_cuatrimestre",
+        valor_esperado=None,
+        tolerancia=Decimal("1"),
+        unidad="COP",
+        origen="semilla",
+        creado_at=now,
+    ).insert()  # abstención OK
+
+    rep = await runner.correr_goldens()
+    assert rep["total"] == 3 and rep["ok"] == 1 and rep["abstenciones_ok"] == 1
+    assert len(rep["fallos"]) == 1 and rep["fallos"][0]["concepto"] == "caja_hoy"
diff --git a/backend/tests/cfo/test_goldens_semilla.py b/backend/tests/cfo/test_goldens_semilla.py
new file mode 100644
index 0000000..b420d20
--- /dev/null
+++ b/backend/tests/cfo/test_goldens_semilla.py
@@ -0,0 +1,25 @@
+import pytest
+import pytest_asyncio
+from app.domain import DOMAIN_DOCUMENTS
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
+@pytest.mark.asyncio
+async def test_sembrar_idempotente(db):
+    from app.cfo.goldens.modelo import CFOGolden
+    from app.cfo.goldens.semilla import sembrar_semilla
+
+    ins1, dup1 = await sembrar_semilla()
+    ins2, dup2 = await sembrar_semilla()  # segunda vez no duplica
+    assert ins1 >= 1 and dup1 == 0
+    assert ins2 == 0 and dup2 == ins1
+    # todos los conceptos sembrados existen
+    assert await CFOGolden.find_all().count() == ins1
diff --git a/backend/tests/cfo/test_s1_aislamiento.py b/backend/tests/cfo/test_s1_aislamiento.py
new file mode 100644
index 0000000..88b156e
--- /dev/null
+++ b/backend/tests/cfo/test_s1_aislamiento.py
@@ -0,0 +1,42 @@
+"""S1: cfo/calc y cfo/goldens NO importan modelos de dominio ajenos ni tocan el driver
+de Mongo; la única subruta que persiste es cfo/datos/repositorios.py y solo cfo_*."""
+
+import pathlib
+import re
+
+CFO = pathlib.Path(__file__).resolve().parents[2] / "app" / "cfo"
+
+# Subrutas que NO pueden tocar Mongo directamente ni importar modelos de dominio ajenos.
+LOGICA = [CFO / "calc", CFO / "goldens"]
+PROHIBIDO_IMPORT = re.compile(
+    r"from app\.domain\.(?!__init__)"
+)  # modelos de dominio ajenos
+PROHIBIDO_DRIVER = re.compile(r"get_pymongo_collection|motor|AsyncIOMotor")
+
+
+def _py_files(base):
+    return [p for p in base.rglob("*.py") if p.name != "__init__.py"]
+
+
+def test_calc_y_goldens_no_tocan_driver_ni_dominio_ajeno():
+    ofensas = []
+    for base in LOGICA:
+        for f in _py_files(base):
+            txt = f.read_text(encoding="utf-8")
+            # excepción: cfo/goldens/modelo.py define su PROPIO Document (cfo_goldens)
+            if f.name == "modelo.py":
+                continue
+            if PROHIBIDO_DRIVER.search(txt):
+                ofensas.append(f"{f}: toca el driver de Mongo")
+            for m in PROHIBIDO_IMPORT.finditer(txt):
+                # se permite importar tipos de lectura de dominio SOLO si el spec lo
+                # documenta; para inc1 no debería hacer falta ninguno en calc/goldens.
+                ofensas.append(f"{f}: importa modelo de dominio ajeno ({m.group()})")
+    assert ofensas == [], "Violaciones S1:\n" + "\n".join(ofensas)
+
+
+def test_solo_repositorios_persiste_cfo():
+    # cfo/datos/repositorios.py solo referencia CFOGolden (colección cfo_goldens)
+    repo = (CFO / "datos" / "repositorios.py").read_text(encoding="utf-8")
+    assert "CFOGolden" in repo
+    assert "app.domain" not in repo  # no persiste colecciones ajenas
diff --git a/backend/tests/test_db.py b/backend/tests/test_db.py
index 801776a..9454db4 100644
--- a/backend/tests/test_db.py
+++ b/backend/tests/test_db.py
@@ -16,16 +16,17 @@ async def test_init_beanie_registra_los_documents_de_dominio():
     Configuracion y Transaccion (§1.5). AuditLog/User/RefreshSession NO están
     (Motor crudo)."""
     from app.audit.models import AuditLog
     from app.domain import DOMAIN_DOCUMENTS, Transaccion
 
     assert mongo.DOCUMENT_MODELS == DOMAIN_DOCUMENTS
     # 9 previos + ModeloMoto + ParametrosProyeccion (COCK-02, CR-COCK)
     # + CarteraPreviaRecaudo (PR-1) + Factura (PR-2a) + LoanTapeCredito (aging)
     # + GastoRecurrente (plantilla de gastos fijos, 1d9f99c)
     # + EscenarioImpacto (D1 §2, escenarios what-if auditados)
-    # + Obligacion/FacturaObligacion/MetaIngreso (D2 §2/§6).
-    assert len(DOMAIN_DOCUMENTS) == 19
+    # + Obligacion/FacturaObligacion/MetaIngreso (D2 §2/§6)
+    # + CFOGolden (Task 7, FABS inc1 — cimiento determinista).
+    assert len(DOMAIN_DOCUMENTS) == 20
     assert Transaccion in mongo.DOCUMENT_MODELS
     assert AuditLog not in mongo.DOCUMENT_MODELS
     client = AsyncMongoMockClient()
     await mongo.init_beanie_for(client, "compas_test")  # no debe lanzar
diff --git a/docs/COMPAS_FABS_ROADMAP.md b/docs/COMPAS_FABS_ROADMAP.md
index 16f8647..a717d0f 100644
--- a/docs/COMPAS_FABS_ROADMAP.md
+++ b/docs/COMPAS_FABS_ROADMAP.md
@@ -18,21 +18,21 @@
 Analista financiero de IA que responde con **cifras reales y trazables** desde COMPAS,
 vigila la caja y prepara el Comité de Pagos — **sin ejecutar operaciones y sin inventar
 ni una cifra** (el modelo nunca calcula; COMPAS calcula, FABS narra con evidencia).
 
 ## 2. Fases / incrementos
 
 Estado: ⬜ Pendiente · 🟡 En curso · ✅ Hecho · 🔒 Bloqueado
 
 | # | Incremento | Qué entrega | Gate | Estado |
 |---|---|---|---|---|
-| **1** | **Cimiento determinista** (sin LLM) | `app/cfo/calc` (3 conceptos: caja hoy · runway · IVA cuatrimestre, cada cifra con evidencia) + arnés de goldens (`cfo/goldens`) + salvaguarda S1 + flag `CFO_ENABLED`. Motor COMPAS cero diffs. | Kimi (lee cifras de plata) | 🟡 En curso |
+| **1** | **Cimiento determinista** (sin LLM) | `app/cfo/calc` (3 conceptos: caja hoy · runway · IVA cuatrimestre, cada cifra con evidencia) + arnés de goldens (`cfo/goldens`) + salvaguarda S1 + flag `CFO_ENABLED`. Motor COMPAS cero diffs. | Kimi (lee cifras de plata) | ✅ Hecho (rama `feat/fabs-inc1`; falta merge a main tras gate) |
 | **2** | **Loop del agente + cifra→evidencia** | Loop con SDK Anthropic (temp 0.1, límites), verificador cifra→evidencia invocado antes de publicar, endpoint `/api/v1/cfo` bajo flag, salida tipada. Primeros eventos `cfo.*` (CR). | Kimi (crítico) + CR eventos | ⬜ Pendiente |
 | **3** | **Canal Telegram + piloto Q&A** | Webhook Telegram en compas-api, vínculo `telegram_id↔user_id`, hilos por usuario (`cfo_hilos`, sin TTL naïve), observabilidad. Piloto pregunta-respuesta (CEO/CGO/CFO). | G2 (núcleo confiable) | ⬜ Pendiente |
 | **4** | **Vigilante + Comité de Pagos** | Jobs `cfo_*` en el Worker (alertas por umbral, paquete del lunes 7:00, cierre mensual comentado) — borrador con liberación humana. | G3 (piloto→operación) | ⬜ Pendiente |
 | **5** | **Chat embebido en COMPAS** | Panel de chat en la app (SSE), mismo hilo por usuario que Telegram, RBAC de COMPAS. | — | ⬜ Pendiente |
 | **6** | **Evolución** (post-estabilización) | Provisión de IVA como tesorería, proyecciones de escenario conversacionales, Teams, reporte inversionistas. | — | ⬜ Pendiente |
 
 ## 3. Gates y prerrequisitos
 
 | Gate | Cuándo | Debe cumplirse |
 |---|---|---|
@@ -46,20 +46,27 @@ Estado: ⬜ Pendiente · 🟡 En curso · ✅ Hecho · 🔒 Bloqueado
 - **LoanTape (SISMO-V3):** para cartera fina; hoy `loantape_creditos` vacía. Ligado a CR-PTS6F.
 - **Sunset del CFO legado de SISMO-V2** (D1): higiene previa; el flag de FABS no apaga al legado.
 - **Presupuesto operativo:** $30 USD/mes (aplica desde el incremento 2, cuando entra el LLM).
 
 ## 4. Registro de cambios (fechado, append-only)
 
 | Fecha | Incremento | Qué cerró / cambió | Evidencia |
 |---|---|---|---|
 | 2026-08-10 | 1 | Spec del incremento 1 aprobado por el CEO | `docs/superpowers/specs/2026-08-10-fabs-cimiento-determinista-design.md` (commit 898d3c9) |
 | 2026-08-10 | 1 | Plan de implementación escrito + roadmap creado | `docs/superpowers/plans/2026-08-10-fabs-cimiento-determinista.md` |
+| 2026-08-11 | 1 | **Incremento 1 CONSTRUIDO** (SDD, 11 tasks, subagente+review por tarea). `app/cfo/`: evidencia · flag · 3 conceptos · refactor DRY `liquidacion_iva()` · modelo/runner/semilla de goldens · guard S1. Suite COMPAS **940 passed / 95 skipped**, flag apagado ⇒ idéntico; `motor.py` cero diffs. | rama `feat/fabs-inc1`, commits `63f8ef3..bbe2c3b` |
+| 2026-08-11 | 1 | Semilla real de goldens desde PROD (snapshot): caja_hoy 704.722.003 · runway abstención · IVA C2-2026 36.204.698,10 (DIAN 10-sep) | `app/cfo/goldens/semilla.py` (`bbe2c3b`) |
 
 ## 5. Estado de datos / decisiones abiertas del CEO
 
 - **Alegra:** CERO en esta fase (revisión 2027 si se requiere).
 - **Fuera de alcance permanente:** CXC socios, interés presuntivo, devengado/P&L, labores contables (COMPAS/FABS NO son ERP).
 - **Fórmulas faltantes** (si las hubiera): se construyen EN COMPAS (aditivas, motor intocable), FABS las consume (D5).
-- **Pendientes del CEO:** rotación del token Alegra filtrado en SISMO-V2 (higiene de seguridad); GO al CR-PTS6F (cartera de apertura).
+- **Pendientes del CEO:** rotación del token Alegra filtrado en SISMO-V2 (higiene de seguridad); GO al CR-PTS6F (cartera de apertura); merge de `feat/fabs-inc1` a main tras el gate.
+
+## 6. Refinamientos conocidos (para incrementos siguientes)
+
+- **`caja_hoy` — semántica de anclaje (inc2):** hoy corre `caja_diaria` desde el `vigente_desde` de los parámetros vigentes. Como esos parámetros se re-guardan seguido (vigente_desde = fecha reciente) y no hay movimientos cargados en esa ventana, en PROD devolvió la `caja_inicial` cruda (704.722.003) con `ref="sin-movimientos"`, no la caja corrida real. Refinar en inc2: anclar desde el último mes CERRADO (o desde el primer movimiento del mes en curso) para reflejar la caja real a la fecha de corte. La abstención honesta y la evidencia ya funcionan; es un ajuste de fuente, no de contrato.
+- **`proximo_pago` lee reloj dentro de módulo "compute-only"** (`app/iva/liquidacion.py`, preexistente, reubicado en el refactor DRY): considerar pasar "hoy" como parámetro para determinismo pleno.
 
 ---
 *Creado 2026-08-10. Este archivo se actualiza al cerrar cada pieza (no al final del incremento).*
```
