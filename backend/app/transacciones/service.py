# backend/app/transacciones/service.py
"""Creación de transacciones manuales (US-10, F-04).

MARCADO PARA AUDITORÍA KIMI (flujo crítico: crea movimientos de dinero).

Reglas: id_banco = 'MAN-'+ULID (único por construcción → dos manuales idénticos
coexisten, F-04); el mes de la fecha debe existir y NO estar cerrado (regla 4 —
las tardías llegan con el flujo de cierre, Sprint 4); rubro explícito debe existir,
estar activo y ser coherente con tipo_flujo (regla 7: no se adivina); sin rubro →
'Por clasificar'. Eventos: `transaccion.creada` en TODA creación manual (CR-S2,
Kimi M-1 — rastro forense permanente) + `transaccion.clasificada` si además el
usuario clasificó (rubro explícito)."""

from decimal import Decimal

from beanie import PydanticObjectId

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.core.time import now_utc
from app.core.ulid import new_ulid
from app.domain.bancos import Banco
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.rubro import Rubro, TipoFlujo
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
) -> Transaccion:
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
    else:
        rubro = await Rubro.find_one(Rubro.nombre == RUBRO_POR_CLASIFICAR)
        if rubro is None:
            raise TransaccionManualError(
                "falta el rubro de sistema 'Por clasificar' (correr semillas)",
                status=500,
            )

    tx = Transaccion(
        fecha=fecha,
        descripcion=descripcion,
        valor=valor,
        tipo_flujo=tipo_flujo,
        rubro_id=rubro.id,
        mes_id=mc.id,
        banco=Banco.MANUAL,
        id_banco=f"MAN-{new_ulid()}",
        clasificada_por=usuario_id if clasificada else None,
        clasificada_at=now_utc() if clasificada else None,
    )
    await tx.insert()

    # CR-S2 (Kimi M-1): TODA creación manual deja rastro forense permanente —
    # es la única vía por la que entra dinero sin archivo de banco.
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
    return tx
