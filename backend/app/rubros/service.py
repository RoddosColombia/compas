# backend/app/rubros/service.py
"""C1 categorías administrables (CR-S4, GO Kimi PLAN-I 9.2): CRUD de rubros.

MARCADO PARA AUDITORÍA KIMI (estructura del sistema presupuestal; gate I-PR1).

Decisiones fijadas en el gate del PLAN:
  - D1/B-1: `tipo_flujo` se CONGELA si el rubro tiene referencias — no solo
    transacciones: ∃ Transaccion(rubro_id) ∨ ∃ PresupuestoLinea(rubro_id). Voltear
    el tipo dejaría una línea calculada como egreso siendo ingreso (integridad
    semántica, regla 4 en espíritu). Nombre/orden editables siempre (no afectan
    cómputo).
  - D2: la baja es LÓGICA (`activo=false`); el histórico queda intacto y visible.
    Alcance de la baja (B-2): (a) la clasificación rechaza rubros inactivos — la
    guarda vive en `transacciones/service.py::crear_transaccion_manual` (y aplicará
    a C3); (b) el motor del sugerido ya omite inactivos (filtro `activo==True` en
    `presupuesto/service.py::generar_sugerido`); (c) la Vista Control CONSERVA las
    líneas ya existentes del rubro inactivo (itera por líneas). Nota: una categoría
    de tipo INGRESO no recibe línea de presupuesto (el presupuesto §1.4 es de
    egresos) — no esperarla en Vista Control.
  - B-3: reactivar = PATCH `activo:true` → emite `rubro.editado` {activo:
    false→true} (rastro completo sin un 34.º evento). PATCH `activo:false` → 422:
    la baja va por POST /desactivar (evento `rubro.desactivado` propio).
  - B-5: auditoría FAIL-CLOSED estilo O1 — mutar → emitir → si el emit falla,
    COMPENSAR (borrar el rubro creado / revertir los campos) y propagar. Es un solo
    documento: la compensación es trivial y consistente con el estándar del ciclo.
  - Rubros de sistema (`es_sistema`): inmutables — PATCH y desactivar → 409.
  - Único (grupo, nombre): pre-check (mongomock) + DuplicateKeyError del índice
    real → 409, nunca 500.
"""

from beanie import PydanticObjectId
from pymongo.errors import DuplicateKeyError

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.domain.presupuesto import PresupuestoLinea
from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
from app.domain.transaccion import Transaccion


class RubrosError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


async def _obtener(rubro_id: str) -> Rubro:
    try:
        rid = PydanticObjectId(rubro_id)
    except Exception:
        raise RubrosError("rubro_id inválido", 422) from None
    r = await Rubro.get(rid)
    if r is None:
        raise RubrosError("el rubro no existe", 404)
    return r


async def _tiene_referencias(rubro_id: PydanticObjectId) -> bool:
    """B-1: referencias = transacciones O líneas de presupuesto (no solo
    movimientos). Consulta cruda con proyección {_id:1}: solo importa la
    EXISTENCIA — no pagar el parse del Document completo."""
    tx = await Transaccion.get_pymongo_collection().find_one(
        {"rubro_id": rubro_id}, {"_id": 1}
    )
    if tx is not None:
        return True
    ln = await PresupuestoLinea.get_pymongo_collection().find_one(
        {"rubro_id": rubro_id}, {"_id": 1}
    )
    return ln is not None


async def listar_rubros(
    *, activo: bool | None = None, grupo: RubroGrupo | None = None
) -> list[Rubro]:
    filtros = []
    if activo is not None:
        filtros.append(Rubro.activo == activo)
    if grupo is not None:
        filtros.append(Rubro.grupo == grupo)
    return await Rubro.find(*filtros).sort(+Rubro.orden).to_list()


async def crear_rubro(
    *,
    grupo: RubroGrupo,
    nombre: str,
    tipo_flujo: TipoFlujo,
    usuario_id: str,
) -> Rubro:
    """POST: crea con `orden` = máx(grupo)+1 y emite `rubro.creado` (fail-closed)."""
    if await Rubro.find_one(Rubro.grupo == grupo, Rubro.nombre == nombre) is not None:
        raise RubrosError(
            f"ya existe un rubro '{nombre}' en el grupo '{grupo.value}'", 409
        )
    ultimo = await Rubro.find(Rubro.grupo == grupo).sort(-Rubro.orden).first_or_none()
    rubro = Rubro(
        grupo=grupo,
        nombre=nombre,
        tipo_flujo=tipo_flujo,
        orden=(ultimo.orden if ultimo is not None else 0) + 1,
    )
    try:
        await rubro.insert()
    except DuplicateKeyError:
        # Carrera real: el índice único (grupo,nombre) atrapa al 2º → 409, no 500.
        raise RubrosError(
            f"ya existe un rubro '{nombre}' en el grupo '{grupo.value}'", 409
        ) from None

    try:
        await emit_audit(
            AuditEvento.rubro_creado,
            entidad="rubro",
            entidad_id=str(rubro.id),
            actor_id=usuario_id,
            metadata={
                "grupo": grupo.value,
                "nombre": nombre,
                "tipo_flujo": tipo_flujo.value,
                "orden": rubro.orden,
            },
        )
    except Exception:
        # B-5 (saga O1): sin rastro no hay cambio estructural → compensar.
        await rubro.delete()
        raise
    return rubro


