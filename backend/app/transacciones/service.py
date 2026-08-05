# backend/app/transacciones/service.py
"""Creación de transacciones manuales (US-10, F-04).

MARCADO PARA AUDITORÍA KIMI (flujo crítico: crea movimientos de dinero).

Reglas: id_banco = 'MAN-'+ULID (único por construcción → dos manuales idénticos
coexisten, F-04); el mes de la fecha debe existir y NO estar cerrado (regla 4 —
las tardías llegan con el flujo de cierre, Sprint 4); rubro explícito debe existir,
estar activo y ser coherente con tipo_flujo (regla 7: no se adivina); sin rubro →
'Por clasificar'. Eventos: `transaccion.creada` en TODA creación manual (CR-S2,
Kimi M-1 — rastro forense permanente) + `transaccion.clasificada` si además el
usuario clasificó (rubro explícito).

C3 (GO Kimi PLAN-I 9.3) — `reclasificar_transaccion`: mueve una transacción a un
rubro existente + ACTIVO (422) + de tipo coherente (409, D1); mes cerrado → 409
(regla 4: el histórico congelado no se reclasifica). Solo mutan rubro_id/
clasificada_por/at — fecha, valor, banco, id_banco INMUTABLES (Spec §2.2). Emite
`transaccion.clasificada` {rubro_anterior→rubro_nuevo} FAIL-CLOSED (compensa si el
emit falla). Con `proponer_regla` (+patrón), crea una ReglaClasificacion APRENDIDA
inactiva (§1.9: nunca auto-activada; la validación de la propuesta corre ANTES de
mutar — si la propuesta es inválida, nada cambia)."""

import hashlib
from decimal import Decimal

from beanie import PydanticObjectId
from pymongo.errors import DuplicateKeyError

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.core.time import now_utc
from app.core.ulid import new_ulid
from app.domain.bancos import Banco
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.rubro import Rubro, TipoFlujo, es_rubro_clasificable
from app.domain.transaccion import Transaccion

RUBRO_POR_CLASIFICAR = "Por clasificar"


class TransaccionManualError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


async def crear_transaccion_manual(
    *,
    fecha: str,
    descripcion: str,
    valor: Decimal,
    tipo_flujo: TipoFlujo,
    usuario_id: str,
    rubro_id: str | None = None,
    idempotency_key: str | None = None,
    endpoint: str | None = None,
) -> tuple[Transaccion, bool]:
    """Devuelve (tx, replay). replay=True cuando la Idempotency-Key ya había
    creado esta tx (colisión en el índice único tras expirar la marca)."""
    mes = fecha[:7] + "-01"
    mc = await MesControl.find_one(MesControl.mes == mes)
    if mc is None:
        raise TransaccionManualError(
            f"el mes {mes[:7]} no tiene MesControl abierto (abrir el mes primero)"
        )
    if mc.estado is EstadoMes.CERRADO:
        raise TransaccionManualError(
            f"el mes {mes[:7]} está cerrado (regla 4); la transacción tardía "
            "llega con el flujo de cierre (Sprint 4)",
            status=409,
        )

    clasificada = rubro_id is not None
    if clasificada:
        rubro = await Rubro.get(PydanticObjectId(rubro_id))
        if rubro is None or not rubro.activo:
            raise TransaccionManualError("rubro inexistente o inactivo")
        if rubro.tipo_flujo is not tipo_flujo:
            raise TransaccionManualError(
                f"rubro '{rubro.nombre}' es {rubro.tipo_flujo.value}, "
                f"incoherente con tipo_flujo={tipo_flujo.value}"
            )
        if not es_rubro_clasificable(rubro):
            raise TransaccionManualError(
                f"el rubro '{rubro.nombre}' es de sistema y no admite "
                "clasificación manual (P0-1)",
                status=422,
            )
    else:
        rubro = await Rubro.find_one(Rubro.nombre == RUBRO_POR_CLASIFICAR)
        if rubro is None:
            raise TransaccionManualError(
                "falta el rubro de sistema 'Por clasificar' (correr semillas)",
                status=500,
            )

    # A-4 (P1-9): id_banco determinista desde la Idempotency-Key → un replay tras
    # expirar el TTL de la marca colisiona en el índice único (banco, id_banco) y
    # NO duplica dinero (la unicidad vive en el índice, no en la marca). Sin key
    # (no debería ocurrir por el endpoint): ULID aleatorio.
    if idempotency_key is not None and endpoint is not None:
        huella = hashlib.sha256(
            f"{usuario_id}|{endpoint}|{idempotency_key}".encode()
        ).hexdigest()
        id_banco = f"MAN-{huella[:24]}"
    else:
        id_banco = f"MAN-{new_ulid()}"

    tx = Transaccion(
        fecha=fecha,
        descripcion=descripcion,
        valor=valor,
        tipo_flujo=tipo_flujo,
        rubro_id=rubro.id,
        mes_id=mc.id,
        banco=Banco.MANUAL,
        id_banco=id_banco,
        clasificada_por=usuario_id if clasificada else None,
        clasificada_at=now_utc() if clasificada else None,
    )
    try:
        await tx.insert()
    except DuplicateKeyError:
        existente = await Transaccion.find_one(
            Transaccion.banco == Banco.MANUAL,
            Transaccion.id_banco == id_banco,
        )
        if existente is not None:
            return existente, True  # replay convergente, una sola tx
        raise

    # A-4 (P1-7): saga O1. CR-S2 (Kimi M-1) exige que TODA creación manual deje
    # rastro forense — es la única vía por la que entra dinero sin archivo de banco.
    # Sin rastro no hay creación: si el emit falla, se compensa borrando la tx
    # (nada persiste) → el router puede borrar la marca y el retry no duplica.
    try:
        await emit_audit(
            AuditEvento.transaccion_creada,
            entidad="transaccion",
            entidad_id=str(tx.id),
            actor_id=usuario_id,
            metadata={
                "origen": "manual",
                "valor": f"{valor:.2f}",
                "tipo_flujo": tipo_flujo.value,
            },
        )
        if clasificada:
            await emit_audit(
                AuditEvento.transaccion_clasificada,
                entidad="transaccion",
                entidad_id=str(tx.id),
                actor_id=usuario_id,
                metadata={
                    "origen": "manual",
                    "rubro_id": str(rubro.id),
                    "valor": f"{valor:.2f}",
                },
            )
    except Exception:
        await tx.delete()  # O1: compensación — sin dinero fantasma
        raise
    return tx, False


