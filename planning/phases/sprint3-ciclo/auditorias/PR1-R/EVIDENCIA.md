# EVIDENCIA — sprint3-ciclo · PR1-R (fixes de I-PR1)

Fix commit `8f68158` sobre `274f47e`. Diff de los hallazgos + salidas reales.

## 1. pytest
```
254 passed, 23 skipped (test_ciclo_abrir_mes.py: 16 — 6 nuevos de M-1/B-2)
```

## 2. ruff
```
check: All checks passed! · format: 90 files already formatted
```

## 3. Protocolo
```
r1:0 | journal-entries:0 | estado-pending:0
```

## 4. git diff --stat (274f47e..8f68158)
```
.github/workflows/ci.yml              |  15 +++++
 backend/app/ciclo/router.py           |  12 +++-
 backend/app/ciclo/service.py          |  62 +++++++++++++++++--
 backend/tests/test_ciclo_abrir_mes.py | 113 +++++++++++++++++++++++++++++++++-
 4 files changed, 195 insertions(+), 7 deletions(-)
```

## 5. Diff completo de los fixes
```diff
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
index d8dfc00..f73196e 100644
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -26,6 +26,21 @@ jobs:
       - run: ruff format --check .
       - run: pytest -q --cov=app --cov-report=term-missing
 
+  # ── Smoke de imports con SOLO requirements.txt (Kimi B-1 sprint3) ──
+  # Reproduce el entorno de Render (runtime puro, sin deps de dev): atrapa el
+  # drift que tumbó el deploy c1566dc (python-multipart ausente en requirements).
+  runtime-imports:
+    runs-on: ubuntu-latest
+    steps:
+      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
+      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5
+        with:
+          python-version: "3.12"
+      - run: pip install -r backend/requirements.txt
+      - name: importar la app como uvicorn (create_app monta todos los routers)
+        working-directory: backend
+        run: python -c "from app.main import create_app; create_app(); print('imports runtime OK')"
+
   # ── Backend real-mongo: los @requires_real_mongo de verdad (DoD #6, índices, concurrencia) ──
   # El mongod corre como REPLICA SET de 1 nodo con auth (keyFile): las transacciones
   # multi-documento (regla 8: finalización de carga, y luego aprobación/cierre) NO
diff --git a/backend/app/ciclo/router.py b/backend/app/ciclo/router.py
index 85d60d6..11d209d 100644
--- a/backend/app/ciclo/router.py
+++ b/backend/app/ciclo/router.py
@@ -35,7 +35,9 @@ class AbrirMesBody(BaseModel):
     model_config = ConfigDict(strict=True, extra="forbid")
 
     mes: str  # YYYY-MM-01 (valida el Document)
-    saldo_inicial_caja: str  # string (regla 1)
+    # M-1 (F-14): SOLO para el primer mes de la historia; con predecesor se
+    # deriva del consolidado bancario anterior y traerlo es 422.
+    saldo_inicial_caja: str | None = None
     saldos_banco: list[SaldoBancoBody] = Field(default_factory=list)
     ingresos_esperados_semana: str | None = None
 
@@ -97,7 +99,11 @@ async def abrir_mes(
     try:
         mc = await service.abrir_mes(
             mes=body.mes,
-            saldo_inicial_caja=_decimal(body.saldo_inicial_caja, "saldo_inicial_caja"),
+            saldo_inicial_caja=(
+                _decimal(body.saldo_inicial_caja, "saldo_inicial_caja")
+                if body.saldo_inicial_caja is not None
+                else None
+            ),
             saldos_banco=saldos,
             ingresos_esperados_semana=(
                 _decimal(body.ingresos_esperados_semana, "ingresos_esperados_semana")
@@ -108,6 +114,8 @@ async def abrir_mes(
         )
     except service.MesYaAbiertoError as e:
         raise HTTPException(409, f"el mes {e.mes[:7]} ya está abierto") from e
+    except service.AperturaInvalidaError as e:
+        raise HTTPException(422, e.detalle) from e
     except ValueError as e:  # validación del Document (mes no normalizado, etc.)
         raise HTTPException(422, str(e)) from e
     return _serializar(mc)
diff --git a/backend/app/ciclo/service.py b/backend/app/ciclo/service.py
index 7690d7f..a255a6d 100644
--- a/backend/app/ciclo/service.py
+++ b/backend/app/ciclo/service.py
@@ -7,8 +7,17 @@ Crea el MesControl (estado inicial `sugerido`) y emite `mes.creado` (regla 11).
 Política O1 (audit fail-closed en operaciones de estado del ciclo): si el emit
 falla, la apertura se COMPENSA (delete del mes) y el error se propaga — no queda
 un mes operable sin rastro de auditoría. La unicidad la garantiza el índice
-`mes_unico` (real) + verificación previa (mongomock/UX)."""
+`mes_unico` (real) + verificación previa (mongomock/UX).
 
+**Arrastre del saldo (Kimi M-1, F-14/US-01):** `saldo_inicial_caja` NO es input
+libre. Con mes anterior existente se DERIVA del consolidado bancario del
+predecesor (Σ saldos_banco reportados; cuando exista el flujo de cierre, Sprint 4,
+será el consolidado fijado al cerrar); digitar el saldo con predecesor → error
+(el override es `ciclo:config` + step-up, futuro). Input obligatorio SOLO para el
+primer mes de la historia. El ciclo es secuencial: no se saltan meses (el
+arrastre solo tiene sentido contiguo)."""
+
+from datetime import datetime
 from decimal import Decimal
 
 from pymongo.errors import DuplicateKeyError
@@ -24,10 +33,52 @@ class MesYaAbiertoError(Exception):
         self.mes = mes
 
 
+class AperturaInvalidaError(Exception):
+    """Apertura que viola el contrato de arrastre (M-1). Mensaje accionable."""
+
+    def __init__(self, detalle: str) -> None:
+        super().__init__(detalle)
+        self.detalle = detalle
+
+
+def _mes_siguiente(mes: str) -> str:
+    d = datetime.strptime(mes, "%Y-%m-%d")
+    return f"{d.year + 1}-01-01" if d.month == 12 else f"{d.year}-{d.month + 1:02d}-01"
+
+
+async def _resolver_saldo_inicial(mes: str, saldo_input: Decimal | None) -> Decimal:
+    """M-1: deriva el saldo del consolidado del predecesor; input solo sin historia."""
+    ultimo = await MesControl.find_all().sort(-MesControl.mes).limit(1).to_list()
+    if not ultimo:  # primer mes de la historia
+        if saldo_input is None:
+            raise AperturaInvalidaError(
+                "saldo_inicial_caja es obligatorio para el primer mes de la historia"
+            )
+        return saldo_input
+
+    anterior = ultimo[0]
+    esperado = _mes_siguiente(anterior.mes)
+    if mes != esperado:
+        raise AperturaInvalidaError(
+            f"el ciclo es secuencial: el siguiente mes a abrir es {esperado[:7]}"
+        )
+    if saldo_input is not None:
+        raise AperturaInvalidaError(
+            "saldo_inicial_caja se deriva del mes anterior (F-14); el override "
+            "manual es ciclo:config + step-up MFA"
+        )
+    if not anterior.saldos_banco:
+        raise AperturaInvalidaError(
+            f"el mes {anterior.mes[:7]} no tiene consolidado bancario (saldos_banco "
+            "vacío); no hay de dónde arrastrar el saldo (regla 7: no se adivina)"
+        )
+    return sum((s.saldo for s in anterior.saldos_banco), Decimal("0"))
+
+
 async def abrir_mes(
     *,
     mes: str,
-    saldo_inicial_caja: Decimal,
+    saldo_inicial_caja: Decimal | None,
     saldos_banco: list[SaldoBanco],
     ingresos_esperados_semana: Decimal | None,
     usuario_id: str,
@@ -36,9 +87,11 @@ async def abrir_mes(
     if existente is not None:
         raise MesYaAbiertoError(mes)
 
+    saldo = await _resolver_saldo_inicial(mes, saldo_inicial_caja)
+
     mc = MesControl(
         mes=mes,
-        saldo_inicial_caja=saldo_inicial_caja,
+        saldo_inicial_caja=saldo,
         saldos_banco=saldos_banco,
         ingresos_esperados_semana=ingresos_esperados_semana,
     )
@@ -55,7 +108,8 @@ async def abrir_mes(
             actor_id=usuario_id,
             metadata={
                 "mes": mes,
-                "saldo_inicial_caja": f"{saldo_inicial_caja:.2f}",
+                "saldo_inicial_caja": f"{saldo:.2f}",
+                "saldo_derivado": saldo_inicial_caja is None,  # M-1: arrastre
                 "bancos": [s.banco.value for s in saldos_banco],
             },
         )
diff --git a/backend/tests/test_ciclo_abrir_mes.py b/backend/tests/test_ciclo_abrir_mes.py
index cee4b5d..241db93 100644
--- a/backend/tests/test_ciclo_abrir_mes.py
+++ b/backend/tests/test_ciclo_abrir_mes.py
@@ -96,6 +96,113 @@ async def test_mes_duplicado_409(api):
     assert await MesControl.find_all().count() == 1
 
 
+# ── M-1 (Kimi): el saldo inicial se ARRASTRA del mes anterior (F-14/US-01) ──
+
+
+async def test_arrastra_saldo_del_consolidado_anterior(api):
+    # Abrir N+1 → saldo_inicial_caja == consolidado bancario de N (no input).
+    ac, _ = api
+    h = await _token(ac)
+    await ac.post(
+        "/api/v1/meses",
+        json=_body(
+            mes="2026-07-01",
+            saldos_banco=[
+                {
+                    "banco": "bancolombia",
+                    "saldo": "2500000",
+                    "fecha_reporte": "2026-07-01",
+                },
+                {"banco": "bbva", "saldo": "500000", "fecha_reporte": "2026-07-01"},
+            ],
+        ),
+        headers=h,
+    )
+    r = await ac.post(
+        "/api/v1/meses",
+        json={
+            "mes": "2026-08-01",
+            "saldos_banco": [
+                {
+                    "banco": "bancolombia",
+                    "saldo": "3000000",
+                    "fecha_reporte": "2026-08-01",
+                }
+            ],
+        },
+        headers=h,
+    )
+    assert r.status_code == 201
+    assert r.json()["saldo_inicial_caja"] == "3000000.00"  # consolidado de N
+
+
+async def test_saldo_explicito_con_predecesor_422(api):
+    # Con mes anterior, digitar el saldo es override → ciclo:config+step-up (futuro).
+    ac, _ = api
+    h = await _token(ac)
+    await ac.post("/api/v1/meses", json=_body(mes="2026-07-01"), headers=h)
+    r = await ac.post(
+        "/api/v1/meses", json=_body(mes="2026-08-01"), headers=h
+    )  # trae saldo_inicial_caja
+    assert r.status_code == 422
+    assert "deriva" in r.json()["detail"].lower()
+
+
+async def test_primer_mes_sin_saldo_422(api):
+    ac, _ = api
+    h = await _token(ac)
+    body = _body()
+    del body["saldo_inicial_caja"]
+    r = await ac.post("/api/v1/meses", json=body, headers=h)
+    assert r.status_code == 422
+
+
+async def test_predecesor_sin_saldos_banco_422(api):
+    # No se adivina (regla 7): si N no reportó saldos bancarios, no hay de dónde
+    # arrastrar → error explícito, no 0.
+    ac, _ = api
+    h = await _token(ac)
+    await ac.post(
+        "/api/v1/meses", json=_body(mes="2026-07-01", saldos_banco=[]), headers=h
+    )
+    r = await ac.post(
+        "/api/v1/meses", json={"mes": "2026-08-01", "saldos_banco": []}, headers=h
+    )
+    assert r.status_code == 422
+    assert (
+        "consolidado" in r.json()["detail"].lower()
+        or "saldos" in r.json()["detail"].lower()
+    )
+
+
+async def test_mes_no_contiguo_422(api):
+    # El ciclo es secuencial: el arrastre solo tiene sentido mes a mes.
+    ac, _ = api
+    h = await _token(ac)
+    await ac.post("/api/v1/meses", json=_body(mes="2026-07-01"), headers=h)
+    r = await ac.post(
+        "/api/v1/meses", json={"mes": "2026-09-01", "saldos_banco": []}, headers=h
+    )
+    assert r.status_code == 422
+    assert "2026-08" in r.json()["detail"]
+
+
+async def test_manual_en_saldos_422(api):
+    # B-2 (Kimi): 'manual' no es un banco de saldos (§1.3).
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(
+        "/api/v1/meses",
+        json=_body(
+            saldos_banco=[
+                {"banco": "manual", "saldo": "1", "fecha_reporte": "2026-07-01"}
+            ]
+        ),
+        headers=h,
+    )
+    assert r.status_code == 422
+
+
 async def test_mes_no_normalizado_422(api):
     ac, _ = api
     h = await _token(ac)
@@ -166,7 +273,11 @@ async def test_listar_meses(api):
     ac, _ = api
     h = await _token(ac)
     await ac.post("/api/v1/meses", json=_body(mes="2026-06-01"), headers=h)
-    await ac.post("/api/v1/meses", json=_body(mes="2026-07-01"), headers=h)
+    # El 2º mes se abre SIN saldo (se arrastra del consolidado de junio, M-1).
+    r2 = await ac.post(
+        "/api/v1/meses", json={"mes": "2026-07-01", "saldos_banco": []}, headers=h
+    )
+    assert r2.status_code == 201
     r = await ac.get("/api/v1/meses", headers=h)
     assert r.status_code == 200
     meses = [m["mes"] for m in r.json()["items"]]
```
