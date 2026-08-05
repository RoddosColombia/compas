# EVIDENCIA — E1 PR1-I: lector de la ejecución real → conceptos del motor

**Commit:** `911bea2` · **Rama:** `feat/e1-p1-lectura-ejecucion` · **Fecha:** 2026-08-05

## 1. Salida de tests (real)

```
$ python -m pytest backend/tests/test_e1_lectura.py -v
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.3, pluggy-1.6.0
rootdir: .../COMPAS/backend
configfile: pyproject.toml
plugins: anyio-4.12.1, asyncio-1.3.0, cov-7.1.0
collected 5 items

test_e1_lectura.py::test_b9_suma_rubros_igual_concepto PASSED            [ 20%]
test_e1_lectura.py::test_r1_1010_entero_a_pago_inventario_no_costo_nueva PASSED [ 40%]
test_e1_lectura.py::test_r2_4040_en_sin_mapear PASSED                     [ 60%]
test_e1_lectura.py::test_a1_neutros_excluidos_por_id PASSED              [ 80%]
test_e1_lectura.py::test_b12_codigo_del_mapeo_ausente_es_ruidoso PASSED  [100%]

============================== 5 passed in 0.07s ==============================
```

## 2. Lint (real)

```
$ python -m ruff check backend/app/proyeccion/ejecucion/ backend/app/domain/rubros_neutros.py backend/tests/test_e1_lectura.py
All checks passed!
```

## 3. Diff completo del commit 911bea2 (real, `git show`)

