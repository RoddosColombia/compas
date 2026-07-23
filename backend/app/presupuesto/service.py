# backend/app/presupuesto/service.py
"""Ciclo del presupuesto (F-06/F-07): generación del sugerido, acotamiento y
aprobación.

MARCADO PARA AUDITORÍA KIMI (motor del sugerido + tabla de autoridad §2.4).

- **generar_sugerido** (§1.4.1): crea las PresupuestoLinea vigentes de un mes desde
  el ejecutado de los meses CERRADOS anteriores. E(i) se calcula con UNA agregación
  `$group` (Baja #4: 1 query vs ~90). Cada línea guarda `creada_por` (Baja #1).
- **acotar_linea** (§2.4 "Proponer/acotar"): fija `monto_definido` + registra un
  `Ajuste` con comentario. Transiciona el mes `sugerido → propuesto` (M-1). Saga
  fail-closed O1 (M-2): si el emit de auditoría falla, compensa (revierte ajuste +
  monto + estado). S4-00 (Kimi, higiene): línea + mes se escriben en TRANSACCIÓN
  MULTI-DOC — antes eran dos `save` secuenciales y una caída de proceso entre
  ambos dejaba ventana de inconsistencia; ahora es atómico como aprobar/cerrar.
- **aprobar_presupuesto** (§2.4 "Aprobar", solo Admin): TRANSACCIÓN MULTI-DOC
  (regla 8/F-09) que fija `monto_definido` (default = sugerido) en las ~30 líneas
  vigentes + MesControl → `en_ejecucion` (M-1, PR #22), atómico, con reintento
  automático de `with_transaction` ante TransientTransactionError. La auditoría
  vive en conexión dedicada → se emite tras el commit; si falla, transacción
  compensatoria revierte (saga O1). Convergencia ante caída vía Idempotency-Key
  (en el router)."""

from decimal import Decimal

from beanie import PydanticObjectId
from bson.decimal128 import Decimal128

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.core.money import money_str
from app.core.time import now_utc
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.presupuesto import Ajuste, PresupuestoLinea
from app.domain.rubro import Rubro, TipoFlujo
from app.domain.transaccion import Transaccion
from app.presupuesto.motor import calcular_sugerido_historico

_ACOTABLE = (EstadoMes.SUGERIDO, EstadoMes.PROPUESTO)


class SugeridoError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


class AcotarError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


class AprobarError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


async def _meses_cerrados_previos(mes: str, limite: int = 3) -> list[MesControl]:
    """Los `limite` meses en estado 'cerrado' con mes < objetivo, del más reciente
    al más antiguo (E(M-1), E(M-2), E(M-3))."""
    return (
        await MesControl.find(
            MesControl.estado == EstadoMes.CERRADO, MesControl.mes < mes
        )
        .sort(-MesControl.mes)
        .limit(limite)
        .to_list()
    )


async def _ejecutados_por_rubro_mes(
    mes_ids: list[PydanticObjectId], rubro_ids: list[PydanticObjectId]
) -> dict[tuple[str, str], Decimal]:
    """Baja #4: UNA agregación `$group` (vs ~90 queries punto a punto). Σ valor de
    las transacciones de EGRESO por (rubro, mes) sobre los meses cerrados dados.
    Claves como str(ObjectId) para hashing estable. Devuelve Decimal (regla 1)."""
    if not mes_ids or not rubro_ids:
        return {}
    col = Transaccion.get_pymongo_collection()
    pipeline = [
        {
            "$match": {
                "tipo_flujo": TipoFlujo.EGRESO.value,
                "mes_id": {"$in": mes_ids},
                "rubro_id": {"$in": rubro_ids},
            }
        },
        {
            "$group": {
                "_id": {"rubro_id": "$rubro_id", "mes_id": "$mes_id"},
                "total": {"$sum": "$valor"},
            }
        },
    ]
    out: dict[tuple[str, str], Decimal] = {}
    async for doc in col.aggregate(pipeline):
        total = doc["total"]
        dec = (
            total.to_decimal() if isinstance(total, Decimal128) else Decimal(str(total))
        )
        out[(str(doc["_id"]["rubro_id"]), str(doc["_id"]["mes_id"]))] = dec
    return out


