# EVIDENCIA — sprint4-vista-control · I-PR1 (Vista Control)

**Rama:** `feat/vista-control` · **PR:** #23 · **commit:** `37426e4` · vs `main`

## Salidas de tests

### Local (mongomock + puros) — 309 passed / 34 skipped
```
309 passed, 34 skipped, 1123 warnings in 263.32s
```
Vista Control: 11 passed. Los 8 puntos exigidos + bordes definido=0 + B-3:
- `test_dorado_celda` — definido 1M / ejec 900k → disp 100k, pct "90.00", verde.
- `test_bordes_semaforo` — 90.00→verde, 90.01→amarillo, 100.00→amarillo, 100.01→rojo (sobre pct cuantizado, B-1).
- `test_semaforo_definido_cero` — gasto→rojo, sin gasto→verde, pct null.
- `test_caja_excluye_ajuste_incluye_por_clasificar` — caja = 100000−30000−20000 = 50000 (ajuste de 999999 excluido; 'Por clasificar' incluido).
- `test_mes_sugerido_409` / `test_mes_inexistente_404` — guardas.
- `test_rbac_cuatro_roles` — consulta/fin/dir/admin → 200.
- `test_group_suma_multiples_tx` — $group suma 3 tx = 600000.
- `test_linealidad_subtotales` — Σ disp = Σ def − Σ ejec por grupo y total.
- `test_serializacion_strings` — pct_ejecutado y montos como string (B-2).
- `test_sin_presupuesto_informativo` — rubro sin línea aparece; 'Por clasificar' (sistema) no (B-3).

### CI (PR #23, run 29950896107) — 6/6 jobs verdes
`backend`, `backend-real-mongo`, `gitleaks`, `pip-audit`, `runtime-imports`, `frontend` → success.
(Vista Control es read-only → sin tests real-mongo nuevos; el job real-mongo corre los 34 existentes.)

### Reglas del protocolo de commit
```
app.alegra.com/api/r1 : 0    journal-entries : 0    estado.*pending : 0    ruff : limpio
```

## Diff real (backend) vs main

