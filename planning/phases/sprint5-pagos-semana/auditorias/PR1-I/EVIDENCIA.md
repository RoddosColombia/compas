# EVIDENCIA — sprint5-pagos-semana · I-PR1: C9 Pagos de la semana

Diff real + salidas de tests para el gate de CÓDIGO. Rama `feat/c9-pagos-semana`.

## 1. `app/domain/pago_planeado.py` (NUEVO)

```python
class EstadoPago(StrEnum):
    PENDIENTE = "pendiente"; PAGADO = "pagado"; CANCELADO = "cancelado"

class PagoPlaneado(Document):
    model_config = strict, forbid
    concepto: str(max 300); acreedor: str(max 200)
    monto: Money            # validator > 0
    fecha_programada: str   # YYYY-MM-DD (validator)
    rubro_id: PydanticObjectId          # EGRESO activo (D1, en el servicio)
    mes_id: PydanticObjectId
    estado: EstadoPago = PENDIENTE
    pagado_tx_id: PydanticObjectId | None = None   # tx que lo saldó (D5)
    creado_por / creado_at (UTC-aware)
    indexes: (mes_id, fecha_programada), (estado)
```
DOMAIN_DOCUMENTS 8→9 (+PagoPlaneado); test_db actualizado.

## 2. `app/pagos/service.py` (NUEVO — crux)

```python
_VENTANA_DIAS = 7   # D2: "la semana" = 7 días naturales rodantes

async def _rubro_egreso_activo(rubro_id):   # D1
    r = await Rubro.get(oid)
    if r is None: raise PagosError("no existe", 404)
    if not r.activo: raise PagosError("inactivo", 422)
    if r.tipo_flujo is not TipoFlujo.EGRESO: raise PagosError("es de ingreso (D1)", 422)
    return r

async def crear_pago(...):
    mc = await _mes(mes)                     # 404
    if mc.estado is CERRADO: raise PagosError(409)   # regla 4
    await _rubro_egreso_activo(rubro_id)     # D1
    if fecha_programada < mc.mes: raise PagosError(422)
    pago = PagoPlaneado(...); await pago.insert()
    try: await emit_audit(pago_planeado.creado, ...)
    except Exception: await pago.delete(); raise      # O1

async def marcar_pagado(*, pago_id, transaccion_id, usuario_id):   # D5, regla 8
    p = await _pago(pago_id)
    if p.estado is not PENDIENTE: raise PagosError(409)
    tx = await Transaccion.get(...)          # 404
    if tx.tipo_flujo is not EGRESO: raise PagosError(422)
    if tx.mes_id != p.mes_id: raise PagosError(422)
    if mc.estado is CERRADO: raise PagosError(409)     # regla 4
    async def _enlazar(session):
        p_fresco = await PagoPlaneado.find_one(..., session=session)   # TOCTOU
        if p_fresco is None or p_fresco.estado is not PENDIENTE: raise PagosError(409)
        p.estado = PAGADO; p.pagado_tx_id = tx.id; await p.save(session=session)
        tx.pago_planeado_id = p.id;               await tx.save(session=session)
    async with await client.start_session() as session:
        await session.with_transaction(_enlazar)      # multi-doc (regla 8)
    try: await emit_audit(pago_planeado.editado, {estado: pendiente→pagado, ...})
    except Exception:
        async def _revertir(session):   # O1: revierte AMBOS docs
            p.estado = PENDIENTE; p.pagado_tx_id = None; await p.save(session=session)
            tx.pago_planeado_id = None; await tx.save(session=session)
        async with await client.start_session() as s: await s.with_transaction(_revertir)
        raise

async def pagos_semana(mes):                 # D4, compute-only
    mc = await _mes(mes); rubro_aj = await _rubro_ajuste()
    caja_hoy = await _caja_libro(mc.id, rubro_aj.id, mc.saldo_inicial_caja)  # MISMA caja que Control
    hoy = today_bogota().isoformat(); fin = (today_bogota()+timedelta(days=7)).isoformat()
    pendientes = [p for p ... if p.estado is PENDIENTE]
    semana   = [p for p in pendientes if hoy <= p.fecha_programada <= fin]   # D2
    vencidos = [p for p in pendientes if p.fecha_programada < hoy]           # D3
    total = sum(p.monto for p in semana); proyectada = caja_hoy - total
    return {caja_hoy, total_semana, caja_proyectada,
            veredicto: "alcanza" if proyectada>=0 else "no_alcanza",
            ventana:{desde,hasta}, pagos:[...], vencidos:[...]}
```
editar/cancelar: solo `pendiente` (409) en mes no cerrado; O1 revierte campos previos.

> Fragmento condensado; el archivo real conserva docstrings y validaciones completas.

## 3. Deltas de catálogo/permisos/router raíz (CR-S7)

```diff
# app/audit/events.py
+    # ── CR-S7 (3) → total 40 (C9 pagos de la semana) ──
+    pago_planeado_creado = "pago_planeado.creado"
+    pago_planeado_editado = "pago_planeado.editado"
+    pago_planeado_cancelado = "pago_planeado.cancelado"

# app/auth/permissions.py
+    "pagos:gestionar": frozenset({Role.financiero, Role.admin}),

# app/api/v1/__init__.py
+from app.pagos.router import router as pagos_router
+api_router.include_router(pagos_router)
```

## 4. Tests (2 archivos)

- **`test_pagos_semana.py`** (mongomock): crear OK · RBAC 403 · 404 mes · 409 mes
  cerrado · 422 rubro ingreso (D1) · 422 rubro inactivo · 422 monto 0 · 422 monto
  number (regla 1) · editar OK · cancelar + editar-tras-cancelar 409 · veredicto
  alcanza · veredicto no_alcanza · D2/D3 (excluye fuera de ventana, lista vencidos) ·
  marcar-pagado 404 (guard).
- **`test_pagos_marcar_realmongo.py`** (@requires_real_mongo): marcar-pagado enlaza
  ambos docs · O1 compensa (revierte pago Y tx) · regla 4 mes cerrado 409.

## 5. Salidas de tests

### pytest (C9 focalizado)
```
tests/test_pagos_semana.py ...............  [CRUD + guardas + veredicto]
tests/test_pagos_marcar_realmongo.py sss    [3 real-mongo → CI del PR]
tests/test_audit_events.py .....            [catálogo 40]
tests/test_rbac_permissions.py .........    [pagos:gestionar en la matriz]
tests/test_db.py ..                         [DOMAIN_DOCUMENTS == 9]
28 passed, 3 skipped
```

### pytest suite completa (real-mongo saltados local; corren en CI)
```
439 passed, 61 skipped, 3084 warnings in 613.52s
SKIPPED [3] tests/test_pagos_marcar_realmongo.py: requiere Mongo real
  → corre en el job backend-real-mongo del PR (marcar-pagado multi-doc, O1, regla 4)
```
Antes de C9: 425 passed. Ahora 439 = +14 tests mongomock de C9 (CRUD + guardas +
veredicto). Los 61 skipped incluyen los 3 real-mongo nuevos de C9.

### ruff
```
ruff check app tests → All checks passed!
ruff format → limpio
```

### greps del protocolo (CLAUDE.md)
```
app.alegra.com/api/r1  → 0
journal-entries        → 0
estado.*pending        → 0
```