async def generar_sugerido(
    *, mes: str, usuario_id: str, crec_pct: Decimal = Decimal("0")
) -> list[PresupuestoLinea]:
    objetivo = await MesControl.find_one(MesControl.mes == mes)
    if objetivo is None:
        raise SugeridoError(f"el mes {mes[:7]} no está abierto")
    if await PresupuestoLinea.find_one(PresupuestoLinea.mes_id == objetivo.id):
        raise SugeridoError(
            f"el mes {mes[:7]} ya tiene presupuesto generado", status=409
        )

    cerrados = await _meses_cerrados_previos(mes)
    rubros = await Rubro.find(
        Rubro.activo == True,  # noqa: E712 (Beanie construye el filtro)
        Rubro.es_sistema == False,  # noqa: E712
    ).to_list()

    agg = await _ejecutados_por_rubro_mes(
        [mc.id for mc in cerrados], [r.id for r in rubros]
    )

    creadas: list[PresupuestoLinea] = []
    for rubro in rubros:
        ejecutados = [
            agg.get((str(rubro.id), str(mc.id)), Decimal("0")) for mc in cerrados
        ]
        comp = calcular_sugerido_historico(ejecutados, crec_pct)
        linea = PresupuestoLinea(
            mes_id=objetivo.id,
            rubro_id=rubro.id,
            monto_sugerido=comp.monto_sugerido,
            prom_3m=comp.prom_3m,
            tendencia_mes=comp.tendencia_mes,
            crec_pct=crec_pct,
            historia_incompleta=comp.historia_incompleta,
            creada_por=usuario_id,  # Baja #1: rastro del actor de la generación
        )
        await linea.insert()
        creadas.append(linea)

    # DECISIÓN (Kimi I-PR1): la generación NO emite evento. El sugerido es un
    # BORRADOR recomputable (monto_definido=null); los eventos reales llegan con el
    # acotamiento (presupuesto.acotado) y la aprobación (presupuesto.definido).
    return creadas


async def acotar_linea(
    *,
    mes: str,
    rubro_id: str,
    monto_definido: Decimal,
    comentario: str | None,
    usuario_id: str,
) -> PresupuestoLinea:
    """§2.4 Proponer/acotar. Fija `monto_definido` en la línea vigente NO aprobada
    y registra un `Ajuste` append-only. M-1: transiciona el mes `sugerido→propuesto`.
    M-2: saga fail-closed O1 — si el emit de auditoría falla, compensa todo.
    S4-00: línea + mes en transacción multi-doc (regla 8)."""
    mc = await MesControl.find_one(MesControl.mes == mes)
    if mc is None:
        raise AcotarError(f"el mes {mes[:7]} no existe", 404)
    if mc.estado is EstadoMes.CERRADO:
        raise AcotarError("el mes está cerrado y es inmutable (regla 4)", 409)
    if mc.estado not in _ACOTABLE:
        raise AcotarError(
            f"el mes está en '{mc.estado.value}'; solo se acota en sugerido/propuesto",
            409,
        )
    try:
        rid = PydanticObjectId(rubro_id)
    except Exception:
        raise AcotarError("rubro_id inválido", 422) from None
    ln = await PresupuestoLinea.find_one(
        PresupuestoLinea.mes_id == mc.id,
        PresupuestoLinea.rubro_id == rid,
        PresupuestoLinea.vigente == True,  # noqa: E712
    )
    if ln is None:
        raise AcotarError("no hay línea de presupuesto vigente para ese rubro", 404)

    # Estado previo para la compensación (M-2).
    prev_monto = ln.monto_definido
    prev_ajustes = len(ln.ajustes)
    prev_estado = mc.estado

    ln.ajustes.append(
        Ajuste(
            valor_anterior=prev_monto,
            valor_nuevo=monto_definido,
            por=usuario_id,
            at=now_utc(),
            comentario=comentario,
        )
    )
    ln.monto_definido = monto_definido
    cambio_mes = mc.estado is EstadoMes.SUGERIDO  # M-1
    client = PresupuestoLinea.get_pymongo_collection().database.client

    # S4-00 (Kimi, higiene): línea + mes ATÓMICOS — una caída de proceso entre los
    # dos save ya no deja el ajuste sin la transición de estado (o viceversa).
    async def _acotar(session):
        await ln.save(session=session)
        if cambio_mes:
            mc.estado = EstadoMes.PROPUESTO
            await mc.save(session=session)

    async with await client.start_session() as session:
        await session.with_transaction(_acotar)

    try:
        await emit_audit(
            AuditEvento.presupuesto_acotado,
            entidad="presupuesto_linea",
            entidad_id=str(ln.id),
            actor_id=usuario_id,
            metadata={
                "mes": mes,
                "rubro_id": rubro_id,
                "valor_anterior": money_str(prev_monto)
                if prev_monto is not None
                else None,
                "valor_nuevo": money_str(monto_definido),
                "comentario": comentario,
            },
        )
    except Exception:
        # M-2 (saga O1): sin auditoría no hay decisión financiera → compensar
        # (también atómico, como la reversión de aprobar).
        async def _revertir(session):
            ln.ajustes = ln.ajustes[:prev_ajustes]
            ln.monto_definido = prev_monto
            await ln.save(session=session)
            if cambio_mes:
                mc.estado = prev_estado
                await mc.save(session=session)

        async with await client.start_session() as session:
            await session.with_transaction(_revertir)
        raise
    return ln


