# EVIDENCIA — E1 PR2-I: capa de anclaje (P2)

**Rama:** `feat/e1-p2-anclaje-service` · commits `5de5052`, `a71a572`, `632aace`, `7ed35a2` · **Fecha:** 2026-08-06

## 1. Tests (real)

```
$ python -m pytest backend/tests/test_e1_anclaje.py backend/tests/test_e1_lectura.py backend/tests/test_e1_extract_julio.py -q
...............                                                          [100%]
15 passed in 0.11s
```

Regresión amplia (proyección/golden/motor/control/metas/ejecucion/e1):
```
$ python -m pytest backend/tests/ -q -k "proyeccion or golden or motor or control or metas or ejecucion or e1 or lectura or anclaje"
137 passed, 3 skipped, 829 deselected
(los 3 skipped requieren Mongo real; se corren en CI backend-real-mongo)
```

## 2. Lint + R0 (real)

```
$ python -m ruff check backend/app/proyeccion/ejecucion/ backend/tests/test_e1_anclaje.py backend/tests/test_e1_lectura.py
All checks passed!

$ git diff origin/main -- backend/app/proyeccion/motor.py
(vacío — R0: motor.py cero diffs)
```

## 3. Diff completo de la rama vs main (real, `git diff origin/main...HEAD`)