async def listar_transacciones(
    *, mes: str, banco: str | None = None
) -> tuple[list[Transaccion], set[str]]:
    """FIX-G2: lista las transacciones de un mes (YYYY-MM) para el panel de manuales.
    Devuelve (txs ordenadas por fecha, ids_anuladas) donde ids_anuladas = ids que ya
    tienen un contra-asiento (algún tx.revierte_id apunta a ellas). `banco` opcional
    filtra por banco (p. ej. 'manual')."""
    mc = await MesControl.find_one(MesControl.mes == f"{mes}-01")
    if mc is None:
        return [], set()
    filtros = [Transaccion.mes_id == mc.id]
    if banco is not None:
        filtros.append(Transaccion.banco == Banco(banco))
    txs = await Transaccion.find(*filtros).sort(+Transaccion.fecha).to_list()
    anuladas = {str(t.revierte_id) for t in txs if t.revierte_id is not None}
    return txs, anuladas


async def anular_transaccion_manual(
    *,
    tx_id: str,
    motivo: str,
    usuario_id: str,
) -> Transaccion:
    """FIX-G2: anula una transacción MANUAL creando su CONTRA-ASIENTO (la Transaccion
    es inmutable, §2.2.2: nunca se borra). Mismo valor/fecha/rubro, tipo_flujo
    invertido, banco=MANUAL, id_banco MAN-+ULID nuevo, revierte_id=original → neto 0 (2
    patas cuentan en libro/caja). Espeja el contra-asiento del reverso de conciliación
    (cierre/service.py). Guardas: solo MANUAL (422 — las bancarias se corrigen
    re-cargando con dedup), solo mes abierto (409, regla 4), no dos veces (409 si ya
    tiene reverso). Evento `transaccion.creada` (existente) con via='contra_asiento'.
    Saga O1: si el emit falla, se borra el reverso (sin dinero fantasma)."""
    try:
        tid = PydanticObjectId(tx_id)
    except Exception:
        raise TransaccionManualError("transaccion_id inválido", 422) from None
    orig = await Transaccion.get(tid)
    if orig is None:
        raise TransaccionManualError("la transacción no existe", 404)

    if orig.banco is not Banco.MANUAL:
        raise TransaccionManualError(
            "solo se anulan transacciones manuales; una bancaria se corrige "
            "re-cargando el extracto (la dedup evita duplicados)",
            422,
        )

    mc = await MesControl.get(orig.mes_id)
    if mc is not None and mc.estado is EstadoMes.CERRADO:
        raise TransaccionManualError(
            "el mes está cerrado y su histórico es inmutable (regla 4)", 409
        )

    ya = await Transaccion.find_one(Transaccion.revierte_id == orig.id)
    if ya is not None:
        raise TransaccionManualError(
            "esta transacción ya fue anulada (ya tiene su contra-asiento)", 409
        )

    inv = (
        TipoFlujo.EGRESO if orig.tipo_flujo is TipoFlujo.INGRESO else TipoFlujo.INGRESO
    )
    desc = f"Anulación de «{orig.descripcion}»: {motivo}"[:300]
    contra = Transaccion(
        fecha=orig.fecha,
        descripcion=desc,
        valor=orig.valor,
        tipo_flujo=inv,
        rubro_id=orig.rubro_id,
        mes_id=orig.mes_id,
        banco=Banco.MANUAL,
        id_banco=f"MAN-{new_ulid()}",
        revierte_id=orig.id,
    )
    await contra.insert()

    try:
        await emit_audit(
            AuditEvento.transaccion_creada,
            entidad="transaccion",
            entidad_id=str(contra.id),
            actor_id=usuario_id,
            metadata={
                "origen": "manual",
                "via": "contra_asiento",
                "revierte_id": str(orig.id),
                "motivo": motivo,
                "valor": f"{orig.valor:.2f}",
                "tipo_flujo": inv.value,
            },
        )
    except Exception:
        await contra.delete()  # O1: sin rastro no hay reverso
        raise
    return contra


