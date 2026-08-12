# backend/app/modelos_moto/service.py
"""CRUD de ModeloMoto (COCK-02, CR-COCK) — catálogo administrable de modelos de moto.

Paralelo EXACTO de `rubros/service.py` (patrón auditado por Kimi en C1):
  - Baja LÓGICA (`activo=false`); un modelo con proyección no se borra (D2). El motor
    ya filtra por `activo` al proyectar.
  - Reactivar = PATCH `activo:true` → `modelo_moto.editado` {activo false→true} (B-3).
    PATCH `activo:false` → 422 (la baja va por POST /desactivar, evento propio).
  - Modelos de sistema (`es_sistema`) inmutables → 409.
  - Único por `nombre`: pre-check (mongomock) + DuplicateKeyError del índice real → 409.
  - Auditoría FAIL-CLOSED estilo O1 (B-5): mutar → emitir → si el emit falla, COMPENSAR
    (borrar el creado / revertir campos) y propagar.
"""

from decimal import Decimal

from beanie import PydanticObjectId
from pymongo.errors import DuplicateKeyError

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.domain.modelo_moto import ModeloMoto


class ModelosMotoError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


async def _obtener(modelo_id: str) -> ModeloMoto:
    try:
        mid = PydanticObjectId(modelo_id)
    except Exception:
        raise ModelosMotoError("modelo_id inválido", 422) from None
    m = await ModeloMoto.get(mid)
    if m is None:
        raise ModelosMotoError("el modelo no existe", 404)
    return m


async def listar_modelos(*, activo: bool | None = None) -> list[ModeloMoto]:
    filtros = []
    if activo is not None:
        filtros.append(ModeloMoto.activo == activo)
    return await ModeloMoto.find(*filtros).sort(+ModeloMoto.orden).to_list()


def _validar_planes(modelo: ModeloMoto) -> None:
    """PLAN-52: coherencia fail-closed del segundo plan. (plazo, cuota) del plan 2 van
    JUNTOS; `peso_plan1` es fracción 0..1 y sin plan 2 debe ser exactamente 1 (el mix
    completo del modelo va al único plan)."""
    tiene_plazo = modelo.plan2_plazo_semanas is not None
    tiene_cuota = modelo.plan2_cuota_semanal is not None
    if tiene_plazo != tiene_cuota:
        raise ModelosMotoError(
            "plan 2 incompleto: plazo y cuota semanal del plan 2 van juntos", 422
        )
    if not (Decimal("0") <= modelo.peso_plan1 <= Decimal("1")):
        raise ModelosMotoError("peso_plan1 debe ser una fracción entre 0 y 1", 422)
    if not tiene_plazo and modelo.peso_plan1 != Decimal("1"):
        raise ModelosMotoError(
            "sin plan 2, peso_plan1 debe ser 1 (todo el mix va al único plan)", 422
        )


async def crear_modelo(
    *,
    nombre: str,
    costo_auteco: Decimal,
    precio_venta_con_iva: Decimal,
    cuota_inicial: Decimal,
    cuota_semanal: Decimal,
    plazo_semanas: int,
    matricula: Decimal,
    participacion_mix: Decimal,
    usuario_id: str,
    plan2_plazo_semanas: int | None = None,
    plan2_cuota_semanal: Decimal | None = None,
    peso_plan1: Decimal = Decimal("1"),
) -> ModeloMoto:
    """POST: crea con `orden` = máx+1 y emite `modelo_moto.creado` (fail-closed)."""
    if await ModeloMoto.find_one(ModeloMoto.nombre == nombre) is not None:
        raise ModelosMotoError(f"ya existe un modelo '{nombre}'", 409)
    ultimo = await ModeloMoto.find_all().sort(-ModeloMoto.orden).first_or_none()
    modelo = ModeloMoto(
        nombre=nombre,
        costo_auteco=costo_auteco,
        precio_venta_con_iva=precio_venta_con_iva,
        cuota_inicial=cuota_inicial,
        cuota_semanal=cuota_semanal,
        plazo_semanas=plazo_semanas,
        matricula=matricula,
        participacion_mix=participacion_mix,
        plan2_plazo_semanas=plan2_plazo_semanas,
        plan2_cuota_semanal=plan2_cuota_semanal,
        peso_plan1=peso_plan1,
        orden=(ultimo.orden if ultimo is not None else 0) + 1,
    )
    _validar_planes(modelo)
    try:
        await modelo.insert()
    except DuplicateKeyError:
        raise ModelosMotoError(f"ya existe un modelo '{nombre}'", 409) from None

    try:
        await emit_audit(
            AuditEvento.modelo_moto_creado,
            entidad="modelo_moto",
            entidad_id=str(modelo.id),
            actor_id=usuario_id,
            metadata={"nombre": nombre, "orden": modelo.orden},
        )
    except Exception:
        await modelo.delete()  # saga O1: sin rastro no hay alta → compensar
        raise
    return modelo


_EDITABLES_MONEY = (
    "costo_auteco",
    "precio_venta_con_iva",
    "cuota_inicial",
    "cuota_semanal",
    "matricula",
    "participacion_mix",
    # PLAN-52: cuota del segundo plan y reparto entre planes (fracción 0..1)
    "plan2_cuota_semanal",
    "peso_plan1",
)


