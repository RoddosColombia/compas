# backend/app/obligaciones/service.py
"""CRUD de Obligacion + FacturaObligacion (D2 §2, CR-D2) — auditado.

Patrón saga O1 fail-closed (espejo de `modelos_moto`/`escenarios_impacto`): mutar →
emitir → si el emit falla, compensar y propagar. Bajas lógicas (`activo=false`). La
obligación de sistema (semilla Auteco, `es_sistema`) es inmutable/no-borrable. Registro
de facturas valida `plazo_base ≤ plazo_elegido ≤ plazo_max` de la obligación. Simular
(política §5) NO pasa por aquí (compute-only)."""

from beanie import PydanticObjectId
from pydantic import ValidationError

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.core.money import Money
from app.core.time import now_bogota
from app.domain.obligacion import FacturaObligacion, Obligacion


class ObligacionesError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


async def _obtener(obligacion_id: str) -> Obligacion:
    try:
        oid = PydanticObjectId(obligacion_id)
    except Exception:
        raise ObligacionesError("obligacion_id inválido", 422) from None
    o = await Obligacion.get(oid)
    if o is None:
        raise ObligacionesError("la obligación no existe", 404)
    return o


async def listar_obligaciones(*, activo: bool | None = None) -> list[Obligacion]:
    filtros = []
    if activo is not None:
        filtros.append(Obligacion.activo == activo)
    return await Obligacion.find(*filtros).sort(+Obligacion.nombre).to_list()


async def crear_obligacion(*, campos: dict, usuario_id: str) -> Obligacion:
    """`campos` = los atributos de la obligación (comunes + los de su naturaleza). El
    validador del dominio exige el set correcto; ValidationError → 422."""
    try:
        obligacion = Obligacion(
            creado_por=usuario_id,
            actualizado_at=now_bogota(),
            activo=True,
            **campos,
        )
    except ValidationError as e:
        raise ObligacionesError(
            f"obligación inválida: {e.errors()[0]['msg']}", 422
        ) from e
    await obligacion.insert()
    try:
        await emit_audit(
            AuditEvento.obligacion_creada,
            entidad="obligacion",
            entidad_id=str(obligacion.id),
            actor_id=usuario_id,
            metadata={"nombre": obligacion.nombre, "naturaleza": obligacion.naturaleza},
        )
    except Exception:
        await obligacion.delete()  # saga O1
        raise
    return obligacion


_EDITABLES_COMUNES = ("nombre", "acreedor")
_EDITABLES_CUOTAS = (
    "monto_total",
    "n_cuotas",
    "periodicidad_meses",
    "tasa_mensual",
    "fecha_inicio",
    "meses_gracia",
)
_EDITABLES_FACT = ("plazo_base_dias", "plazo_max_dias", "tasa_excedente_mensual")


async def editar_obligacion(
    *,
    obligacion_id: str,
    usuario_id: str,
    campos: dict | None = None,
    activo: bool | None = None,
) -> Obligacion:
    """PATCH: edita atributos (no la naturaleza — es inmutable) y reactiva. `campos`
    solo puede tocar los editables de la naturaleza de la obligación."""
    obligacion = await _obtener(obligacion_id)
    if obligacion.es_sistema:
        raise ObligacionesError(
            f"'{obligacion.nombre}' es de sistema y es inmutable", 409
        )

    permitidos = set(_EDITABLES_COMUNES) | set(
        _EDITABLES_CUOTAS if obligacion.naturaleza == "cuotas" else _EDITABLES_FACT
    )
    cambios: dict[str, dict] = {}
    previos: dict[str, object] = {}

    for campo, nuevo in (campos or {}).items():
        if campo not in permitidos:
            raise ObligacionesError(f"campo no editable: {campo}", 422)
        actual = getattr(obligacion, campo)
        if nuevo != actual:
            previos[campo] = actual
            cambios[campo] = {"anterior": str(actual), "nuevo": str(nuevo)}
            setattr(obligacion, campo, nuevo)

    if activo is not None:
        if activo is False:
            raise ObligacionesError("la baja va por DELETE /obligaciones/{id}", 422)
        if not obligacion.activo:
            previos["activo"] = obligacion.activo
            cambios["activo"] = {"anterior": False, "nuevo": True}
            obligacion.activo = True

    if (
        obligacion.naturaleza == "facturacion"
        and obligacion.plazo_max_dias is not None
        and obligacion.plazo_base_dias is not None
        and obligacion.plazo_max_dias < obligacion.plazo_base_dias
    ):
        raise ObligacionesError("plazo_max_dias no puede ser menor que plazo_base_dias")

    if not cambios:
        raise ObligacionesError("nada que editar (ningún campo cambia)", 422)

    obligacion.actualizado_at = now_bogota()
    await obligacion.save()
    try:
        await emit_audit(
            AuditEvento.obligacion_editada,
            entidad="obligacion",
            entidad_id=str(obligacion.id),
            actor_id=usuario_id,
            metadata={"cambios": cambios},
        )
    except Exception:
        for campo, valor in previos.items():
            setattr(obligacion, campo, valor)
        await obligacion.save()
        raise
    return obligacion


