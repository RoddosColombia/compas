# EVIDENCIA — sprint4-deuda · I-PR1: S4-00 + S4-06

**PR:** #26 `fix/deuda-s4-transacciones` → `main` · 2026-07-22

## 1. Salidas de tests (reales, locales)

### Suite completa del backend
```
411 passed, 46 skipped, 2850 warnings in 240.64s (0:04:00)
```
(46 skipped = requires_real_mongo → job backend-real-mongo del CI del PR #26, que ejecuta
los tests decisivos de esta pieza: acotar transaccional (4, incl. rollback total) y
TOCTOU del cierre (2). Estado final visible en el PR.)

### Guardas mongomock (acotar/aprobar + cierre/reapertura, incl. B-3 step-up)
```
24 passed, 339 warnings in 25.63s
```

### Lint
```
ruff check . → All checks passed! · ruff format --check . → limpio · greps protocolo: 0
```

## 2. Diff completo (backend)

```diff
diff --git a/backend/app/cierre/service.py b/backend/app/cierre/service.py
index f84040e..b7940b2 100644
--- a/backend/app/cierre/service.py
+++ b/backend/app/cierre/service.py
@@ -197,6 +197,25 @@ async def confirmar_cierre(*, mes: str, usuario_id: str) -> dict:
     creado = {"ajuste_id": None}
 
     async def _cerrar(session):
+        # S4-06/B-2 (Kimi, TOCTOU): las guardas de arriba corren FUERA de la
+        # transacción — releer el estado DENTRO de la sesión y abortar si otro
+        # proceso lo cambió (doble cierre / ajuste a mes inmutable).
+        mc_fresco = await MesControl.find_one(MesControl.mes == mc.mes, session=session)
+        sig_fresco = await MesControl.find_one(
+            MesControl.mes == siguiente.mes, session=session
+        )
+        if mc_fresco is None or mc_fresco.estado is not EstadoMes.EN_EJECUCION:
+            raise CierreError(
+                f"el estado del mes {mes[:7]} cambió durante el cierre "
+                "(concurrencia); reintentar",
+                409,
+            )
+        if sig_fresco is None or sig_fresco.estado is EstadoMes.CERRADO:
+            raise CierreError(
+                f"el mes {siguiente.mes[:7]} cambió de estado durante el cierre "
+                "(concurrencia); reintentar",
+                409,
+            )
         siguiente.saldo_inicial_caja = r_m  # M-2: re-anclar a R_M
         await siguiente.save(session=session)
         aj_id = None
@@ -292,6 +311,25 @@ async def reabrir_mes(*, mes: str, usuario_id: str) -> dict:
     creado = {"contra_id": None}
 
     async def _reabrir(session):
+        # S4-06/B-2 simétrico: revalidar DENTRO de la sesión (doble reapertura /
+        # LIFO roto por concurrencia).
+        mc_fresco = await MesControl.find_one(MesControl.mes == mc.mes, session=session)
+        if mc_fresco is None or mc_fresco.estado is not EstadoMes.CERRADO:
+            raise CierreError(
+                f"el estado del mes {mes[:7]} cambió durante la reapertura "
+                "(concurrencia); reintentar",
+                409,
+            )
+        if siguiente is not None:
+            sig_fresco = await MesControl.find_one(
+                MesControl.mes == siguiente.mes, session=session
+            )
+            if sig_fresco is not None and sig_fresco.estado is EstadoMes.CERRADO:
+                raise CierreError(
+                    f"el mes {siguiente.mes[:7]} se cerró durante la reapertura "
+                    "(LIFO); reintentar",
+                    409,
+                )
         if ci and ci.ajuste_tx_id:
             orig = await Transaccion.get(PydanticObjectId(ci.ajuste_tx_id))
             if orig is not None:
diff --git a/backend/app/presupuesto/service.py b/backend/app/presupuesto/service.py
index a5951ba..a6c1c75 100644
--- a/backend/app/presupuesto/service.py
+++ b/backend/app/presupuesto/service.py
@@ -10,7 +10,9 @@ MARCADO PARA AUDITORÍA KIMI (motor del sugerido + tabla de autoridad §2.4).
 - **acotar_linea** (§2.4 "Proponer/acotar"): fija `monto_definido` + registra un
   `Ajuste` con comentario. Transiciona el mes `sugerido → propuesto` (M-1). Saga
   fail-closed O1 (M-2): si el emit de auditoría falla, compensa (revierte ajuste +
-  monto + estado). No es transacción Mongo (afecta pocos docs secuenciales).
+  monto + estado). S4-00 (Kimi, higiene): línea + mes se escriben en TRANSACCIÓN
+  MULTI-DOC — antes eran dos `save` secuenciales y una caída de proceso entre
+  ambos dejaba ventana de inconsistencia; ahora es atómico como aprobar/cerrar.
 - **aprobar_presupuesto** (§2.4 "Aprobar", solo Admin): TRANSACCIÓN MULTI-DOC
   (regla 8/F-09) que fija `monto_definido` (default = sugerido) en las ~30 líneas
   vigentes + MesControl → `definido`, atómico, con reintento automático de
@@ -160,7 +162,8 @@ async def acotar_linea(
 ) -> PresupuestoLinea:
     """§2.4 Proponer/acotar. Fija `monto_definido` en la línea vigente NO aprobada
     y registra un `Ajuste` append-only. M-1: transiciona el mes `sugerido→propuesto`.
-    M-2: saga fail-closed O1 — si el emit de auditoría falla, compensa todo."""
+    M-2: saga fail-closed O1 — si el emit de auditoría falla, compensa todo.
+    S4-00: línea + mes en transacción multi-doc (regla 8)."""
     mc = await MesControl.find_one(MesControl.mes == mes)
     if mc is None:
         raise AcotarError(f"el mes {mes[:7]} no existe", 404)
@@ -198,13 +201,19 @@ async def acotar_linea(
         )
     )
     ln.monto_definido = monto_definido
-    await ln.save()
+    cambio_mes = mc.estado is EstadoMes.SUGERIDO  # M-1
+    client = PresupuestoLinea.get_pymongo_collection().database.client
 
-    cambio_mes = False
-    if mc.estado is EstadoMes.SUGERIDO:  # M-1
-        mc.estado = EstadoMes.PROPUESTO
-        await mc.save()
-        cambio_mes = True
+    # S4-00 (Kimi, higiene): línea + mes ATÓMICOS — una caída de proceso entre los
+    # dos save ya no deja el ajuste sin la transición de estado (o viceversa).
+    async def _acotar(session):
+        await ln.save(session=session)
+        if cambio_mes:
+            mc.estado = EstadoMes.PROPUESTO
+            await mc.save(session=session)
+
+    async with await client.start_session() as session:
+        await session.with_transaction(_acotar)
 
     try:
         await emit_audit(
@@ -223,13 +232,18 @@ async def acotar_linea(
             },
         )
     except Exception:
-        # M-2 (saga O1): sin auditoría no hay decisión financiera → compensar.
-        ln.ajustes = ln.ajustes[:prev_ajustes]
-        ln.monto_definido = prev_monto
-        await ln.save()
-        if cambio_mes:
-            mc.estado = prev_estado
-            await mc.save()
+        # M-2 (saga O1): sin auditoría no hay decisión financiera → compensar
+        # (también atómico, como la reversión de aprobar).
+        async def _revertir(session):
+            ln.ajustes = ln.ajustes[:prev_ajustes]
+            ln.monto_definido = prev_monto
+            await ln.save(session=session)
+            if cambio_mes:
+                mc.estado = prev_estado
+                await mc.save(session=session)
+
+        async with await client.start_session() as session:
+            await session.with_transaction(_revertir)
         raise
     return ln
 
diff --git a/backend/tests/test_cierre_conciliacion.py b/backend/tests/test_cierre_conciliacion.py
index 52b048d..d726456 100644
--- a/backend/tests/test_cierre_conciliacion.py
+++ b/backend/tests/test_cierre_conciliacion.py
@@ -253,3 +253,17 @@ async def test_reabrir_no_admin_403(api):
     await _mes("2026-07-01", EstadoMes.CERRADO)
     r = await api.post("/api/v1/meses/2026-07/reabrir", headers=h)
     assert r.status_code == 403
+
+
+async def test_reabrir_admin_sin_step_up_403(api):
+    # S4-06/B-3 (Kimi I-PR1 cierre): POST /reabrir exige step-up MFA — un admin
+    # SIN 2º factor reciente es rechazado. Este test BLINDA el `require_step_up`
+    # del router contra una refactorización que lo quite sin que CI lo note.
+    h = await _token(api, "admin@roddos.com")  # login sin MFA → sin mfa_at
+    await _mes("2026-07-01", EstadoMes.CERRADO)
+    r = await api.post("/api/v1/meses/2026-07/reabrir", headers=h)
+    assert r.status_code == 403
+    assert "Step-up" in r.json()["detail"]
+    # y el mes NO se tocó
+    mc = await MesControl.find_one(MesControl.mes == "2026-07-01")
+    assert mc.estado is EstadoMes.CERRADO
diff --git a/backend/tests/test_cierre_realmongo.py b/backend/tests/test_cierre_realmongo.py
index dd5e464..6540c9d 100644
--- a/backend/tests/test_cierre_realmongo.py
+++ b/backend/tests/test_cierre_realmongo.py
@@ -259,3 +259,55 @@ class TestCierreReal:
         # converge
         assert (await self._confirmar(ac, h, "ka2")).status_code == 200
         assert (await MesControl.get(jun.id)).estado is EstadoMes.CERRADO
+
+    async def test_toctou_estado_cambiado_aborta_cierre(self, entorno, monkeypatch):
+        # S4-06/B-2 (Kimi I-PR1 cierre): las guardas de estado se evalúan fuera de
+        # la transacción — si OTRO proceso cierra el mes ENTRE el check y la
+        # transacción, el re-read DENTRO de la sesión debe abortar (409), nunca
+        # doble-cerrar (doble ajuste / re-ancla inconsistente).
+        ac, db = entorno
+        h = await self._token(ac)
+        jun, jul, arr = await self._sembrar("118")
+
+        orig = service._conciliar
+
+        async def tramposo(mc, rubro_id):
+            r = await orig(mc, rubro_id)
+            # "otro proceso" completa un cierre justo después de las guardas
+            await db["meses_control"].update_one(
+                {"mes": "2026-06-01"}, {"$set": {"estado": "cerrado"}}
+            )
+            return r
+
+        monkeypatch.setattr(service, "_conciliar", tramposo)
+        r = await self._confirmar(ac, h, "toc-1")
+        assert r.status_code == 409
+        monkeypatch.undo()
+        # NO hubo doble cierre: sin ajuste en jul y ancla intacta (el estado
+        # 'cerrado' lo puso el proceso concurrente simulado, no este intento).
+        assert await Transaccion.find(Transaccion.mes_id == jul.id).count() == 0
+        assert (await MesControl.get(jul.id)).saldo_inicial_caja == Decimal("0")
+        assert await db["audit_log"].count_documents({"evento": "mes.cerrado"}) == 0
+
+    async def test_toctou_siguiente_cerrado_aborta_cierre(self, entorno, monkeypatch):
+        # S4-06/B-2 simétrico: si M+1 queda CERRADO entre el check y la transacción,
+        # el cierre aborta (el ajuste se imputaría a un mes inmutable — regla 4).
+        ac, db = entorno
+        h = await self._token(ac)
+        jun, jul, arr = await self._sembrar("118")
+
+        orig = service._conciliar
+
+        async def tramposo(mc, rubro_id):
+            r = await orig(mc, rubro_id)
+            await db["meses_control"].update_one(
+                {"mes": "2026-07-01"}, {"$set": {"estado": "cerrado"}}
+            )
+            return r
+
+        monkeypatch.setattr(service, "_conciliar", tramposo)
+        r = await self._confirmar(ac, h, "toc-2")
+        assert r.status_code == 409
+        monkeypatch.undo()
+        assert (await MesControl.get(jun.id)).estado is EstadoMes.EN_EJECUCION
+        assert await Transaccion.find(Transaccion.mes_id == jul.id).count() == 0
diff --git a/backend/tests/test_presupuesto_acotar_aprobar.py b/backend/tests/test_presupuesto_acotar_aprobar.py
index c734aab..3606645 100644
--- a/backend/tests/test_presupuesto_acotar_aprobar.py
+++ b/backend/tests/test_presupuesto_acotar_aprobar.py
@@ -13,7 +13,6 @@ transacción."""
 from decimal import Decimal
 
 import httpx
-import pytest
 import pytest_asyncio
 from app.audit.service import configure_audit, reset_audit
 from app.auth import passwords, repository
@@ -24,7 +23,6 @@ from app.domain import DOMAIN_DOCUMENTS
 from app.domain.mes_control import EstadoMes, MesControl
 from app.domain.presupuesto import PresupuestoLinea
 from app.domain.rubro import Rubro
-from app.presupuesto import service
 from beanie import init_beanie
 from mongomock_motor import AsyncMongoMockClient
 
@@ -97,48 +95,7 @@ async def _linea(
     return ln
 
 
-# ── ACOTAR ────────────────────────────────────────────────────────────────
-
-
-async def test_acotar_fija_monto_y_transiciona_a_propuesto(api):
-    h = await _token(api, "dir@roddos.com")  # Directivo acota (§2.4)
-    mc = await _mes("2026-07-01", EstadoMes.SUGERIDO)
-    rubro = await _rubro("Arriendos", 4)
-    await _linea(mc.id, rubro.id, sugerido="1000000")
-    r = await api.patch(
-        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
-        json={"monto_definido": "1200000", "comentario": "renegociado"},
-        headers=h,
-    )
-    assert r.status_code == 200
-    assert r.json()["monto_definido"] == "1200000.00"
-    # M-1: el mes pasó a 'propuesto'
-    mc2 = await MesControl.find_one(MesControl.mes == "2026-07-01")
-    assert mc2.estado is EstadoMes.PROPUESTO
-    # ajuste con comentario persistido
-    ln = await PresupuestoLinea.find_one(PresupuestoLinea.rubro_id == rubro.id)
-    assert len(ln.ajustes) == 1
-    assert ln.ajustes[0].comentario == "renegociado"
-    assert ln.ajustes[0].valor_anterior is None
-    assert ln.ajustes[0].valor_nuevo == Decimal("1200000")
-
-
-async def test_acotar_segunda_vez_conserva_propuesto_y_valor_anterior(api):
-    h = await _token(api)
-    mc = await _mes("2026-07-01", EstadoMes.PROPUESTO)
-    rubro = await _rubro("Arriendos", 4)
-    await _linea(mc.id, rubro.id, sugerido="1000000", definido="1200000")
-    r = await api.patch(
-        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
-        json={"monto_definido": "1500000"},
-        headers=h,
-    )
-    assert r.status_code == 200
-    ln = await PresupuestoLinea.find_one(PresupuestoLinea.rubro_id == rubro.id)
-    assert ln.monto_definido == Decimal("1500000")
-    assert ln.ajustes[-1].valor_anterior == Decimal("1200000")
-    mc2 = await MesControl.find_one(MesControl.mes == "2026-07-01")
-    assert mc2.estado is EstadoMes.PROPUESTO  # sin cambio
+# ── ACOTAR (solo guardas; happy path + convergencia en real-mongo, S4-00) ──
 
 
 async def test_acotar_consulta_403(api):
@@ -205,29 +162,9 @@ async def test_acotar_monto_negativo_422(api):
     assert r.status_code == 422
 
 
-async def test_acotar_compensa_si_falla_auditoria(api, monkeypatch):
-    # M-2 (saga O1): si el emit falla, se revierte ajuste + monto + estado del mes.
-    mc = await _mes("2026-07-01", EstadoMes.SUGERIDO)
-    rubro = await _rubro("Arriendos", 4)
-    await _linea(mc.id, rubro.id, sugerido="1000000")
-
-    async def _boom(*a, **k):
-        raise RuntimeError("audit caído")
-
-    monkeypatch.setattr("app.presupuesto.service.emit_audit", _boom)
-    with pytest.raises(RuntimeError):
-        await service.acotar_linea(
-            mes="2026-07-01",
-            rubro_id=str(rubro.id),
-            monto_definido=Decimal("1200000"),
-            comentario="x",
-            usuario_id="u1",
-        )
-    ln = await PresupuestoLinea.find_one(PresupuestoLinea.rubro_id == rubro.id)
-    assert ln.monto_definido is None  # revertido
-    assert len(ln.ajustes) == 0  # ajuste retirado
-    mc2 = await MesControl.find_one(MesControl.mes == "2026-07-01")
-    assert mc2.estado is EstadoMes.SUGERIDO  # estado revertido
+# La compensación O1 del acotar (emit falla → revierte) migró a
+# test_presupuesto_acotar_realmongo.py: S4-00 volvió transaccional el acotar y
+# mongomock no soporta sesiones.
 
 
 # ── APROBAR (solo guardas; happy path + convergencia en real-mongo) ─────────
diff --git a/backend/tests/test_presupuesto_acotar_realmongo.py b/backend/tests/test_presupuesto_acotar_realmongo.py
new file mode 100644
index 0000000..e4a35ae
--- /dev/null
+++ b/backend/tests/test_presupuesto_acotar_realmongo.py
@@ -0,0 +1,196 @@
+# backend/tests/test_presupuesto_acotar_realmongo.py
+"""Acotamiento — TRANSACCIÓN MULTI-DOC (S4-00, higiene Kimi) contra Mongo REAL.
+
+MARCADO PARA AUDITORÍA KIMI (§2.4 acotar + regla 8 + saga O1).
+
+S4-00: `acotar_linea` pasó de dos `save` secuenciales (ventana de inconsistencia
+si el proceso moría entre ambos) a transacción multi-doc como aprobar/cerrar.
+mongomock NO soporta sesiones → los happy-path viven aquí (@requires_real_mongo,
+CI replica set); las GUARDAS (RBAC/estado/404/422, que retornan ANTES de la
+transacción) siguen en el archivo mongomock hermano."""
+
+import os
+from decimal import Decimal
+
+import httpx
+import pytest
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
+from app.presupuesto import service
+from beanie import init_beanie
+from motor.motor_asyncio import AsyncIOMotorClient
+
+PWD = "clave-larga-1234"
+
+
+@pytest.mark.requires_real_mongo
+class TestAcotarReal:
+    @pytest_asyncio.fixture
+    async def entorno(self, monkeypatch):
+        uri = os.environ.get("COMPAS_TEST_MONGO_URI")
+        if not uri:
+            pytest.skip("COMPAS_TEST_MONGO_URI no configurado")
+        monkeypatch.setenv("APP_ENV", "development")
+        monkeypatch.setenv("JWT_SECRET", "x" * 40)
+        monkeypatch.setenv("COOKIE_SECURE", "False")
+        monkeypatch.delenv("RUN_SCHEDULER", raising=False)
+        get_settings.cache_clear()
+        from app.main import create_app
+
+        app = create_app()
+        client = AsyncIOMotorClient(uri, tz_aware=True)
+        dbname = "compas_test_acotar"
+        await client.drop_database(dbname)
+        db = client[dbname]
+        await init_beanie(database=db, document_models=DOMAIN_DOCUMENTS)
+        repository.configure_auth(client, dbname)
+        configure_audit(client, dbname)
+        for correo, rol in [
+            ("fin@roddos.com", Role.financiero),
+            ("dir@roddos.com", Role.directivo),
+        ]:
+            await repository.create_user(
+                User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
+            )
+        transport = httpx.ASGITransport(app=app)
+        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
+            yield ac, db
+        repository.reset_auth()
+        reset_audit()
+        await client.drop_database(dbname)
+        client.close()
+        get_settings.cache_clear()
+
+    async def _token(self, ac, email="fin@roddos.com"):
+        r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
+        return {"Authorization": f"Bearer {r.json()['access_token']}"}
+
+    async def _sembrar(self, estado=EstadoMes.SUGERIDO, definido=None):
+        mc = MesControl(
+            mes="2026-07-01", saldo_inicial_caja=Decimal("0"), estado=estado
+        )
+        await mc.insert()
+        rubro = Rubro(grupo="operacion", nombre="Arriendos", orden=4)
+        await rubro.insert()
+        ln = PresupuestoLinea(
+            mes_id=mc.id,
+            rubro_id=rubro.id,
+            monto_sugerido=Decimal("1000000"),
+            prom_3m=Decimal("1000000"),
+            tendencia_mes=Decimal("0"),
+            crec_pct=Decimal("0"),
+            historia_incompleta=False,
+            monto_definido=Decimal(definido) if definido is not None else None,
+        )
+        await ln.insert()
+        return mc, rubro, ln
+
+    async def test_acotar_fija_monto_y_transiciona_a_propuesto(self, entorno):
+        ac, db = entorno
+        h = await self._token(ac, "dir@roddos.com")  # Directivo acota (§2.4)
+        mc, rubro, _ = await self._sembrar()
+        r = await ac.patch(
+            f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
+            json={"monto_definido": "1200000", "comentario": "renegociado"},
+            headers=h,
+        )
+        assert r.status_code == 200
+        assert r.json()["monto_definido"] == "1200000.00"
+        # M-1: el mes pasó a 'propuesto' — ATÓMICO con la línea (S4-00)
+        assert (await MesControl.get(mc.id)).estado is EstadoMes.PROPUESTO
+        ln = await PresupuestoLinea.find_one(PresupuestoLinea.rubro_id == rubro.id)
+        assert len(ln.ajustes) == 1
+        assert ln.ajustes[0].comentario == "renegociado"
+        assert ln.ajustes[0].valor_anterior is None
+        assert ln.ajustes[0].valor_nuevo == Decimal("1200000")
+
+    async def test_acotar_segunda_vez_conserva_propuesto_y_valor_anterior(
+        self, entorno
+    ):
+        ac, _ = entorno
+        h = await self._token(ac)
+        mc, rubro, _ = await self._sembrar(
+            estado=EstadoMes.PROPUESTO, definido="1200000"
+        )
+        r = await ac.patch(
+            f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
+            json={"monto_definido": "1500000"},
+            headers=h,
+        )
+        assert r.status_code == 200
+        ln = await PresupuestoLinea.find_one(PresupuestoLinea.rubro_id == rubro.id)
+        assert ln.monto_definido == Decimal("1500000")
+        assert ln.ajustes[-1].valor_anterior == Decimal("1200000")
+        assert (await MesControl.get(mc.id)).estado is EstadoMes.PROPUESTO
+
+    async def test_acotar_abort_datos_rollback_total(self, entorno, monkeypatch):
+        # S4-00 (el caso que motivó la transacción): si la escritura del MES falla,
+        # la LÍNEA tampoco queda — antes quedaba el ajuste sin la transición.
+        ac, _ = entorno
+        mc, rubro, ln0 = await self._sembrar()
+
+        orig = MesControl.save
+
+        async def flaky(self, *a, **k):
+            if k.get("session") is not None:
+                raise RuntimeError("caída entre línea y mes")
+            return await orig(self, *a, **k)
+
+        monkeypatch.setattr(MesControl, "save", flaky)
+        with pytest.raises(RuntimeError):
+            await service.acotar_linea(
+                mes="2026-07-01",
+                rubro_id=str(rubro.id),
+                monto_definido=Decimal("1200000"),
+                comentario="x",
+                usuario_id="u1",
+            )
+        monkeypatch.undo()
+        # rollback TOTAL: ni ajuste ni monto ni estado
+        ln = await PresupuestoLinea.get(ln0.id)
+        assert ln.monto_definido is None and len(ln.ajustes) == 0
+        assert (await MesControl.get(mc.id)).estado is EstadoMes.SUGERIDO
+
+    async def test_acotar_compensa_si_falla_auditoria(self, entorno, monkeypatch):
+        # M-2 (saga O1): commit OK pero el emit falla → compensación transaccional.
+        ac, db = entorno
+        h = await self._token(ac)
+        mc, rubro, ln0 = await self._sembrar()
+
+        async def _boom(*a, **k):
+            raise RuntimeError("audit caído")
+
+        monkeypatch.setattr("app.presupuesto.service.emit_audit", _boom)
+        with pytest.raises(RuntimeError):
+            await service.acotar_linea(
+                mes="2026-07-01",
+                rubro_id=str(rubro.id),
+                monto_definido=Decimal("1200000"),
+                comentario="x",
+                usuario_id="u1",
+            )
+        monkeypatch.undo()
+        ln = await PresupuestoLinea.get(ln0.id)
+        assert ln.monto_definido is None  # revertido
+        assert len(ln.ajustes) == 0  # ajuste retirado
+        assert (await MesControl.get(mc.id)).estado is EstadoMes.SUGERIDO
+        assert (
+            await db["audit_log"].count_documents({"evento": "presupuesto.acotado"})
+            == 0
+        )
+        # converge al reintentar
+        r = await ac.patch(
+            f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
+            json={"monto_definido": "1200000"},
+            headers=h,
+        )
+        assert r.status_code == 200
+        assert (await MesControl.get(mc.id)).estado is EstadoMes.PROPUESTO

```
