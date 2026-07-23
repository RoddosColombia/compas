# backend/app/cierre/service.py
"""Cierre de mes + conciliación por banco (Sprint 4, GO PLAN R 9.4).

MARCADO PARA AUDITORÍA KIMI (regla 8: cierre multi-doc + F-14 + saga O1).

- **conciliacion(mes)** — cierre operativo (compute-only, sin estado, sin evento).
  Por banco (M-3): calculado(b) = reportado(b) @ fecha_reporte + Σ signo(movimientos
  de b con fecha > fecha_reporte(b)); banco con movimientos pero SIN saldo reportado →
  'sin dato' (regla 7, nunca contra 0). `R_M` = Σ_b calculado(b) (bancos con dato);
  `C_M` = caja del LIBRO (saldo_inicial + Σ signo(tx), EXCLUYENDO el rubro de sistema
  'Ajuste de conciliación' — anti-doble-conteo, M-2/B-2). `diferencia = R_M − C_M`.
- **confirmar_cierre(mes)** — TRANSACCIÓN MULTI-DOC (regla 8): re-ancla
  `saldo_inicial(M+1) := R_M` (guardando el previo en `cierre_info`, M-2), crea el
  'Ajuste de conciliación' en M+1 (día-1, omitido si diferencia==0, B-2), congela M
  (→cerrado). Auditoría `mes.cerrado` post-commit con saga O1 (compensa como la
  apertura certificada: borra los artefactos del cierre FALLIDO y revierte).
- **reabrir_mes(mes)** — CONTRA-ASIENTO del ajuste (M-4, §2.2.2: la Transaccion es
  inmutable, jamás se borra un asiento histórico), restaura el ancla previa, M→
  en_ejecucion. Admin + step-up MFA. LIFO: M+1 debe seguir editable.
"""

from decimal import Decimal

from beanie import PydanticObjectId

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.ciclo.service import _mes_siguiente
from app.core.money import money_str
from app.core.time import now_utc
from app.core.ulid import new_ulid
from app.domain.bancos import Banco
from app.domain.configuracion import ClaveConfig, Configuracion
from app.domain.mes_control import CierreInfo, EstadoMes, MesControl
from app.domain.rubro import Rubro, TipoFlujo
from app.domain.transaccion import Transaccion

_RUBRO_AJUSTE = "Ajuste de conciliación"


class CierreError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


def _signo(t: Transaccion) -> Decimal:
    return t.valor if t.tipo_flujo == TipoFlujo.INGRESO else -t.valor


async def _umbral() -> Decimal:
    cfg = (
        await Configuracion.find(
            Configuracion.clave == ClaveConfig.UMBRAL_DIF_BANCO_CIERRE
        )
        .sort(-Configuracion.vigente_desde)
        .limit(1)
        .to_list()
    )
    if not cfg or cfg[0].valor_decimal is None:
        raise CierreError("UMBRAL_DIF_BANCO_CIERRE no está configurado", 500)
    return cfg[0].valor_decimal


async def _rubro_ajuste() -> Rubro:
    r = await Rubro.find_one(
        Rubro.nombre == _RUBRO_AJUSTE,
        Rubro.es_sistema == True,  # noqa: E712
    )
    if r is None:
        raise CierreError("rubro de sistema 'Ajuste de conciliación' no sembrado", 500)
    return r


async def _mes(mes: str) -> MesControl:
    mc = await MesControl.find_one(MesControl.mes == mes)
    if mc is None:
        raise CierreError(f"el mes {mes[:7]} no existe", 404)
    return mc


async def _caja_libro(
    mes_id: PydanticObjectId, rubro_ajuste_id, saldo_inicial: Decimal
) -> Decimal:
    """C_M: caja del libro = saldo_inicial + Σ signo(tx) EXCLUYENDO el rubro de
    sistema 'Ajuste de conciliación' (anti-doble-conteo, M-2)."""
    total = saldo_inicial
    async for t in Transaccion.find(Transaccion.mes_id == mes_id):
        if t.rubro_id == rubro_ajuste_id:
            continue
        total += _signo(t)
    return total