async def reclasificar_transaccion(
    *,
    tx_id: str,
    rubro_id: str,
    usuario_id: str,
    proponer_regla: bool = False,
    patron: str | None = None,
) -> Transaccion:
    """C3: reclasificación manual (ver docstring del módulo)."""
    try:
        tid = PydanticObjectId(tx_id)
    except Exception:
        raise TransaccionManualError("transaccion_id inválido", 422) from None
    tx = await Transaccion.get(tid)
    if tx is None:
        raise TransaccionManualError("la transacción no existe", 404)

    mc = await MesControl.get(tx.mes_id)
    if mc is not None and mc.estado is EstadoMes.CERRADO:
        raise TransaccionManualError(
            "el mes está cerrado y su histórico es inmutable (regla 4)", 409
        )

    try:
        rid = PydanticObjectId(rubro_id)
    except Exception:
        raise TransaccionManualError("rubro_id inválido", 422) from None
    rubro = await Rubro.get(rid)
    if rubro is None:
        raise TransaccionManualError("el rubro no existe", 404)
    if not rubro.activo:
        raise TransaccionManualError(
            f"el rubro '{rubro.nombre}' está inactivo (B-2a C1)", 422
        )
    if rubro.tipo_flujo is not tx.tipo_flujo:
        raise TransaccionManualError(
            f"el rubro '{rubro.nombre}' es {rubro.tipo_flujo.value}, incoherente "
            f"con una transacción de {tx.tipo_flujo.value} (D1)",
            409,
        )
    if not es_rubro_clasificable(rubro):
        raise TransaccionManualError(
            f"el rubro '{rubro.nombre}' es de sistema y no admite "
            "reclasificación manual (P0-1)",
            422,
        )
    if proponer_regla:
        if patron is None or len(patron.strip()) < 3:
            raise TransaccionManualError(
                "proponer_regla exige un patrón de al menos 3 caracteres", 422
            )
        # La propuesta se valida ANTES de mutar: si es inválida, nada cambia.
        from app.reglas.service import _patron_activo_duplicado

        if await _patron_activo_duplicado(patron.strip(), tx.tipo_flujo):
            raise TransaccionManualError(
                f"ya existe una regla ACTIVA con el patrón '{patron.strip()}'", 409
            )

    # Estado previo para la compensación (O1). Inmutables §2.2: NO se tocan.
    prev_rubro = tx.rubro_id
    prev_por = tx.clasificada_por
    prev_at = tx.clasificada_at

    tx.rubro_id = rubro.id
    tx.clasificada_por = usuario_id
    tx.clasificada_at = now_utc()
    await tx.save()

    try:
        await emit_audit(
            AuditEvento.transaccion_clasificada,
            entidad="transaccion",
            entidad_id=str(tx.id),
            actor_id=usuario_id,
            metadata={
                "origen": "reclasificacion",
                "rubro_anterior": str(prev_rubro),
                "rubro_nuevo": str(rubro.id),
            },
        )
    except Exception:
        # O1: sin rastro no hay reclasificación → compensar.
        tx.rubro_id = prev_rubro
        tx.clasificada_por = prev_por
        tx.clasificada_at = prev_at
        await tx.save()
        raise

    if proponer_regla:
        # §1.9/D5: propuesta APRENDIDA inactiva; la activa el Financiero (/aprobar).
        from app.reglas.service import ReglasError, proponer_regla_aprendida

        try:
            await proponer_regla_aprendida(
                patron=patron.strip(),
                rubro_id=rubro.id,
                tipo_flujo=tx.tipo_flujo,
                usuario_id=usuario_id,
            )
        except ReglasError as e:
            raise TransaccionManualError(e.detalle, e.status) from e
    return tx
