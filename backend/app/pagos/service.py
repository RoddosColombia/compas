# backend/app/pagos/service.py
"""C9/S5-01 — Pagos de la semana (CR-S7, GO CEO 2026-07-23; Kimi retro 25-jul).

MARCADO PARA AUDITORÍA KIMI (D1 coherencia de tipo + regla 4 + regla 8 marcar-pagado
+ saga O1 + D4 reuso de _caja_libro).

- **CRUD de PagoPlaneado:** crear/editar/cancelar/listar. Cada mutación valida el mes
  (no cerrado, regla 4) y el rubro destino (EGRESO activo, D1). Auditoría fail-closed
  O1 (estándar C1/B-5): si el emit falla, compensa y propaga.
- **marcar-pagado (D5):** enlaza el pago a una Transaccion EXISTENTE (egreso, mismo
  mes, no cerrado) en TRANSACCIÓN MULTI-DOC (regla 8): pago→pagado + pagado_tx_id y
  tx.pago_planeado_id. La tx solo GANA el FK (inmutable §2.2). El matching automático
  queda fuera (manual explícito).
- **veredicto (D4):** GET pagos-semana reusa `_caja_libro` (la MISMA caja de la Vista
  Control) — una sola verdad de "caja disponible". caja_proyectada = caja_hoy −
  Σ pagos de [hoy, hoy+7d]. Vencidos (fecha < hoy) van aparte (D3, fail-loud)."""

from datetime import timedelta
from decimal import Decimal

from beanie import PydanticObjectId

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cierre.service import _caja_libro, _rubro_ajuste
from app.core.money import money_str
from app.core.time import now_utc, today_bogota
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.pago_planeado import EstadoPago, PagoPlaneado
from app.domain.rubro import Rubro, TipoFlujo
from app.domain.transaccion import Transaccion

_VENTANA_DIAS = 7  # D2: "la semana" = 7 días naturales rodantes desde hoy


class PagosError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


async def _mes(mes: str) -> MesControl:
    mc = await MesControl.find_one(MesControl.mes == mes)
    if mc is None:
        raise PagosError(f"el mes {mes[:7]} no existe", 404)
    return mc


async def _rubro_egreso_activo(rubro_id: str) -> Rubro:
    """D1: el destino debe ser un rubro EGRESO activo (un pago no calza en ingreso)."""
    try:
        oid = PydanticObjectId(rubro_id)
    except Exception as e:
        raise PagosError(f"rubro_id inválido: {rubro_id}", 422) from e
    r = await Rubro.get(oid)
    if r is None:
        raise PagosError("el rubro destino no existe", 404)
    if not r.activo:
        raise PagosError(f"el rubro '{r.nombre}' está inactivo", 422)
    if r.tipo_flujo is not TipoFlujo.EGRESO:
        raise PagosError(
            f"el rubro '{r.nombre}' es de ingreso; un pago es egreso (D1)", 422
        )
    return r


async def crear_pago(
    *,
    mes: str,
    concepto: str,
    acreedor: str,
    monto: Decimal,
    fecha_programada: str,
    rubro_id: str,
    usuario_id: str,
) -> PagoPlaneado:
    mc = await _mes(mes)
    if mc.estado is EstadoMes.CERRADO:  # regla 4
        raise PagosError(f"el mes {mes[:7]} está cerrado y es inmutable", 409)
    await _rubro_egreso_activo(rubro_id)
    if fecha_programada < mc.mes:
        raise PagosError(
            f"fecha_programada {fecha_programada} es anterior al mes {mes[:7]}", 422
        )
    pago = PagoPlaneado(
        concepto=concepto,
        acreedor=acreedor,
        monto=monto,
        fecha_programada=fecha_programada,
        rubro_id=PydanticObjectId(rubro_id),
        mes_id=mc.id,
        creado_por=usuario_id,
        creado_at=now_utc(),
    )
    await pago.insert()
    try:
        await emit_audit(
            AuditEvento.pago_planeado_creado,
            entidad="pago_planeado",
            entidad_id=str(pago.id),
            actor_id=usuario_id,
            metadata={
                "mes": mes[:7],
                "acreedor": acreedor,
                "monto": money_str(monto),
                "fecha_programada": fecha_programada,
                "rubro_id": rubro_id,
            },
        )
    except Exception:  # O1: sin auditoría no hay operación → compensar y propagar
        await pago.delete()
        raise
    return pago