async def _conciliar(mc: MesControl, rubro_ajuste_id) -> dict:
    """Núcleo de la conciliación (M-3). No cambia estado."""
    reportados = {sb.banco: sb for sb in mc.saldos_banco}
    # movimientos por banco (excluye el rubro de ajuste)
    bancos_con_mov: set[Banco] = set()
    mov_post: dict[Banco, Decimal] = {}
    async for t in Transaccion.find(Transaccion.mes_id == mc.id):
        if t.rubro_id == rubro_ajuste_id:
            continue
        bancos_con_mov.add(t.banco)
        sb = reportados.get(t.banco)
        if sb is not None and t.fecha > sb.fecha_reporte:
            mov_post[t.banco] = mov_post.get(t.banco, Decimal("0")) + _signo(t)

    por_banco = []
    r_m = Decimal("0")
    for banco, sb in reportados.items():
        calc = sb.saldo + mov_post.get(banco, Decimal("0"))
        r_m += calc
        por_banco.append(
            {
                "banco": banco.value,
                "reportado": money_str(sb.saldo),
                "calculado": money_str(calc),
            }
        )
    # banco con movimientos pero sin saldo reportado → 'sin dato' (regla 7)
    sin_dato = sorted(b.value for b in bancos_con_mov if b not in reportados)

    c_m = await _caja_libro(mc.id, rubro_ajuste_id, mc.saldo_inicial_caja)
    diferencia = r_m - c_m
    umbral = await _umbral()
    dentro = abs(diferencia) <= umbral and not sin_dato
    return {
        "por_banco": por_banco,
        "sin_dato": sin_dato,
        "consolidado_reportado": r_m,
        "caja_libro": c_m,
        "diferencia": diferencia,
        "umbral": umbral,
        "dentro_de_umbral": dentro,
    }


async def conciliacion(mes: str) -> dict:
    """Cierre operativo: reporte de conciliación (compute-only)."""
    mc = await _mes(mes)
    if mc.estado is not EstadoMes.EN_EJECUCION:
        raise CierreError(
            f"solo se concilia un mes en ejecución (está en '{mc.estado.value}')", 409
        )
    rubro_aj = await _rubro_ajuste()
    r = await _conciliar(mc, rubro_aj.id)
    return {
        "mes": mes[:7],
        "por_banco": r["por_banco"],
        "sin_dato": r["sin_dato"],
        "consolidado_reportado": money_str(r["consolidado_reportado"]),
        "caja_libro": money_str(r["caja_libro"]),
        "diferencia": money_str(r["diferencia"]),
        "umbral": money_str(r["umbral"]),
        "dentro_de_umbral": r["dentro_de_umbral"],
    }


