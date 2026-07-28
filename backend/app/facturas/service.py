# backend/app/facturas/service.py
"""CRUD de Factura (C11, PR-2a "Fidelidad de caja") — carga de facturas para liquidar
el IVA cuatrimestral.

Paralelo del patrón auditado (rubros/modelos_moto): baja LÓGICA (`anular`), único por
(tercero_nit, numero), auditoría FAIL-CLOSED estilo O1 (mutar → emitir → si el emit
falla, COMPENSAR). El IVA se calcula AQUÍ (regla 1): `iva_valor = base × tarifa`,
`total = base + iva_valor`. `obtener_facturas_iva()` proyecta las facturas ACTIVAS a
`FacturaIva` para el liquidador (puente C11↔liquidación)."""

from decimal import Decimal

from beanie import PydanticObjectId
from pymongo.errors import DuplicateKeyError

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.domain.configuracion import ClaveConfig, Configuracion
from app.domain.factura import Factura, OrigenFactura, TipoFactura
from app.iva.liquidacion import FacturaIva, Periodicidad, iva_desde_base


class FacturasError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


async def _obtener(factura_id: str) -> Factura:
    try:
        fid = PydanticObjectId(factura_id)
    except Exception:
        raise FacturasError("factura_id inválido", 422) from None
    f = await Factura.get(fid)
    if f is None:
        raise FacturasError("la factura no existe", 404)
    return f


async def crear_factura(
    *,
    usuario_id: str,
    tipo: str,
    origen: str,
    numero: str,
    tercero_nombre: str,
    tercero_nit: str,
    fecha: str,
    base_gravable: Decimal,
    tarifa_iva: Decimal,
    deducible: bool = False,
) -> Factura:
    """Crea la factura calculando IVA y total en el backend (regla 1). Emite
    `factura.creada` (fail-closed). Duplicado (tercero_nit, numero) → 409."""
    if (
        await Factura.find_one(
            Factura.tercero_nit == tercero_nit, Factura.numero == numero
        )
        is not None
    ):
        raise FacturasError(
            f"ya existe la factura '{numero}' del NIT {tercero_nit}", 409
        )

    iva_valor = iva_desde_base(base_gravable, tarifa_iva)
    factura = Factura(
        tipo=TipoFactura(tipo),
        origen=OrigenFactura(origen),
        numero=numero,
        tercero_nombre=tercero_nombre,
        tercero_nit=tercero_nit,
        fecha=fecha,
        base_gravable=base_gravable,
        tarifa_iva=tarifa_iva,
        iva_valor=iva_valor,
        total=base_gravable + iva_valor,
        deducible=deducible,
    )
    try:
        await factura.insert()
    except DuplicateKeyError:
        raise FacturasError(
            f"ya existe la factura '{numero}' del NIT {tercero_nit}", 409
        ) from None

    try:
        await emit_audit(
            AuditEvento.factura_creada,
            entidad="factura",
            entidad_id=str(factura.id),
            actor_id=usuario_id,
            metadata={
                "tipo": tipo,
                "numero": numero,
                "tercero_nit": tercero_nit,
                "iva_valor": str(iva_valor),
            },
        )
    except Exception:
        await factura.delete()  # saga O1: sin rastro no hay alta → compensar
        raise
    return factura


async def listar_facturas(*, activo: bool | None = None) -> list[Factura]:
    filtros = []
    if activo is not None:
        filtros.append(Factura.activo == activo)
    return await Factura.find(*filtros).sort(+Factura.fecha).to_list()


async def anular_factura(*, factura_id: str, usuario_id: str) -> Factura:
    """Baja LÓGICA (una factura mal cargada no se borra). Emite `factura.anulada`
    (fail-closed). Ya anulada → 409."""
    factura = await _obtener(factura_id)
    if not factura.activo:
        raise FacturasError(f"la factura '{factura.numero}' ya está anulada", 409)

    factura.activo = False
    await factura.save()
    try:
        await emit_audit(
            AuditEvento.factura_anulada,
            entidad="factura",
            entidad_id=str(factura.id),
            actor_id=usuario_id,
            metadata={"numero": factura.numero, "tercero_nit": factura.tercero_nit},
        )
    except Exception:
        factura.activo = True
        await factura.save()
        raise
    return factura


async def obtener_periodicidad() -> Periodicidad:
    """Periodicidad de IVA VIGENTE (clave CONFIGURACION `PERIODICIDAD_IVA`). Ausente o
    valor no reconocido → cuatrimestral (realidad actual RODDOS; nunca crashea)."""
    cfg = (
        await Configuracion.find(Configuracion.clave == ClaveConfig.PERIODICIDAD_IVA)
        .sort(-Configuracion.vigente_desde)
        .limit(1)
        .to_list()
    )
    if cfg and cfg[0].valor_json:
        valor = cfg[0].valor_json.get("periodicidad")
        if valor in Periodicidad._value2member_map_:
            return Periodicidad(valor)
    return Periodicidad.cuatrimestral


async def obtener_facturas_iva() -> list[FacturaIva]:
    """Proyecta las facturas ACTIVAS a `FacturaIva` (insumo del liquidador). Una
    factura anulada no afecta la liquidación."""
    activas = await listar_facturas(activo=True)
    return [
        FacturaIva(
            tipo=f.tipo.value,
            fecha=f.fecha,
            iva_valor=f.iva_valor,
            deducible=f.deducible,
        )
        for f in activas
    ]
