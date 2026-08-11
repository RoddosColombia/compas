# backend/app/facturas/service.py
"""CRUD de Factura (C11, PR-2a "Fidelidad de caja") — carga de facturas para liquidar
el IVA cuatrimestral.

Paralelo del patrón auditado (rubros/modelos_moto): baja LÓGICA (`anular`), único por
(tercero_nit, numero), auditoría FAIL-CLOSED estilo O1 (mutar → emitir → si el emit
falla, COMPENSAR). El IVA se calcula AQUÍ (regla 1): `iva_valor = base × tarifa`,
`total = base + iva_valor`. `obtener_facturas_iva()` proyecta las facturas ACTIVAS a
`FacturaIva` para el liquidador (puente C11↔liquidación)."""

import re
from decimal import Decimal

from beanie import PydanticObjectId
from pymongo.errors import DuplicateKeyError

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.domain.configuracion import ClaveConfig, Configuracion
from app.domain.factura import Factura, OrigenFactura, TipoFactura
from app.iva.liquidacion import (
    FacturaIva,
    Periodicidad,
    SaldoFavorDeclarado,
    iva_desde_base,
)

_MES = re.compile(r"^\d{4}-\d{2}$")


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
    base_gravable: Decimal | None = None,
    tarifa_iva: Decimal | None = None,
    iva_valor: Decimal | None = None,
    deducible: bool = False,
) -> Factura:
    """Crea la factura calculando IVA y total en el backend (regla 1). Emite
    `factura.creada` (fail-closed). Duplicado (tercero_nit, numero) → 409.

    Precedencia del IVA (D-13 / pieza 2): si viene `iva_valor` directo, MANDA y
    base/tarifa quedan opcionales (no se inventa una base — captura agregada del IVA
    generado del mes). Sin él, se exige base+tarifa y el IVA = base × tarifa."""
    if (
        await Factura.find_one(
            Factura.tercero_nit == tercero_nit, Factura.numero == numero
        )
        is not None
    ):
        raise FacturasError(
            f"ya existe la factura '{numero}' del NIT {tercero_nit}", 409
        )

    if iva_valor is not None:
        # el IVA dado manda; total = base + IVA si hay base, si no el único monto
        # conocido es el propio IVA (no se fabrica una base ni un total, R5)
        iva = iva_valor
        total = (base_gravable + iva) if base_gravable is not None else iva
    else:
        if base_gravable is None or tarifa_iva is None:
            raise FacturasError(
                "sin iva_valor, base_gravable y tarifa_iva son obligatorias", 422
            )
        iva = iva_desde_base(base_gravable, tarifa_iva)
        total = base_gravable + iva
    factura = Factura(
        tipo=TipoFactura(tipo),
        origen=OrigenFactura(origen),
        numero=numero,
        tercero_nombre=tercero_nombre,
        tercero_nit=tercero_nit,
        fecha=fecha,
        base_gravable=base_gravable,
        tarifa_iva=tarifa_iva,
        iva_valor=iva,
        total=total,
        deducible=deducible,
        # captura manual = el usuario dio el valor explícitamente → ya decidido
        # (no entra al contador de "sin decidir" del §2, aunque haya elegido "No").
        deducible_decidido=True,
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
                "iva_valor": str(iva),
            },
        )
    except Exception:
        await factura.delete()  # saga O1: sin rastro no hay alta → compensar
        raise
    return factura


async def _nit_roddos() -> str | None:
    """NIT propio de RODDOS (clave NIT_RODDOS, última vigencia). Ausente → None. El NIT
    vive en Configuracion, jamás hardcodeado."""
    cfg = (
        await Configuracion.find(Configuracion.clave == ClaveConfig.NIT_RODDOS)
        .sort(-Configuracion.vigente_desde)
        .limit(1)
        .to_list()
    )
    if cfg and cfg[0].valor_json:
        nit = cfg[0].valor_json.get("nit")
        return str(nit) if nit else None
    return None


async def registrar_iva_generado(
    *, usuario_id: str, mes: str, iva_valor: Decimal
) -> Factura:
    """Pieza 2 (decisión CEO): captura MANUAL AGREGADA del IVA generado de un mes
    vencido. Arma una venta sintética `VENTAS-YYYY-MM` a nombre de RODDOS con solo el
    IVA del mes (D-13: el IVA se lee, no se calcula; no se inventa una base). El índice
    único (tercero_nit, numero) impide cargarla dos veces (→ 409). Aparece en el
    generado del período de `mes`."""
    if not _MES.match(mes):
        raise FacturasError("mes debe ser 'YYYY-MM'", 422)
    if iva_valor <= 0:
        raise FacturasError("el IVA generado debe ser mayor que cero", 422)
    nit = await _nit_roddos()
    if not nit:
        raise FacturasError(
            "NIT_RODDOS no está en Configuracion: no se puede registrar el IVA "
            "generado a nombre de RODDOS. Corra la migración 20260728_e2_facturas_iva.",
            409,
        )
    return await crear_factura(
        usuario_id=usuario_id,
        tipo="venta",
        origen="otro",  # agregado del mes: no es una venta de moto concreta
        numero=f"VENTAS-{mes}",
        tercero_nombre="RODDOS",
        tercero_nit=nit,
        fecha=f"{mes}-01",  # día 1 → el período se deriva de la fecha
        iva_valor=iva_valor,
    )


