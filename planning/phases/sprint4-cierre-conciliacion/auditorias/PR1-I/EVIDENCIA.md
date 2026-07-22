# EVIDENCIA — sprint4-cierre-conciliacion · I-PR1 (cierre + conciliación + reapertura)

**Rama:** `feat/cierre-conciliacion` · **PR:** #22 · **commit:** `6f57c9a` · vs `main`

## Salidas de tests

### Local (mongomock + puros) — 298 passed / 34 skipped
```
298 passed, 34 skipped, 883 warnings in 186.25s
```
Cierre (mongomock): 12 passed (conciliación: diferencia, exclusión del rubro, "sin dato"; guardas + RBAC).

### CI real-mongo (PR #22) — replica set 1-nodo · TODOS los jobs verdes
`backend`, `backend-real-mongo`, `gitleaks`, `pip-audit`, `runtime-imports`, `frontend` → success.
Job `backend-real-mongo`:
```
34 passed, 298 deselected, 503 warnings in 15.49s
```
Los 7 tests del cierre (los 8 puntos exigidos, uno cubre dorado+exclusión):
- `test_dorado_numerico_cuadra_a_118` — C_M=120, R_M=118, dif=−2; ajuste egreso 2 en M+1 día-1; saldo_inicial(M+1)=118; **disponible(M+1)=118 excluyendo el rubro ajuste** → cuadra por ambas vías. 1 evento mes.cerrado.
- `test_ajuste_omitido_si_diferencia_cero` — R_M=C_M=120 → sin ajuste (B-2); saldo M+1=120.
- `test_reabrir_contra_asiento_y_restaura_ancla` — ajuste original intacto (§2.2.2), contra-asiento con revierte_id + tipo invertido + valor 2; ancla M+1 restaurada a 0; 1 evento mes.reabierto.
- `test_doble_cierre_distinta_key_409` — 2º cierre (otra key) → 409.
- `test_idempotencia_replay` — misma key → misma respuesta, 1 solo evento.
- `test_convergencia_falla_emit_compensa` — commit OK + emit caído → compensación (mes en_ejecucion, sin ajuste, ancla restaurada, 0 eventos) → reintento converge.
- `test_convergencia_abort_datos` — fallo en la escritura del estado CERRADO → rollback total (mes en_ejecucion, sin ajuste, M+1 intacto) → reintento converge.

### Reglas del protocolo de commit
```
app.alegra.com/api/r1 : 0    journal-entries : 0    estado.*pending : 0    ruff : limpio
```

## Diff real (backend) vs main