async def aprobar_presupuesto(*, mes: str, usuario_id: str) -> dict:
    """§2.4 Aprobar (solo Admin). TRANSACCIÓN MULTI-DOC (regla 8): fija
    `monto_definido` (= sugerido donde sea null) en las líneas vigentes + MesControl
    → `definido`, atómico. La auditoría (conexión dedicada) se emite tras el commit;
    si falla, transacción compensatoria revierte (saga O1)."""
    mc = await MesControl.find_one(MesControl.mes == mes)
    if mc is None:
        raise AprobarError(f"el mes {mes[:7]} no existe", 404)
    if mc.estado is EstadoMes.CERRADO:
        raise AprobarError("el mes está cerrado y es inmutable (regla 4)", 409)
    if mc.estado is EstadoMes.DEFINIDO:
        raise AprobarError(f"el mes {mes[:7]} ya está definido", 409)
    if mc.estado not in _ACOTABLE:
        raise AprobarError(f"no se puede aprobar un mes en '{mc.estado.value}'", 409)
    lineas = await PresupuestoLinea.find(
        PresupuestoLinea.mes_id == mc.id,
        PresupuestoLinea.vigente == True,  # noqa: E712
    ).to_list()
    if not lineas:
        raise AprobarError("el mes no tiene líneas de presupuesto que aprobar", 409)

    # Estado previo para compensar si el emit de auditoría falla (saga O1).
    ids_null_previo = {ln.id for ln in lineas if ln.monto_definido is None}
    estado_previo = mc.estado
    client = PresupuestoLinea.get_pymongo_collection().database.client

    async def _aprobar(session):
        for ln in lineas:
            if ln.monto_definido is None:  # D2: aceptar la recomendación del motor
                ln.monto_definido = ln.monto_sugerido
                await ln.save(session=session)
        # M-1 (Kimi Sprint 4): la aprobación deja el mes en EN_EJECUCION (US-02: "el
        # mes pasa a en_ejecucion"). `definido_por/at` + el evento presupuesto.definido
        # son el registro de la aprobación; no se usa un estado 'definido' en reposo.
        mc.estado = EstadoMes.EN_EJECUCION
        mc.definido_por = usuario_id
        mc.definido_at = now_utc()
        await mc.save(session=session)

    # with_transaction REINTENTA solo TransientTransactionError / commit desconocido.
    async with await client.start_session() as session:
        await session.with_transaction(_aprobar)

    try:
        await emit_audit(
            AuditEvento.presupuesto_definido,
            entidad="mes",
            entidad_id=str(mc.id),
            actor_id=usuario_id,
            metadata={"mes": mes, "lineas": len(lineas), "definido_por": usuario_id},
        )
    except Exception:

        async def _revertir(session):
            for ln in lineas:
                if ln.id in ids_null_previo:
                    ln.monto_definido = None
                    await ln.save(session=session)
            mc.estado = estado_previo
            mc.definido_por = None
            mc.definido_at = None
            await mc.save(session=session)

        async with await client.start_session() as session:
            await session.with_transaction(_revertir)
        raise
    return {"mes": mes, "estado": mc.estado.value, "lineas": len(lineas)}
