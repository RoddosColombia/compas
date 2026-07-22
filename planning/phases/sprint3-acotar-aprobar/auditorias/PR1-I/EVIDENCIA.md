# EVIDENCIA — sprint3-acotar-aprobar · I-PR1 (acotamiento + aprobación)

**Rama:** `feat/acotar-aprobar` · **PR:** #21 · **commit:** `2277d32` · vs `main`

## Salidas de tests

### Local (mongomock + puros) — 286 passed / 27 skipped
```
286 passed, 27 skipped, 670 warnings in 187.30s
```
Presupuesto (motor + generar + acotar/aprobar guardas):
```
32 passed  (test_motor_sugerido + test_presupuesto_generar + test_presupuesto_acotar_aprobar)
```
Incluye el TEST DORADO 48/61/75M → 84.033.333,33 corriendo sobre la agregación `$group` (Baja #4, equivalencia probada).

### CI real-mongo (PR #21, run 29883289498) — replica set 1-nodo
Job `backend-real-mongo`:
```
27 passed, 286 deselected, 246 warnings in 9.22s
```
Los 4 tests de la transacción multi-doc + convergencia:
- `test_aprobar_happy_atomico` — fija monto_definido (null→sugerido, acotada conserva) + mes→definido, atómico.
- `test_idempotencia_replay` — replay de la Idempotency-Key devuelve la respuesta original; un solo evento de auditoría.
- `test_convergencia_abort_datos` — (a) fallo en la última escritura → rollback TOTAL (líneas revertidas) → converge al reintentar.
- `test_convergencia_falla_emit_compensa` — (b) commit OK + emit falla → compensación (saga O1) preserva la acotada y revierte null→sugerido → converge.

Todos los jobs verdes: `backend`, `backend-real-mongo`, `gitleaks`, `pip-audit`, `runtime-imports`, `frontend`.

### Reglas del protocolo de commit
```
app.alegra.com/api/r1 : 0
journal-entries       : 0
estado.*pending       : 0
ruff check + format   : limpio
```

## Diff real (backend) vs main

```diff
diff --git a/backend/app/domain/presupuesto.py b/backend/app/domain/presupuesto.py
index f381eef..dd10ebc 100644
--- a/backend/app/domain/presupuesto.py
+++ b/backend/app/domain/presupuesto.py
@@ -38,6 +38,7 @@ class Ajuste(BaseModel):
     valor_nuevo: Money
     por: str  # usuario_id
     at: datetime
+    comentario: str | None = None  # Baja #3 (US-02: motivo, p. ej. "renegociado")
 
 
 class PresupuestoLinea(Document):
@@ -54,6 +55,7 @@ class PresupuestoLinea(Document):
     )
     compromisos_programados: Money = Decimal("0")  # informativo; NO entra en la fórmula
     monto_definido: Money | None = None  # null hasta aprobar (F-07)
+    creada_por: str | None = None  # Baja #1: actor de la generación (rastro)
     historia_incompleta: bool
     modo_calculo: ModoCalculo = ModoCalculo.HISTORICO
     ajustes: list[Ajuste] = Field(default_factory=list)
diff --git a/backend/app/presupuesto/router.py b/backend/app/presupuesto/router.py
index 0ca3e0f..4355f56 100644
--- a/backend/app/presupuesto/router.py
+++ b/backend/app/presupuesto/router.py
@@ -7,16 +7,21 @@ RBAC §2.4: generar = `ciclo:abrir` (fila "Abrir mes / generar sugerido"); leer
 `dashboard:leer`. `crec_pct` viaja como string (Decimal exacto). `mes` en la ruta es
 YYYY-MM (se normaliza al día 1)."""
 
+import hashlib
+import json
 import re
 from decimal import Decimal, InvalidOperation
 
-from fastapi import APIRouter, Depends, HTTPException
-from pydantic import BaseModel, ConfigDict
+from fastapi import APIRouter, Depends, Header, HTTPException
+from fastapi.responses import JSONResponse
+from pydantic import BaseModel, ConfigDict, Field
+from pymongo.errors import DuplicateKeyError
 
 from app.auth.deps import require_permission
 from app.auth.models import User
 from app.auth.router import verify_origin
 from app.core.money import money_str
+from app.domain.idempotency import IdempotencyKey
 from app.domain.mes_control import MesControl
 from app.domain.presupuesto import PresupuestoLinea
 from app.presupuesto import service
@@ -24,6 +29,7 @@ from app.presupuesto import service
 router = APIRouter(prefix="/meses", tags=["presupuesto"])
 
 _MES = re.compile(r"^\d{4}-\d{2}$")
+_ENDPOINT_APROBAR = "POST /meses/{mes}/presupuesto/aprobar"
 
 
 class GenerarSugeridoBody(BaseModel):
@@ -32,6 +38,13 @@ class GenerarSugeridoBody(BaseModel):
     crec_pct: str = "0"  # tasa como string (p. ej. "0.15"); Decimal exacto
 
 
+class AcotarBody(BaseModel):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    monto_definido: str  # monto COP como string (regla 1)
+    comentario: str | None = Field(default=None, max_length=300)
+
+
 def _mes_key(mes: str) -> str:
     if not _MES.match(mes):
         raise HTTPException(422, "mes debe ser 'YYYY-MM'")
@@ -92,3 +105,89 @@ async def listar_presupuesto(
         PresupuestoLinea.vigente == True,  # noqa: E712
     ).to_list()
     return {"mes": mes, "lineas": [_serializar(x) for x in lineas]}
+
+
+def _parse_monto(s: str) -> Decimal:
+    try:
+        v = Decimal(s)
+    except InvalidOperation:
+        raise HTTPException(422, "monto_definido no es un decimal válido") from None
+    if v < 0:
+        raise HTTPException(422, "monto_definido no puede ser negativo")
+    return v
+
+
+@router.patch("/{mes}/presupuesto/{rubro_id}")
+async def acotar_linea(
+    mes: str,
+    rubro_id: str,
+    body: AcotarBody,
+    user: User = Depends(require_permission("presupuesto:acotar")),
+    _: None = Depends(verify_origin),
+):
+    monto = _parse_monto(body.monto_definido)
+    try:
+        ln = await service.acotar_linea(
+            mes=_mes_key(mes),
+            rubro_id=rubro_id,
+            monto_definido=monto,
+            comentario=body.comentario,
+            usuario_id=user.id,
+        )
+    except service.AcotarError as e:
+        raise HTTPException(e.status, e.detalle) from e
+    return _serializar(ln)
+
+
+@router.post("/{mes}/presupuesto/aprobar")
+async def aprobar_presupuesto(
+    mes: str,
+    idempotency_key: str = Header(
+        alias="Idempotency-Key", min_length=1, max_length=128
+    ),
+    user: User = Depends(require_permission("ciclo:aprobar")),
+    _: None = Depends(verify_origin),
+):
+    # §1.12 replay seguro (aprobaciones): scope (usuario, endpoint, key). Reusado
+    # además para CONVERGER si el proceso cae entre el commit y el emit de auditoría.
+    req_hash = hashlib.sha256(
+        json.dumps({"mes": mes}, sort_keys=True).encode()
+    ).hexdigest()
+    previa = await IdempotencyKey.find_one(
+        IdempotencyKey.usuario_id == user.id,
+        IdempotencyKey.endpoint == _ENDPOINT_APROBAR,
+        IdempotencyKey.key == idempotency_key,
+    )
+    if previa is not None:
+        if previa.request_hash != req_hash:
+            raise HTTPException(422, "Idempotency-Key ya usada con un payload distinto")
+        if previa.response_status is None:
+            raise HTTPException(409, "petición con esta Idempotency-Key en curso")
+        return JSONResponse(previa.response_body, status_code=previa.response_status)
+
+    marca = IdempotencyKey(
+        usuario_id=user.id,
+        endpoint=_ENDPOINT_APROBAR,
+        key=idempotency_key,
+        request_hash=req_hash,
+    )
+    try:
+        await marca.insert()
+    except DuplicateKeyError:
+        raise HTTPException(409, "petición con esta Idempotency-Key en curso") from None
+
+    try:
+        resultado = await service.aprobar_presupuesto(
+            mes=_mes_key(mes), usuario_id=user.id
+        )
+    except service.AprobarError as e:
+        await marca.delete()  # una petición fallida no quema la key
+        raise HTTPException(e.status, e.detalle) from e
+    except Exception:
+        await marca.delete()
+        raise
+
+    marca.response_status = 200
+    marca.response_body = resultado
+    await marca.save()
+    return resultado
diff --git a/backend/app/presupuesto/service.py b/backend/app/presupuesto/service.py
index 0294eff..54a46b0 100644
--- a/backend/app/presupuesto/service.py
+++ b/backend/app/presupuesto/service.py
@@ -1,25 +1,40 @@
 # backend/app/presupuesto/service.py
-"""Generación del sugerido (F-07): crea las PresupuestoLinea vigentes de un mes a
-partir del ejecutado de los meses CERRADOS anteriores (§1.4.1).
+"""Ciclo del presupuesto (F-06/F-07): generación del sugerido, acotamiento y
+aprobación.
 
-MARCADO PARA AUDITORÍA KIMI (motor del sugerido — fórmula celda a celda).
+MARCADO PARA AUDITORÍA KIMI (motor del sugerido + tabla de autoridad §2.4).
 
-Alcance de este incremento: generar líneas en modo HISTÓRICO para los rubros
-activos NO de sistema ('Por clasificar'/'Ajuste'/'Recaudo' se excluyen — no son
-líneas presupuestables). El acotamiento (monto_definido) y la aprobación (→definido)
-son incrementos siguientes; aquí toda línea nace `vigente`, version 1, sin definir.
-
-E(i) = Σ valor de Transaccion (egreso) del rubro en el mes cerrado i. Se toman los 3
-meses 'cerrado' inmediatamente anteriores al mes objetivo (los que existan)."""
+- **generar_sugerido** (§1.4.1): crea las PresupuestoLinea vigentes de un mes desde
+  el ejecutado de los meses CERRADOS anteriores. E(i) se calcula con UNA agregación
+  `$group` (Baja #4: 1 query vs ~90). Cada línea guarda `creada_por` (Baja #1).
+- **acotar_linea** (§2.4 "Proponer/acotar"): fija `monto_definido` + registra un
+  `Ajuste` con comentario. Transiciona el mes `sugerido → propuesto` (M-1). Saga
+  fail-closed O1 (M-2): si el emit de auditoría falla, compensa (revierte ajuste +
+  monto + estado). No es transacción Mongo (afecta pocos docs secuenciales).
+- **aprobar_presupuesto** (§2.4 "Aprobar", solo Admin): TRANSACCIÓN MULTI-DOC
+  (regla 8/F-09) que fija `monto_definido` (default = sugerido) en las ~30 líneas
+  vigentes + MesControl → `definido`, atómico, con reintento automático de
+  `with_transaction` ante TransientTransactionError. La auditoría vive en conexión
+  dedicada → se emite tras el commit; si falla, transacción compensatoria revierte
+  (saga O1). Convergencia ante caída vía Idempotency-Key (en el router)."""
 
 from decimal import Decimal
 
+from beanie import PydanticObjectId
+from bson.decimal128 import Decimal128
+
+from app.audit.events import AuditEvento
+from app.audit.service import emit_audit
+from app.core.money import money_str
+from app.core.time import now_utc
 from app.domain.mes_control import EstadoMes, MesControl
-from app.domain.presupuesto import PresupuestoLinea
+from app.domain.presupuesto import Ajuste, PresupuestoLinea
 from app.domain.rubro import Rubro, TipoFlujo
 from app.domain.transaccion import Transaccion
 from app.presupuesto.motor import calcular_sugerido_historico
 
+_ACOTABLE = (EstadoMes.SUGERIDO, EstadoMes.PROPUESTO)
+
 
 class SugeridoError(Exception):
     def __init__(self, detalle: str, status: int = 422) -> None:
@@ -28,6 +43,20 @@ class SugeridoError(Exception):
         self.status = status
 
 
+class AcotarError(Exception):
+    def __init__(self, detalle: str, status: int = 422) -> None:
+        super().__init__(detalle)
+        self.detalle = detalle
+        self.status = status
+
+
+class AprobarError(Exception):
+    def __init__(self, detalle: str, status: int = 422) -> None:
+        super().__init__(detalle)
+        self.detalle = detalle
+        self.status = status
+
+
 async def _meses_cerrados_previos(mes: str, limite: int = 3) -> list[MesControl]:
     """Los `limite` meses en estado 'cerrado' con mes < objetivo, del más reciente
     al más antiguo (E(M-1), E(M-2), E(M-3))."""
@@ -41,16 +70,38 @@ async def _meses_cerrados_previos(mes: str, limite: int = 3) -> list[MesControl]
     )
 
 
-async def _ejecutado(rubro_id, mes_id) -> Decimal:
-    """Σ valor de las transacciones de EGRESO del rubro en ese mes cerrado."""
-    total = Decimal("0")
-    async for t in Transaccion.find(
-        Transaccion.rubro_id == rubro_id,
-        Transaccion.mes_id == mes_id,
-        Transaccion.tipo_flujo == TipoFlujo.EGRESO,
-    ):
-        total += t.valor
-    return total
+async def _ejecutados_por_rubro_mes(
+    mes_ids: list[PydanticObjectId], rubro_ids: list[PydanticObjectId]
+) -> dict[tuple[str, str], Decimal]:
+    """Baja #4: UNA agregación `$group` (vs ~90 queries punto a punto). Σ valor de
+    las transacciones de EGRESO por (rubro, mes) sobre los meses cerrados dados.
+    Claves como str(ObjectId) para hashing estable. Devuelve Decimal (regla 1)."""
+    if not mes_ids or not rubro_ids:
+        return {}
+    col = Transaccion.get_pymongo_collection()
+    pipeline = [
+        {
+            "$match": {
+                "tipo_flujo": TipoFlujo.EGRESO.value,
+                "mes_id": {"$in": mes_ids},
+                "rubro_id": {"$in": rubro_ids},
+            }
+        },
+        {
+            "$group": {
+                "_id": {"rubro_id": "$rubro_id", "mes_id": "$mes_id"},
+                "total": {"$sum": "$valor"},
+            }
+        },
+    ]
+    out: dict[tuple[str, str], Decimal] = {}
+    async for doc in col.aggregate(pipeline):
+        total = doc["total"]
+        dec = (
+            total.to_decimal() if isinstance(total, Decimal128) else Decimal(str(total))
+        )
+        out[(str(doc["_id"]["rubro_id"]), str(doc["_id"]["mes_id"]))] = dec
+    return out
 
 
 async def generar_sugerido(
@@ -70,9 +121,15 @@ async def generar_sugerido(
         Rubro.es_sistema == False,  # noqa: E712
     ).to_list()
 
+    agg = await _ejecutados_por_rubro_mes(
+        [mc.id for mc in cerrados], [r.id for r in rubros]
+    )
+
     creadas: list[PresupuestoLinea] = []
     for rubro in rubros:
-        ejecutados = [await _ejecutado(rubro.id, mc.id) for mc in cerrados]
+        ejecutados = [
+            agg.get((str(rubro.id), str(mc.id)), Decimal("0")) for mc in cerrados
+        ]
         comp = calcular_sugerido_historico(ejecutados, crec_pct)
         linea = PresupuestoLinea(
             mes_id=objetivo.id,
@@ -82,14 +139,162 @@ async def generar_sugerido(
             tendencia_mes=comp.tendencia_mes,
             crec_pct=crec_pct,
             historia_incompleta=comp.historia_incompleta,
+            creada_por=usuario_id,  # Baja #1: rastro del actor de la generación
         )
         await linea.insert()
         creadas.append(linea)
 
-    # DECISIÓN (Kimi): la generación NO emite evento. El catálogo cerrado (regla 11)
-    # no tiene 'sugerido.generado'; usar presupuesto.acotado sería mal uso semántico
-    # (acotar = ajustar una línea existente, no generarla). El sugerido es un
+    # DECISIÓN (Kimi I-PR1): la generación NO emite evento. El sugerido es un
     # BORRADOR recomputable (monto_definido=null); los eventos reales llegan con el
-    # acotamiento (presupuesto.acotado) y la aprobación (presupuesto.definido). Si el
-    # gate exige rastro de generación → CR para 'presupuesto.sugerido_generado'.
+    # acotamiento (presupuesto.acotado) y la aprobación (presupuesto.definido).
     return creadas
+
+
+async def acotar_linea(
+    *,
+    mes: str,
+    rubro_id: str,
+    monto_definido: Decimal,
+    comentario: str | None,
+    usuario_id: str,
+) -> PresupuestoLinea:
+    """§2.4 Proponer/acotar. Fija `monto_definido` en la línea vigente NO aprobada
+    y registra un `Ajuste` append-only. M-1: transiciona el mes `sugerido→propuesto`.
+    M-2: saga fail-closed O1 — si el emit de auditoría falla, compensa todo."""
+    mc = await MesControl.find_one(MesControl.mes == mes)
+    if mc is None:
+        raise AcotarError(f"el mes {mes[:7]} no existe", 404)
+    if mc.estado is EstadoMes.CERRADO:
+        raise AcotarError("el mes está cerrado y es inmutable (regla 4)", 409)
+    if mc.estado not in _ACOTABLE:
+        raise AcotarError(
+            f"el mes está en '{mc.estado.value}'; solo se acota en sugerido/propuesto",
+            409,
+        )
+    try:
+        rid = PydanticObjectId(rubro_id)
+    except Exception:
+        raise AcotarError("rubro_id inválido", 422) from None
+    ln = await PresupuestoLinea.find_one(
+        PresupuestoLinea.mes_id == mc.id,
+        PresupuestoLinea.rubro_id == rid,
+        PresupuestoLinea.vigente == True,  # noqa: E712
+    )
+    if ln is None:
+        raise AcotarError("no hay línea de presupuesto vigente para ese rubro", 404)
+
+    # Estado previo para la compensación (M-2).
+    prev_monto = ln.monto_definido
+    prev_ajustes = len(ln.ajustes)
+    prev_estado = mc.estado
+
+    ln.ajustes.append(
+        Ajuste(
+            valor_anterior=prev_monto,
+            valor_nuevo=monto_definido,
+            por=usuario_id,
+            at=now_utc(),
+            comentario=comentario,
+        )
+    )
+    ln.monto_definido = monto_definido
+    await ln.save()
+
+    cambio_mes = False
+    if mc.estado is EstadoMes.SUGERIDO:  # M-1
+        mc.estado = EstadoMes.PROPUESTO
+        await mc.save()
+        cambio_mes = True
+
+    try:
+        await emit_audit(
+            AuditEvento.presupuesto_acotado,
+            entidad="presupuesto_linea",
+            entidad_id=str(ln.id),
+            actor_id=usuario_id,
+            metadata={
+                "mes": mes,
+                "rubro_id": rubro_id,
+                "valor_anterior": money_str(prev_monto)
+                if prev_monto is not None
+                else None,
+                "valor_nuevo": money_str(monto_definido),
+                "comentario": comentario,
+            },
+        )
+    except Exception:
+        # M-2 (saga O1): sin auditoría no hay decisión financiera → compensar.
+        ln.ajustes = ln.ajustes[:prev_ajustes]
+        ln.monto_definido = prev_monto
+        await ln.save()
+        if cambio_mes:
+            mc.estado = prev_estado
+            await mc.save()
+        raise
+    return ln
+
+
+async def aprobar_presupuesto(*, mes: str, usuario_id: str) -> dict:
+    """§2.4 Aprobar (solo Admin). TRANSACCIÓN MULTI-DOC (regla 8): fija
+    `monto_definido` (= sugerido donde sea null) en las líneas vigentes + MesControl
+    → `definido`, atómico. La auditoría (conexión dedicada) se emite tras el commit;
+    si falla, transacción compensatoria revierte (saga O1)."""
+    mc = await MesControl.find_one(MesControl.mes == mes)
+    if mc is None:
+        raise AprobarError(f"el mes {mes[:7]} no existe", 404)
+    if mc.estado is EstadoMes.CERRADO:
+        raise AprobarError("el mes está cerrado y es inmutable (regla 4)", 409)
+    if mc.estado is EstadoMes.DEFINIDO:
+        raise AprobarError(f"el mes {mes[:7]} ya está definido", 409)
+    if mc.estado not in _ACOTABLE:
+        raise AprobarError(f"no se puede aprobar un mes en '{mc.estado.value}'", 409)
+    lineas = await PresupuestoLinea.find(
+        PresupuestoLinea.mes_id == mc.id,
+        PresupuestoLinea.vigente == True,  # noqa: E712
+    ).to_list()
+    if not lineas:
+        raise AprobarError("el mes no tiene líneas de presupuesto que aprobar", 409)
+
+    # Estado previo para compensar si el emit de auditoría falla (saga O1).
+    ids_null_previo = {ln.id for ln in lineas if ln.monto_definido is None}
+    estado_previo = mc.estado
+    client = PresupuestoLinea.get_pymongo_collection().database.client
+
+    async def _aprobar(session):
+        for ln in lineas:
+            if ln.monto_definido is None:  # D2: aceptar la recomendación del motor
+                ln.monto_definido = ln.monto_sugerido
+                await ln.save(session=session)
+        mc.estado = EstadoMes.DEFINIDO
+        mc.definido_por = usuario_id
+        mc.definido_at = now_utc()
+        await mc.save(session=session)
+
+    # with_transaction REINTENTA solo TransientTransactionError / commit desconocido.
+    async with await client.start_session() as session:
+        await session.with_transaction(_aprobar)
+
+    try:
+        await emit_audit(
+            AuditEvento.presupuesto_definido,
+            entidad="mes",
+            entidad_id=str(mc.id),
+            actor_id=usuario_id,
+            metadata={"mes": mes, "lineas": len(lineas), "definido_por": usuario_id},
+        )
+    except Exception:
+
+        async def _revertir(session):
+            for ln in lineas:
+                if ln.id in ids_null_previo:
+                    ln.monto_definido = None
+                    await ln.save(session=session)
+            mc.estado = estado_previo
+            mc.definido_por = None
+            mc.definido_at = None
+            await mc.save(session=session)
+
+        async with await client.start_session() as session:
+            await session.with_transaction(_revertir)
+        raise
+    return {"mes": mes, "estado": mc.estado.value, "lineas": len(lineas)}
diff --git a/backend/tests/test_presupuesto_acotar_aprobar.py b/backend/tests/test_presupuesto_acotar_aprobar.py
new file mode 100644
index 0000000..c734aab
--- /dev/null
+++ b/backend/tests/test_presupuesto_acotar_aprobar.py
@@ -0,0 +1,298 @@
+# backend/tests/test_presupuesto_acotar_aprobar.py
+"""Acotamiento (§2.4) + guardas de aprobación — parte mongomock.
+
+MARCADO PARA AUDITORÍA KIMI (tabla de autoridad §2.4 + saga O1).
+
+Cubre acotar END-TO-END (mongomock lo soporta: no usa transacción Mongo): happy,
+comentario persistido, M-1 (sugerido→propuesto), M-2 (compensación si el emit de
+auditoría falla), RBAC y guardas de estado. La transacción multi-doc de la
+aprobación (regla 8) y su convergencia viven en el archivo real-mongo hermano; aquí
+solo se prueban las GUARDAS de aprobar (RBAC/estado), que retornan ANTES de la
+transacción."""
+
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
+
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
+async def _mes(mesd: str, estado: EstadoMes) -> MesControl:
+    mc = MesControl(mes=mesd, saldo_inicial_caja=Decimal("0"), estado=estado)
+    await mc.insert()
+    return mc
+
+
+async def _rubro(nombre: str, orden: int) -> Rubro:
+    r = Rubro(grupo="operacion", nombre=nombre, orden=orden, es_sistema=False)
+    await r.insert()
+    return r
+
+
+async def _linea(
+    mes_id, rubro_id, sugerido="1000000", definido=None
+) -> PresupuestoLinea:
+    ln = PresupuestoLinea(
+        mes_id=mes_id,
+        rubro_id=rubro_id,
+        monto_sugerido=Decimal(sugerido),
+        prom_3m=Decimal(sugerido),
+        tendencia_mes=Decimal("0"),
+        crec_pct=Decimal("0"),
+        historia_incompleta=False,
+        monto_definido=Decimal(definido) if definido is not None else None,
+    )
+    await ln.insert()
+    return ln
+
+
+# ── ACOTAR ────────────────────────────────────────────────────────────────
+
+
+async def test_acotar_fija_monto_y_transiciona_a_propuesto(api):
+    h = await _token(api, "dir@roddos.com")  # Directivo acota (§2.4)
+    mc = await _mes("2026-07-01", EstadoMes.SUGERIDO)
+    rubro = await _rubro("Arriendos", 4)
+    await _linea(mc.id, rubro.id, sugerido="1000000")
+    r = await api.patch(
+        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
+        json={"monto_definido": "1200000", "comentario": "renegociado"},
+        headers=h,
+    )
+    assert r.status_code == 200
+    assert r.json()["monto_definido"] == "1200000.00"
+    # M-1: el mes pasó a 'propuesto'
+    mc2 = await MesControl.find_one(MesControl.mes == "2026-07-01")
+    assert mc2.estado is EstadoMes.PROPUESTO
+    # ajuste con comentario persistido
+    ln = await PresupuestoLinea.find_one(PresupuestoLinea.rubro_id == rubro.id)
+    assert len(ln.ajustes) == 1
+    assert ln.ajustes[0].comentario == "renegociado"
+    assert ln.ajustes[0].valor_anterior is None
+    assert ln.ajustes[0].valor_nuevo == Decimal("1200000")
+
+
+async def test_acotar_segunda_vez_conserva_propuesto_y_valor_anterior(api):
+    h = await _token(api)
+    mc = await _mes("2026-07-01", EstadoMes.PROPUESTO)
+    rubro = await _rubro("Arriendos", 4)
+    await _linea(mc.id, rubro.id, sugerido="1000000", definido="1200000")
+    r = await api.patch(
+        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
+        json={"monto_definido": "1500000"},
+        headers=h,
+    )
+    assert r.status_code == 200
+    ln = await PresupuestoLinea.find_one(PresupuestoLinea.rubro_id == rubro.id)
+    assert ln.monto_definido == Decimal("1500000")
+    assert ln.ajustes[-1].valor_anterior == Decimal("1200000")
+    mc2 = await MesControl.find_one(MesControl.mes == "2026-07-01")
+    assert mc2.estado is EstadoMes.PROPUESTO  # sin cambio
+
+
+async def test_acotar_consulta_403(api):
+    h = await _token(api, "consulta@roddos.com")
+    mc = await _mes("2026-07-01", EstadoMes.SUGERIDO)
+    rubro = await _rubro("Arriendos", 4)
+    await _linea(mc.id, rubro.id)
+    r = await api.patch(
+        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
+        json={"monto_definido": "1"},
+        headers=h,
+    )
+    assert r.status_code == 403
+
+
+async def test_acotar_mes_cerrado_409(api):
+    h = await _token(api)
+    mc = await _mes("2026-07-01", EstadoMes.CERRADO)
+    rubro = await _rubro("Arriendos", 4)
+    await _linea(mc.id, rubro.id)
+    r = await api.patch(
+        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
+        json={"monto_definido": "1"},
+        headers=h,
+    )
+    assert r.status_code == 409
+
+
+async def test_acotar_mes_definido_409(api):
+    h = await _token(api)
+    mc = await _mes("2026-07-01", EstadoMes.DEFINIDO)
+    rubro = await _rubro("Arriendos", 4)
+    await _linea(mc.id, rubro.id)
+    r = await api.patch(
+        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
+        json={"monto_definido": "1"},
+        headers=h,
+    )
+    assert r.status_code == 409
+
+
+async def test_acotar_sin_linea_404(api):
+    h = await _token(api)
+    await _mes("2026-07-01", EstadoMes.SUGERIDO)
+    rubro = await _rubro("Arriendos", 4)  # sin línea creada
+    r = await api.patch(
+        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
+        json={"monto_definido": "1"},
+        headers=h,
+    )
+    assert r.status_code == 404
+
+
+async def test_acotar_monto_negativo_422(api):
+    h = await _token(api)
+    mc = await _mes("2026-07-01", EstadoMes.SUGERIDO)
+    rubro = await _rubro("Arriendos", 4)
+    await _linea(mc.id, rubro.id)
+    r = await api.patch(
+        f"/api/v1/meses/2026-07/presupuesto/{rubro.id}",
+        json={"monto_definido": "-5"},
+        headers=h,
+    )
+    assert r.status_code == 422
+
+
+async def test_acotar_compensa_si_falla_auditoria(api, monkeypatch):
+    # M-2 (saga O1): si el emit falla, se revierte ajuste + monto + estado del mes.
+    mc = await _mes("2026-07-01", EstadoMes.SUGERIDO)
+    rubro = await _rubro("Arriendos", 4)
+    await _linea(mc.id, rubro.id, sugerido="1000000")
+
+    async def _boom(*a, **k):
+        raise RuntimeError("audit caído")
+
+    monkeypatch.setattr("app.presupuesto.service.emit_audit", _boom)
+    with pytest.raises(RuntimeError):
+        await service.acotar_linea(
+            mes="2026-07-01",
+            rubro_id=str(rubro.id),
+            monto_definido=Decimal("1200000"),
+            comentario="x",
+            usuario_id="u1",
+        )
+    ln = await PresupuestoLinea.find_one(PresupuestoLinea.rubro_id == rubro.id)
+    assert ln.monto_definido is None  # revertido
+    assert len(ln.ajustes) == 0  # ajuste retirado
+    mc2 = await MesControl.find_one(MesControl.mes == "2026-07-01")
+    assert mc2.estado is EstadoMes.SUGERIDO  # estado revertido
+
+
+# ── APROBAR (solo guardas; happy path + convergencia en real-mongo) ─────────
+
+
+async def test_aprobar_no_admin_403(api):
+    for email in ("fin@roddos.com", "dir@roddos.com", "consulta@roddos.com"):
+        h = await _token(api, email)
+        r = await api.post(
+            "/api/v1/meses/2026-07/presupuesto/aprobar",
+            headers={**h, "Idempotency-Key": f"k-{email}"},
+        )
+        assert r.status_code == 403, email
+
+
+async def test_aprobar_mes_inexistente_404(api):
+    h = await _token(api, "admin@roddos.com")
+    r = await api.post(
+        "/api/v1/meses/2026-07/presupuesto/aprobar",
+        headers={**h, "Idempotency-Key": "k1"},
+    )
+    assert r.status_code == 404
+
+
+async def test_aprobar_mes_cerrado_409(api):
+    h = await _token(api, "admin@roddos.com")
+    await _mes("2026-07-01", EstadoMes.CERRADO)
+    r = await api.post(
+        "/api/v1/meses/2026-07/presupuesto/aprobar",
+        headers={**h, "Idempotency-Key": "k1"},
+    )
+    assert r.status_code == 409
+
+
+async def test_aprobar_mes_ya_definido_409(api):
+    h = await _token(api, "admin@roddos.com")
+    await _mes("2026-07-01", EstadoMes.DEFINIDO)
+    r = await api.post(
+        "/api/v1/meses/2026-07/presupuesto/aprobar",
+        headers={**h, "Idempotency-Key": "k1"},
+    )
+    assert r.status_code == 409
+
+
+async def test_aprobar_sin_lineas_409(api):
+    h = await _token(api, "admin@roddos.com")
+    await _mes("2026-07-01", EstadoMes.PROPUESTO)  # sin líneas
+    r = await api.post(
+        "/api/v1/meses/2026-07/presupuesto/aprobar",
+        headers={**h, "Idempotency-Key": "k1"},
+    )
+    assert r.status_code == 409
+
+
+async def test_aprobar_peticion_fallida_no_quema_la_key(api):
+    # una guarda fallida borra la marca → se puede reintentar con la misma key.
+    h = await _token(api, "admin@roddos.com")
+    await _mes("2026-07-01", EstadoMes.DEFINIDO)
+    r1 = await api.post(
+        "/api/v1/meses/2026-07/presupuesto/aprobar",
+        headers={**h, "Idempotency-Key": "k1"},
+    )
+    assert r1.status_code == 409
+    r2 = await api.post(
+        "/api/v1/meses/2026-07/presupuesto/aprobar",
+        headers={**h, "Idempotency-Key": "k1"},
+    )
+    assert r2.status_code == 409  # no 422 "key con payload distinto"
diff --git a/backend/tests/test_presupuesto_aprobar_realmongo.py b/backend/tests/test_presupuesto_aprobar_realmongo.py
new file mode 100644
index 0000000..997c3f9
--- /dev/null
+++ b/backend/tests/test_presupuesto_aprobar_realmongo.py
@@ -0,0 +1,217 @@
+# backend/tests/test_presupuesto_aprobar_realmongo.py
+"""Aprobación del presupuesto — TRANSACCIÓN MULTI-DOC (regla 8/F-09) contra Mongo REAL.
+
+MARCADO PARA AUDITORÍA KIMI (§2.4 aprobar + regla 8 + saga O1).
+
+mongomock NO soporta sesiones/transacciones → estos tests exigen un replica set real
+(@requires_real_mongo; CI lo provee, local con COMPAS_TEST_MONGO_URI). Cubren:
+  • happy: fija monto_definido (null→sugerido, acotada conserva) + mes→definido.
+  • idempotencia: replay de la misma Idempotency-Key devuelve la respuesta original.
+  • "aprobación interrumpida CONVERGE" en los DOS puntos de fallo (Kimi):
+      (a) abort de la transacción de datos → rollback total (atomicidad).
+      (b) fallo del emit de auditoría tras el commit → compensación (saga O1).
+    Tras cada fallo, re-ejecutar CONVERGE al estado definido."""
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
+from beanie import init_beanie
+from motor.motor_asyncio import AsyncIOMotorClient
+
+PWD = "clave-larga-1234"
+
+
+@pytest.mark.requires_real_mongo
+class TestAprobarReal:
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
+        dbname = "compas_test_aprobar"
+        await client.drop_database(dbname)
+        db = client[dbname]
+        await init_beanie(database=db, document_models=DOMAIN_DOCUMENTS)
+        repository.configure_auth(client, dbname)
+        configure_audit(client, dbname)
+        for correo, rol in [
+            ("fin@roddos.com", Role.financiero),
+            ("admin@roddos.com", Role.admin),
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
+    async def _token(self, ac, email):
+        r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
+        return {"Authorization": f"Bearer {r.json()['access_token']}"}
+
+    async def _sembrar(self, estado=EstadoMes.PROPUESTO):
+        """Mes + 2 líneas vigentes: una acotada (1.200.000), una sin acotar
+        (sugerido 1.000.000 → debe tomar el sugerido al aprobar)."""
+        mc = MesControl(
+            mes="2026-07-01", saldo_inicial_caja=Decimal("0"), estado=estado
+        )
+        await mc.insert()
+        r1 = Rubro(grupo="operacion", nombre="Arriendos", orden=4, es_sistema=False)
+        r2 = Rubro(grupo="operacion", nombre="Servicios", orden=5, es_sistema=False)
+        await r1.insert()
+        await r2.insert()
+
+        async def _ln(rid, sug, defi):
+            ln = PresupuestoLinea(
+                mes_id=mc.id,
+                rubro_id=rid,
+                monto_sugerido=Decimal(sug),
+                prom_3m=Decimal(sug),
+                tendencia_mes=Decimal("0"),
+                crec_pct=Decimal("0"),
+                historia_incompleta=False,
+                monto_definido=Decimal(defi) if defi else None,
+            )
+            await ln.insert()
+            return ln
+
+        acotada = await _ln(r1.id, "1000000", "1200000")
+        sin_acotar = await _ln(r2.id, "1000000", None)
+        return mc, acotada, sin_acotar
+
+    async def test_aprobar_happy_atomico(self, entorno):
+        ac, db = entorno
+        h = await self._token(ac, "admin@roddos.com")
+        mc, acotada, sin_acotar = await self._sembrar()
+        r = await ac.post(
+            "/api/v1/meses/2026-07/presupuesto/aprobar",
+            headers={**h, "Idempotency-Key": "ap-1"},
+        )
+        assert r.status_code == 200
+        assert r.json()["estado"] == "definido"
+        # acotada conserva; sin acotar toma el sugerido (D2)
+        a2 = await PresupuestoLinea.get(acotada.id)
+        s2 = await PresupuestoLinea.get(sin_acotar.id)
+        assert a2.monto_definido == Decimal("1200000")
+        assert s2.monto_definido == Decimal("1000000")
+        mc2 = await MesControl.get(mc.id)
+        assert mc2.estado is EstadoMes.DEFINIDO
+        assert mc2.definido_por is not None and mc2.definido_at is not None
+        n = await db["audit_log"].count_documents({"evento": "presupuesto.definido"})
+        assert n == 1
+
+    async def test_idempotencia_replay(self, entorno):
+        ac, db = entorno
+        h = await self._token(ac, "admin@roddos.com")
+        await self._sembrar()
+        r1 = await ac.post(
+            "/api/v1/meses/2026-07/presupuesto/aprobar",
+            headers={**h, "Idempotency-Key": "ap-x"},
+        )
+        r2 = await ac.post(
+            "/api/v1/meses/2026-07/presupuesto/aprobar",
+            headers={**h, "Idempotency-Key": "ap-x"},
+        )
+        assert r1.status_code == 200 and r2.status_code == 200
+        assert r1.json() == r2.json()  # replay de la respuesta original
+        # el replay NO re-ejecuta: un solo evento de auditoría
+        n = await db["audit_log"].count_documents({"evento": "presupuesto.definido"})
+        assert n == 1
+
+    async def test_convergencia_abort_datos(self, entorno, monkeypatch):
+        # (a) Falla la última escritura de la transacción → abort → rollback TOTAL
+        # (las líneas guardadas dentro de la sesión se revierten). Luego CONVERGE.
+        ac, db = entorno
+        h = await self._token(ac, "admin@roddos.com")
+        mc, acotada, sin_acotar = await self._sembrar()
+
+        orig = MesControl.save
+
+        async def flaky(self, *a, **k):
+            if k.get("session") is not None:
+                raise RuntimeError("caída a mitad de la transacción de datos")
+            return await orig(self, *a, **k)
+
+        monkeypatch.setattr(MesControl, "save", flaky)
+        with pytest.raises(RuntimeError):
+            await ac.post(
+                "/api/v1/meses/2026-07/presupuesto/aprobar",
+                headers={**h, "Idempotency-Key": "ap-a"},
+            )
+        # rollback: nada cambió
+        assert (await MesControl.get(mc.id)).estado is EstadoMes.PROPUESTO
+        assert (await PresupuestoLinea.get(sin_acotar.id)).monto_definido is None
+        # la key fallida se liberó → se puede reintentar
+        monkeypatch.undo()
+        r = await ac.post(
+            "/api/v1/meses/2026-07/presupuesto/aprobar",
+            headers={**h, "Idempotency-Key": "ap-a"},
+        )
+        assert r.status_code == 200
+        assert (await MesControl.get(mc.id)).estado is EstadoMes.DEFINIDO
+        assert (await PresupuestoLinea.get(sin_acotar.id)).monto_definido == Decimal(
+            "1000000"
+        )
+
+    async def test_convergencia_falla_emit_compensa(self, entorno, monkeypatch):
+        # (b) Commit OK, pero el emit de auditoría falla → compensación (saga O1)
+        # revierte mes + los monto_definido que eran null. Luego CONVERGE.
+        ac, db = entorno
+        h = await self._token(ac, "admin@roddos.com")
+        mc, acotada, sin_acotar = await self._sembrar()
+
+        async def boom(*a, **k):
+            raise RuntimeError("auditoría caída")
+
+        monkeypatch.setattr("app.presupuesto.service.emit_audit", boom)
+        with pytest.raises(RuntimeError):
+            await ac.post(
+                "/api/v1/meses/2026-07/presupuesto/aprobar",
+                headers={**h, "Idempotency-Key": "ap-b"},
+            )
+        # compensado: mes de vuelta a propuesto; la línea null vuelve a null;
+        # la acotada NO se toca (dato legítimo preservado).
+        assert (await MesControl.get(mc.id)).estado is EstadoMes.PROPUESTO
+        assert (await PresupuestoLinea.get(sin_acotar.id)).monto_definido is None
+        assert (await PresupuestoLinea.get(acotada.id)).monto_definido == Decimal(
+            "1200000"
+        )
+        # ningún evento persistió
+        assert (
+            await db["audit_log"].count_documents({"evento": "presupuesto.definido"})
+            == 0
+        )
+        # converge al reintentar
+        monkeypatch.undo()
+        r = await ac.post(
+            "/api/v1/meses/2026-07/presupuesto/aprobar",
+            headers={**h, "Idempotency-Key": "ap-b"},
+        )
+        assert r.status_code == 200
+        assert (await MesControl.get(mc.id)).estado is EstadoMes.DEFINIDO
diff --git a/backend/tests/test_presupuesto_generar.py b/backend/tests/test_presupuesto_generar.py
index cb701bb..f335e09 100644
--- a/backend/tests/test_presupuesto_generar.py
+++ b/backend/tests/test_presupuesto_generar.py
@@ -80,16 +80,17 @@ async def _rubro(nombre: str, orden: int, sistema: bool = False) -> Rubro:
 _SEQ = [0]
 
 
-async def _ejec(rubro_id, mes_id, monto: str):
-    """Una transacción de egreso que aporta `monto` al ejecutado del rubro/mes."""
+async def _ejec(rubro_id, mc: MesControl, monto: str):
+    """Una transacción de egreso que aporta `monto` al ejecutado del rubro/mes.
+    Baja #5: la fecha cae DENTRO del mes (antes 2026-01-15 fija → incoherente)."""
     _SEQ[0] += 1
     await Transaccion(
-        fecha="2026-01-15",
+        fecha=f"{mc.mes[:7]}-15",
         descripcion="EJEC",
         valor=Decimal(monto),
         tipo_flujo="egreso",
         rubro_id=rubro_id,
-        mes_id=mes_id,
+        mes_id=mc.id,
         banco="manual",
         id_banco=f"MAN-EJEC-{_SEQ[0]}",
     ).insert()
@@ -104,10 +105,10 @@ async def test_ejemplo_oficial_end_to_end(api):
     await _mes("2026-07-01", EstadoMes.SUGERIDO)  # objetivo (abierto)
     rubro = await _rubro("Arriendos", 4)
     # dos transacciones en un mes para verificar que E(i) SUMA
-    await _ejec(rubro.id, abr.id, "20000000")
-    await _ejec(rubro.id, abr.id, "28000000")  # abr total 48M
-    await _ejec(rubro.id, may.id, "61000000")
-    await _ejec(rubro.id, jun.id, "75000000")
+    await _ejec(rubro.id, abr, "20000000")
+    await _ejec(rubro.id, abr, "28000000")  # abr total 48M
+    await _ejec(rubro.id, may, "61000000")
+    await _ejec(rubro.id, jun, "75000000")
 
     r = await api.post(
         "/api/v1/meses/2026-07/sugerido", json={"crec_pct": "0.15"}, headers=h
@@ -129,7 +130,7 @@ async def test_solo_cuenta_meses_cerrados(api):
     await _mes("2026-07-01", EstadoMes.SUGERIDO)  # abierto, no cerrado
     await _mes("2026-08-01", EstadoMes.SUGERIDO)  # objetivo
     rubro = await _rubro("Arriendos", 4)
-    await _ejec(rubro.id, jun.id, "50000000")
+    await _ejec(rubro.id, jun, "50000000")
     r = await api.post("/api/v1/meses/2026-08/sugerido", json={}, headers=h)
     ln = next(x for x in r.json()["lineas"] if x["rubro_id"] == str(rubro.id))
     assert ln["historia_incompleta"] is True  # solo 1 mes cerrado
```