async def eliminar_obligacion(*, obligacion_id: str, usuario_id: str) -> None:
    obligacion = await _obtener(obligacion_id)
    if obligacion.es_sistema:
        raise ObligacionesError(
            f"'{obligacion.nombre}' es de sistema y no se puede eliminar", 409
        )
    if not obligacion.activo:
        raise ObligacionesError(f"'{obligacion.nombre}' ya está inactiva", 409)
    obligacion.activo = False
    obligacion.actualizado_at = now_bogota()
    await obligacion.save()
    try:
        await emit_audit(
            AuditEvento.obligacion_eliminada,
            entidad="obligacion",
            entidad_id=str(obligacion.id),
            actor_id=usuario_id,
            metadata={"nombre": obligacion.nombre},
        )
    except Exception:
        obligacion.activo = True
        await obligacion.save()
        raise


# ── Facturas ──────────────────────────────────────────────────────────────────


async def registrar_factura(
    *,
    obligacion_id: str,
    fecha_factura: str,
    valor: Money,
    plazo_elegido_dias: int,
    nota: str | None,
    usuario_id: str,
) -> FacturaObligacion:
    obligacion = await _obtener(obligacion_id)
    if obligacion.naturaleza != "facturacion":
        raise ObligacionesError(
            "solo las obligaciones de facturación registran facturas", 422
        )
    base = obligacion.plazo_base_dias or 0
    maximo = obligacion.plazo_max_dias or 0
    if not base <= plazo_elegido_dias <= maximo:
        raise ObligacionesError(
            f"plazo_elegido_dias debe estar en [{base}, {maximo}]", 422
        )
    factura = FacturaObligacion(
        obligacion_id=obligacion.id,
        fecha_factura=fecha_factura,
        valor=valor,
        plazo_elegido_dias=plazo_elegido_dias,
        nota=nota,
        activo=True,
        registrada_por=usuario_id,
        registrada_at=now_bogota(),
    )
    await factura.insert()
    try:
        await emit_audit(
            AuditEvento.factura_obligacion_registrada,
            entidad="factura_obligacion",
            entidad_id=str(factura.id),
            actor_id=usuario_id,
            metadata={
                "obligacion_id": str(obligacion.id),
                "fecha_factura": fecha_factura,
                "plazo_elegido_dias": plazo_elegido_dias,
            },
        )
    except Exception:
        await factura.delete()
        raise
    return factura


async def listar_facturas(
    *, obligacion_id: str | None = None, activo: bool | None = True
) -> list[FacturaObligacion]:
    filtros = []
    if obligacion_id is not None:
        try:
            filtros.append(
                FacturaObligacion.obligacion_id == PydanticObjectId(obligacion_id)
            )
        except Exception:
            raise ObligacionesError("obligacion_id inválido", 422) from None
    if activo is not None:
        filtros.append(FacturaObligacion.activo == activo)
    return await FacturaObligacion.find(*filtros).to_list()


async def anular_factura(*, factura_id: str, usuario_id: str) -> None:
    try:
        fid = PydanticObjectId(factura_id)
    except Exception:
        raise ObligacionesError("factura_id inválido", 422) from None
    factura = await FacturaObligacion.get(fid)
    if factura is None:
        raise ObligacionesError("la factura no existe", 404)
    if not factura.activo:
        raise ObligacionesError("la factura ya está anulada", 409)
    factura.activo = False
    await factura.save()
    try:
        await emit_audit(
            AuditEvento.factura_obligacion_anulada,
            entidad="factura_obligacion",
            entidad_id=str(factura.id),
            actor_id=usuario_id,
            metadata={"obligacion_id": str(factura.obligacion_id)},
        )
    except Exception:
        factura.activo = True
        await factura.save()
        raise