async def confirmar_cierre(*, mes: str, usuario_id: str) -> dict:
    """Confirmar cierre (solo Admin). Transacción multi-doc (regla 8) + saga O1."""
    mc = await _mes(mes)
    if mc.estado is EstadoMes.CERRADO:
        raise CierreError(f"el mes {mes[:7]} ya está cerrado", 409)
    if mc.estado is not EstadoMes.EN_EJECUCION:
        raise CierreError(
            f"solo se cierra un mes en ejecución (está en '{mc.estado.value}')", 409
        )
    siguiente = await MesControl.find_one(MesControl.mes == _mes_siguiente(mc.mes))
    if siguiente is None:  # D2
        raise CierreError(
            f"abre el mes {_mes_siguiente(mc.mes)[:7]} antes de cerrar {mes[:7]} "
            "(el ajuste de conciliación se imputa al mes que abre)",
            409,
        )
    if siguiente.estado is EstadoMes.CERRADO:
        raise CierreError(
            f"el mes {siguiente.mes[:7]} está cerrado; no es editable", 409
        )

    rubro_aj = await _rubro_ajuste()
    recon = await _conciliar(mc, rubro_aj.id)
    if not recon["dentro_de_umbral"]:
        motivo = (
            "hay bancos sin saldo reportado: " + ", ".join(recon["sin_dato"])
            if recon["sin_dato"]
            else f"la diferencia {money_str(recon['diferencia'])} supera el umbral "
            f"{money_str(recon['umbral'])}"
        )
        raise CierreError(f"no se puede cerrar: {motivo}", 409)

    r_m = recon["consolidado_reportado"]
    diferencia = recon["diferencia"]
    ancla_prev = siguiente.saldo_inicial_caja
    client = MesControl.get_pymongo_collection().database.client
    creado = {"ajuste_id": None}

    async def _cerrar(session):
        # S4-06/B-2 (Kimi, TOCTOU): las guardas de arriba corren FUERA de la
        # transacción — releer el estado DENTRO de la sesión y abortar si otro
        # proceso lo cambió (doble cierre / ajuste a mes inmutable).
        mc_fresco = await MesControl.find_one(MesControl.mes == mc.mes, session=session)
        sig_fresco = await MesControl.find_one(
            MesControl.mes == siguiente.mes, session=session
        )
        if mc_fresco is None or mc_fresco.estado is not EstadoMes.EN_EJECUCION:
            raise CierreError(
                f"el estado del mes {mes[:7]} cambió durante el cierre "
                "(concurrencia); reintentar",
                409,
            )
        if sig_fresco is None or sig_fresco.estado is EstadoMes.CERRADO:
            raise CierreError(
                f"el mes {siguiente.mes[:7]} cambió de estado durante el cierre "
                "(concurrencia); reintentar",
                409,
            )
        siguiente.saldo_inicial_caja = r_m  # M-2: re-anclar a R_M
        await siguiente.save(session=session)
        aj_id = None
        if diferencia != 0:  # B-2: omitir el ajuste si no hay diferencia
            tipo = TipoFlujo.INGRESO if diferencia > 0 else TipoFlujo.EGRESO
            aj = Transaccion(
                fecha=siguiente.mes,  # día-1 de M+1 (nit-9)
                descripcion=f"Ajuste de conciliación cierre {mc.mes[:7]}",
                valor=abs(diferencia),
                tipo_flujo=tipo,
                rubro_id=rubro_aj.id,
                mes_id=siguiente.id,
                banco=Banco.MANUAL,
                id_banco=f"MAN-{new_ulid()}",
            )
            await aj.insert(session=session)
            aj_id = str(aj.id)
        creado["ajuste_id"] = aj_id
        mc.estado = EstadoMes.CERRADO
        mc.cerrado_por = usuario_id
        mc.cerrado_at = now_utc()
        mc.cierre_info = CierreInfo(
            ancla_anterior_siguiente=ancla_prev,
            diferencia=diferencia,
            ajuste_tx_id=aj_id,
        )
        await mc.save(session=session)

    async with await client.start_session() as session:
        await session.with_transaction(_cerrar)

    try:
        await emit_audit(
            AuditEvento.mes_cerrado,
            entidad="mes",
            entidad_id=str(mc.id),
            actor_id=usuario_id,
            metadata={
                "mes": mes[:7],
                "consolidado_reportado": money_str(r_m),
                "caja_libro": money_str(recon["caja_libro"]),
                "diferencia": money_str(diferencia),
                "ajuste_tx_id": creado["ajuste_id"],
            },
        )
    except Exception:
        # Saga O1 (igual que la apertura certificada): el cierre FALLÓ (sin evento) →
        # se borran sus artefactos y se revierte. No es mutar historia (§2.2.2): el
        # cierre nunca se completó.
        async def _revertir(session):
            if creado["ajuste_id"]:
                aj = await Transaccion.get(PydanticObjectId(creado["ajuste_id"]))
                if aj is not None:
                    await aj.delete(session=session)
            siguiente.saldo_inicial_caja = ancla_prev
            await siguiente.save(session=session)
            mc.estado = EstadoMes.EN_EJECUCION
            mc.cerrado_por = None
            mc.cerrado_at = None
            mc.cierre_info = None
            await mc.save(session=session)

        async with await client.start_session() as session:
            await session.with_transaction(_revertir)
        raise
    return {
        "mes": mes[:7],
        "estado": mc.estado.value,
        "diferencia": money_str(diferencia),
        "ajuste_tx_id": creado["ajuste_id"],
        "saldo_inicial_siguiente": money_str(r_m),
    }