async def _pago(pago_id: str) -> PagoPlaneado:
    try:
        oid = PydanticObjectId(pago_id)
    except Exception as e:
        raise PagosError(f"pago_id inválido: {pago_id}", 422) from e
    p = await PagoPlaneado.get(oid)
    if p is None:
        raise PagosError("el pago planeado no existe", 404)
    return p


async def _asegura_editable(p: PagoPlaneado) -> MesControl:
    if p.estado is not EstadoPago.PENDIENTE:
        raise PagosError(
            f"el pago está '{p.estado.value}'; solo se edita un pago pendiente", 409
        )
    mc = await MesControl.get(p.mes_id)
    if mc is not None and mc.estado is EstadoMes.CERRADO:  # regla 4
        raise PagosError("el mes del pago está cerrado y es inmutable", 409)
    return mc


async def editar_pago(
    *,
    pago_id: str,
    usuario_id: str,
    concepto: str | None = None,
    acreedor: str | None = None,
    monto: Decimal | None = None,
    fecha_programada: str | None = None,
    rubro_id: str | None = None,
) -> PagoPlaneado:
    p = await _pago(pago_id)
    mc = await _asegura_editable(p)
    prev = {
        "concepto": p.concepto,
        "acreedor": p.acreedor,
        "monto": money_str(p.monto),
        "fecha_programada": p.fecha_programada,
        "rubro_id": str(p.rubro_id),
    }
    if rubro_id is not None:
        await _rubro_egreso_activo(rubro_id)
        p.rubro_id = PydanticObjectId(rubro_id)
    if concepto is not None:
        p.concepto = concepto
    if acreedor is not None:
        p.acreedor = acreedor
    if monto is not None:
        if monto <= 0:
            raise PagosError("monto debe ser > 0", 422)
        p.monto = monto
    if fecha_programada is not None:
        if mc is not None and fecha_programada < mc.mes:
            raise PagosError(
                f"fecha_programada {fecha_programada} es anterior al mes", 422
            )
        p.fecha_programada = fecha_programada
    await p.save()
    try:
        await emit_audit(
            AuditEvento.pago_planeado_editado,
            entidad="pago_planeado",
            entidad_id=str(p.id),
            actor_id=usuario_id,
            metadata={"anterior": prev, "nuevo": _snapshot(p)},
        )
    except Exception:
        # O1: revertir los campos a su estado previo y propagar.
        p.concepto = prev["concepto"]
        p.acreedor = prev["acreedor"]
        p.monto = Decimal(prev["monto"])
        p.fecha_programada = prev["fecha_programada"]
        p.rubro_id = PydanticObjectId(prev["rubro_id"])
        await p.save()
        raise
    return p


async def cancelar_pago(*, pago_id: str, usuario_id: str) -> PagoPlaneado:
    p = await _pago(pago_id)
    await _asegura_editable(p)  # solo un pendiente en mes no cerrado se cancela
    p.estado = EstadoPago.CANCELADO
    await p.save()
    try:
        await emit_audit(
            AuditEvento.pago_planeado_cancelado,
            entidad="pago_planeado",
            entidad_id=str(p.id),
            actor_id=usuario_id,
            metadata={"acreedor": p.acreedor, "monto": money_str(p.monto)},
        )
    except Exception:
        p.estado = EstadoPago.PENDIENTE
        await p.save()
        raise
    return p