async def actualizar_factura(
    *,
    factura_id: str,
    usuario_id: str,
    deducible: bool | None = None,
    origen: str | None = None,
) -> tuple[Factura, bool]:
    """CR-E2-EDITAR: edita SOLO los campos no fiscales `deducible`/`origen` (la factura
    es inmutable en lo fiscal: montos/fechas/tipo se anulan y se recargan). Emite
    `factura.actualizada` con autor (fail-closed saga O1). Solo cuenta y emite si algo
    cambió de verdad; sin cambios → 422. `deducible` en una venta → 422 (solo compras).

    Devuelve `(factura, cambió)`: `cambió=False` cuando los valores enviados ya eran
    los actuales (no-op, sin evento). No toca `motor.py` ni la proyección."""
    if deducible is None and origen is None:
        raise FacturasError("nada que actualizar: envía deducible u origen", 422)

    factura = await _obtener(factura_id)
    cambios: dict[str, dict] = {}
    previos: dict[str, object] = {}

    if origen is not None and origen != factura.origen.value:
        cambios["origen"] = {"antes": factura.origen.value, "despues": origen}
        previos["origen"] = factura.origen
        factura.origen = OrigenFactura(origen)

    if deducible is not None:
        if factura.tipo == TipoFactura.venta:
            # deducible no aplica a ventas: 'Sí' es error; 'No' es no-op silencioso
            # (nunca se "decide" la deducibilidad de una venta → no toca decidido).
            if deducible:
                raise FacturasError(
                    "deducible solo aplica a compras; esta factura es de venta", 422
                )
        else:
            # cambia el VALOR → se registra el cambio de valor
            if deducible != factura.deducible:
                cambios["deducible"] = {
                    "antes": factura.deducible,
                    "despues": deducible,
                }
                previos["deducible"] = factura.deducible
                factura.deducible = deducible
            # marcar "No" sobre una compra SIN DECIDIR es un cambio real aunque el
            # bool no varíe: lo que cambia es la DECISIÓN (sin decidir → decidido).
            if not factura.deducible_decidido:
                cambios["deducible_decidido"] = {"antes": False, "despues": True}
                previos["deducible_decidido"] = factura.deducible_decidido
                factura.deducible_decidido = True

    if not cambios:  # los valores enviados ya eran los actuales → no-op sin evento
        return factura, False

    await factura.save()
    try:
        await emit_audit(
            AuditEvento.factura_actualizada,
            entidad="factura",
            entidad_id=str(factura.id),
            actor_id=usuario_id,
            # sin PII (Ley 1581): CUFE+número identifican; nada de tercero.
            metadata={"numero": factura.numero, "cufe": factura.cufe, **cambios},
        )
    except Exception:
        for campo, valor in previos.items():  # saga O1: sin rastro, no hay cambio
            setattr(factura, campo, valor)
        await factura.save()
        raise
    return factura, True


async def actualizar_deducibilidad_lote(
    *, ids: list[str], deducible: bool, usuario_id: str
) -> list[dict]:
    """Marca la deducibilidad de un lote (spec de diseño §4). Tolerante a fallos
    PARCIALES y fail-closed POR FACTURA (refinamiento CEO): cada id es su propia saga;
    si una falla (incl. el emit del evento, ya revertido en `actualizar_factura`), sale
    con `estado='error'` y su motivo, y las demás siguen. Estados: actualizada |
    sin_cambio | error."""
    resultados: list[dict] = []
    for fid in ids:
        try:
            _, cambio = await actualizar_factura(
                factura_id=fid, usuario_id=usuario_id, deducible=deducible
            )
            resultados.append(
                {"id": fid, "estado": "actualizada" if cambio else "sin_cambio"}
            )
        except FacturasError as e:
            resultados.append({"id": fid, "estado": "error", "motivo": e.detalle})
        except Exception:
            resultados.append({"id": fid, "estado": "error", "motivo": "error interno"})
    return resultados


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


async def obtener_saldo_favor_declarado() -> SaldoFavorDeclarado | None:
    """Última vigencia de `SALDO_FAVOR_IVA_DECLARADO` (la cifra oficial de la
    declaración DIAN anterior a los datos de COMPAS — CEO 2026-08-11). Ausente o
    incompleta → None (no aplica; NUNCA se inventa un saldo, R5)."""
    cfg = (
        await Configuracion.find(
            Configuracion.clave == ClaveConfig.SALDO_FAVOR_IVA_DECLARADO
        )
        .sort(-Configuracion.vigente_desde)
        .limit(1)
        .to_list()
    )
    if not (cfg and cfg[0].valor_json):
        return None
    aplica_desde = cfg[0].valor_json.get("aplica_desde")
    valor = cfg[0].valor_json.get("valor")
    if not aplica_desde or valor is None:
        return None
    try:
        return SaldoFavorDeclarado(
            aplica_desde=str(aplica_desde), valor=Decimal(str(valor))
        )
    except Exception:
        return None  # valor ilegible = no aplica; jamás se adivina (regla 7)


async def obtener_calendario_dian() -> dict:
    """Última vigencia de `CALENDARIO_DIAN` ({"2026": {"ene_abr": "2026-05-13", ...}}).
    Ausente → {} (la UI omite la línea del próximo pago; NUNCA se inventa una fecha,
    R5). Es la única fuente del §3③ del spec de diseño."""
    cfg = (
        await Configuracion.find(Configuracion.clave == ClaveConfig.CALENDARIO_DIAN)
        .sort(-Configuracion.vigente_desde)
        .limit(1)
        .to_list()
    )
    return cfg[0].valor_json if cfg and cfg[0].valor_json else {}


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
