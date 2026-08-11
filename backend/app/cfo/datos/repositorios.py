"""FABS · única puerta de escritura del módulo. SOLO colecciones cfo_*. (S1: ninguna
otra subruta de cfo/ toca el driver de Mongo.)"""

from app.cfo.goldens.modelo import CFOGolden


async def upsert_golden(g: CFOGolden) -> bool:
    """Inserta el golden si no existe uno con el mismo (concepto, nota). Devuelve True
    si insertó, False si ya existía. Idempotente."""
    existe = await CFOGolden.find_one(
        CFOGolden.concepto == g.concepto, CFOGolden.nota == g.nota
    )
    if existe is not None:
        return False
    await g.insert()
    return True