```diff
diff --git a/backend/app/domain/rubros_neutros.py b/backend/app/domain/rubros_neutros.py
new file mode 100644
index 0000000..1c4a92e
--- /dev/null
+++ b/backend/app/domain/rubros_neutros.py
@@ -0,0 +1,23 @@
+# backend/app/domain/rubros_neutros.py
+"""Rubros NEUTROS para la lectura de la realidad (una verdad, un lugar).
+
+Dinero que entró/salió de la cuenta pero NO es recaudo ni gasto operativo: contarlo
+inflaría el ingreso real (metas) o el ejecutado anclado (E1). La exclusión se resuelve
+SIEMPRE por `rubro_id` (nunca por grupo ni `es_sistema`): el id es la identidad estable;
+el nombre puede cambiar y grupo/es_sistema barren de más.
+
+El set:
+  • 'Reversas y devoluciones'    — FIX-B: reversas GMF, devoluciones, reembolsos.
+  • 'Tránsito Wava mes anterior' — CR-WAVA: depósito Wava del mes previo que llega.
+  • 'Ajuste de conciliación'     — CR-WAVA: contra-asiento de una reapertura de cierre.
+
+Promovido desde `metas_ingreso.service` (donde nació con FIX-B) para que E1 y metas
+compartan exactamente el mismo conjunto — no dos copias que puedan divergir."""
+
+RUBROS_NEUTROS_INGRESO_REAL: frozenset[str] = frozenset(
+    {
+        "Reversas y devoluciones",
+        "Tránsito Wava mes anterior",
+        "Ajuste de conciliación",
+    }
+)
diff --git a/backend/app/metas_ingreso/service.py b/backend/app/metas_ingreso/service.py
index 06d0d39..a61121d 100644
--- a/backend/app/metas_ingreso/service.py
+++ b/backend/app/metas_ingreso/service.py
@@ -17,21 +17,13 @@ from app.core.time import now_bogota
 from app.domain.mes_control import MesControl
 from app.domain.obligacion import LineaMeta, MetaIngreso
 from app.domain.rubro import Rubro
-from app.domain.transaccion import TipoFlujo, Transaccion
 
-# Rubros "neutros" para el ingreso real: dinero que entró a la cuenta pero NO es
-# recaudo operativo. Contarlos inflaría el cumplimiento de la meta. Exclusión por
-# rubro_id (nunca por grupo ni por es_sistema). El set:
-#   • 'Reversas y devoluciones'    — FIX-B: reversas GMF, devoluciones, reembolsos.
-#   • 'Tránsito Wava mes anterior' — CR-WAVA: depósito Wava del mes previo que llega.
-#   • 'Ajuste de conciliación'     — CR-WAVA: contra-asiento INGRESO de una reapertura.
-RUBROS_NEUTROS_INGRESO_REAL: frozenset[str] = frozenset(
-    {
-        "Reversas y devoluciones",
-        "Tránsito Wava mes anterior",
-        "Ajuste de conciliación",
-    }
+# El set de neutros vive en `app.domain.rubros_neutros` (E1 lo comparte — una verdad,
+# un lugar); se re-exporta aquí para no romper los importadores existentes.
+from app.domain.rubros_neutros import (
+    RUBROS_NEUTROS_INGRESO_REAL as RUBROS_NEUTROS_INGRESO_REAL,
 )
+from app.domain.transaccion import TipoFlujo, Transaccion
 
 
 class MetasError(Exception):
diff --git a/backend/app/proyeccion/ejecucion/__init__.py b/backend/app/proyeccion/ejecucion/__init__.py
new file mode 100644
index 0000000..92f634d
--- /dev/null
+++ b/backend/app/proyeccion/ejecucion/__init__.py
@@ -0,0 +1,7 @@
+# backend/app/proyeccion/ejecucion/__init__.py
+"""Capa E1 — anclaje de la proyección a la ejecución real (tercera capa post-motor).
+
+Orden de aplicación: motor → EJECUCIÓN (E1) → OBLIGACIONES (D2) → IMPACTOS (D1).
+E1 reemplaza las líneas de gasto/costo/ingreso de los meses cerrado / en-ejecución /
+futuro-con-presupuesto con la mejor fuente disponible, y re-acumula la caja desde ahí.
+`motor.py` cero diffs (R0)."""
diff --git a/backend/app/proyeccion/ejecucion/lectura.py b/backend/app/proyeccion/ejecucion/lectura.py
new file mode 100644
index 0000000..a776a33
--- /dev/null
+++ b/backend/app/proyeccion/ejecucion/lectura.py
@@ -0,0 +1,132 @@
+# backend/app/proyeccion/ejecucion/lectura.py
+"""E1 · P1 — lectura de la ejecución real mapeada a los conceptos del motor.
+
+Traduce el ejecutado por rubro (la verdad del libro) a los conceptos que el motor
+proyecta, usando el mapeo del Plan de Cuentas (I-PLAN §10, decisiones del CEO):
+
+    neto (ingreso)   ← 0110 Recaudo · 0120 Cuotas iniciales · 0130 RODANTE · 0140 Otros
+    pago_inventario  ← 1010 Producto + 4060 Inventario Auteco (150d)   [coexisten, R-1]
+    fondeo           ← 4030 Garantía cupo (Auteco)          [REEMPLAZA el paramétrico]
+    costo_nueva      ← 1020 SOAT/Matrículas                 [R-1: 1010 no entra aquí]
+    gps              ← 1030 Seguros (Hunter)
+    gastos_fijos     ← TODO OPERACIÓN + NÓMINA + OTROS (menos 5060 y menos sistema)
+    int_deuda        ← 4010 Préstamos · 4020 Tarjetas · 4050 Proveedores
+    iva              ← 5060 Impuestos
+
+FUNCIÓN PURA (sin Mongo): recibe el snapshot de rubros + el valor ejecutado por
+rubro_id + los ids de los rubros neutros, y devuelve {concepto: Decimal} + sin_mapear.
+Nada se adivina:
+  • los 3 NEUTROS se excluyen por rubro_id (A1) — antes que cualquier regla de grupo;
+  • R-1 (1010→pago_inventario entero) y R-2 (4040 sin concepto) quedan documentados:
+    4040 sale en `sin_mapear`, no se suma a nada;
+  • si un código del mapeo NO existe en la taxonomía → error ruidoso (B12).
+
+E1 NO decide temporalidad aquí: esta capa solo MAPEA. Qué meses se anclan y con qué
+regla (cerrado/en-ejecución/futuro) es P2. Auteco: para meses cerrados el pago real ES
+parte del ejecutado (1010+4060, 4030) y E1 lo refleja; el Auteco FUTURO lo posee D2 —
+la precedencia (P3) evita el doble conteo.
+"""
+
+from __future__ import annotations
+
+from dataclasses import dataclass
+from decimal import Decimal
+
+_CERO = Decimal("0.00")
+
+# Conceptos del motor que E1 puede anclar (Auteco incluido para meses cerrados).
+CONCEPTOS = (
+    "neto",
+    "pago_inventario",
+    "fondeo",
+    "costo_nueva",
+    "gps",
+    "gastos_fijos",
+    "int_deuda",
+    "iva",
+)
+
+# Mapeo explícito por código (los específicos del §10).
+_CONCEPTO_POR_CODIGO: dict[str, str] = {
+    "0110": "neto",
+    "0120": "neto",
+    "0130": "neto",
+    "0140": "neto",
+    "1010": "pago_inventario",  # R-1: entero a pago_inventario
+    "4060": "pago_inventario",
+    "4030": "fondeo",
+    "1020": "costo_nueva",
+    "1030": "gps",
+    "4010": "int_deuda",
+    "4020": "int_deuda",
+    "4050": "int_deuda",
+    "5060": "iva",
+}
+
+# `gastos_fijos` = todo lo de estos grupos que no esté ya mapeado por código, no sea de
+# sistema y no sea neutro. Robusto a que la taxonomía sume rubros nuevos (2130, 2140…).
+_GRUPOS_GASTOS_FIJOS = frozenset({"operacion", "nomina", "otros"})
+
+
+@dataclass(frozen=True)
+class RubroInfo:
+    """Lo mínimo del rubro para mapear (snapshot, sin Mongo)."""
+
+    id: str
+    codigo: str | None
+    grupo: str
+    nombre: str
+    es_sistema: bool
+
+
+@dataclass(frozen=True)
+class ResultadoMapeo:
+    conceptos: dict[str, Decimal]  # {concepto: Σ valor}
+    sin_mapear: list[str]  # nombres de rubros con valor y sin concepto (se reportan)
+
+
+def _concepto_de(rubro: RubroInfo) -> str | None:
+    """El concepto de un rubro, o None si no mapea. NO aplica la exclusión de neutros
+    (eso lo hace el llamador ANTES, por id)."""
+    if rubro.codigo is not None and rubro.codigo in _CONCEPTO_POR_CODIGO:
+        return _CONCEPTO_POR_CODIGO[rubro.codigo]
+    if rubro.grupo in _GRUPOS_GASTOS_FIJOS and not rubro.es_sistema:
+        return "gastos_fijos"
+    return None
+
+
+def mapear_a_conceptos(
+    *,
+    rubros: list[RubroInfo],
+    valor_por_rubro_id: dict[str, Decimal],
+    neutros_ids: set[str],
+) -> ResultadoMapeo:
+    """Suma el ejecutado por concepto del motor. `valor_por_rubro_id` es la magnitud
+    ejecutada por rubro (Σ egresos para egresos; Σ ingresos para los rubros de ingreso;
+    lo arma el llamador P2). Excluye los neutros por id ANTES de mapear (A1). Verifica
+    que todo código del mapeo exista en la taxonomía (B12) → error ruidoso si falta."""
+    # B12: la taxonomía debe contener todos los códigos que el mapeo referencia.
+    codigos_presentes = {r.codigo for r in rubros if r.codigo is not None}
+    faltantes = sorted(set(_CONCEPTO_POR_CODIGO) - codigos_presentes)
+    if faltantes:
+        raise ValueError(
+            "E1: el mapeo referencia códigos ausentes de la taxonomía vigente "
+            f"(B12): {faltantes}. Créalos por C1 antes de anclar."
+        )
+
+    conceptos: dict[str, Decimal] = {c: _CERO for c in CONCEPTOS}
+    sin_mapear: list[str] = []
+    for r in rubros:
+        if r.id in neutros_ids:  # A1: exclusión por id, primero
+            continue
+        valor = valor_por_rubro_id.get(r.id)
+        concepto = _concepto_de(r)
+        if concepto is None:
+            # R-2 (4040) y cualquier rubro no-sistema sin concepto: se reporta si movió
+            # dinero (para no ensuciar con rubros vacíos).
+            if valor is not None and valor != _CERO and not r.es_sistema:
+                sin_mapear.append(r.nombre)
+            continue
+        if valor is not None:
+            conceptos[concepto] = conceptos[concepto] + valor
+    return ResultadoMapeo(conceptos=conceptos, sin_mapear=sorted(sin_mapear))
diff --git a/backend/tests/test_e1_lectura.py b/backend/tests/test_e1_lectura.py
new file mode 100644
index 0000000..adaceac
--- /dev/null
+++ b/backend/tests/test_e1_lectura.py
@@ -0,0 +1,141 @@
+# backend/tests/test_e1_lectura.py
+"""E1 · P1 — mapeo de la ejecución real a los conceptos del motor (función pura).
+
+Cubre: B9 (Σ rubros == concepto, fixture del Plan de Cuentas real) · B12 (código del
+mapeo ausente → error ruidoso) · A1 (neutros excluidos por rubro_id) · R-1 (1010 entero
+a pago_inventario) · R-2 (4040 en sin_mapear)."""
+
+from decimal import Decimal
+
+import pytest
+from app.proyeccion.ejecucion.lectura import (
+    RubroInfo,
+    mapear_a_conceptos,
+)
+
+# Fixture: el Plan de Cuentas real (código, grupo, nombre, es_sistema) — mismo que
+# domain/rubro.py._seed(). El `id` es sintético (str del código) para el test puro.
+_PLAN = [
+    # ingresos
+    ("0110", "ingresos_operativos", "Recaudo de cartera", True),
+    ("0120", "ingresos_operativos", "Cuotas iniciales", False),
+    ("0130", "ingresos_operativos", "RODANTE (crédito de repuestos)", False),
+    ("0140", "ingresos_operativos", "Otros ingresos", False),
+    # costo producto
+    ("1010", "costo_producto", "Producto", False),
+    ("1020", "costo_producto", "SOAT/Matrículas", False),
+    ("1030", "costo_producto", "Seguros (Hunter)", False),
+    # operación (muestra + 2130/2140 que el I-PLAN no listaba → por grupo igual entran)
+    ("2010", "operacion", "Arriendos", False),
+    ("2070", "operacion", "Transporte/peajes/combustible/parqueo", False),
+    ("2140", "operacion", "Freelance", False),
+    # nómina
+    ("3010", "nomina", "Sueldos empleados", False),
+    # deudas
+    ("4010", "deudas_obligaciones", "Préstamos", False),
+    ("4020", "deudas_obligaciones", "Deudas tarjetas de crédito", False),
+    ("4030", "deudas_obligaciones", "Garantía cupo (Auteco)", False),
+    ("4040", "deudas_obligaciones", "Deudas impuestos", False),
+    ("4050", "deudas_obligaciones", "Deudas proveedores anteriores", False),
+    ("4060", "deudas_obligaciones", "Inventario Auteco (150 días)", False),
+    # otros
+    ("5010", "otros", "Otros gastos", False),
+    ("5060", "otros", "Impuestos", False),
+    ("5070", "otros", "Por clasificar", True),
+    # sistema sin código (neutros)
+    (None, "otros", "Ajuste de conciliación", True),
+    (None, "otros", "Reversas y devoluciones", False),
+    (None, "ingresos_operativos", "Tránsito Wava mes anterior", True),
+]
+
+
+def _rubros() -> list[RubroInfo]:
+    return [
+        RubroInfo(id=nombre, codigo=cod, grupo=gr, nombre=nombre, es_sistema=sis)
+        for (cod, gr, nombre, sis) in _PLAN
+    ]
+
+
+def _valores(**por_nombre) -> dict[str, Decimal]:
+    return {k: Decimal(v) for k, v in por_nombre.items()}
+
+
+def test_b9_suma_rubros_igual_concepto():
+    rubros = _rubros()
+    valores = _valores(
+        **{
+            "Cuotas iniciales": "10000",
+            "Otros ingresos": "5000",
+            "Producto": "70000",  # → pago_inventario
+            "Inventario Auteco (150 días)": "30000",  # → pago_inventario
+            "Garantía cupo (Auteco)": "1600",  # → fondeo
+            "SOAT/Matrículas": "2000",  # → costo_nueva
+            "Seguros (Hunter)": "800",  # → gps
+            "Arriendos": "4000",  # → gastos_fijos
+            "Freelance": "500",  # → gastos_fijos (2140, por grupo)
+            "Sueldos empleados": "9000",  # → gastos_fijos
+            "Otros gastos": "300",  # → gastos_fijos
+            "Préstamos": "1000",  # → int_deuda
+            "Deudas tarjetas de crédito": "500",  # → int_deuda
+            "Deudas proveedores anteriores": "700",  # → int_deuda
+            "Impuestos": "6000",  # → iva
+        }
+    )
+    r = mapear_a_conceptos(rubros=rubros, valor_por_rubro_id=valores, neutros_ids=set())
+    c = r.conceptos
+    assert c["neto"] == Decimal("15000")  # 10000 + 5000
+    assert c["pago_inventario"] == Decimal("100000")  # 70000 + 30000
+    assert c["fondeo"] == Decimal("1600")
+    assert c["costo_nueva"] == Decimal("2000")
+    assert c["gps"] == Decimal("800")
+    assert c["gastos_fijos"] == Decimal("13800")  # 4000+500+9000+300
+    assert c["int_deuda"] == Decimal("2200")  # 1000+500+700
+    assert c["iva"] == Decimal("6000")
+
+
+def test_r1_1010_entero_a_pago_inventario_no_costo_nueva():
+    rubros = _rubros()
+    r = mapear_a_conceptos(
+        rubros=rubros,
+        valor_por_rubro_id=_valores(Producto="50000"),
+        neutros_ids=set(),
+    )
+    assert r.conceptos["pago_inventario"] == Decimal("50000")
+    assert r.conceptos["costo_nueva"] == Decimal("0.00")
+
+
+def test_r2_4040_en_sin_mapear():
+    rubros = _rubros()
+    r = mapear_a_conceptos(
+        rubros=rubros,
+        valor_por_rubro_id=_valores(**{"Deudas impuestos": "8000"}),
+        neutros_ids=set(),
+    )
+    assert "Deudas impuestos" in r.sin_mapear
+    # y no se sumó a ningún concepto
+    assert all(v == Decimal("0.00") for v in r.conceptos.values())
+
+
+def test_a1_neutros_excluidos_por_id():
+    rubros = _rubros()
+    # 'Reversas y devoluciones' (grupo otros, NO sistema) mapearía a gastos_fijos si no
+    # se excluyera; su id en neutros_ids lo saca ANTES de la regla de grupo.
+    valores = _valores(**{"Arriendos": "4000", "Reversas y devoluciones": "9999"})
+    r = mapear_a_conceptos(
+        rubros=rubros,
+        valor_por_rubro_id=valores,
+        neutros_ids={
+            "Reversas y devoluciones",
+            "Ajuste de conciliación",
+            "Tránsito Wava mes anterior",
+        },
+    )
+    assert r.conceptos["gastos_fijos"] == Decimal("4000")  # sin los 9999 del neutro
+    assert "Reversas y devoluciones" not in r.sin_mapear
+
+
+def test_b12_codigo_del_mapeo_ausente_es_ruidoso():
+    # Quitar 4060 de la taxonomía → el mapeo lo referencia → error ruidoso.
+    rubros = [r for r in _rubros() if r.codigo != "4060"]
+    with pytest.raises(ValueError, match="B12"):
+        mapear_a_conceptos(rubros=rubros, valor_por_rubro_id={}, neutros_ids=set())
```