async def marcar_pagado(
    *, pago_id: str, transaccion_id: str, usuario_id: str
) -> PagoPlaneado:
    """D5: enlaza el pago a una Transaccion existente. Multi-doc (regla 8) + O1."""
    p = await _pago(pago_id)
    if p.estado is not EstadoPago.PENDIENTE:
        raise PagosError(
            f"el pago está '{p.estado.value}'; solo se marca pagado un pendiente", 409
        )
    try:
        tx_oid = PydanticObjectId(transaccion_id)
    except Exception as e:
        raise PagosError(f"transaccion_id inválido: {transaccion_id}", 422) from e
    tx = await Transaccion.get(tx_oid)
    if tx is None:
        raise PagosError("la transacción no existe", 404)
    if tx.tipo_flujo is not TipoFlujo.EGRESO:
        raise PagosError("la transacción debe ser un egreso", 422)
    if tx.mes_id != p.mes_id:
        raise PagosError("la transacción es de otro mes que el pago", 422)
    mc = await MesControl.get(p.mes_id)
    if mc is not None and mc.estado is EstadoMes.CERRADO:  # regla 4
        raise PagosError("el mes está cerrado y es inmutable", 409)

    client = MesControl.get_pymongo_collection().database.client

    async def _enlazar(session):
        # revalidar dentro de la sesión (TOCTOU, patrón S4-06)
        p_fresco = await PagoPlaneado.find_one(PagoPlaneado.id == p.id, session=session)
        if p_fresco is None or p_fresco.estado is not EstadoPago.PENDIENTE:
            raise PagosError("el pago cambió de estado (concurrencia); reintentar", 409)
        p.estado = EstadoPago.PAGADO
        p.pagado_tx_id = tx.id
        await p.save(session=session)
        tx.pago_planeado_id = p.id
        await tx.save(session=session)

    async with await client.start_session() as session:
        await session.with_transaction(_enlazar)

    try:
        await emit_audit(
            AuditEvento.pago_planeado_editado,
            entidad="pago_planeado",
            entidad_id=str(p.id),
            actor_id=usuario_id,
            metadata={
                "estado": {"anterior": "pendiente", "nuevo": "pagado"},
                "pagado_tx_id": str(tx.id),
            },
        )
    except Exception:

        async def _revertir(session):
            p.estado = EstadoPago.PENDIENTE
            p.pagado_tx_id = None
            await p.save(session=session)
            tx.pago_planeado_id = None
            await tx.save(session=session)

        async with await client.start_session() as session:
            await session.with_transaction(_revertir)
        raise
    return p


def _snapshot(p: PagoPlaneado) -> dict:
    return {
        "concepto": p.concepto,
        "acreedor": p.acreedor,
        "monto": money_str(p.monto),
        "fecha_programada": p.fecha_programada,
        "rubro_id": str(p.rubro_id),
    }


async def listar_pagos(
    *, mes: str, estado: EstadoPago | None = None
) -> list[PagoPlaneado]:
    mc = await _mes(mes)
    q = PagoPlaneado.find(PagoPlaneado.mes_id == mc.id)
    filas = await q.to_list()
    if estado is not None:
        filas = [p for p in filas if p.estado is estado]
    return sorted(filas, key=lambda p: (p.fecha_programada, str(p.id)))


async def pagos_semana(mes: str) -> dict:
    """D4: veredicto '¿alcanza la caja?'. Compute-only (sin estado, sin evento)."""
    mc = await _mes(mes)
    rubro_aj = await _rubro_ajuste()  # fail-loud si no está sembrado (como Control)
    caja_hoy = await _caja_libro(mc.id, rubro_aj.id, mc.saldo_inicial_caja)

    hoy = today_bogota()
    hoy_s = hoy.isoformat()
    fin_s = (hoy + timedelta(days=_VENTANA_DIAS)).isoformat()

    pendientes = [
        p
        for p in await PagoPlaneado.find(PagoPlaneado.mes_id == mc.id).to_list()
        if p.estado is EstadoPago.PENDIENTE
    ]
    semana = sorted(
        (p for p in pendientes if hoy_s <= p.fecha_programada <= fin_s),
        key=lambda p: (p.fecha_programada, str(p.id)),
    )
    vencidos = sorted(  # D3: pendientes con fecha pasada (fail-loud, aparte)
        (p for p in pendientes if p.fecha_programada < hoy_s),
        key=lambda p: (p.fecha_programada, str(p.id)),
    )
    total_semana = sum((p.monto for p in semana), Decimal("0"))
    caja_proyectada = caja_hoy - total_semana

    return {
        "mes": mes[:7],
        "caja_hoy": money_str(caja_hoy),
        "total_semana": money_str(total_semana),
        "caja_proyectada": money_str(caja_proyectada),
        "veredicto": "alcanza" if caja_proyectada >= 0 else "no_alcanza",
        "ventana": {"desde": hoy_s, "hasta": fin_s},
        "pagos": [_serializar(p) for p in semana],
        "vencidos": [_serializar(p) for p in vencidos],
    }


def _serializar(p: PagoPlaneado) -> dict:
    return {
        "id": str(p.id),
        "concepto": p.concepto,
        "acreedor": p.acreedor,
        "monto": money_str(p.monto),
        "fecha_programada": p.fecha_programada,
        "rubro_id": str(p.rubro_id),
        "estado": p.estado.value,
        "pagado_tx_id": str(p.pagado_tx_id) if p.pagado_tx_id else None,
    }