async def reabrir_mes(*, mes: str, usuario_id: str) -> dict:
    """Reapertura (Admin + step-up MFA): contra-asiento del ajuste (M-4) + restaura
    el ancla previa + M→en_ejecucion. Transacción multi-doc + saga O1."""
    mc = await _mes(mes)
    if mc.estado is not EstadoMes.CERRADO:
        raise CierreError(
            f"solo se reabre un mes cerrado (está en '{mc.estado.value}')", 409
        )
    siguiente = await MesControl.find_one(MesControl.mes == _mes_siguiente(mc.mes))
    if siguiente is not None and siguiente.estado is EstadoMes.CERRADO:
        raise CierreError(
            f"cierra en orden inverso: {siguiente.mes[:7]} sigue cerrado (LIFO)", 409
        )
    ci = mc.cierre_info
    ancla_restaurar = ci.ancla_anterior_siguiente if ci else None
    # saldo de M+1 ANTES de reabrir (= R_M re-anclado en el cierre) — para compensar.
    saldo_sig_previo = siguiente.saldo_inicial_caja if siguiente is not None else None
    client = MesControl.get_pymongo_collection().database.client
    creado = {"contra_id": None}

    async def _reabrir(session):
        # S4-06/B-2 simétrico: revalidar DENTRO de la sesión (doble reapertura /
        # LIFO roto por concurrencia).
        mc_fresco = await MesControl.find_one(MesControl.mes == mc.mes, session=session)
        if mc_fresco is None or mc_fresco.estado is not EstadoMes.CERRADO:
            raise CierreError(
                f"el estado del mes {mes[:7]} cambió durante la reapertura "
                "(concurrencia); reintentar",
                409,
            )
        if siguiente is not None:
            sig_fresco = await MesControl.find_one(
                MesControl.mes == siguiente.mes, session=session
            )
            if sig_fresco is not None and sig_fresco.estado is EstadoMes.CERRADO:
                raise CierreError(
                    f"el mes {siguiente.mes[:7]} se cerró durante la reapertura "
                    "(LIFO); reintentar",
                    409,
                )
        if ci and ci.ajuste_tx_id:
            orig = await Transaccion.get(PydanticObjectId(ci.ajuste_tx_id))
            if orig is not None:
                inv = (
                    TipoFlujo.EGRESO
                    if orig.tipo_flujo == TipoFlujo.INGRESO
                    else TipoFlujo.INGRESO
                )
                contra = Transaccion(
                    fecha=orig.fecha,
                    descripcion=f"Reverso ajuste conciliación {mc.mes[:7]}",
                    valor=orig.valor,
                    tipo_flujo=inv,
                    rubro_id=orig.rubro_id,
                    mes_id=orig.mes_id,
                    banco=Banco.MANUAL,
                    id_banco=f"MAN-{new_ulid()}",
                    revierte_id=orig.id,
                )
                await contra.insert(session=session)
                creado["contra_id"] = str(contra.id)
        if siguiente is not None and ancla_restaurar is not None:
            siguiente.saldo_inicial_caja = ancla_restaurar
            await siguiente.save(session=session)
        mc.estado = EstadoMes.EN_EJECUCION
        mc.cerrado_por = None
        mc.cerrado_at = None
        mc.cierre_info = None
        await mc.save(session=session)

    async with await client.start_session() as session:
        await session.with_transaction(_reabrir)

    try:
        await emit_audit(
            AuditEvento.mes_reabierto,
            entidad="mes",
            entidad_id=str(mc.id),
            actor_id=usuario_id,
            metadata={"mes": mes[:7], "contra_asiento_id": creado["contra_id"]},
        )
    except Exception:

        async def _revertir(session):
            if creado["contra_id"]:
                c = await Transaccion.get(PydanticObjectId(creado["contra_id"]))
                if c is not None:
                    await c.delete(session=session)
            if siguiente is not None and saldo_sig_previo is not None:
                siguiente.saldo_inicial_caja = saldo_sig_previo
                await siguiente.save(session=session)
            mc.estado = EstadoMes.CERRADO
            mc.cerrado_por = usuario_id
            mc.cerrado_at = now_utc()
            mc.cierre_info = ci
            await mc.save(session=session)

        async with await client.start_session() as session:
            await session.with_transaction(_revertir)
        raise
    return {
        "mes": mes[:7],
        "estado": mc.estado.value,
        "contra_asiento_id": creado["contra_id"],
    }
