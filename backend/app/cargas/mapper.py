# backend/app/cargas/mapper.py
"""Puente parser → dominio: MovimientoBancario (DTO del parser) → Transaccion.

Puro y sin Mongo: el servicio de carga resuelve `rubro_id` ('Por clasificar') y
`mes_id` (MesControl del mes derivado de la fecha) y se los pasa aquí. La
derivación de `id_banco` y el mapeo tipo(débito/crédito)→tipo_flujo(egreso/ingreso)
viven aquí para que sean verificables sin base de datos.
"""

from beanie import PydanticObjectId

from app.domain.rubro import TipoFlujo
from app.domain.transaccion import Transaccion, derivar_id_banco
from app.parsers.bank_parsers import MovimientoBancario, TipoMovimiento

_TIPO_A_FLUJO = {
    TipoMovimiento.CREDITO: TipoFlujo.INGRESO,  # entra plata
    TipoMovimiento.DEBITO: TipoFlujo.EGRESO,  # sale plata
}


def movimiento_a_transaccion(
    mov: MovimientoBancario,
    *,
    rubro_id: PydanticObjectId,
    mes_id: PydanticObjectId,
    carga_id: PydanticObjectId | None = None,
    ocurrencia: int = 1,
    regla_id: PydanticObjectId | None = None,
) -> Transaccion:
    """Construye una Transaccion a partir de un movimiento parseado.

    C3: el servicio de carga resuelve el rubro por reglas de clasificación —
    `rubro_id` llega ya decidido y `regla_id` es el rastro forense (§1.5/F-05) de
    la regla que clasificó; sin match, rubro='Por clasificar' y regla_id=None.
    `ocurrencia` es el ordinal de la huella dentro del archivo (Kimi A-01): lo asigna
    el servicio de carga contando repeticiones por (fecha, tipo, desc, monto)."""
    fecha = mov.fecha.isoformat()  # date → 'YYYY-MM-DD'
    tipo_flujo = _TIPO_A_FLUJO[mov.tipo]
    id_banco = derivar_id_banco(
        banco=mov.banco,
        fecha=fecha,
        descripcion=mov.descripcion,
        valor=mov.monto,
        tipo_flujo=tipo_flujo,
        referencia=mov.referencia,
        ocurrencia=ocurrencia,
    )
    # Moneda extranjera (Global66): si el parser capturó moneda, se conserva el
    # original re-derivable (hoy la hoja COP → 'COP'/1; valor_original == valor).
    valor_original = mov.monto if mov.moneda_original is not None else None
    return Transaccion(
        fecha=fecha,
        descripcion=mov.descripcion,
        valor=mov.monto,
        tipo_flujo=tipo_flujo,
        rubro_id=rubro_id,
        mes_id=mes_id,
        banco=mov.banco,
        id_banco=id_banco,
        moneda_original=mov.moneda_original,
        valor_original=valor_original,
        tasa_cambio=mov.tasa_cambio,
        carga_id=carga_id,
        regla_id=regla_id,
    )
