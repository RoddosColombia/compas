# backend/app/parametros_proyeccion/service.py
"""Drivers del motor de proyección (COCK-02, CR-COCK) — get vigente + upsert versionado.

Versionado por `vigente_desde` (como Configuracion): actualizar crea o pisa la fila de
esa fecha; `obtener_vigente` devuelve la de mayor `vigente_desde`. Emite
`parametros_proyeccion.actualizado` fail-closed (saga O1): si el emit falla tras un
upsert que CREÓ la fila, se compensa borrándola; si solo la editó, se revierte el
documento previo. Un solo documento → compensación trivial."""

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.domain.parametros_proyeccion import ParametrosProyeccion


class ParametrosError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


async def obtener_vigente() -> ParametrosProyeccion | None:
    """La fila de mayor `vigente_desde` (los parámetros activos del motor)."""
    return (
        await ParametrosProyeccion.find_all()
        .sort(-ParametrosProyeccion.vigente_desde)
        .first_or_none()
    )


async def actualizar(
    *, vigente_desde: str, campos: dict, usuario_id: str, nota: str | None = None
) -> ParametrosProyeccion:
    """Upsert de la fila de `vigente_desde` con `campos` (ya validados/parseados a
    Decimal). Emite `parametros_proyeccion.actualizado` (fail-closed); la `nota`
    del editor (C3: por qué el cambio) viaja en la metadata del evento."""
    existente = await ParametrosProyeccion.find_one(
        ParametrosProyeccion.vigente_desde == vigente_desde
    )
    snapshot = existente.model_dump() if existente is not None else None
    creado = existente is None

    if existente is None:
        doc = ParametrosProyeccion(
            vigente_desde=vigente_desde, modificado_por=usuario_id, **campos
        )
        await doc.insert()
    else:
        for k, v in campos.items():
            setattr(existente, k, v)
        existente.modificado_por = usuario_id
        await existente.save()
        doc = existente

    try:
        await emit_audit(
            AuditEvento.parametros_proyeccion_actualizado,
            entidad="parametros_proyeccion",
            entidad_id=str(doc.id),
            actor_id=usuario_id,
            metadata={
                "vigente_desde": vigente_desde,
                "creado": creado,
                **({"nota": nota} if nota else {}),
            },
        )
    except Exception:
        # saga O1: sin rastro no hay cambio → compensar.
        if creado:
            await doc.delete()
        elif snapshot is not None:
            snapshot.pop("id", None)
            for k, v in snapshot.items():
                setattr(doc, k, v)
            await doc.save()
        raise
    return doc