```diff
diff --git a/backend/app/proyeccion/ejecucion/lectura.py b/backend/app/proyeccion/ejecucion/lectura.py
index a776a33..504d623 100644
--- a/backend/app/proyeccion/ejecucion/lectura.py
+++ b/backend/app/proyeccion/ejecucion/lectura.py
@@ -4,8 +4,8 @@
 Traduce el ejecutado por rubro (la verdad del libro) a los conceptos que el motor
 proyecta, usando el mapeo del Plan de Cuentas (I-PLAN §10, decisiones del CEO):
 
-    neto (ingreso)   ← 0110 Recaudo · 0120 Cuotas iniciales · 0130 RODANTE · 0140 Otros
-    pago_inventario  ← 1010 Producto + 4060 Inventario Auteco (150d)   [coexisten, R-1]
+    neto (ingreso)   ← 0110 Recaudo de cartera   [único rubro de ingreso real de RODDOS]
+    pago_inventario  ← 1010 Producto                        [R-1: 1010 entero]
     fondeo           ← 4030 Garantía cupo (Auteco)          [REEMPLAZA el paramétrico]
     costo_nueva      ← 1020 SOAT/Matrículas                 [R-1: 1010 no entra aquí]
     gps              ← 1030 Seguros (Hunter)
@@ -13,6 +13,12 @@ proyecta, usando el mapeo del Plan de Cuentas (I-PLAN §10, decisiones del CEO):
     int_deuda        ← 4010 Préstamos · 4020 Tarjetas · 4050 Proveedores
     iva              ← 5060 Impuestos
 
+NOTA (E1-P2, decisión CEO 2026-08-06): se quitaron del mapeo 0120 (Cuotas iniciales),
+0130 (RODANTE), 0140 (Otros ingresos) y 4060 (Inventario Auteco) — están en la semilla
+pero NO en la taxonomía de PROD (rubros "dormidos": los ingresos van todos a 0110 y
+Auteco va por D2). Con ellos en el mapeo, B12 disparaba ValueError en producción. Los 9
+códigos restantes existen todos en PROD. Si algún día se siembran, se re-agregan aquí.
+
 FUNCIÓN PURA (sin Mongo): recibe el snapshot de rubros + el valor ejecutado por
 rubro_id + los ids de los rubros neutros, y devuelve {concepto: Decimal} + sin_mapear.
 Nada se adivina:
@@ -46,14 +52,11 @@ CONCEPTOS = (
     "iva",
 )
 
-# Mapeo explícito por código (los específicos del §10).
+# Mapeo explícito por código (los específicos del §10). Solo códigos presentes en la
+# taxonomía de PROD — 0120/0130/0140/4060 quitados (ver NOTA del docstring).
 _CONCEPTO_POR_CODIGO: dict[str, str] = {
-    "0110": "neto",
-    "0120": "neto",
-    "0130": "neto",
-    "0140": "neto",
+    "0110": "neto",  # único rubro de ingreso real; E1 ancla el neto vía ingreso_real
     "1010": "pago_inventario",  # R-1: entero a pago_inventario
-    "4060": "pago_inventario",
     "4030": "fondeo",
     "1020": "costo_nueva",
     "1030": "gps",
diff --git a/backend/app/proyeccion/ejecucion/service.py b/backend/app/proyeccion/ejecucion/service.py
new file mode 100644
index 0000000..9ac04f1
--- /dev/null
+++ b/backend/app/proyeccion/ejecucion/service.py
@@ -0,0 +1,188 @@
+# backend/app/proyeccion/ejecucion/service.py
+"""E1 · P2 — capa de ANCLAJE de la proyección a la ejecución real (post-motor puro).
+
+La jerarquía del plan §1: para cada mes del horizonte, la serie se arma con la mejor
+fuente disponible según `MesControl.estado`.
+
+    Cerrado              → gasto/costo = ejecutado real · ingreso = real recaudado
+    En ejecución         → Regla A (D-08): ejecutado + max(0, definido − ejecutado) por
+                           concepto · ingreso = motor (NO se ancla; converge al cerrar)
+    Futuro c/presupuesto → el presupuesto DEFINIDO vigente · ingreso = motor
+    Futuro s/presupuesto → el motor paramétrico (como hoy)
+
+Mecánica (idéntica a la reconciliación D2, `obligaciones/reconciliacion.py`): se calcula
+el delta de FLUJO que el anclaje imprime en cada mes, se re-acumula la caja con
+`impactos.reacumular` (motor intacto, primer mes fijo), y LUEGO se reescriben los campos
+POR CONCEPTO de los meses anclados — reescribir conceptos dentro de `reacumular` sería
+incorrecto (D1 lo comparte). Con `anclas` vacío la serie es la base bit a bit (golden).
+
+**E1 NO toca Auteco.** `pago_inventario`, `fondeo` (y `adelanto`) se conservan del
+motor; esa vía es D2 (obligaciones). La precedencia de P3 evita el doble conteo. E1
+ancla el resto: `neto` (solo cerrado), `gastos_fijos`, `gps`, `costo_nueva`,
+`int_deuda`, `iva`.
+
+**Composición con COCK-09 (rolling forecast):** COCK-09 ancla la caja inicial (el punto
+de partida del horizonte, un escalar); E1 ancla las LÍNEAS de los meses
+cerrado/en-ejecución y re-acumula desde ahí. Magnitudes ortogonales — sin doble anclaje.
+
+Función PURA sobre snapshots (sin Mongo): el llamador (P3) arma
+`anclas`/`rubros`/`neutros_ids` desde `control.service`, `MesControl` y transacciones.
+"""
+
+from __future__ import annotations
+
+from dataclasses import dataclass, replace
+from decimal import Decimal
+
+from app.proyeccion.ejecucion.lectura import RubroInfo, mapear_a_conceptos
+from app.proyeccion.impactos import ResultadoAjustado, reacumular
+from app.proyeccion.motor import MesProyeccion, ResultadoProyeccion, _cop
+
+_CERO = Decimal("0.00")
+
+# Conceptos de EGRESO que E1 ancla (el resto —adelanto/pago_inventario/fondeo— es del
+# motor / D2). Son los de `mapear_a_conceptos` menos los de Auteco.
+_EGRESOS_ANCLADOS = ("gastos_fijos", "gps", "costo_nueva", "int_deuda", "iva")
+
+# Estados que anclan y con qué regla (los demás → sin ancla → motor intacto).
+CERRADO = "cerrado"
+EN_EJECUCION = "en_ejecucion"
+PRESUPUESTO = "presupuesto"  # futuro con presupuesto definido vigente
+_ANCLABLES = (CERRADO, EN_EJECUCION, PRESUPUESTO)
+
+
+@dataclass(frozen=True)
+class AnclaMes:
+    """Insumos para anclar UN mes del horizonte. `estado` decide la regla (§1).
+
+    - `ejecutado_por_rubro_id`: Σ egresos por rubro del mes (magnitud POSITIVA). Usado
+      por cerrado y en-ejecución.
+    - `definido_por_rubro_id`: presupuesto DEFINIDO vigente por rubro (POSITIVO). Usado
+      por en-ejecución (Regla A) y futuro-con-presupuesto. `{}` si no aplica.
+    - `ingreso_real`: neto recaudado del mes (POSITIVO), SOLO para cerrado (se ancla el
+      ingreso). None en los demás (el ingreso queda del motor).
+    """
+
+    estado: str
+    ejecutado_por_rubro_id: dict[str, Decimal]
+    definido_por_rubro_id: dict[str, Decimal]
+    ingreso_real: Decimal | None
+
+
+def _conceptos_egreso(
+    valor_por_rubro_id: dict[str, Decimal],
+    *,
+    rubros: list[RubroInfo],
+    neutros_ids: set[str],
+) -> dict[str, Decimal]:
+    """Mapea rubro→concepto (reusa P1) y devuelve SOLO los conceptos de egreso que E1
+    ancla, en magnitud POSITIVA. Auteco (`pago_inventario`/`fondeo`) se ignora aquí."""
+    r = mapear_a_conceptos(
+        rubros=rubros, valor_por_rubro_id=valor_por_rubro_id, neutros_ids=neutros_ids
+    )
+    return {c: r.conceptos[c] for c in _EGRESOS_ANCLADOS}
+
+
+def _egresos_anclados_del_mes(
+    ancla: AnclaMes, *, rubros: list[RubroInfo], neutros_ids: set[str]
+) -> dict[str, Decimal]:
+    """Los 5 conceptos de egreso anclados del mes (magnitud POSITIVA), por estado."""
+    if ancla.estado == CERRADO:
+        return _conceptos_egreso(
+            ancla.ejecutado_por_rubro_id, rubros=rubros, neutros_ids=neutros_ids
+        )
+    if ancla.estado == PRESUPUESTO:
+        return _conceptos_egreso(
+            ancla.definido_por_rubro_id, rubros=rubros, neutros_ids=neutros_ids
+        )
+    # EN_EJECUCION → Regla A (D-08) por concepto: ejec + max(0, definido − ejec).
+    ejec = _conceptos_egreso(
+        ancla.ejecutado_por_rubro_id, rubros=rubros, neutros_ids=neutros_ids
+    )
+    defi = _conceptos_egreso(
+        ancla.definido_por_rubro_id, rubros=rubros, neutros_ids=neutros_ids
+    )
+    return {c: ejec[c] + max(_CERO, defi[c] - ejec[c]) for c in _EGRESOS_ANCLADOS}
+
+
+def _fila_anclada(
+    fila: MesProyeccion, ancla: AnclaMes, egr: dict[str, Decimal]
+) -> MesProyeccion:
+    """Fila con los conceptos anclados escritos (egresos NEGATIVOS), el `neto` real si
+    el mes es cerrado, y `egresos`/`flujo` recalculados. Conserva del motor `adelanto`,
+    `pago_inventario`, `fondeo` (Auteco → D2) y los componentes de ingreso."""
+    neto = fila.neto if ancla.ingreso_real is None else _cop(ancla.ingreso_real)
+    gastos_fijos = _cop(-egr["gastos_fijos"])
+    gps = _cop(-egr["gps"])
+    costo_nueva = _cop(-egr["costo_nueva"])
+    int_deuda = _cop(-egr["int_deuda"])
+    iva = _cop(-egr["iva"])
+    egresos = _cop(
+        gastos_fijos
+        + gps
+        + costo_nueva
+        + int_deuda
+        + iva
+        + fila.adelanto
+        + fila.pago_inventario
+        + fila.fondeo
+    )
+    flujo = _cop(neto + egresos)
+    return replace(
+        fila,
+        neto=neto,
+        gastos_fijos=gastos_fijos,
+        gps=gps,
+        costo_nueva=costo_nueva,
+        int_deuda=int_deuda,
+        iva=iva,
+        egresos=egresos,
+        flujo=flujo,
+    )
+
+
+def anclar(
+    *,
+    resultado: ResultadoProyeccion,
+    caja_minima: Decimal,
+    anclas: dict[str, AnclaMes],
+    rubros: list[RubroInfo],
+    neutros_ids: set[str],
+) -> ResultadoAjustado:
+    """Ancla la serie del motor a la ejecución real (§1) y re-acumula la caja. `anclas`
+    mapea 'YYYY-MM'→AnclaMes; los meses fuera del dict quedan intactos (motor). Con
+    `anclas` vacío devuelve la base bit a bit (== golden, B1)."""
+    base = resultado.meses
+    n = len(base)
+    idx = {fila.mes: i for i, fila in enumerate(base)}
+
+    # 1) fila anclada + delta de flujo por mes (solo los anclables del horizonte).
+    ancladas: dict[int, MesProyeccion] = {}
+    deltas = [_CERO] * n
+    for mes, ancla in anclas.items():
+        if mes not in idx or ancla.estado not in _ANCLABLES:
+            continue  # fuera del horizonte o estado no anclable → motor intacto
+        m = idx[mes]
+        egr = _egresos_anclados_del_mes(ancla, rubros=rubros, neutros_ids=neutros_ids)
+        nueva = _fila_anclada(base[m], ancla, egr)
+        ancladas[m] = nueva
+        deltas[m] = _cop(nueva.flujo - base[m].flujo)
+
+    # 2) re-acumular caja/flujo/estado con la mecánica del motor (D2/D1 la comparten).
+    ajustado = reacumular(resultado, deltas, caja_minima)
+
+    # 3) reescribir los campos POR CONCEPTO de los meses anclados (reacumular solo tocó
+    #    flujo/caja/estado). Así `neto + Σ egresos == flujo` al peso en la serie (B6).
+    filas = list(ajustado.meses)
+    for m, nueva in ancladas.items():
+        filas[m] = replace(
+            filas[m],
+            neto=nueva.neto,
+            gastos_fijos=nueva.gastos_fijos,
+            gps=nueva.gps,
+            costo_nueva=nueva.costo_nueva,
+            int_deuda=nueva.int_deuda,
+            iva=nueva.iva,
+            egresos=nueva.egresos,
+        )
+    return replace(ajustado, meses=filas)
diff --git a/backend/tests/fixtures/e1_julio_2026_ejecutado.json b/backend/tests/fixtures/e1_julio_2026_ejecutado.json
new file mode 100644
index 0000000..49f237b
--- /dev/null
+++ b/backend/tests/fixtures/e1_julio_2026_ejecutado.json
@@ -0,0 +1,379 @@
+{
+  "_meta": {
+    "descripcion": "E1 Paso 0 — ejecutado real de julio 2026 (fixture congelado, read-only de PROD)",
+    "mes": "2026-07",
+    "extraccion": "2026-08-06T08:46:40-05:00",
+    "comando": "MONGODB_URI_COMPAS=*** MONGODB_DB=compas PYTHONUTF8=1 python scripts/extract_e1_julio_2026.py",
+    "controles": {
+      "egresos_total": "372200776.84",
+      "ingreso_real": "179710080.31",
+      "egresos_total_esperado": "372200776.84",
+      "ingreso_real_esperado": "179710080.31"
+    }
+  },
+  "rubros": [
+    {
+      "id": "6a5edaaade90904d0daaa3ca",
+      "codigo": "1010",
+      "grupo": "costo_producto",
+      "nombre": "Producto",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaabde90904d0daaa3cb",
+      "codigo": "1020",
+      "grupo": "costo_producto",
+      "nombre": "SOAT/Matrículas",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaabde90904d0daaa3cc",
+      "codigo": "1030",
+      "grupo": "costo_producto",
+      "nombre": "Seguros (Hunter)",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaabde90904d0daaa3cd",
+      "codigo": "2010",
+      "grupo": "operacion",
+      "nombre": "Arriendos",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaabde90904d0daaa3ce",
+      "codigo": "2020",
+      "grupo": "operacion",
+      "nombre": "Tecnología y software",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaabde90904d0daaa3cf",
+      "codigo": "2030",
+      "grupo": "operacion",
+      "nombre": "Mobiliario/planta/equipo",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaabde90904d0daaa3d0",
+      "codigo": "2040",
+      "grupo": "operacion",
+      "nombre": "Servicios públicos y telecom",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaabde90904d0daaa3d1",
+      "codigo": "2050",
+      "grupo": "operacion",
+      "nombre": "Mercado y aseo",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaacde90904d0daaa3d2",
+      "codigo": "2060",
+      "grupo": "operacion",
+      "nombre": "Cafetería",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaacde90904d0daaa3d3",
+      "codigo": "2070",
+      "grupo": "operacion",
+      "nombre": "Transporte/peajes/combustible/parqueo",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaacde90904d0daaa3d4",
+      "codigo": "2080",
+      "grupo": "operacion",
+      "nombre": "Papelería",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaacde90904d0daaa3d5",
+      "codigo": "2090",
+      "grupo": "operacion",
+      "nombre": "Marketing y publicidad",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaacde90904d0daaa3d6",
+      "codigo": "2100",
+      "grupo": "operacion",
+      "nombre": "Gastos de representación",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaacde90904d0daaa3d7",
+      "codigo": "2120",
+      "grupo": "operacion",
+      "nombre": "Renting",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaacde90904d0daaa3d8",
+      "codigo": "3010",
+      "grupo": "nomina",
+      "nombre": "Sueldos empleados",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaacde90904d0daaa3d9",
+      "codigo": "3020",
+      "grupo": "nomina",
+      "nombre": "Sueldos directivos",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaadde90904d0daaa3da",
+      "codigo": "3030",
+      "grupo": "nomina",
+      "nombre": "Bonificaciones",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaadde90904d0daaa3db",
+      "codigo": "3040",
+      "grupo": "nomina",
+      "nombre": "Beneficios Heads",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaadde90904d0daaa3dc",
+      "codigo": "3060",
+      "grupo": "nomina",
+      "nombre": "Planillas nuevas",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaadde90904d0daaa3dd",
+      "codigo": "3070",
+      "grupo": "nomina",
+      "nombre": "Planillas anteriores",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaadde90904d0daaa3de",
+      "codigo": "4010",
+      "grupo": "deudas_obligaciones",
+      "nombre": "Préstamos",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaadde90904d0daaa3df",
+      "codigo": "4020",
+      "grupo": "deudas_obligaciones",
+      "nombre": "Deudas tarjetas de crédito",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaadde90904d0daaa3e0",
+      "codigo": "4030",
+      "grupo": "deudas_obligaciones",
+      "nombre": "Garantía cupo",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaaede90904d0daaa3e1",
+      "codigo": "4040",
+      "grupo": "deudas_obligaciones",
+      "nombre": "Deudas impuestos",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaaede90904d0daaa3e2",
+      "codigo": "4050",
+      "grupo": "deudas_obligaciones",
+      "nombre": "Deudas proveedores anteriores",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaaede90904d0daaa3e3",
+      "codigo": "5010",
+      "grupo": "otros",
+      "nombre": "Otros gastos",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaaede90904d0daaa3e4",
+      "codigo": "5020",
+      "grupo": "otros",
+      "nombre": "Gastos notariales",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaaede90904d0daaa3e5",
+      "codigo": "5040",
+      "grupo": "otros",
+      "nombre": "Gastos bancarios",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaaede90904d0daaa3e6",
+      "codigo": "5050",
+      "grupo": "otros",
+      "nombre": "Gastos financieros",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaaede90904d0daaa3e7",
+      "codigo": "5060",
+      "grupo": "otros",
+      "nombre": "Impuestos",
+      "es_sistema": false
+    },
+    {
+      "id": "6a5edaafde90904d0daaa3e8",
+      "codigo": "5070",
+      "grupo": "otros",
+      "nombre": "Por clasificar",
+      "es_sistema": true
+    },
+    {
+      "id": "6a5edaafde90904d0daaa3e9",
+      "codigo": null,
+      "grupo": "otros",
+      "nombre": "Ajuste de conciliación",
+      "es_sistema": true
+    },
+    {
+      "id": "6a5ee39ade90904d0daaa3ed",
+      "codigo": "0110",
+      "grupo": "ingresos_operativos",
+      "nombre": "Recaudo de cartera",
+      "es_sistema": true
+    },
+    {
+      "id": "6a6165903893bb86c32a205c",
+      "codigo": "2110",
+      "grupo": "operacion",
+      "nombre": "Viajes corporativos",
+      "es_sistema": false
+    },
+    {
+      "id": "6a6165903893bb86c32a205d",
+      "codigo": "2130",
+      "grupo": "operacion",
+      "nombre": "Grúas y traslados",
+      "es_sistema": false
+    },
+    {
+      "id": "6a6165903893bb86c32a205e",
+      "codigo": "3050",
+      "grupo": "nomina",
+      "nombre": "Dotación empleados",
+      "es_sistema": false
+    },
+    {
+      "id": "6a6165903893bb86c32a205f",
+      "codigo": "2140",
+      "grupo": "operacion",
+      "nombre": "Freelance",
+      "es_sistema": false
+    },
+    {
+      "id": "6a6165933893bb86c32a2060",
+      "codigo": "5030",
+      "grupo": "otros",
+      "nombre": "Asuntos legales",
+      "es_sistema": false
+    },
+    {
+      "id": "6a6165933893bb86c32a2061",
+      "codigo": null,
+      "grupo": "otros",
+      "nombre": "Arriendos",
+      "es_sistema": false
+    },
+    {
+      "id": "6a665875dcb531f981a16847",
+      "codigo": null,
+      "grupo": "otros",
+      "nombre": "Aportes de capital",
+      "es_sistema": false
+    },
+    {
+      "id": "6a66b3701f492eb845bb286a",
+      "codigo": "3080",
+      "grupo": "nomina",
+      "nombre": "Parafiscales",
+      "es_sistema": false
+    },
+    {
+      "id": "6a66b3701f492eb845bb286b",
+      "codigo": "2150",
+      "grupo": "operacion",
+      "nombre": "Contingencia",
+      "es_sistema": false
+    },
+    {
+      "id": "6a6fff9a019561c47fef5e3e",
+      "codigo": null,
+      "grupo": "costo_producto",
+      "nombre": "Combustible motos",
+      "es_sistema": false
+    },
+    {
+      "id": "6a6fff9a019561c47fef5e3f",
+      "codigo": null,
+      "grupo": "operacion",
+      "nombre": "Comisiones externas",
+      "es_sistema": false
+    },
+    {
+      "id": "6a7003d312ba5ac9e981a9d5",
+      "codigo": null,
+      "grupo": "otros",
+      "nombre": "Reversas y devoluciones",
+      "es_sistema": false
+    },
+    {
+      "id": "6a71f2ab0d3803ddca891524",
+      "codigo": null,
+      "grupo": "otros",
+      "nombre": "Tránsito Wava mes anterior",
+      "es_sistema": true
+    }
+  ],
+  "egresos_por_rubro_id": {
+    "6a5edaaede90904d0daaa3e4": "3986812.2",
+    "6a5edaabde90904d0daaa3d0": "1206406.68",
+    "6a5edaacde90904d0daaa3d2": "390100",
+    "6a5edaacde90904d0daaa3d9": "37661949.93",
+    "6a5edaadde90904d0daaa3da": "80964900.81",
+    "6a6165903893bb86c32a205f": "350000",
+    "6a5edaabde90904d0daaa3cd": "12628608",
+    "6a5edaabde90904d0daaa3cc": "8250130.33",
+    "6a5edaaede90904d0daaa3e2": "17533399.36",
+    "6a5edaabde90904d0daaa3ce": "5924050.83",
+    "6a5edaabde90904d0daaa3cf": "1071099.3",
+    "6a6fff9a019561c47fef5e3e": "82000",
+    "6a5edaacde90904d0daaa3d3": "2196565.96",
+    "6a5edaadde90904d0daaa3df": "9200000",
+    "6a5edaaede90904d0daaa3e7": "4614018.41",
+    "6a6165933893bb86c32a2060": "2883199.92",
+    "6a5edaacde90904d0daaa3d8": "10556272.12",
+    "6a5edaaede90904d0daaa3e3": "8199245.06",
+    "6a5edaaede90904d0daaa3e5": "74062",
+    "6a5edaaade90904d0daaa3ca": "14503249.06",
+    "6a5edaabde90904d0daaa3cb": "33136677.74",
+    "6a6165903893bb86c32a205d": "599998.66",
+    "6a5edaadde90904d0daaa3dd": "77958400",
+    "6a5edaabde90904d0daaa3d1": "784178",
+    "6a5edaafde90904d0daaa3e8": "288000",
+    "6a5edaadde90904d0daaa3de": "24728783.55",
+    "6a5edaacde90904d0daaa3d5": "203219",
+    "6a5edaacde90904d0daaa3d7": "10799999.92",
+    "6a6165903893bb86c32a205e": "255450",
+    "6a6fff9a019561c47fef5e3f": "1170000"
+  },
+  "ingresos_por_rubro_id": {
+    "6a5ee39ade90904d0daaa3ed": "179710080.31",
+    "6a7003d312ba5ac9e981a9d5": "43410148.73"
+  },
+  "neutros_ids": [
+    "6a5edaafde90904d0daaa3e9",
+    "6a7003d312ba5ac9e981a9d5",
+    "6a71f2ab0d3803ddca891524"
+  ]
+}
\ No newline at end of file
diff --git a/backend/tests/test_e1_anclaje.py b/backend/tests/test_e1_anclaje.py
new file mode 100644
index 0000000..166ac36
--- /dev/null
+++ b/backend/tests/test_e1_anclaje.py
@@ -0,0 +1,272 @@
+# backend/tests/test_e1_anclaje.py
+"""E1 · P2 — capa de anclaje (función pura sobre snapshots).
+
+B1 (sin ancla → base bit a bit) · B2 (cerrado → ejecutado real + re-acumulación) ·
+B3 (Regla A, incl. ejecutado>definido) · B4 (futuro con presupuesto → definido) ·
+B5 (futuro sin presupuesto → motor) · B6 (invariante neto + egresos == flujo al peso) ·
+A3 (fixture real de julio 2026 verificando B2 + B6 sobre la realidad de producción)."""
+
+import json
+from decimal import Decimal
+from pathlib import Path
+
+from app.proyeccion.ejecucion.lectura import RubroInfo, mapear_a_conceptos
+from app.proyeccion.ejecucion.service import (
+    CERRADO,
+    EN_EJECUCION,
+    PRESUPUESTO,
+    AnclaMes,
+    anclar,
+)
+from app.proyeccion.motor import MesProyeccion, ResultadoProyeccion
+
+_CAJA_MIN = Decimal("0.00")
+
+# Plan de cuentas sintético (los 13 códigos del mapeo deben existir → B12 no dispara).
+_PLAN = [
+    ("0110", "ingresos_operativos", "Recaudo de cartera", True),
+    ("0120", "ingresos_operativos", "Cuotas iniciales", False),
+    ("0130", "ingresos_operativos", "RODANTE", False),
+    ("0140", "ingresos_operativos", "Otros ingresos", False),
+    ("1010", "costo_producto", "Producto", False),
+    ("1020", "costo_producto", "SOAT/Matrículas", False),
+    ("1030", "costo_producto", "Seguros (Hunter)", False),
+    ("2010", "operacion", "Arriendos", False),
+    ("3010", "nomina", "Sueldos empleados", False),
+    ("4010", "deudas_obligaciones", "Préstamos", False),
+    ("4020", "deudas_obligaciones", "Tarjetas", False),
+    ("4030", "deudas_obligaciones", "Garantía cupo (Auteco)", False),
+    ("4050", "deudas_obligaciones", "Proveedores", False),
+    ("4060", "deudas_obligaciones", "Inventario Auteco", False),
+    ("5060", "otros", "Impuestos", False),
+]
+
+
+def _rubros():
+    return [
+        RubroInfo(id=cod, codigo=cod, grupo=gr, nombre=nom, es_sistema=sis)
+        for (cod, gr, nom, sis) in _PLAN
+    ]
+
+
+def _mp(
+    mes,
+    *,
+    neto,
+    gastos_fijos=Decimal("0.00"),
+    gps=Decimal("0.00"),
+    costo_nueva=Decimal("0.00"),
+    int_deuda=Decimal("0.00"),
+    iva=Decimal("0.00"),
+    adelanto=Decimal("0.00"),
+    pago_inventario=Decimal("0.00"),
+    fondeo=Decimal("0.00"),
+    caja=Decimal("0.00"),
+):
+    """MesProyeccion con los egresos ya NEGATIVOS. egresos/flujo derivados."""
+    egresos = (
+        gastos_fijos + gps + costo_nueva + int_deuda + iva
+        + adelanto + pago_inventario + fondeo
+    )
+    return MesProyeccion(
+        mes=mes, motos=0, cartera=0, recaudo_credito=Decimal("0.00"),
+        cuotas_iniciales=Decimal("0.00"), ingreso_bruto=neto, neto=neto,
+        provision=Decimal("0.00"), gastos_fijos=gastos_fijos, gps=gps,
+        costo_nueva=costo_nueva, adelanto=adelanto, pago_inventario=pago_inventario,
+        fondeo=fondeo, int_deuda=int_deuda, iva=iva, egresos=egresos,
+        flujo=neto + egresos, caja=caja, estado="ok",
+    )
+
+
+def _resultado(filas: list[MesProyeccion]) -> ResultadoProyeccion:
+    return ResultadoProyeccion(
+        meses=filas, piso_caja=min(f.caja for f in filas),
+        mes_mas_ajustado=filas[0].mes, meses_bajo_minimo=0,
+        caja_final=filas[-1].caja, capital_requerido=Decimal("0.00"), runway_meses=None,
+    )
+
+
+def _serie_coherente(caja_inicial, datos):
+    """Serie con caja re-acumulada como el motor (m0 fija = caja_inicial)."""
+    filas, caja = [], caja_inicial
+    for i, (mes, kw) in enumerate(datos):
+        f = _mp(mes, **kw)
+        caja = caja_inicial if i == 0 else caja + f.flujo
+        filas.append(_mp(mes, caja=caja, **kw))
+    return _resultado(filas)
+
+
+def _invariante_ok(res):
+    """B6: neto + egresos == flujo al peso en TODA la serie."""
+    return all(f.neto + f.egresos == f.flujo for f in res.meses)
+
+
+# ─────────────────────────────── B1 ───────────────────────────────
+def test_b1_sin_ancla_es_base_bit_a_bit():
+    res = _serie_coherente(
+        Decimal("1000000.00"),
+        [
+            ("2026-08", {"neto": Decimal("500000.00"),
+                         "gastos_fijos": Decimal("-200000.00")}),
+            ("2026-09", {"neto": Decimal("400000.00"),
+                         "gastos_fijos": Decimal("-150000.00")}),
+            ("2026-10", {"neto": Decimal("600000.00"),
+                         "gastos_fijos": Decimal("-100000.00")}),
+        ],
+    )
+    out = anclar(resultado=res, caja_minima=_CAJA_MIN, anclas={},
+                 rubros=_rubros(), neutros_ids=set())
+    assert out.meses == res.meses  # idéntico, bit a bit
+    assert _invariante_ok(out)
+
+
+# ─────────────────────────────── B2 ───────────────────────────────
+def test_b2_cerrado_ejecutado_real_y_reacumula():
+    # Base: ago(caja 1.000.000 fija) · sep(flujo 250.000→caja 1.250.000) ·
+    # oct(flujo 500.000→caja 1.750.000).
+    res = _serie_coherente(
+        Decimal("1000000.00"),
+        [
+            ("2026-08", {"neto": Decimal("500000.00"),
+                         "gastos_fijos": Decimal("-200000.00")}),
+            ("2026-09", {"neto": Decimal("400000.00"),
+                         "gastos_fijos": Decimal("-150000.00")}),
+            ("2026-10", {"neto": Decimal("600000.00"),
+                         "gastos_fijos": Decimal("-100000.00")}),
+        ],
+    )
+    # sep (m1) cerrado: gasto real = Arriendos 350.000, ingreso real 300.000. Ancla en
+    # m>0 para ver la re-acumulación de los meses SIGUIENTES.
+    ancla = AnclaMes(estado=CERRADO,
+                     ejecutado_por_rubro_id={"2010": Decimal("350000")},
+                     definido_por_rubro_id={}, ingreso_real=Decimal("300000"))
+    out = anclar(resultado=res, caja_minima=_CAJA_MIN, anclas={"2026-09": ancla},
+                 rubros=_rubros(), neutros_ids=set())
+    sep = out.meses[1]
+    assert sep.neto == Decimal("300000.00")           # ingreso real
+    assert sep.gastos_fijos == Decimal("-350000.00")  # ejecutado real (negativo)
+    assert sep.flujo == Decimal("-50000.00")          # 300000 - 350000
+    # ago (m0) intacto; sep y oct re-acumulados desde el nuevo flujo de sep.
+    assert out.meses[0].caja == Decimal("1000000.00")  # m0 fija
+    assert sep.caja == Decimal("950000.00")            # 1.000.000 + (-50.000)
+    assert out.meses[2].caja == Decimal("1450000.00")  # 950.000 + flujo_oct 500.000
+    assert _invariante_ok(out)
+
+
+# ─────────────────────────────── B3 ───────────────────────────────
+def test_b3_regla_a_incluye_ejecutado_mayor_que_definido():
+    res = _serie_coherente(
+        Decimal("1000000.00"),
+        [
+            ("2026-08", {"neto": Decimal("500000.00"),
+                         "gastos_fijos": Decimal("-100000.00"),
+                         "gps": Decimal("-50000.00")}),
+        ],
+    )
+    # en ejecución: gastos_fijos ejec 300.000 > definido 200.000 → vale el ejecutado;
+    # gps ejec 10.000 < definido 40.000 → vale el definido. Regla A por concepto.
+    ancla = AnclaMes(
+        estado=EN_EJECUCION,
+        ejecutado_por_rubro_id={"2010": Decimal("300000"), "1030": Decimal("10000")},
+        definido_por_rubro_id={"2010": Decimal("200000"), "1030": Decimal("40000")},
+        ingreso_real=None,  # el ingreso NO se ancla en ejecución
+    )
+    out = anclar(resultado=res, caja_minima=_CAJA_MIN, anclas={"2026-08": ancla},
+                 rubros=_rubros(), neutros_ids=set())
+    ago = out.meses[0]
+    assert ago.gastos_fijos == Decimal("-300000.00")  # max(ejec, definido) = ejec
+    assert ago.gps == Decimal("-40000.00")            # max(ejec, definido) = definido
+    assert ago.neto == Decimal("500000.00")           # sin anclar (motor)
+    assert _invariante_ok(out)
+
+
+# ─────────────────────────────── B4 ───────────────────────────────
+def test_b4_futuro_con_presupuesto_usa_definido():
+    res = _serie_coherente(
+        Decimal("1000000.00"),
+        [
+            ("2026-11", {"neto": Decimal("500000.00"),
+                         "gastos_fijos": Decimal("-999999.00")}),
+        ],
+    )
+    ancla = AnclaMes(estado=PRESUPUESTO, ejecutado_por_rubro_id={},
+                     definido_por_rubro_id={"2010": Decimal("250000")},
+                     ingreso_real=None)
+    out = anclar(resultado=res, caja_minima=_CAJA_MIN, anclas={"2026-11": ancla},
+                 rubros=_rubros(), neutros_ids=set())
+    assert out.meses[0].gastos_fijos == Decimal("-250000.00")  # definido, no el motor
+    assert out.meses[0].neto == Decimal("500000.00")           # ingreso del motor
+    assert _invariante_ok(out)
+
+
+# ─────────────────────────────── B5 ───────────────────────────────
+def test_b5_futuro_sin_presupuesto_es_el_motor():
+    res = _serie_coherente(
+        Decimal("1000000.00"),
+        [
+            ("2026-08", {"neto": Decimal("500000.00"),
+                         "gastos_fijos": Decimal("-200000.00")}),
+            ("2026-12", {"neto": Decimal("400000.00"),
+                         "gastos_fijos": Decimal("-123456.00")}),
+        ],
+    )
+    # solo ago anclado; dic NO está en anclas → queda intacto (motor).
+    ancla = AnclaMes(estado=CERRADO,
+                     ejecutado_por_rubro_id={"2010": Decimal("200000")},
+                     definido_por_rubro_id={}, ingreso_real=Decimal("500000"))
+    out = anclar(resultado=res, caja_minima=_CAJA_MIN, anclas={"2026-08": ancla},
+                 rubros=_rubros(), neutros_ids=set())
+    assert out.meses[1].gastos_fijos == Decimal("-123456.00")  # dic intacto
+    assert _invariante_ok(out)
+
+
+# ─────────────────────────────── B6 + A3 ───────────────────────────────
+def test_a3_fixture_julio_real_b2_y_b6():
+    fx = json.loads(
+        (Path(__file__).resolve().parent / "fixtures"
+         / "e1_julio_2026_ejecutado.json").read_text(encoding="utf-8")
+    )
+    rubros = [
+        RubroInfo(id=r["id"], codigo=r["codigo"], grupo=r["grupo"],
+                  nombre=r["nombre"], es_sistema=r["es_sistema"])
+        for r in fx["rubros"]
+    ]
+    ejecutado = {k: Decimal(v) for k, v in fx["egresos_por_rubro_id"].items()}
+    neutros = set(fx["neutros_ids"])
+    ingreso_real = Decimal(fx["_meta"]["controles"]["ingreso_real"])
+
+    # oráculo: el mapeo P1 (ya auditado) sobre el ejecutado real de julio.
+    esperado = mapear_a_conceptos(
+        rubros=rubros, valor_por_rubro_id=ejecutado, neutros_ids=neutros
+    )
+
+    # serie sintética con julio; el motor trae pago_inventario/fondeo (Auteco) que E1
+    # debe CONSERVAR.
+    res = _serie_coherente(
+        Decimal("800000000.00"),
+        [
+            ("2026-07", {"neto": Decimal("111111.00"),
+                         "gastos_fijos": Decimal("-1.00"),
+                         "pago_inventario": Decimal("-5000000.00"),
+                         "fondeo": Decimal("-80000.00")}),
+        ],
+    )
+    ancla = AnclaMes(estado=CERRADO, ejecutado_por_rubro_id=ejecutado,
+                     definido_por_rubro_id={}, ingreso_real=ingreso_real)
+    out = anclar(resultado=res, caja_minima=_CAJA_MIN, anclas={"2026-07": ancla},
+                 rubros=rubros, neutros_ids=neutros)
+    jul = out.meses[0]
+
+    # B2: ingreso real + ejecutado real al peso (los 5 conceptos E1).
+    assert jul.neto == ingreso_real  # 179.710.080,31
+    assert jul.gastos_fijos == -esperado.conceptos["gastos_fijos"]
+    assert jul.gps == -esperado.conceptos["gps"]
+    assert jul.costo_nueva == -esperado.conceptos["costo_nueva"]
+    assert jul.int_deuda == -esperado.conceptos["int_deuda"]
+    assert jul.iva == -esperado.conceptos["iva"]
+    # Auteco conservado del motor (E1 NO lo toca).
+    assert jul.pago_inventario == Decimal("-5000000.00")
+    assert jul.fondeo == Decimal("-80000.00")
+    # B6: invariante al peso sobre la realidad.
+    assert jul.neto + jul.egresos == jul.flujo
+    assert _invariante_ok(out)
diff --git a/backend/tests/test_e1_extract_julio.py b/backend/tests/test_e1_extract_julio.py
new file mode 100644
index 0000000..4b678b0
--- /dev/null
+++ b/backend/tests/test_e1_extract_julio.py
@@ -0,0 +1,82 @@
+# backend/tests/test_e1_extract_julio.py
+"""E1 · Paso 0 — test de la lógica PURA del extractor del fixture de julio.
+
+Hermético: NO toca Mongo ni PROD. Verifica los controles de calidad fail-loud (regla 7)
+y el ensamblado del fixture (montos string, ingreso_real excluye neutros, cabecera con
+los totales de control). La extracción viva (Mongo) se prueba corriendo el script contra
+PROD con los dos controles al peso, no aquí."""
+
+import importlib.util
+from decimal import Decimal
+from pathlib import Path
+
+import pytest
+
+_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "extract_e1_julio_2026.py"
+
+
+def _cargar():
+    spec = importlib.util.spec_from_file_location("extract_e1_julio_2026", _SCRIPT)
+    mod = importlib.util.module_from_spec(spec)
+    spec.loader.exec_module(mod)
+    return mod
+
+
+m = _cargar()
+
+
+def test_verificar_controles_pasa_al_peso():
+    # Los valores exactos del CEO no lanzan.
+    m.verificar_controles(m.CTRL_EGRESOS, m.CTRL_INGRESO_REAL)
+
+
+def test_verificar_controles_falla_ruidoso_si_no_cuadra():
+    with pytest.raises(SystemExit, match="regla 7"):
+        m.verificar_controles(m.CTRL_EGRESOS + Decimal("0.01"), m.CTRL_INGRESO_REAL)
+    with pytest.raises(SystemExit, match="regla 7"):
+        m.verificar_controles(m.CTRL_EGRESOS, m.CTRL_INGRESO_REAL - Decimal("1"))
+
+
+def test_construir_fixture_shape_y_montos_string():
+    rubros = [
+        {"id": "a", "codigo": "0110", "grupo": "ingresos_operativos",
+         "nombre": "Recaudo de cartera", "es_sistema": True},
+        {"id": "b", "codigo": "1010", "grupo": "costo_producto",
+         "nombre": "Producto", "es_sistema": False},
+    ]
+    egresos = {"b": Decimal("100.00")}
+    ingresos = {"a": Decimal("50.00")}
+    fx = m.construir_fixture(
+        rubros=rubros, egresos=egresos, ingresos=ingresos,
+        neutros_ids=set(), extraccion_iso="2026-08-05T00:00:00-05:00",
+        comando="python scripts/extract_e1_julio_2026.py",
+    )
+    # cabecera y controles
+    assert fx["_meta"]["mes"] == "2026-07"
+    assert fx["_meta"]["controles"]["egresos_total"] == "100.00"
+    assert fx["_meta"]["controles"]["ingreso_real"] == "50.00"
+    # montos como string (regla 1), nunca float
+    assert fx["egresos_por_rubro_id"] == {"b": "100.00"}
+    assert fx["ingresos_por_rubro_id"] == {"a": "50.00"}
+    assert isinstance(fx["egresos_por_rubro_id"]["b"], str)
+    assert fx["rubros"] == rubros
+
+
+def test_construir_fixture_ingreso_real_excluye_neutros():
+    # 'rev' es neutro (grupo otros, NO sistema): NO debe entrar al ingreso_real.
+    rubros = [
+        {"id": "cuo", "codigo": "0120", "grupo": "ingresos_operativos",
+         "nombre": "Cuotas iniciales", "es_sistema": False},
+        {"id": "rev", "codigo": None, "grupo": "otros",
+         "nombre": "Reversas y devoluciones", "es_sistema": False},
+    ]
+    ingresos = {"cuo": Decimal("30000"), "rev": Decimal("9999")}
+    fx = m.construir_fixture(
+        rubros=rubros, egresos={}, ingresos=ingresos, neutros_ids={"rev"},
+        extraccion_iso="2026-08-05T00:00:00-05:00", comando="cmd",
+    )
+    # ingreso_real excluye 'rev'
+    assert fx["_meta"]["controles"]["ingreso_real"] == "30000"
+    # pero los ingresos crudos por rubro SÍ conservan 'rev' (transparencia)
+    assert fx["ingresos_por_rubro_id"]["rev"] == "9999"
+    assert fx["neutros_ids"] == ["rev"]
diff --git a/backend/tests/test_e1_lectura.py b/backend/tests/test_e1_lectura.py
index adaceac..302cae2 100644
--- a/backend/tests/test_e1_lectura.py
+++ b/backend/tests/test_e1_lectura.py
@@ -64,10 +64,9 @@ def test_b9_suma_rubros_igual_concepto():
     rubros = _rubros()
     valores = _valores(
         **{
-            "Cuotas iniciales": "10000",
-            "Otros ingresos": "5000",
-            "Producto": "70000",  # → pago_inventario
-            "Inventario Auteco (150 días)": "30000",  # → pago_inventario
+            "Recaudo de cartera": "15000",  # 0110 → neto (único ingreso real; el resto
+            #                                  de rubros de ingreso no existe en PROD)
+            "Producto": "70000",  # → pago_inventario (1010 entero)
             "Garantía cupo (Auteco)": "1600",  # → fondeo
             "SOAT/Matrículas": "2000",  # → costo_nueva
             "Seguros (Hunter)": "800",  # → gps
@@ -83,8 +82,8 @@ def test_b9_suma_rubros_igual_concepto():
     )
     r = mapear_a_conceptos(rubros=rubros, valor_por_rubro_id=valores, neutros_ids=set())
     c = r.conceptos
-    assert c["neto"] == Decimal("15000")  # 10000 + 5000
-    assert c["pago_inventario"] == Decimal("100000")  # 70000 + 30000
+    assert c["neto"] == Decimal("15000")  # 0110 Recaudo
+    assert c["pago_inventario"] == Decimal("70000")  # 1010 entero (4060 ya no mapea)
     assert c["fondeo"] == Decimal("1600")
     assert c["costo_nueva"] == Decimal("2000")
     assert c["gps"] == Decimal("800")
@@ -135,7 +134,7 @@ def test_a1_neutros_excluidos_por_id():
 
 
 def test_b12_codigo_del_mapeo_ausente_es_ruidoso():
-    # Quitar 4060 de la taxonomía → el mapeo lo referencia → error ruidoso.
-    rubros = [r for r in _rubros() if r.codigo != "4060"]
+    # Quitar 1010 de la taxonomía → el mapeo lo referencia → error ruidoso.
+    rubros = [r for r in _rubros() if r.codigo != "1010"]
     with pytest.raises(ValueError, match="B12"):
         mapear_a_conceptos(rubros=rubros, valor_por_rubro_id={}, neutros_ids=set())
diff --git a/scripts/extract_e1_julio_2026.py b/scripts/extract_e1_julio_2026.py
new file mode 100644
index 0000000..b807cd5
--- /dev/null
+++ b/scripts/extract_e1_julio_2026.py
@@ -0,0 +1,181 @@
+# -*- coding: utf-8 -*-
+"""E1 · Paso 0 — extracción READ-ONLY del ejecutado real de julio 2026 a un fixture congelado.
+
+Vuelca de PROD (solo lecturas, cero escrituras) a
+`backend/tests/fixtures/e1_julio_2026_ejecutado.json`:
+  - egresos por rubro_id   (Σ EGRESO del mes; reusa control._egresos_por_rubro)
+  - ingresos por rubro_id  (Σ INGRESO del mes; espeja la misma agregación)
+  - snapshot de rubros      (id, codigo, grupo, nombre, es_sistema) para armar RubroInfo
+  - ids de los rubros neutros
+
+Controles de calidad FAIL-LOUD (regla 7), ANTES de escribir el JSON:
+  - Σ egresos == 372.200.786,62   (Ejecutado real de julio — Control del CEO)
+  - ingreso_real (Σ INGRESO excluyendo neutros por id) == 179.710.080,31  (FIX-B)
+Si algo no cuadra: SystemExit y NO se escribe nada.
+
+Uso (PROD, read-only):
+  MONGODB_URI_COMPAS=... MONGODB_DB=compas PYTHONUTF8=1 \
+      python scripts/extract_e1_julio_2026.py
+
+El test A3 (P2) lee el JSON congelado — hermético, nunca toca PROD.
+Los imports de `app`/Mongo son perezosos (dentro de la extracción) para que la lógica
+pura sea testeable sin Mongo.
+"""
+from __future__ import annotations
+
+import asyncio
+import json
+import os
+import sys
+from decimal import Decimal
+from pathlib import Path
+
+MES = "2026-07"
+MES_ID_STR = "2026-07-01"
+# Ejecutado real del libro (Σ egresos de las 505 tx de julio en PROD), verificado por 2
+# métodos. El Control del CEO traía 372.200.786,62 (de su Excel Flujo de pagos deudas.xlsx);
+# la diferencia de $9,78 no cae en ningún rubro (ruido de centavos del Excel). Decisión CEO
+# 2026-08-06: la verdad es Mongo — E1 ancla las transacciones reales, no el Excel. El
+# ingreso_real cuadra al peso exacto, lo que confirma que la data de julio está bien.
+CTRL_EGRESOS = Decimal("372200776.84")
+CTRL_INGRESO_REAL = Decimal("179710080.31")
+FIXTURE_PATH = Path("backend/tests/fixtures/e1_julio_2026_ejecutado.json")
+COMANDO = "MONGODB_URI_COMPAS=*** MONGODB_DB=compas PYTHONUTF8=1 python scripts/extract_e1_julio_2026.py"
+
+
+# ─────────────────────────── lógica pura (testeable sin Mongo) ───────────────────────────
+def verificar_controles(egresos_total: Decimal, ingreso_real_val: Decimal) -> None:
+    """Regla 7: los dos totales de control deben cuadrar al peso o se aborta (sin escribir)."""
+    errores: list[str] = []
+    if egresos_total != CTRL_EGRESOS:
+        errores.append(
+            f"Sigma egresos = {egresos_total} != control {CTRL_EGRESOS} "
+            f"(dif {egresos_total - CTRL_EGRESOS})"
+        )
+    if ingreso_real_val != CTRL_INGRESO_REAL:
+        errores.append(
+            f"ingreso_real = {ingreso_real_val} != control {CTRL_INGRESO_REAL} "
+            f"(dif {ingreso_real_val - CTRL_INGRESO_REAL})"
+        )
+    if errores:
+        raise SystemExit("[FALLA regla 7] no se escribe nada:\n  - " + "\n  - ".join(errores))
+
+
+def construir_fixture(
+    *,
+    rubros: list[dict],
+    egresos: dict[str, Decimal],
+    ingresos: dict[str, Decimal],
+    neutros_ids: set[str],
+    extraccion_iso: str,
+    comando: str,
+) -> dict:
+    """Ensambla el fixture. Montos como string (regla 1). Puro: no toca Mongo."""
+    egresos_total = sum(egresos.values(), Decimal("0"))
+    ingreso_real_val = sum(
+        (v for rid, v in ingresos.items() if rid not in neutros_ids), Decimal("0")
+    )
+    return {
+        "_meta": {
+            "descripcion": "E1 Paso 0 — ejecutado real de julio 2026 (fixture congelado, read-only de PROD)",
+            "mes": MES,
+            "extraccion": extraccion_iso,
+            "comando": comando,
+            "controles": {
+                "egresos_total": str(egresos_total),
+                "ingreso_real": str(ingreso_real_val),
+                "egresos_total_esperado": str(CTRL_EGRESOS),
+                "ingreso_real_esperado": str(CTRL_INGRESO_REAL),
+            },
+        },
+        "rubros": rubros,
+        "egresos_por_rubro_id": {k: str(v) for k, v in egresos.items()},
+        "ingresos_por_rubro_id": {k: str(v) for k, v in ingresos.items()},
+        "neutros_ids": sorted(neutros_ids),
+    }
+
+
+# ─────────────────────────── extracción viva (Mongo, read-only) ───────────────────────────
+async def _ingresos_por_rubro(mes_id) -> dict[str, Decimal]:
+    """Espejo de control._egresos_por_rubro pero para INGRESO (misma agregación $group)."""
+    from bson.decimal128 import Decimal128
+    from app.domain.rubro import TipoFlujo
+    from app.domain.transaccion import Transaccion
+
+    col = Transaccion.get_pymongo_collection()
+    pipeline = [
+        {"$match": {"mes_id": mes_id, "tipo_flujo": TipoFlujo.INGRESO.value}},
+        {"$group": {"_id": "$rubro_id", "total": {"$sum": "$valor"}}},
+    ]
+    out: dict[str, Decimal] = {}
+    async for d in col.aggregate(pipeline):
+        t = d["total"]
+        out[str(d["_id"])] = t.to_decimal() if isinstance(t, Decimal128) else Decimal(str(t))
+    return out
+
+
+async def _extraer(uri: str, db: str) -> tuple[list[dict], dict[str, Decimal], dict[str, Decimal], set[str]]:
+    """Conecta a PROD (solo lecturas) y devuelve rubros/egresos/ingresos/neutros."""
+    sys.path.insert(0, "backend")
+    from app.control.service import _egresos_por_rubro  # noqa: E402
+    from app.db import mongo  # noqa: E402
+    from app.domain.mes_control import MesControl  # noqa: E402
+    from app.domain.rubro import Rubro  # noqa: E402
+    from app.metas_ingreso.service import _ids_rubros_neutros  # noqa: E402
+
+    client = mongo.create_client(uri)
+    await mongo.init_beanie_for(client, db)
+
+    mc = await MesControl.find_one(MesControl.mes == MES_ID_STR)
+    if mc is None:
+        raise SystemExit(f"[FALLA] no existe MesControl {MES_ID_STR} en la base '{db}'.")
+
+    egresos = await _egresos_por_rubro(mc.id)
+    ingresos = await _ingresos_por_rubro(mc.id)
+    rubros = [
+        {
+            "id": str(r.id),
+            "codigo": r.codigo,
+            "grupo": r.grupo.value,
+            "nombre": r.nombre,
+            "es_sistema": r.es_sistema,
+        }
+        for r in await Rubro.find_all().to_list()
+    ]
+    neutros = {str(i) for i in await _ids_rubros_neutros()}
+    return rubros, egresos, ingresos, neutros
+
+
+def main() -> None:
+    uri = os.environ.get("MONGODB_URI_COMPAS")
+    if not uri:
+        raise SystemExit("[FALLA] falta la variable de entorno MONGODB_URI_COMPAS (read-only).")
+    db = os.environ.get("MONGODB_DB", "compas")
+
+    rubros, egresos, ingresos, neutros = asyncio.run(_extraer(uri, db))
+
+    egresos_total = sum(egresos.values(), Decimal("0"))
+    ingreso_real_val = sum((v for rid, v in ingresos.items() if rid not in neutros), Decimal("0"))
+    verificar_controles(egresos_total, ingreso_real_val)  # aborta si no cuadra (regla 7)
+
+    from datetime import datetime, timezone  # local: no lo necesita el test puro
+
+    extraccion_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
+    fixture = construir_fixture(
+        rubros=rubros,
+        egresos=egresos,
+        ingresos=ingresos,
+        neutros_ids=neutros,
+        extraccion_iso=extraccion_iso,
+        comando=COMANDO,
+    )
+    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
+    FIXTURE_PATH.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
+    print(f"[OK] fixture escrito: {FIXTURE_PATH}")
+    print(f"     Sigma egresos     = {egresos_total}  (control {CTRL_EGRESOS})")
+    print(f"     ingreso_real      = {ingreso_real_val}  (control {CTRL_INGRESO_REAL})")
+    print(f"     rubros: {len(rubros)} · egresos: {len(egresos)} · ingresos: {len(ingresos)} · neutros: {len(neutros)}")
+
+
+if __name__ == "__main__":
+    main()

```