async def editar_rubro(
    *,
    rubro_id: str,
    usuario_id: str,
    nombre: str | None = None,
    orden: int | None = None,
    tipo_flujo: TipoFlujo | None = None,
    activo: bool | None = None,
) -> Rubro:
    """PATCH: edita nombre/orden/tipo_flujo y reactiva (B-3). Emite `rubro.editado`
    con {campo: {anterior, nuevo}} (fail-closed B-5)."""
    rubro = await _obtener(rubro_id)
    if rubro.es_sistema:
        raise RubrosError(
            f"'{rubro.nombre}' es un rubro de sistema y es inmutable (§2.2)", 409
        )

    cambios: dict[str, dict] = {}
    previos: dict[str, object] = {}

    if activo is not None:
        if activo is False:
            raise RubrosError("la baja va por POST /rubros/{id}/desactivar (B-3)", 422)
        if not rubro.activo:
            previos["activo"] = rubro.activo
            cambios["activo"] = {"anterior": False, "nuevo": True}
            rubro.activo = True

    if tipo_flujo is not None and tipo_flujo is not rubro.tipo_flujo:
        if await _tiene_referencias(rubro.id):
            raise RubrosError(
                "tipo_flujo está congelado: el rubro tiene transacciones o líneas "
                "de presupuesto (D1/B-1)",
                409,
            )
        previos["tipo_flujo"] = rubro.tipo_flujo
        cambios["tipo_flujo"] = {
            "anterior": rubro.tipo_flujo.value,
            "nuevo": tipo_flujo.value,
        }
        rubro.tipo_flujo = tipo_flujo

    if nombre is not None and nombre != rubro.nombre:
        existe = await Rubro.find_one(
            Rubro.grupo == rubro.grupo, Rubro.nombre == nombre
        )
        if existe is not None:
            raise RubrosError(
                f"ya existe un rubro '{nombre}' en el grupo '{rubro.grupo.value}'",
                409,
            )
        previos["nombre"] = rubro.nombre
        cambios["nombre"] = {"anterior": rubro.nombre, "nuevo": nombre}
        rubro.nombre = nombre

    if orden is not None and orden != rubro.orden:
        previos["orden"] = rubro.orden
        cambios["orden"] = {"anterior": rubro.orden, "nuevo": orden}
        rubro.orden = orden

    if not cambios:
        raise RubrosError("nada que editar (ningún campo cambia)", 422)

    try:
        await rubro.save()
    except DuplicateKeyError:
        raise RubrosError(
            f"ya existe un rubro '{rubro.nombre}' en el grupo '{rubro.grupo.value}'",
            409,
        ) from None

    try:
        await emit_audit(
            AuditEvento.rubro_editado,
            entidad="rubro",
            entidad_id=str(rubro.id),
            actor_id=usuario_id,
            metadata={"cambios": cambios},
        )
    except Exception:
        # B-5 (saga O1): revertir los campos editados y propagar.
        for campo, valor in previos.items():
            setattr(rubro, campo, valor)
        await rubro.save()
        raise
    return rubro


async def desactivar_rubro(*, rubro_id: str, usuario_id: str) -> Rubro:
    """POST /desactivar: baja LÓGICA (D2). Emite `rubro.desactivado` (fail-closed)."""
    rubro = await _obtener(rubro_id)
    if rubro.es_sistema:
        raise RubrosError(
            f"'{rubro.nombre}' es un rubro de sistema y es inmutable (§2.2)", 409
        )
    if not rubro.activo:
        raise RubrosError(f"'{rubro.nombre}' ya está inactivo", 409)

    rubro.activo = False
    await rubro.save()
    try:
        await emit_audit(
            AuditEvento.rubro_desactivado,
            entidad="rubro",
            entidad_id=str(rubro.id),
            actor_id=usuario_id,
            metadata={"grupo": rubro.grupo.value, "nombre": rubro.nombre},
        )
    except Exception:
        # B-5 (saga O1): sin rastro no hay baja → revertir.
        rubro.activo = True
        await rubro.save()
        raise
    return rubro
