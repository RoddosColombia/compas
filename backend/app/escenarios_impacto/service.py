# backend/app/escenarios_impacto/service.py
"""CRUD de EscenarioImpacto (D1 §2, CR-D1) — escenarios what-if nombrados, auditados.

Patrón espejo de `modelos_moto/service.py` (saga O1 auditada por Kimi en C1/COCK):
  - Guardar es EXPLÍCITO; simular no escribe. Baja LÓGICA (`activo=false`).
  - Reactivar = editar `activo:true` → `escenario_impacto.editado` {activo false→true}.
  - Único por `nombre` entre activos (pre-check; la baja libera el nombre).
  - Auditoría FAIL-CLOSED: mutar → emitir → si el emit falla, COMPENSAR y propagar.
"""

from beanie import PydanticObjectId

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.core.time import now_bogota
from app.domain.escenario_impacto import AjusteEmbebido, EscenarioImpacto


class EscenariosError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


async def _obtener(escenario_id: str) -> EscenarioImpacto:
    try:
        eid = PydanticObjectId(escenario_id)
    except Exception:
        raise EscenariosError("escenario_id inválido", 422) from None
    e = await EscenarioImpacto.get(eid)
    if e is None:
        raise EscenariosError("el escenario no existe", 404)
    return e


async def _nombre_tomado(
    nombre: str, excluir_id: PydanticObjectId | None = None
) -> bool:
    e = await EscenarioImpacto.find_one(
        EscenarioImpacto.nombre == nombre,
        EscenarioImpacto.activo == True,  # noqa: E712
    )
    return e is not None and e.id != excluir_id


async def listar_escenarios(*, activo: bool | None = None) -> list[EscenarioImpacto]:
    filtros = []
    if activo is not None:
        filtros.append(EscenarioImpacto.activo == activo)
    return (
        await EscenarioImpacto.find(*filtros).sort(+EscenarioImpacto.nombre).to_list()
    )


async def crear_escenario(
    *,
    nombre: str,
    descripcion: str | None,
    ajustes: list[AjusteEmbebido],
    usuario_id: str,
) -> EscenarioImpacto:
    if await _nombre_tomado(nombre):
        raise EscenariosError(f"ya existe un escenario '{nombre}'", 409)
    escenario = EscenarioImpacto(
        nombre=nombre,
        descripcion=descripcion,
        ajustes=ajustes,
        creado_por=usuario_id,
        actualizado_at=now_bogota(),
        activo=True,
    )
    await escenario.insert()
    try:
        await emit_audit(
            AuditEvento.escenario_impacto_creado,
            entidad="escenario_impacto",
            entidad_id=str(escenario.id),
            actor_id=usuario_id,
            metadata={"nombre": nombre, "n_ajustes": len(ajustes)},
        )
    except Exception:
        await escenario.delete()  # saga O1: sin rastro no hay alta → compensar
        raise
    return escenario


async def editar_escenario(
    *,
    escenario_id: str,
    usuario_id: str,
    nombre: str | None = None,
    descripcion: str | None = None,
    descripcion_set: bool = False,
    ajustes: list[AjusteEmbebido] | None = None,
    activo: bool | None = None,
) -> EscenarioImpacto:
    escenario = await _obtener(escenario_id)
    cambios: dict[str, dict] = {}
    previos: dict[str, object] = {}

    if nombre is not None and nombre != escenario.nombre:
        if await _nombre_tomado(nombre, excluir_id=escenario.id):
            raise EscenariosError(f"ya existe un escenario '{nombre}'", 409)
        previos["nombre"] = escenario.nombre
        cambios["nombre"] = {"anterior": escenario.nombre, "nuevo": nombre}
        escenario.nombre = nombre

    if descripcion_set and descripcion != escenario.descripcion:
        previos["descripcion"] = escenario.descripcion
        cambios["descripcion"] = {
            "anterior": escenario.descripcion,
            "nuevo": descripcion,
        }
        escenario.descripcion = descripcion

    if ajustes is not None:
        previos["ajustes"] = escenario.ajustes
        cambios["ajustes"] = {
            "anterior": len(escenario.ajustes),
            "nuevo": len(ajustes),
        }
        escenario.ajustes = ajustes

    if activo is not None:
        if activo is False:
            raise EscenariosError("la baja va por DELETE /escenarios-impacto/{id}", 422)
        if not escenario.activo:
            previos["activo"] = escenario.activo
            cambios["activo"] = {"anterior": False, "nuevo": True}
            escenario.activo = True

    if not cambios:
        raise EscenariosError("nada que editar (ningún campo cambia)", 422)

    escenario.actualizado_at = now_bogota()
    await escenario.save()
    try:
        await emit_audit(
            AuditEvento.escenario_impacto_editado,
            entidad="escenario_impacto",
            entidad_id=str(escenario.id),
            actor_id=usuario_id,
            metadata={"cambios": cambios},
        )
    except Exception:
        for campo, valor in previos.items():
            setattr(escenario, campo, valor)
        await escenario.save()
        raise
    return escenario


async def eliminar_escenario(*, escenario_id: str, usuario_id: str) -> None:
    """Baja LÓGICA. Emite `escenario_impacto.eliminado` (fail-closed)."""
    escenario = await _obtener(escenario_id)
    if not escenario.activo:
        raise EscenariosError(f"'{escenario.nombre}' ya está inactivo", 409)
    escenario.activo = False
    escenario.actualizado_at = now_bogota()
    await escenario.save()
    try:
        await emit_audit(
            AuditEvento.escenario_impacto_eliminado,
            entidad="escenario_impacto",
            entidad_id=str(escenario.id),
            actor_id=usuario_id,
            metadata={"nombre": escenario.nombre},
        )
    except Exception:
        escenario.activo = True
        await escenario.save()
        raise