```diff
diff --git a/backend/app/api/v1/__init__.py b/backend/app/api/v1/__init__.py
index 4ee714a..94e3ebe 100644
--- a/backend/app/api/v1/__init__.py
+++ b/backend/app/api/v1/__init__.py
@@ -8,6 +8,7 @@ from app.auth.router import router as auth_router
 from app.cargas.router import router as cargas_router
 from app.ciclo.router import router as ciclo_router
 from app.cierre.router import router as cierre_router
+from app.control.router import router as control_router
 from app.presupuesto.router import router as presupuesto_router
 from app.transacciones.router import router as transacciones_router
 
@@ -17,5 +18,6 @@ api_router.include_router(auth_router)
 api_router.include_router(cargas_router)
 api_router.include_router(ciclo_router)
 api_router.include_router(cierre_router)
+api_router.include_router(control_router)
 api_router.include_router(presupuesto_router)
 api_router.include_router(transacciones_router)
diff --git a/backend/app/control/__init__.py b/backend/app/control/__init__.py
new file mode 100644
index 0000000..6d691ec
--- /dev/null
+++ b/backend/app/control/__init__.py
@@ -0,0 +1 @@
+# backend/app/control/__init__.py
diff --git a/backend/app/control/router.py b/backend/app/control/router.py
new file mode 100644
index 0000000..52b6e5c
--- /dev/null
+++ b/backend/app/control/router.py
@@ -0,0 +1,31 @@
+# backend/app/control/router.py
+"""Vista Control (Sprint 4): GET /meses/{mes}/control (read-only, dashboard:leer)."""
+
+import re
+
+from fastapi import APIRouter, Depends, HTTPException
+
+from app.auth.deps import require_permission
+from app.auth.models import User
+from app.control import service
+
+router = APIRouter(prefix="/meses", tags=["control"])
+
+_MES = re.compile(r"^\d{4}-\d{2}$")
+
+
+def _mes_key(mes: str) -> str:
+    if not _MES.match(mes):
+        raise HTTPException(422, "mes debe ser 'YYYY-MM'")
+    return f"{mes}-01"
+
+
+@router.get("/{mes}/control")
+async def vista_control(
+    mes: str,
+    user: User = Depends(require_permission("dashboard:leer")),
+):
+    try:
+        return await service.control(_mes_key(mes))
+    except service.ControlError as e:
+        raise HTTPException(e.status, e.detalle) from e
diff --git a/backend/app/control/service.py b/backend/app/control/service.py
new file mode 100644
index 0000000..8675ed5
--- /dev/null
+++ b/backend/app/control/service.py
@@ -0,0 +1,174 @@
+# backend/app/control/service.py
+"""Vista Control (Sprint 4, GO PLAN I 9.3): presupuesto vs ejecutado vs disponible.
+
+MARCADO PARA AUDITORÍA KIMI (% ejecutado — DoD #3).
+
+READ-ONLY: sin escrituras, sin transacciones, sin eventos. Por rubro (línea vigente
+del mes) agrupado en los 5 grupos: `definido` (monto_definido), `ejecutado` (Σ egresos
+del rubro en el mes, misma E(i) del motor §1.4.1), `disponible` (=definido−ejecutado),
+`pct_ejecutado` (Decimal 2 dec HALF_EVEN, string; null si definido==0), `semaforo`
+(verde ≤90 · amarillo 90–100 · rojo >100, calculado sobre el pct CUANTIZADO — B-1).
+`caja` = saldo_inicial + Σ signo(tx) excluyendo SOLO el rubro 'Ajuste de conciliación'
+('Por clasificar' SÍ cuenta: es dinero bancario real). `sin_presupuesto`: egresos en
+rubros NO de sistema sin línea vigente (informativo, B-3)."""
+
+from decimal import ROUND_HALF_EVEN, Decimal
+
+from beanie import PydanticObjectId
+from bson.decimal128 import Decimal128
+
+from app.cierre.service import _RUBRO_AJUSTE, _caja_libro
+from app.core.money import money_str
+from app.domain.mes_control import EstadoMes, MesControl
+from app.domain.presupuesto import PresupuestoLinea
+from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
+from app.domain.transaccion import Transaccion
+
+_CENTAVO = Decimal("0.01")
+_ABIERTO = (EstadoMes.EN_EJECUCION, EstadoMes.CERRADO)
+_GRUPOS_ORDEN = list(RubroGrupo)  # orden de declaración (§1.2)
+
+
+class ControlError(Exception):
+    def __init__(self, detalle: str, status: int = 422) -> None:
+        super().__init__(detalle)
+        self.detalle = detalle
+        self.status = status
+
+
+def _pct(ejecutado: Decimal, definido: Decimal) -> Decimal | None:
+    """% ejecutado cuantizado a 2 dec HALF_EVEN. None si definido==0 (regla 7)."""
+    if definido == 0:
+        return None
+    return (ejecutado / definido * 100).quantize(_CENTAVO, rounding=ROUND_HALF_EVEN)
+
+
+def _semaforo(pct: Decimal | None, ejecutado: Decimal) -> str:
+    """Sobre el pct CUANTIZADO (B-1). definido==0: gasto→rojo, sin gasto→verde."""
+    if pct is None:
+        return "rojo" if ejecutado > 0 else "verde"
+    if pct <= 90:
+        return "verde"
+    if pct <= 100:
+        return "amarillo"
+    return "rojo"
+
+
+async def _egresos_por_rubro(mes_id: PydanticObjectId) -> dict[str, Decimal]:
+    """$group: Σ egresos por rubro del mes (1 agregación; equivalente a la suma
+    directa, mismo patrón del motor)."""
+    col = Transaccion.get_pymongo_collection()
+    pipeline = [
+        {"$match": {"mes_id": mes_id, "tipo_flujo": TipoFlujo.EGRESO.value}},
+        {"$group": {"_id": "$rubro_id", "total": {"$sum": "$valor"}}},
+    ]
+    out: dict[str, Decimal] = {}
+    async for d in col.aggregate(pipeline):
+        t = d["total"]
+        dec = t.to_decimal() if isinstance(t, Decimal128) else Decimal(str(t))
+        out[str(d["_id"])] = dec
+    return out
+
+
+async def control(mes: str) -> dict:
+    mc = await MesControl.find_one(MesControl.mes == mes)
+    if mc is None:
+        raise ControlError(f"el mes {mes[:7]} no existe", 404)
+    if mc.estado not in _ABIERTO:
+        raise ControlError(
+            f"la Vista Control aplica a meses en ejecución o cerrados "
+            f"(está en '{mc.estado.value}')",
+            409,
+        )
+
+    lineas = await PresupuestoLinea.find(
+        PresupuestoLinea.mes_id == mc.id,
+        PresupuestoLinea.vigente == True,  # noqa: E712
+    ).to_list()
+    rubros = {r.id: r for r in await Rubro.find_all().to_list()}
+    egresos = await _egresos_por_rubro(mc.id)
+    rubro_aj = next(
+        (r for r in rubros.values() if r.nombre == _RUBRO_AJUSTE and r.es_sistema), None
+    )
+
+    por_grupo: dict[str, list[dict]] = {}
+    con_linea: set[str] = set()
+    for ln in lineas:
+        r = rubros.get(ln.rubro_id)
+        if r is None:
+            continue
+        con_linea.add(str(r.id))
+        definido = ln.monto_definido if ln.monto_definido is not None else Decimal("0")
+        ejec = egresos.get(str(r.id), Decimal("0"))
+        disp = definido - ejec
+        pct = _pct(ejec, definido)
+        por_grupo.setdefault(r.grupo.value, []).append(
+            {
+                "rubro_id": str(r.id),
+                "rubro": r.nombre,
+                "orden": r.orden,
+                "definido": definido,
+                "ejecutado": ejec,
+                "disponible": disp,
+                "pct_ejecutado": str(pct) if pct is not None else None,
+                "semaforo": _semaforo(pct, ejec),
+            }
+        )
+
+    grupos_out = []
+    tot_d = tot_e = tot_disp = Decimal("0")
+    for g in _GRUPOS_ORDEN:
+        filas = sorted(por_grupo.get(g.value, []), key=lambda f: f["orden"])
+        if not filas:
+            continue
+        sd = sum((f["definido"] for f in filas), Decimal("0"))
+        se = sum((f["ejecutado"] for f in filas), Decimal("0"))
+        tot_d += sd
+        tot_e += se
+        tot_disp += sd - se
+        grupos_out.append(
+            {
+                "grupo": g.value,
+                "lineas": [
+                    {
+                        "rubro_id": f["rubro_id"],
+                        "rubro": f["rubro"],
+                        "definido": money_str(f["definido"]),
+                        "ejecutado": money_str(f["ejecutado"]),
+                        "disponible": money_str(f["disponible"]),
+                        "pct_ejecutado": f["pct_ejecutado"],
+                        "semaforo": f["semaforo"],
+                    }
+                    for f in filas
+                ],
+                "subtotal": {
+                    "definido": money_str(sd),
+                    "ejecutado": money_str(se),
+                    "disponible": money_str(sd - se),
+                },
+            }
+        )
+
+    # B-3: egresos en rubros NO de sistema y sin línea vigente (informativo, regla 7).
+    sin_presupuesto = []
+    for rid, total in egresos.items():
+        r = rubros.get(PydanticObjectId(rid))
+        if r is None or r.es_sistema or rid in con_linea:
+            continue
+        sin_presupuesto.append({"rubro": r.nombre, "ejecutado": money_str(total)})
+
+    caja = await _caja_libro(
+        mc.id, rubro_aj.id if rubro_aj else None, mc.saldo_inicial_caja
+    )
+    return {
+        "mes": mes[:7],
+        "estado": mc.estado.value,
+        "grupos": grupos_out,
+        "total": {
+            "definido": money_str(tot_d),
+            "ejecutado": money_str(tot_e),
+            "disponible": money_str(tot_disp),
+        },
+        "caja_disponible": money_str(caja),
+        "sin_presupuesto": sin_presupuesto,
+    }
diff --git a/backend/tests/test_control.py b/backend/tests/test_control.py
new file mode 100644
index 0000000..17c3547
--- /dev/null
+++ b/backend/tests/test_control.py
@@ -0,0 +1,308 @@
+# backend/tests/test_control.py
+"""Vista Control — % ejecutado / disponible / semáforo (los 8 tests del gate I-PR1).
+
+MARCADO PARA AUDITORÍA KIMI (% ejecutado — DoD #3). READ-ONLY → todo mongomock.
+Cubre: dorado de celda · bordes del semáforo (sobre pct cuantizado, B-1) · caja con
+el ajuste excluido y 'Por clasificar' incluido · guardas · RBAC 4 roles · equivalencia
+$group · linealidad de subtotales · serialización (strings, B-2) · sin_presupuesto B-3.
+"""
+
+from decimal import Decimal
+
+import httpx
+import pytest_asyncio
+from app.audit.service import configure_audit, reset_audit
+from app.auth import passwords, repository
+from app.auth.models import User
+from app.auth.roles import Role
+from app.config import get_settings
+from app.domain import DOMAIN_DOCUMENTS
+from app.domain.mes_control import EstadoMes, MesControl
+from app.domain.presupuesto import PresupuestoLinea
+from app.domain.rubro import Rubro
+from app.domain.transaccion import Transaccion
+from beanie import init_beanie
+from mongomock_motor import AsyncMongoMockClient
+
+PWD = "clave-larga-1234"
+
+
+@pytest_asyncio.fixture
+async def api(monkeypatch):
+    monkeypatch.setenv("APP_ENV", "development")
+    monkeypatch.setenv("JWT_SECRET", "x" * 40)
+    monkeypatch.setenv("COOKIE_SECURE", "False")
+    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
+    get_settings.cache_clear()
+    from app.main import create_app
+
+    app = create_app()
+    c = AsyncMongoMockClient(tz_aware=True)
+    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
+    repository.configure_auth(c, "compas_test")
+    configure_audit(c, "compas_test")
+    for correo, rol in [
+        ("consulta@roddos.com", Role.consulta),
+        ("fin@roddos.com", Role.financiero),
+        ("dir@roddos.com", Role.directivo),
+        ("admin@roddos.com", Role.admin),
+    ]:
+        await repository.create_user(
+            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
+        )
+    await Rubro(
+        grupo="otros", nombre="Ajuste de conciliación", orden=98, es_sistema=True
+    ).insert()
+    await Rubro(
+        grupo="otros", nombre="Por clasificar", orden=99, es_sistema=True
+    ).insert()
+    transport = httpx.ASGITransport(app=app)
+    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
+        yield ac
+    repository.reset_auth()
+    reset_audit()
+    get_settings.cache_clear()
+
+
+async def _token(ac, email="fin@roddos.com") -> dict:
+    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
+    return {"Authorization": f"Bearer {r.json()['access_token']}"}
+
+
+async def _mes(
+    mes="2026-07-01", estado=EstadoMes.EN_EJECUCION, saldo="0"
+) -> MesControl:
+    mc = MesControl(mes=mes, saldo_inicial_caja=Decimal(saldo), estado=estado)
+    await mc.insert()
+    return mc
+
+
+_ORD = [0]
+
+
+async def _rubro(nombre, grupo="operacion", sistema=False) -> Rubro:
+    _ORD[0] += 1
+    r = Rubro(grupo=grupo, nombre=nombre, orden=_ORD[0], es_sistema=sistema)
+    await r.insert()
+    return r
+
+
+async def _linea(mc, rubro, definido) -> PresupuestoLinea:
+    ln = PresupuestoLinea(
+        mes_id=mc.id,
+        rubro_id=rubro.id,
+        monto_sugerido=Decimal(definido),
+        prom_3m=Decimal(definido),
+        tendencia_mes=Decimal("0"),
+        crec_pct=Decimal("0"),
+        historia_incompleta=False,
+        monto_definido=Decimal(definido),
+    )
+    await ln.insert()
+    return ln
+
+
+async def _tx(mc, rubro, valor, tipo="egreso"):
+    import app.core.ulid as u
+
+    await Transaccion(
+        fecha=f"{mc.mes[:7]}-10",
+        descripcion="mov",
+        valor=Decimal(valor),
+        tipo_flujo=tipo,
+        rubro_id=rubro.id,
+        mes_id=mc.id,
+        banco="bancolombia",
+        id_banco=f"MAN-{u.new_ulid()}",
+    ).insert()
+
+
+def _fila(data, rubro_id):
+    for g in data["grupos"]:
+        for f in g["lineas"]:
+            if f["rubro_id"] == rubro_id:
+                return f
+    raise AssertionError("rubro no encontrado en la respuesta")
+
+
+# ── 1. Dorado de celda ──────────────────────────────────────────────────────
+
+
+async def test_dorado_celda(api):
+    h = await _token(api)
+    mc = await _mes()
+    r = await _rubro("Arriendos")
+    await _linea(mc, r, "1000000")
+    await _tx(mc, r, "900000")  # 90%
+    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
+    f = _fila(data, str(r.id))
+    assert f["definido"] == "1000000.00"
+    assert f["ejecutado"] == "900000.00"
+    assert f["disponible"] == "100000.00"
+    assert f["pct_ejecutado"] == "90.00"
+    assert f["semaforo"] == "verde"
+
+
+# ── 2. Bordes del semáforo (sobre pct cuantizado, B-1) ──────────────────────
+
+
+async def test_bordes_semaforo(api):
+    h = await _token(api)
+    mc = await _mes()
+    casos = [
+        ("r90", "10000", "9000", "90.00", "verde"),
+        ("r9001", "10000", "9001", "90.01", "amarillo"),
+        ("r100", "10000", "10000", "100.00", "amarillo"),
+        ("r10001", "10000", "10001", "100.01", "rojo"),
+    ]
+    ids = {}
+    for nombre, defi, ejec, _, _ in casos:
+        ru = await _rubro(nombre)
+        await _linea(mc, ru, defi)
+        await _tx(mc, ru, ejec)
+        ids[nombre] = str(ru.id)
+    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
+    for nombre, _, _, pct, sem in casos:
+        f = _fila(data, ids[nombre])
+        assert f["pct_ejecutado"] == pct, nombre
+        assert f["semaforo"] == sem, nombre
+
+
+async def test_semaforo_definido_cero(api):
+    h = await _token(api)
+    mc = await _mes()
+    con_gasto = await _rubro("SinPresupConGasto")
+    sin_gasto = await _rubro("SinPresupSinGasto")
+    await _linea(mc, con_gasto, "0")
+    await _linea(mc, sin_gasto, "0")
+    await _tx(mc, con_gasto, "500")
+    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
+    fc = _fila(data, str(con_gasto.id))
+    assert fc["pct_ejecutado"] is None and fc["semaforo"] == "rojo"
+    fs = _fila(data, str(sin_gasto.id))
+    assert fs["pct_ejecutado"] is None and fs["semaforo"] == "verde"
+
+
+# ── 3. Caja: excluye ajuste, incluye 'Por clasificar' ───────────────────────
+
+
+async def test_caja_excluye_ajuste_incluye_por_clasificar(api):
+    h = await _token(api)
+    mc = await _mes(saldo="100000")
+    arr = await _rubro("Arriendos")
+    ajuste = await Rubro.find_one(Rubro.nombre == "Ajuste de conciliación")
+    porclas = await Rubro.find_one(Rubro.nombre == "Por clasificar")
+    await _linea(mc, arr, "50000")
+    await _tx(mc, arr, "30000", "egreso")  # cuenta
+    await _tx(mc, porclas, "20000", "egreso")  # cuenta en caja (dinero real)
+    await _tx(mc, ajuste, "999999", "egreso")  # NO cuenta en caja
+    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
+    # caja = 100000 − 30000 − 20000 = 50000 (el ajuste de 999999 se excluye)
+    assert data["caja_disponible"] == "50000.00"
+
+
+# ── 4. Guardas ──────────────────────────────────────────────────────────────
+
+
+async def test_mes_sugerido_409(api):
+    h = await _token(api)
+    await _mes(estado=EstadoMes.SUGERIDO)
+    r = await api.get("/api/v1/meses/2026-07/control", headers=h)
+    assert r.status_code == 409
+
+
+async def test_mes_inexistente_404(api):
+    h = await _token(api)
+    r = await api.get("/api/v1/meses/2026-07/control", headers=h)
+    assert r.status_code == 404
+
+
+# ── 5. RBAC 4 roles (dashboard:leer) ────────────────────────────────────────
+
+
+async def test_rbac_cuatro_roles(api):
+    await _mes()
+    for email in (
+        "consulta@roddos.com",
+        "fin@roddos.com",
+        "dir@roddos.com",
+        "admin@roddos.com",
+    ):
+        h = await _token(api, email)
+        r = await api.get("/api/v1/meses/2026-07/control", headers=h)
+        assert r.status_code == 200, email
+
+
+# ── 6. Equivalencia $group (suma de varias tx) ──────────────────────────────
+
+
+async def test_group_suma_multiples_tx(api):
+    h = await _token(api)
+    mc = await _mes()
+    r = await _rubro("Arriendos")
+    await _linea(mc, r, "1000000")
+    await _tx(mc, r, "300000")
+    await _tx(mc, r, "250000")
+    await _tx(mc, r, "50000")  # total ejecutado 600000
+    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
+    assert _fila(data, str(r.id))["ejecutado"] == "600000.00"
+
+
+# ── 7. Linealidad de subtotales y total ─────────────────────────────────────
+
+
+async def test_linealidad_subtotales(api):
+    h = await _token(api)
+    mc = await _mes()
+    r1 = await _rubro("A", grupo="operacion")
+    r2 = await _rubro("B", grupo="operacion")
+    r3 = await _rubro("C", grupo="nomina")
+    for ru, defi, ejec in [(r1, "100", "40"), (r2, "200", "250"), (r3, "500", "100")]:
+        await _linea(mc, ru, defi)
+        await _tx(mc, ru, ejec)
+    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
+    for g in data["grupos"]:
+        st = g["subtotal"]
+        assert Decimal(st["disponible"]) == Decimal(st["definido"]) - Decimal(
+            st["ejecutado"]
+        )
+    t = data["total"]
+    assert Decimal(t["disponible"]) == Decimal(t["definido"]) - Decimal(t["ejecutado"])
+    assert Decimal(t["definido"]) == Decimal("800")  # 100+200+500
+    assert Decimal(t["ejecutado"]) == Decimal("390")  # 40+250+100
+
+
+# ── 8. Serialización (strings, B-2) ─────────────────────────────────────────
+
+
+async def test_serializacion_strings(api):
+    h = await _token(api)
+    mc = await _mes()
+    r = await _rubro("Arriendos")
+    await _linea(mc, r, "1000000")
+    await _tx(mc, r, "500000")
+    f = _fila(
+        (await api.get("/api/v1/meses/2026-07/control", headers=h)).json(), str(r.id)
+    )
+    for k in ("definido", "ejecutado", "disponible", "pct_ejecutado"):
+        assert isinstance(f[k], str), k
+
+
+# ── B-3: egresos en rubro sin línea vigente (informativo) ───────────────────
+
+
+async def test_sin_presupuesto_informativo(api):
+    h = await _token(api)
+    mc = await _mes()
+    con = await _rubro("ConLinea")
+    sin = await _rubro("SinLinea")  # egreso sin línea de presupuesto
+    porclas = await Rubro.find_one(Rubro.nombre == "Por clasificar")
+    await _linea(mc, con, "1000")
+    await _tx(mc, con, "500")
+    await _tx(mc, sin, "700")
+    await _tx(mc, porclas, "300", "egreso")  # sistema: NO va a sin_presupuesto
+    data = (await api.get("/api/v1/meses/2026-07/control", headers=h)).json()
+    nombres = {x["rubro"] for x in data["sin_presupuesto"]}
+    assert "SinLinea" in nombres
+    assert "Por clasificar" not in nombres  # de sistema, excluido
+    assert "ConLinea" not in nombres  # tiene línea
```
