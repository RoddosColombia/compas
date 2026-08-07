# backend/app/domain/rubros_neutros.py
"""Rubros NEUTROS para la lectura de la realidad (una verdad, un lugar).

Dinero que entró/salió de la cuenta pero NO es recaudo ni gasto operativo: contarlo
inflaría el ingreso real (metas) o el ejecutado anclado (E1). La exclusión se resuelve
SIEMPRE por `rubro_id` (nunca por grupo ni `es_sistema`): el id es la identidad estable;
el nombre puede cambiar y grupo/es_sistema barren de más.

El set:
  • 'Reversas y devoluciones'    — FIX-B: reversas GMF, devoluciones, reembolsos.
  • 'Tránsito Wava mes anterior' — CR-WAVA: depósito Wava del mes previo que llega.
  • 'Ajuste de conciliación'     — CR-WAVA: contra-asiento de una reapertura de cierre.

Promovido desde `metas_ingreso.service` (donde nació con FIX-B) para que E1 y metas
compartan exactamente el mismo conjunto — no dos copias que puedan divergir. El set Y su
resolver nombre→id viven aquí (una verdad, un lugar); `metas_ingreso` los re-exporta
y el loader E1 los importa de aquí."""

from beanie import PydanticObjectId
from beanie.operators import In

from app.domain.rubro import Rubro

RUBROS_NEUTROS_INGRESO_REAL: frozenset[str] = frozenset(
    {
        "Reversas y devoluciones",
        "Tránsito Wava mes anterior",
        "Ajuste de conciliación",
    }
)


async def _ids_rubros_neutros() -> set[PydanticObjectId]:
    """IDs de los rubros neutros (por nombre) presentes en la BD. Vacío si ninguno
    existe todavía (p. ej. antes de FIX-B) → la exclusión es inocua. La exclusión se
    resuelve SIEMPRE por `rubro_id` (una verdad compartida por E1 y metas)."""
    return {
        r.id
        async for r in Rubro.find(In(Rubro.nombre, list(RUBROS_NEUTROS_INGRESO_REAL)))
    }