async def editar_modelo(
    *,
    modelo_id: str,
    usuario_id: str,
    nombre: str | None = None,
    orden: int | None = None,
    plazo_semanas: int | None = None,
    plan2_plazo_semanas: int | None = None,
    quitar_plan2: bool = False,
    activo: bool | None = None,
    campos_money: dict[str, Decimal] | None = None,
) -> ModeloMoto:
    """PATCH: edita atributos y reactiva (B-3). Emite `modelo_moto.editado` con
    {campo: {anterior, nuevo}} (fail-closed B-5). Ningún campo afecta el histórico:
    el motor es compute-only y recalcula con el catálogo vigente."""
    modelo = await _obtener(modelo_id)
    if modelo.es_sistema:
        raise ModelosMotoError(f"'{modelo.nombre}' es de sistema y es inmutable", 409)

    cambios: dict[str, dict] = {}
    previos: dict[str, object] = {}

    for campo, nuevo in (campos_money or {}).items():
        if campo not in _EDITABLES_MONEY:
            raise ModelosMotoError(f"campo no editable: {campo}", 422)
        actual = getattr(modelo, campo)
        if nuevo != actual:
            previos[campo] = actual
            cambios[campo] = {"anterior": str(actual), "nuevo": str(nuevo)}
            setattr(modelo, campo, nuevo)

    if plazo_semanas is not None and plazo_semanas != modelo.plazo_semanas:
        previos["plazo_semanas"] = modelo.plazo_semanas
        cambios["plazo_semanas"] = {
            "anterior": modelo.plazo_semanas,
            "nuevo": plazo_semanas,
        }
        modelo.plazo_semanas = plazo_semanas

    if plan2_plazo_semanas is not None and (
        plan2_plazo_semanas != modelo.plan2_plazo_semanas
    ):
        previos["plan2_plazo_semanas"] = modelo.plan2_plazo_semanas
        cambios["plan2_plazo_semanas"] = {
            "anterior": modelo.plan2_plazo_semanas,
            "nuevo": plan2_plazo_semanas,
        }
        modelo.plan2_plazo_semanas = plan2_plazo_semanas

    if quitar_plan2 and (
        modelo.plan2_plazo_semanas is not None
        or modelo.plan2_cuota_semanal is not None
        or modelo.peso_plan1 != Decimal("1")
    ):
        for campo, nuevo in (
            ("plan2_plazo_semanas", None),
            ("plan2_cuota_semanal", None),
            ("peso_plan1", Decimal("1")),
        ):
            actual = getattr(modelo, campo)
            if nuevo != actual:
                previos[campo] = actual
                cambios[campo] = {"anterior": str(actual), "nuevo": str(nuevo)}
                setattr(modelo, campo, nuevo)

    if activo is not None:
        if activo is False:
            raise ModelosMotoError(
                "la baja va por POST /modelos-moto/{id}/desactivar", 422
            )
        if not modelo.activo:
            previos["activo"] = modelo.activo
            cambios["activo"] = {"anterior": False, "nuevo": True}
            modelo.activo = True

    if nombre is not None and nombre != modelo.nombre:
        if await ModeloMoto.find_one(ModeloMoto.nombre == nombre) is not None:
            raise ModelosMotoError(f"ya existe un modelo '{nombre}'", 409)
        previos["nombre"] = modelo.nombre
        cambios["nombre"] = {"anterior": modelo.nombre, "nuevo": nombre}
        modelo.nombre = nombre

    if orden is not None and orden != modelo.orden:
        previos["orden"] = modelo.orden
        cambios["orden"] = {"anterior": modelo.orden, "nuevo": orden}
        modelo.orden = orden

    if not cambios:
        raise ModelosMotoError("nada que editar (ningún campo cambia)", 422)

    _validar_planes(modelo)  # PLAN-52: el estado FINAL debe ser coherente (422)

    try:
        await modelo.save()
    except DuplicateKeyError:
        raise ModelosMotoError(f"ya existe un modelo '{modelo.nombre}'", 409) from None

    try:
        await emit_audit(
            AuditEvento.modelo_moto_editado,
            entidad="modelo_moto",
            entidad_id=str(modelo.id),
            actor_id=usuario_id,
            metadata={"cambios": cambios},
        )
    except Exception:
        for campo, valor in previos.items():
            setattr(modelo, campo, valor)
        await modelo.save()
        raise
    return modelo


async def desactivar_modelo(*, modelo_id: str, usuario_id: str) -> ModeloMoto:
    """POST /desactivar: baja LÓGICA. Emite `modelo_moto.desactivado` (fail-closed)."""
    modelo = await _obtener(modelo_id)
    if modelo.es_sistema:
        raise ModelosMotoError(f"'{modelo.nombre}' es de sistema y es inmutable", 409)
    if not modelo.activo:
        raise ModelosMotoError(f"'{modelo.nombre}' ya está inactivo", 409)

    modelo.activo = False
    await modelo.save()
    try:
        await emit_audit(
            AuditEvento.modelo_moto_desactivado,
            entidad="modelo_moto",
            entidad_id=str(modelo.id),
            actor_id=usuario_id,
            metadata={"nombre": modelo.nombre},
        )
    except Exception:
        modelo.activo = True
        await modelo.save()
        raise
    return modelo