```diff
diff --git a/backend/app/api/v1/__init__.py b/backend/app/api/v1/__init__.py
index 2f842d2..4ee714a 100644
--- a/backend/app/api/v1/__init__.py
+++ b/backend/app/api/v1/__init__.py
@@ -7,6 +7,7 @@ from app.api.v1 import health
 from app.auth.router import router as auth_router
 from app.cargas.router import router as cargas_router
 from app.ciclo.router import router as ciclo_router
+from app.cierre.router import router as cierre_router
 from app.presupuesto.router import router as presupuesto_router
 from app.transacciones.router import router as transacciones_router
 
@@ -15,5 +16,6 @@ api_router.include_router(health.router)
 api_router.include_router(auth_router)
 api_router.include_router(cargas_router)
 api_router.include_router(ciclo_router)
+api_router.include_router(cierre_router)
 api_router.include_router(presupuesto_router)
 api_router.include_router(transacciones_router)
diff --git a/backend/app/cierre/__init__.py b/backend/app/cierre/__init__.py
new file mode 100644
index 0000000..024773e
--- /dev/null
+++ b/backend/app/cierre/__init__.py
@@ -0,0 +1 @@
+# backend/app/cierre/__init__.py
diff --git a/backend/app/cierre/router.py b/backend/app/cierre/router.py
new file mode 100644
index 0000000..6699026
--- /dev/null
+++ b/backend/app/cierre/router.py
@@ -0,0 +1,111 @@
+# backend/app/cierre/router.py
+"""Cierre de mes + conciliación (Sprint 4).
+
+MARCADO PARA AUDITORÍA KIMI (regla 8 + §2.4).
+
+- POST /meses/{mes}/cierre/conciliacion — cierre operativo (ciclo:cierre_operativo).
+- POST /meses/{mes}/cierre/confirmar — confirmar cierre (solo Admin, Idempotency-Key).
+- POST /meses/{mes}/reabrir — reapertura (Admin + step-up MFA).
+"""
+
+import hashlib
+import json
+import re
+
+from fastapi import APIRouter, Depends, Header, HTTPException
+from fastapi.responses import JSONResponse
+from pymongo.errors import DuplicateKeyError
+
+from app.auth.deps import require_permission, require_step_up
+from app.auth.models import User
+from app.auth.router import verify_origin
+from app.cierre import service
+from app.domain.idempotency import IdempotencyKey
+
+router = APIRouter(prefix="/meses", tags=["cierre"])
+
+_MES = re.compile(r"^\d{4}-\d{2}$")
+_ENDPOINT_CONFIRMAR = "POST /meses/{mes}/cierre/confirmar"
+
+
+def _mes_key(mes: str) -> str:
+    if not _MES.match(mes):
+        raise HTTPException(422, "mes debe ser 'YYYY-MM'")
+    return f"{mes}-01"
+
+
+@router.post("/{mes}/cierre/conciliacion")
+async def cierre_operativo(
+    mes: str,
+    user: User = Depends(require_permission("ciclo:cierre_operativo")),
+    _: None = Depends(verify_origin),
+):
+    try:
+        return await service.conciliacion(_mes_key(mes))
+    except service.CierreError as e:
+        raise HTTPException(e.status, e.detalle) from e
+
+
+@router.post("/{mes}/cierre/confirmar")
+async def confirmar_cierre(
+    mes: str,
+    idempotency_key: str = Header(
+        alias="Idempotency-Key", min_length=1, max_length=128
+    ),
+    user: User = Depends(require_permission("ciclo:confirmar_cierre")),
+    _: None = Depends(verify_origin),
+):
+    req_hash = hashlib.sha256(
+        json.dumps({"mes": mes}, sort_keys=True).encode()
+    ).hexdigest()
+    previa = await IdempotencyKey.find_one(
+        IdempotencyKey.usuario_id == user.id,
+        IdempotencyKey.endpoint == _ENDPOINT_CONFIRMAR,
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
+        endpoint=_ENDPOINT_CONFIRMAR,
+        key=idempotency_key,
+        request_hash=req_hash,
+    )
+    try:
+        await marca.insert()
+    except DuplicateKeyError:
+        raise HTTPException(409, "petición con esta Idempotency-Key en curso") from None
+
+    try:
+        resultado = await service.confirmar_cierre(
+            mes=_mes_key(mes), usuario_id=user.id
+        )
+    except service.CierreError as e:
+        await marca.delete()
+        raise HTTPException(e.status, e.detalle) from e
+    except Exception:
+        await marca.delete()
+        raise
+
+    marca.response_status = 200
+    marca.response_body = resultado
+    await marca.save()
+    return resultado
+
+
+@router.post("/{mes}/reabrir")
+async def reabrir(
+    mes: str,
+    user: User = Depends(require_permission("ciclo:reabrir")),
+    _step_up: User = Depends(require_step_up()),  # Admin + MFA reciente (§2.4)
+    _: None = Depends(verify_origin),
+):
+    try:
+        return await service.reabrir_mes(mes=_mes_key(mes), usuario_id=user.id)
+    except service.CierreError as e:
+        raise HTTPException(e.status, e.detalle) from e
diff --git a/backend/app/cierre/service.py b/backend/app/cierre/service.py
new file mode 100644
index 0000000..f84040e
--- /dev/null
+++ b/backend/app/cierre/service.py
@@ -0,0 +1,359 @@
+# backend/app/cierre/service.py
+"""Cierre de mes + conciliación por banco (Sprint 4, GO PLAN R 9.4).
+
+MARCADO PARA AUDITORÍA KIMI (regla 8: cierre multi-doc + F-14 + saga O1).
+
+- **conciliacion(mes)** — cierre operativo (compute-only, sin estado, sin evento).
+  Por banco (M-3): calculado(b) = reportado(b) @ fecha_reporte + Σ signo(movimientos
+  de b con fecha > fecha_reporte(b)); banco con movimientos pero SIN saldo reportado →
+  'sin dato' (regla 7, nunca contra 0). `R_M` = Σ_b calculado(b) (bancos con dato);
+  `C_M` = caja del LIBRO (saldo_inicial + Σ signo(tx), EXCLUYENDO el rubro de sistema
+  'Ajuste de conciliación' — anti-doble-conteo, M-2/B-2). `diferencia = R_M − C_M`.
+- **confirmar_cierre(mes)** — TRANSACCIÓN MULTI-DOC (regla 8): re-ancla
+  `saldo_inicial(M+1) := R_M` (guardando el previo en `cierre_info`, M-2), crea el
+  'Ajuste de conciliación' en M+1 (día-1, omitido si diferencia==0, B-2), congela M
+  (→cerrado). Auditoría `mes.cerrado` post-commit con saga O1 (compensa como la
+  apertura certificada: borra los artefactos del cierre FALLIDO y revierte).
+- **reabrir_mes(mes)** — CONTRA-ASIENTO del ajuste (M-4, §2.2.2: la Transaccion es
+  inmutable, jamás se borra un asiento histórico), restaura el ancla previa, M→
+  en_ejecucion. Admin + step-up MFA. LIFO: M+1 debe seguir editable.
+"""
+
+from decimal import Decimal
+
+from beanie import PydanticObjectId
+
+from app.audit.events import AuditEvento
+from app.audit.service import emit_audit
+from app.ciclo.service import _mes_siguiente
+from app.core.money import money_str
+from app.core.time import now_utc
+from app.core.ulid import new_ulid
+from app.domain.bancos import Banco
+from app.domain.configuracion import ClaveConfig, Configuracion
+from app.domain.mes_control import CierreInfo, EstadoMes, MesControl
+from app.domain.rubro import Rubro, TipoFlujo
+from app.domain.transaccion import Transaccion
+
+_RUBRO_AJUSTE = "Ajuste de conciliación"
+
+
+class CierreError(Exception):
+    def __init__(self, detalle: str, status: int = 422) -> None:
+        super().__init__(detalle)
+        self.detalle = detalle
+        self.status = status
+
+
+def _signo(t: Transaccion) -> Decimal:
+    return t.valor if t.tipo_flujo == TipoFlujo.INGRESO else -t.valor
+
+
+async def _umbral() -> Decimal:
+    cfg = (
+        await Configuracion.find(
+            Configuracion.clave == ClaveConfig.UMBRAL_DIF_BANCO_CIERRE
+        )
+        .sort(-Configuracion.vigente_desde)
+        .limit(1)
+        .to_list()
+    )
+    if not cfg or cfg[0].valor_decimal is None:
+        raise CierreError("UMBRAL_DIF_BANCO_CIERRE no está configurado", 500)
+    return cfg[0].valor_decimal
+
+
+async def _rubro_ajuste() -> Rubro:
+    r = await Rubro.find_one(
+        Rubro.nombre == _RUBRO_AJUSTE,
+        Rubro.es_sistema == True,  # noqa: E712
+    )
+    if r is None:
+        raise CierreError("rubro de sistema 'Ajuste de conciliación' no sembrado", 500)
+    return r
+
+
+async def _mes(mes: str) -> MesControl:
+    mc = await MesControl.find_one(MesControl.mes == mes)
+    if mc is None:
+        raise CierreError(f"el mes {mes[:7]} no existe", 404)
+    return mc
+
+
+async def _caja_libro(
+    mes_id: PydanticObjectId, rubro_ajuste_id, saldo_inicial: Decimal
+) -> Decimal:
+    """C_M: caja del libro = saldo_inicial + Σ signo(tx) EXCLUYENDO el rubro de
+    sistema 'Ajuste de conciliación' (anti-doble-conteo, M-2)."""
+    total = saldo_inicial
+    async for t in Transaccion.find(Transaccion.mes_id == mes_id):
+        if t.rubro_id == rubro_ajuste_id:
+            continue
+        total += _signo(t)
+    return total
+
+
+async def _conciliar(mc: MesControl, rubro_ajuste_id) -> dict:
+    """Núcleo de la conciliación (M-3). No cambia estado."""
+    reportados = {sb.banco: sb for sb in mc.saldos_banco}
+    # movimientos por banco (excluye el rubro de ajuste)
+    bancos_con_mov: set[Banco] = set()
+    mov_post: dict[Banco, Decimal] = {}
+    async for t in Transaccion.find(Transaccion.mes_id == mc.id):
+        if t.rubro_id == rubro_ajuste_id:
+            continue
+        bancos_con_mov.add(t.banco)
+        sb = reportados.get(t.banco)
+        if sb is not None and t.fecha > sb.fecha_reporte:
+            mov_post[t.banco] = mov_post.get(t.banco, Decimal("0")) + _signo(t)
+
+    por_banco = []
+    r_m = Decimal("0")
+    for banco, sb in reportados.items():
+        calc = sb.saldo + mov_post.get(banco, Decimal("0"))
+        r_m += calc
+        por_banco.append(
+            {
+                "banco": banco.value,
+                "reportado": money_str(sb.saldo),
+                "calculado": money_str(calc),
+            }
+        )
+    # banco con movimientos pero sin saldo reportado → 'sin dato' (regla 7)
+    sin_dato = sorted(b.value for b in bancos_con_mov if b not in reportados)
+
+    c_m = await _caja_libro(mc.id, rubro_ajuste_id, mc.saldo_inicial_caja)
+    diferencia = r_m - c_m
+    umbral = await _umbral()
+    dentro = abs(diferencia) <= umbral and not sin_dato
+    return {
+        "por_banco": por_banco,
+        "sin_dato": sin_dato,
+        "consolidado_reportado": r_m,
+        "caja_libro": c_m,
+        "diferencia": diferencia,
+        "umbral": umbral,
+        "dentro_de_umbral": dentro,
+    }
+
+
+async def conciliacion(mes: str) -> dict:
+    """Cierre operativo: reporte de conciliación (compute-only)."""
+    mc = await _mes(mes)
+    if mc.estado is not EstadoMes.EN_EJECUCION:
+        raise CierreError(
+            f"solo se concilia un mes en ejecución (está en '{mc.estado.value}')", 409
+        )
+    rubro_aj = await _rubro_ajuste()
+    r = await _conciliar(mc, rubro_aj.id)
+    return {
+        "mes": mes[:7],
+        "por_banco": r["por_banco"],
+        "sin_dato": r["sin_dato"],
+        "consolidado_reportado": money_str(r["consolidado_reportado"]),
+        "caja_libro": money_str(r["caja_libro"]),
+        "diferencia": money_str(r["diferencia"]),
+        "umbral": money_str(r["umbral"]),
+        "dentro_de_umbral": r["dentro_de_umbral"],
+    }
+
+
+async def confirmar_cierre(*, mes: str, usuario_id: str) -> dict:
+    """Confirmar cierre (solo Admin). Transacción multi-doc (regla 8) + saga O1."""
+    mc = await _mes(mes)
+    if mc.estado is EstadoMes.CERRADO:
+        raise CierreError(f"el mes {mes[:7]} ya está cerrado", 409)
+    if mc.estado is not EstadoMes.EN_EJECUCION:
+        raise CierreError(
+            f"solo se cierra un mes en ejecución (está en '{mc.estado.value}')", 409
+        )
+    siguiente = await MesControl.find_one(MesControl.mes == _mes_siguiente(mc.mes))
+    if siguiente is None:  # D2
+        raise CierreError(
+            f"abre el mes {_mes_siguiente(mc.mes)[:7]} antes de cerrar {mes[:7]} "
+            "(el ajuste de conciliación se imputa al mes que abre)",
+            409,
+        )
+    if siguiente.estado is EstadoMes.CERRADO:
+        raise CierreError(
+            f"el mes {siguiente.mes[:7]} está cerrado; no es editable", 409
+        )
+
+    rubro_aj = await _rubro_ajuste()
+    recon = await _conciliar(mc, rubro_aj.id)
+    if not recon["dentro_de_umbral"]:
+        motivo = (
+            "hay bancos sin saldo reportado: " + ", ".join(recon["sin_dato"])
+            if recon["sin_dato"]
+            else f"la diferencia {money_str(recon['diferencia'])} supera el umbral "
+            f"{money_str(recon['umbral'])}"
+        )
+        raise CierreError(f"no se puede cerrar: {motivo}", 409)
+
+    r_m = recon["consolidado_reportado"]
+    diferencia = recon["diferencia"]
+    ancla_prev = siguiente.saldo_inicial_caja
+    client = MesControl.get_pymongo_collection().database.client
+    creado = {"ajuste_id": None}
+
+    async def _cerrar(session):
+        siguiente.saldo_inicial_caja = r_m  # M-2: re-anclar a R_M
+        await siguiente.save(session=session)
+        aj_id = None
+        if diferencia != 0:  # B-2: omitir el ajuste si no hay diferencia
+            tipo = TipoFlujo.INGRESO if diferencia > 0 else TipoFlujo.EGRESO
+            aj = Transaccion(
+                fecha=siguiente.mes,  # día-1 de M+1 (nit-9)
+                descripcion=f"Ajuste de conciliación cierre {mc.mes[:7]}",
+                valor=abs(diferencia),
+                tipo_flujo=tipo,
+                rubro_id=rubro_aj.id,
+                mes_id=siguiente.id,
+                banco=Banco.MANUAL,
+                id_banco=f"MAN-{new_ulid()}",
+            )
+            await aj.insert(session=session)
+            aj_id = str(aj.id)
+        creado["ajuste_id"] = aj_id
+        mc.estado = EstadoMes.CERRADO
+        mc.cerrado_por = usuario_id
+        mc.cerrado_at = now_utc()
+        mc.cierre_info = CierreInfo(
+            ancla_anterior_siguiente=ancla_prev,
+            diferencia=diferencia,
+            ajuste_tx_id=aj_id,
+        )
+        await mc.save(session=session)
+
+    async with await client.start_session() as session:
+        await session.with_transaction(_cerrar)
+
+    try:
+        await emit_audit(
+            AuditEvento.mes_cerrado,
+            entidad="mes",
+            entidad_id=str(mc.id),
+            actor_id=usuario_id,
+            metadata={
+                "mes": mes[:7],
+                "consolidado_reportado": money_str(r_m),
+                "caja_libro": money_str(recon["caja_libro"]),
+                "diferencia": money_str(diferencia),
+                "ajuste_tx_id": creado["ajuste_id"],
+            },
+        )
+    except Exception:
+        # Saga O1 (igual que la apertura certificada): el cierre FALLÓ (sin evento) →
+        # se borran sus artefactos y se revierte. No es mutar historia (§2.2.2): el
+        # cierre nunca se completó.
+        async def _revertir(session):
+            if creado["ajuste_id"]:
+                aj = await Transaccion.get(PydanticObjectId(creado["ajuste_id"]))
+                if aj is not None:
+                    await aj.delete(session=session)
+            siguiente.saldo_inicial_caja = ancla_prev
+            await siguiente.save(session=session)
+            mc.estado = EstadoMes.EN_EJECUCION
+            mc.cerrado_por = None
+            mc.cerrado_at = None
+            mc.cierre_info = None
+            await mc.save(session=session)
+
+        async with await client.start_session() as session:
+            await session.with_transaction(_revertir)
+        raise
+    return {
+        "mes": mes[:7],
+        "estado": mc.estado.value,
+        "diferencia": money_str(diferencia),
+        "ajuste_tx_id": creado["ajuste_id"],
+        "saldo_inicial_siguiente": money_str(r_m),
+    }
+
+
+async def reabrir_mes(*, mes: str, usuario_id: str) -> dict:
+    """Reapertura (Admin + step-up MFA): contra-asiento del ajuste (M-4) + restaura
+    el ancla previa + M→en_ejecucion. Transacción multi-doc + saga O1."""
+    mc = await _mes(mes)
+    if mc.estado is not EstadoMes.CERRADO:
+        raise CierreError(
+            f"solo se reabre un mes cerrado (está en '{mc.estado.value}')", 409
+        )
+    siguiente = await MesControl.find_one(MesControl.mes == _mes_siguiente(mc.mes))
+    if siguiente is not None and siguiente.estado is EstadoMes.CERRADO:
+        raise CierreError(
+            f"cierra en orden inverso: {siguiente.mes[:7]} sigue cerrado (LIFO)", 409
+        )
+    ci = mc.cierre_info
+    ancla_restaurar = ci.ancla_anterior_siguiente if ci else None
+    # saldo de M+1 ANTES de reabrir (= R_M re-anclado en el cierre) — para compensar.
+    saldo_sig_previo = siguiente.saldo_inicial_caja if siguiente is not None else None
+    client = MesControl.get_pymongo_collection().database.client
+    creado = {"contra_id": None}
+
+    async def _reabrir(session):
+        if ci and ci.ajuste_tx_id:
+            orig = await Transaccion.get(PydanticObjectId(ci.ajuste_tx_id))
+            if orig is not None:
+                inv = (
+                    TipoFlujo.EGRESO
+                    if orig.tipo_flujo == TipoFlujo.INGRESO
+                    else TipoFlujo.INGRESO
+                )
+                contra = Transaccion(
+                    fecha=orig.fecha,
+                    descripcion=f"Reverso ajuste conciliación {mc.mes[:7]}",
+                    valor=orig.valor,
+                    tipo_flujo=inv,
+                    rubro_id=orig.rubro_id,
+                    mes_id=orig.mes_id,
+                    banco=Banco.MANUAL,
+                    id_banco=f"MAN-{new_ulid()}",
+                    revierte_id=orig.id,
+                )
+                await contra.insert(session=session)
+                creado["contra_id"] = str(contra.id)
+        if siguiente is not None and ancla_restaurar is not None:
+            siguiente.saldo_inicial_caja = ancla_restaurar
+            await siguiente.save(session=session)
+        mc.estado = EstadoMes.EN_EJECUCION
+        mc.cerrado_por = None
+        mc.cerrado_at = None
+        mc.cierre_info = None
+        await mc.save(session=session)
+
+    async with await client.start_session() as session:
+        await session.with_transaction(_reabrir)
+
+    try:
+        await emit_audit(
+            AuditEvento.mes_reabierto,
+            entidad="mes",
+            entidad_id=str(mc.id),
+            actor_id=usuario_id,
+            metadata={"mes": mes[:7], "contra_asiento_id": creado["contra_id"]},
+        )
+    except Exception:
+
+        async def _revertir(session):
+            if creado["contra_id"]:
+                c = await Transaccion.get(PydanticObjectId(creado["contra_id"]))
+                if c is not None:
+                    await c.delete(session=session)
+            if siguiente is not None and saldo_sig_previo is not None:
+                siguiente.saldo_inicial_caja = saldo_sig_previo
+                await siguiente.save(session=session)
+            mc.estado = EstadoMes.CERRADO
+            mc.cerrado_por = usuario_id
+            mc.cerrado_at = now_utc()
+            mc.cierre_info = ci
+            await mc.save(session=session)
+
+        async with await client.start_session() as session:
+            await session.with_transaction(_revertir)
+        raise
+    return {
+        "mes": mes[:7],
+        "estado": mc.estado.value,
+        "contra_asiento_id": creado["contra_id"],
+    }
diff --git a/backend/app/domain/mes_control.py b/backend/app/domain/mes_control.py
index fb175ff..163a855 100644
--- a/backend/app/domain/mes_control.py
+++ b/backend/app/domain/mes_control.py
@@ -47,6 +47,20 @@ class MesCerradoError(Exception):
     """Se intentó editar un mes cerrado (histórico inmutable, regla 4)."""
 
 
+class CierreInfo(BaseModel):
+    """Rastro del cierre para poder REVERTIR en la reapertura (M-4).
+
+    `ancla_anterior_siguiente` = `saldo_inicial_caja(M+1)` ANTES de re-anclarlo a R_M
+    (M-2); la reapertura lo restaura. `diferencia` = R_M − C_M (puede ser negativa).
+    `ajuste_tx_id` = id del 'Ajuste de conciliación' creado en M+1 (None si dif==0)."""
+
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    ancla_anterior_siguiente: Money
+    diferencia: Money
+    ajuste_tx_id: str | None = None
+
+
 class SaldoBanco(BaseModel):
     model_config = ConfigDict(strict=True, extra="forbid")
 
@@ -77,6 +91,7 @@ class MesControl(Document):
     definido_at: datetime | None = None
     cerrado_por: str | None = None
     cerrado_at: datetime | None = None
+    cierre_info: CierreInfo | None = None  # rastro para revertir (M-4)
 
     class Settings:
         name = MESES_CONTROL_COLLECTION
diff --git a/backend/app/domain/transaccion.py b/backend/app/domain/transaccion.py
index 0b1f404..dfb3725 100644
--- a/backend/app/domain/transaccion.py
+++ b/backend/app/domain/transaccion.py
@@ -85,6 +85,9 @@ class Transaccion(Document):
     carga_id: PydanticObjectId | None = None
     clasificada_por: str | None = None
     clasificada_at: datetime | None = None
+    # M-4: contra-asiento del 'Ajuste de conciliación' al reabrir → apunta al ajuste
+    # original que revierte (la Transaccion es inmutable, §2.2.2: nunca se borra).
+    revierte_id: PydanticObjectId | None = None
     pago_planeado_id: PydanticObjectId | None = None
     factura_id: PydanticObjectId | None = None
     regla_id: PydanticObjectId | None = None
diff --git a/backend/app/presupuesto/service.py b/backend/app/presupuesto/service.py
index 54a46b0..a5951ba 100644
--- a/backend/app/presupuesto/service.py
+++ b/backend/app/presupuesto/service.py
@@ -265,7 +265,10 @@ async def aprobar_presupuesto(*, mes: str, usuario_id: str) -> dict:
             if ln.monto_definido is None:  # D2: aceptar la recomendación del motor
                 ln.monto_definido = ln.monto_sugerido
                 await ln.save(session=session)
-        mc.estado = EstadoMes.DEFINIDO
+        # M-1 (Kimi Sprint 4): la aprobación deja el mes en EN_EJECUCION (US-02: "el
+        # mes pasa a en_ejecucion"). `definido_por/at` + el evento presupuesto.definido
+        # son el registro de la aprobación; no se usa un estado 'definido' en reposo.
+        mc.estado = EstadoMes.EN_EJECUCION
         mc.definido_por = usuario_id
         mc.definido_at = now_utc()
         await mc.save(session=session)
diff --git a/backend/tests/test_cierre_conciliacion.py b/backend/tests/test_cierre_conciliacion.py
new file mode 100644
index 0000000..52b048d
--- /dev/null
+++ b/backend/tests/test_cierre_conciliacion.py
@@ -0,0 +1,255 @@
+# backend/tests/test_cierre_conciliacion.py
+"""Conciliación por banco + guardas del cierre/reapertura — parte mongomock.
+
+MARCADO PARA AUDITORÍA KIMI (regla 8 + §2.4 + M-3 conciliación).
+
+La conciliación es compute-only (mongomock la soporta): ancla por banco, 'sin dato'
+(regla 7), exclusión del rubro de ajuste. La transacción multi-doc del cierre y la
+convergencia viven en el archivo real-mongo hermano; aquí las GUARDAS (RBAC/estado/
+M+1/umbral) que retornan ANTES de la transacción."""
+
+from decimal import Decimal
+
+import httpx
+import pytest_asyncio
+from app.audit.service import configure_audit, reset_audit
+from app.auth import passwords, repository
+from app.auth.models import User
+from app.auth.roles import Role
+from app.cierre import service
+from app.config import get_settings
+from app.domain import DOMAIN_DOCUMENTS
+from app.domain.configuracion import Configuracion
+from app.domain.mes_control import EstadoMes, MesControl, SaldoBanco
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
+        ("admin@roddos.com", Role.admin),
+    ]:
+        await repository.create_user(
+            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
+        )
+    # semilla: umbral + rubros (sistema 'Ajuste de conciliación' + uno operativo)
+    await Configuracion(
+        clave="UMBRAL_DIF_BANCO_CIERRE",
+        valor_decimal=Decimal("50000"),
+        vigente_desde="2026-01-01",
+    ).insert()
+    await Rubro(
+        grupo="otros", nombre="Ajuste de conciliación", orden=98, es_sistema=True
+    ).insert()
+    await Rubro(
+        grupo="operacion", nombre="Arriendos", orden=4, es_sistema=False
+    ).insert()
+    transport = httpx.ASGITransport(app=app)
+    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
+        yield ac
+    repository.reset_auth()
+    reset_audit()
+    get_settings.cache_clear()
+
+
+async def _token(ac, email="admin@roddos.com") -> dict:
+    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
+    return {"Authorization": f"Bearer {r.json()['access_token']}"}
+
+
+async def _rubro(nombre) -> Rubro:
+    return await Rubro.find_one(Rubro.nombre == nombre)
+
+
+async def _mes(mes, estado, saldo_inicial="100", bancos=None) -> MesControl:
+    mc = MesControl(
+        mes=mes,
+        saldo_inicial_caja=Decimal(saldo_inicial),
+        estado=estado,
+        saldos_banco=bancos or [],
+    )
+    await mc.insert()
+    return mc
+
+
+async def _tx(mc, rubro, valor, tipo, banco="bancolombia", fecha=None):
+    import app.core.ulid as u
+
+    await Transaccion(
+        fecha=fecha or f"{mc.mes[:7]}-10",
+        descripcion="mov",
+        valor=Decimal(valor),
+        tipo_flujo=tipo,
+        rubro_id=rubro.id,
+        mes_id=mc.id,
+        banco=banco,
+        id_banco=f"MAN-{u.new_ulid()}",
+    ).insert()
+
+
+# ── CONCILIACIÓN (compute-only) ─────────────────────────────────────────────
+
+
+async def test_conciliacion_reporte_y_diferencia(api):
+    h = await _token(api, "fin@roddos.com")
+    sb = SaldoBanco(
+        banco="bancolombia", saldo=Decimal("118"), fecha_reporte="2026-07-31"
+    )
+    mc = await _mes("2026-07-01", EstadoMes.EN_EJECUCION, "100", [sb])
+    arr = await _rubro("Arriendos")
+    await _tx(mc, arr, "50", "ingreso")
+    await _tx(mc, arr, "30", "egreso")
+    r = await api.post("/api/v1/meses/2026-07/cierre/conciliacion", headers=h)
+    assert r.status_code == 200
+    d = r.json()
+    assert d["caja_libro"] == "120.00"  # 100 + 50 − 30
+    assert d["consolidado_reportado"] == "118.00"
+    assert d["diferencia"] == "-2.00"  # 118 − 120
+    assert d["dentro_de_umbral"] is True
+    assert d["sin_dato"] == []
+
+
+async def test_conciliacion_excluye_rubro_ajuste(api):
+    h = await _token(api, "fin@roddos.com")
+    sb = SaldoBanco(
+        banco="bancolombia", saldo=Decimal("120"), fecha_reporte="2026-07-31"
+    )
+    mc = await _mes("2026-07-01", EstadoMes.EN_EJECUCION, "100", [sb])
+    arr = await _rubro("Arriendos")
+    aj = await _rubro("Ajuste de conciliación")
+    await _tx(mc, arr, "50", "ingreso")
+    await _tx(mc, arr, "30", "egreso")
+    await _tx(mc, aj, "999", "egreso")  # NO debe contar en la caja del libro
+    r = await api.post("/api/v1/meses/2026-07/cierre/conciliacion", headers=h)
+    assert r.json()["caja_libro"] == "120.00"  # el ajuste de 999 se excluye
+
+
+async def test_conciliacion_sin_dato_por_banco(api):
+    h = await _token(api, "fin@roddos.com")
+    sb = SaldoBanco(
+        banco="bancolombia", saldo=Decimal("100"), fecha_reporte="2026-07-31"
+    )
+    mc = await _mes("2026-07-01", EstadoMes.EN_EJECUCION, "100", [sb])
+    arr = await _rubro("Arriendos")
+    await _tx(mc, arr, "10", "egreso", banco="bbva")  # bbva sin saldo reportado
+    r = await api.post("/api/v1/meses/2026-07/cierre/conciliacion", headers=h)
+    d = r.json()
+    assert "bbva" in d["sin_dato"]
+    assert d["dentro_de_umbral"] is False  # no se puede conciliar bbva
+
+
+async def test_conciliacion_no_en_ejecucion_409(api):
+    h = await _token(api, "fin@roddos.com")
+    await _mes("2026-07-01", EstadoMes.SUGERIDO)
+    r = await api.post("/api/v1/meses/2026-07/cierre/conciliacion", headers=h)
+    assert r.status_code == 409
+
+
+async def test_cierre_operativo_consulta_403(api):
+    h = await _token(api, "consulta@roddos.com")
+    await _mes("2026-07-01", EstadoMes.EN_EJECUCION)
+    r = await api.post("/api/v1/meses/2026-07/cierre/conciliacion", headers=h)
+    assert r.status_code == 403
+
+
+# ── CONFIRMAR CIERRE — guardas (antes de la transacción) ────────────────────
+
+
+async def test_confirmar_no_admin_403(api):
+    for email in ("fin@roddos.com", "consulta@roddos.com"):
+        h = await _token(api, email)
+        r = await api.post(
+            "/api/v1/meses/2026-07/cierre/confirmar",
+            headers={**h, "Idempotency-Key": f"k-{email}"},
+        )
+        assert r.status_code == 403, email
+
+
+async def test_confirmar_mes_inexistente_404(api):
+    h = await _token(api)
+    r = await api.post(
+        "/api/v1/meses/2026-07/cierre/confirmar", headers={**h, "Idempotency-Key": "k1"}
+    )
+    assert r.status_code == 404
+
+
+async def test_confirmar_no_en_ejecucion_409(api):
+    h = await _token(api)
+    await _mes("2026-07-01", EstadoMes.SUGERIDO)
+    r = await api.post(
+        "/api/v1/meses/2026-07/cierre/confirmar", headers={**h, "Idempotency-Key": "k1"}
+    )
+    assert r.status_code == 409
+
+
+async def test_confirmar_sin_mes_siguiente_409(api):
+    h = await _token(api)
+    sb = SaldoBanco(
+        banco="bancolombia", saldo=Decimal("100"), fecha_reporte="2026-07-31"
+    )
+    await _mes("2026-07-01", EstadoMes.EN_EJECUCION, "100", [sb])
+    r = await api.post(
+        "/api/v1/meses/2026-07/cierre/confirmar", headers={**h, "Idempotency-Key": "k1"}
+    )
+    assert r.status_code == 409  # agosto no está abierto (D2)
+
+
+async def test_confirmar_diferencia_supera_umbral_409(api):
+    h = await _token(api)
+    # umbral chico → la diferencia de 2 lo supera
+    await Configuracion(
+        clave="UMBRAL_DIF_BANCO_CIERRE",
+        valor_decimal=Decimal("1"),
+        vigente_desde="2026-06-01",
+    ).insert()
+    sb = SaldoBanco(
+        banco="bancolombia", saldo=Decimal("118"), fecha_reporte="2026-07-31"
+    )
+    mc = await _mes("2026-07-01", EstadoMes.EN_EJECUCION, "100", [sb])
+    await _mes("2026-08-01", EstadoMes.SUGERIDO, "0")  # M+1 abierto
+    arr = await _rubro("Arriendos")
+    await _tx(mc, arr, "50", "ingreso")
+    await _tx(mc, arr, "30", "egreso")  # C_M=120, R_M=118, dif=-2 > umbral 1
+    r = await api.post(
+        "/api/v1/meses/2026-07/cierre/confirmar", headers={**h, "Idempotency-Key": "k1"}
+    )
+    assert r.status_code == 409
+
+
+# ── REAPERTURA — guardas ────────────────────────────────────────────────────
+
+
+async def test_reabrir_no_cerrado_409_service(api):
+    # guarda de estado a nivel de servicio (retorna antes de cualquier transacción).
+    await _mes("2026-07-01", EstadoMes.EN_EJECUCION)
+    try:
+        await service.reabrir_mes(mes="2026-07-01", usuario_id="u1")
+        raise AssertionError("debió fallar")
+    except service.CierreError as e:
+        assert e.status == 409
+
+
+async def test_reabrir_no_admin_403(api):
+    h = await _token(api, "fin@roddos.com")
+    await _mes("2026-07-01", EstadoMes.CERRADO)
+    r = await api.post("/api/v1/meses/2026-07/reabrir", headers=h)
+    assert r.status_code == 403
diff --git a/backend/tests/test_cierre_realmongo.py b/backend/tests/test_cierre_realmongo.py
new file mode 100644
index 0000000..dd5e464
--- /dev/null
+++ b/backend/tests/test_cierre_realmongo.py
@@ -0,0 +1,261 @@
+# backend/tests/test_cierre_realmongo.py
+"""Cierre de mes — TRANSACCIÓN MULTI-DOC (regla 8) contra Mongo REAL.
+
+MARCADO PARA AUDITORÍA KIMI (los 8 tests exigidos en el certificado R-PLAN 9.4).
+
+mongomock NO soporta transacciones → @requires_real_mongo (CI: replica set). Cubre:
+  1. dorado numérico (cuadra a 118 por ambas vías) · 2. exclusión del rubro en la
+  disponible · 3. contra-asiento + ancla restaurada al reabrir · 4. doble cierre
+  abortado · 5. replay Idempotency-Key sin duplicar · 6-7. convergencia en los 2
+  puntos de fallo (abort de datos / fallo de emit) · 8. ajuste omitido si dif==0."""
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
+from app.cierre import service
+from app.config import get_settings
+from app.domain import DOMAIN_DOCUMENTS
+from app.domain.configuracion import Configuracion
+from app.domain.mes_control import EstadoMes, MesControl, SaldoBanco
+from app.domain.rubro import Rubro
+from app.domain.transaccion import Transaccion
+from beanie import init_beanie
+from motor.motor_asyncio import AsyncIOMotorClient
+
+PWD = "clave-larga-1234"
+
+
+@pytest.mark.requires_real_mongo
+class TestCierreReal:
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
+        dbname = "compas_test_cierre"
+        await client.drop_database(dbname)
+        db = client[dbname]
+        await init_beanie(database=db, document_models=DOMAIN_DOCUMENTS)
+        repository.configure_auth(client, dbname)
+        configure_audit(client, dbname)
+        await repository.create_user(
+            User(
+                email="admin@roddos.com",
+                password_hash=passwords.hash_password(PWD),
+                rol=Role.admin,
+            )
+        )
+        await Configuracion(
+            clave="UMBRAL_DIF_BANCO_CIERRE",
+            valor_decimal=Decimal("50000"),
+            vigente_desde="2026-01-01",
+        ).insert()
+        await Rubro(
+            grupo="otros", nombre="Ajuste de conciliación", orden=98, es_sistema=True
+        ).insert()
+        await Rubro(
+            grupo="operacion", nombre="Arriendos", orden=4, es_sistema=False
+        ).insert()
+        transport = httpx.ASGITransport(app=app)
+        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
+            yield ac, db
+        repository.reset_auth()
+        reset_audit()
+        await client.drop_database(dbname)
+        client.close()
+        get_settings.cache_clear()
+
+    async def _token(self, ac):
+        r = await ac.post(
+            "/api/v1/auth/login", json={"email": "admin@roddos.com", "password": PWD}
+        )
+        return {"Authorization": f"Bearer {r.json()['access_token']}"}
+
+    async def _sembrar(self, reportado="118"):
+        """M (jun) en ejecución con C_M=120 (100+50−30) y R_M=`reportado`; M+1 (jul)
+        abierto con saldo provisional 0."""
+        arr = await Rubro.find_one(Rubro.nombre == "Arriendos")
+        sb = SaldoBanco(
+            banco="bancolombia",
+            saldo=Decimal(reportado),
+            fecha_reporte="2026-06-30",
+        )
+        jun = MesControl(
+            mes="2026-06-01",
+            saldo_inicial_caja=Decimal("100"),
+            estado=EstadoMes.EN_EJECUCION,
+            saldos_banco=[sb],
+        )
+        await jun.insert()
+        jul = MesControl(
+            mes="2026-07-01",
+            saldo_inicial_caja=Decimal("0"),
+            estado=EstadoMes.SUGERIDO,
+        )
+        await jul.insert()
+        import app.core.ulid as u
+
+        for valor, tipo in [("50", "ingreso"), ("30", "egreso")]:
+            await Transaccion(
+                fecha="2026-06-10",
+                descripcion="mov",
+                valor=Decimal(valor),
+                tipo_flujo=tipo,
+                rubro_id=arr.id,
+                mes_id=jun.id,
+                banco="bancolombia",
+                id_banco=f"MAN-{u.new_ulid()}",
+            ).insert()
+        return jun, jul, arr
+
+    async def _confirmar(self, ac, h, key="c1"):
+        return await ac.post(
+            "/api/v1/meses/2026-06/cierre/confirmar",
+            headers={**h, "Idempotency-Key": key},
+        )
+
+    async def test_dorado_numerico_cuadra_a_118(self, entorno):
+        ac, db = entorno
+        h = await self._token(ac)
+        jun, jul, arr = await self._sembrar("118")
+        r = await self._confirmar(ac, h)
+        assert r.status_code == 200
+        j = r.json()
+        assert j["diferencia"] == "-2.00"
+        assert j["saldo_inicial_siguiente"] == "118.00"
+        # jun cerrado + cierre_info
+        jun2 = await MesControl.get(jun.id)
+        assert jun2.estado is EstadoMes.CERRADO
+        assert jun2.cierre_info.diferencia == Decimal("-2")
+        assert jun2.cierre_info.ancla_anterior_siguiente == Decimal("0")
+        # ajuste egreso 2 en jul, rubro de sistema
+        aj = await Transaccion.get(
+            __import__("beanie").PydanticObjectId(j["ajuste_tx_id"])
+        )
+        assert aj.valor == Decimal("2") and aj.tipo_flujo.value == "egreso"
+        assert aj.mes_id == jul.id and aj.fecha == "2026-07-01"
+        # M+1 re-anclado a R_M
+        jul2 = await MesControl.get(jul.id)
+        assert jul2.saldo_inicial_caja == Decimal("118")
+        # disponible de jul = 118 (el ajuste se EXCLUYE) → cuadra por ambas vías
+        rubro_aj = await service._rubro_ajuste()
+        disp = await service._caja_libro(jul.id, rubro_aj.id, jul2.saldo_inicial_caja)
+        assert disp == Decimal("118")
+        assert await db["audit_log"].count_documents({"evento": "mes.cerrado"}) == 1
+
+    async def test_idempotencia_replay(self, entorno):
+        ac, db = entorno
+        h = await self._token(ac)
+        await self._sembrar("118")
+        r1 = await self._confirmar(ac, h, "kx")
+        r2 = await self._confirmar(ac, h, "kx")
+        assert r1.status_code == 200 and r2.status_code == 200
+        assert r1.json() == r2.json()
+        assert await db["audit_log"].count_documents({"evento": "mes.cerrado"}) == 1
+
+    async def test_doble_cierre_distinta_key_409(self, entorno):
+        ac, db = entorno
+        h = await self._token(ac)
+        await self._sembrar("118")
+        assert (await self._confirmar(ac, h, "k1")).status_code == 200
+        r2 = await self._confirmar(ac, h, "k2")  # otra key, mes ya cerrado
+        assert r2.status_code == 409
+
+    async def test_ajuste_omitido_si_diferencia_cero(self, entorno):
+        ac, db = entorno
+        h = await self._token(ac)
+        jun, jul, arr = await self._sembrar("120")  # R_M = C_M = 120 → dif 0
+        r = await self._confirmar(ac, h)
+        assert r.status_code == 200
+        assert r.json()["ajuste_tx_id"] is None  # B-2: no se crea ajuste
+        assert (await MesControl.get(jul.id)).saldo_inicial_caja == Decimal("120")
+        # no hay transacciones en jul
+        assert await Transaccion.find(Transaccion.mes_id == jul.id).count() == 0
+
+    async def test_reabrir_contra_asiento_y_restaura_ancla(self, entorno):
+        ac, db = entorno
+        h = await self._token(ac)
+        jun, jul, arr = await self._sembrar("118")
+        await self._confirmar(ac, h)
+        aj_id = (await MesControl.get(jun.id)).cierre_info.ajuste_tx_id
+        # reabrir a nivel de servicio (evita el step-up MFA del router)
+        await service.reabrir_mes(mes="2026-06-01", usuario_id="admin")
+        jun2 = await MesControl.get(jun.id)
+        assert jun2.estado is EstadoMes.EN_EJECUCION
+        assert jun2.cierre_info is None
+        # el ajuste original NO se borra (inmutable §2.2.2); hay un contra-asiento
+        from beanie import PydanticObjectId
+
+        orig = await Transaccion.get(PydanticObjectId(aj_id))
+        assert orig is not None  # sigue existiendo
+        contra = await Transaccion.find_one(
+            Transaccion.revierte_id == PydanticObjectId(aj_id)
+        )
+        assert contra is not None
+        assert contra.tipo_flujo.value == "ingreso"  # invertido (orig era egreso)
+        assert contra.valor == Decimal("2")
+        # ancla de jul restaurada al valor previo (0)
+        assert (await MesControl.get(jul.id)).saldo_inicial_caja == Decimal("0")
+        assert await db["audit_log"].count_documents({"evento": "mes.reabierto"}) == 1
+
+    async def test_convergencia_falla_emit_compensa(self, entorno, monkeypatch):
+        ac, db = entorno
+        h = await self._token(ac)
+        jun, jul, arr = await self._sembrar("118")
+
+        async def boom(*a, **k):
+            raise RuntimeError("auditoría caída")
+
+        monkeypatch.setattr("app.cierre.service.emit_audit", boom)
+        with pytest.raises(RuntimeError):
+            await self._confirmar(ac, h, "kf")
+        # compensado: jun sigue en ejecución, sin ajuste en jul, ancla restaurada
+        assert (await MesControl.get(jun.id)).estado is EstadoMes.EN_EJECUCION
+        assert (await MesControl.get(jul.id)).saldo_inicial_caja == Decimal("0")
+        assert await Transaccion.find(Transaccion.mes_id == jul.id).count() == 0
+        assert await db["audit_log"].count_documents({"evento": "mes.cerrado"}) == 0
+        # converge al reintentar
+        monkeypatch.undo()
+        assert (await self._confirmar(ac, h, "kf2")).status_code == 200
+        assert (await MesControl.get(jun.id)).estado is EstadoMes.CERRADO
+
+    async def test_convergencia_abort_datos(self, entorno, monkeypatch):
+        ac, db = entorno
+        h = await self._token(ac)
+        jun, jul, arr = await self._sembrar("118")
+
+        orig = MesControl.save
+
+        async def flaky(self, *a, **k):
+            # falla al escribir el estado CERRADO (última escritura) → rollback total
+            if k.get("session") is not None and self.estado is EstadoMes.CERRADO:
+                raise RuntimeError("caída a mitad de la transacción")
+            return await orig(self, *a, **k)
+
+        monkeypatch.setattr(MesControl, "save", flaky)
+        with pytest.raises(RuntimeError):
+            await self._confirmar(ac, h, "ka")
+        monkeypatch.undo()
+        # rollback total: jun en ejecución, sin ajuste, jul intacto
+        assert (await MesControl.get(jun.id)).estado is EstadoMes.EN_EJECUCION
+        assert await Transaccion.find(Transaccion.mes_id == jul.id).count() == 0
+        assert (await MesControl.get(jul.id)).saldo_inicial_caja == Decimal("0")
+        # converge
+        assert (await self._confirmar(ac, h, "ka2")).status_code == 200
+        assert (await MesControl.get(jun.id)).estado is EstadoMes.CERRADO
diff --git a/backend/tests/test_presupuesto_aprobar_realmongo.py b/backend/tests/test_presupuesto_aprobar_realmongo.py
index 997c3f9..24b053e 100644
--- a/backend/tests/test_presupuesto_aprobar_realmongo.py
+++ b/backend/tests/test_presupuesto_aprobar_realmongo.py
@@ -114,14 +114,14 @@ class TestAprobarReal:
             headers={**h, "Idempotency-Key": "ap-1"},
         )
         assert r.status_code == 200
-        assert r.json()["estado"] == "definido"
+        assert r.json()["estado"] == "en_ejecucion"  # M-1: aprobar → en_ejecucion
         # acotada conserva; sin acotar toma el sugerido (D2)
         a2 = await PresupuestoLinea.get(acotada.id)
         s2 = await PresupuestoLinea.get(sin_acotar.id)
         assert a2.monto_definido == Decimal("1200000")
         assert s2.monto_definido == Decimal("1000000")
         mc2 = await MesControl.get(mc.id)
-        assert mc2.estado is EstadoMes.DEFINIDO
+        assert mc2.estado is EstadoMes.EN_EJECUCION  # M-1
         assert mc2.definido_por is not None and mc2.definido_at is not None
         n = await db["audit_log"].count_documents({"evento": "presupuesto.definido"})
         assert n == 1
@@ -174,7 +174,7 @@ class TestAprobarReal:
             headers={**h, "Idempotency-Key": "ap-a"},
         )
         assert r.status_code == 200
-        assert (await MesControl.get(mc.id)).estado is EstadoMes.DEFINIDO
+        assert (await MesControl.get(mc.id)).estado is EstadoMes.EN_EJECUCION
         assert (await PresupuestoLinea.get(sin_acotar.id)).monto_definido == Decimal(
             "1000000"
         )
@@ -214,4 +214,4 @@ class TestAprobarReal:
             headers={**h, "Idempotency-Key": "ap-b"},
         )
         assert r.status_code == 200
-        assert (await MesControl.get(mc.id)).estado is EstadoMes.DEFINIDO
+        assert (await MesControl.get(mc.id)).estado is EstadoMes.EN_EJECUCION
```
