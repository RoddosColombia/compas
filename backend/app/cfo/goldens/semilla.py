"""FABS · lote semilla de goldens (origen='semilla'). Valores editables/corregibles por
el CEO. El set completo (240+60, con Fabián) llega en un incremento posterior.

Task 11: los 3 casos de abajo son valores reales, calculados a mano desde PROD
(solo lectura) por el controlador — snapshot 2026-08-11. Ya no son placeholder."""

from decimal import Decimal

from app.cfo.datos.repositorios import upsert_golden
from app.cfo.goldens.modelo import CFOGolden
from app.core.time import now_bogota

# Snapshot PROD 2026-08-11 (Task 11). Editables/corregibles por el CEO; el set
# completo (240+60, con Fabián) llega en un incremento posterior.
SEMILLA: list[dict] = [
    {
        "concepto": "caja_hoy",
        "valor_esperado": Decimal("704722003"),
        "tolerancia": Decimal("1"),
        "unidad": "COP",
        "nota": (
            "snapshot 2026-08-11: caja anclada a caja_inicial (params vigentes "
            "2026-08-10, sin movimientos en la ventana)"
        ),
    },
    {
        "concepto": "runway",
        "valor_esperado": None,  # ABSTENCIÓN
        "tolerancia": Decimal("0.1"),
        "unidad": "meses",
        "nota": (
            "snapshot 2026-08-11: sin quema neta en PROD -> runway N/A (abstención)"
        ),
    },
    {
        "concepto": "iva_cuatrimestre",
        "valor_esperado": Decimal("36204698.10"),
        "tolerancia": Decimal("1"),
        "unidad": "COP",
        "nota": "snapshot 2026-08-11: C2-2026, vence DIAN 2026-09-10",
    },
]


async def sembrar_semilla() -> tuple[int, int]:
    now = now_bogota()
    insertados = duplicados = 0
    for c in SEMILLA:
        g = CFOGolden(
            concepto=c["concepto"],
            filtros=c.get("filtros", {}),
            valor_esperado=c["valor_esperado"],
            tolerancia=c["tolerancia"],
            unidad=c["unidad"],
            origen="semilla",
            nota=c.get("nota"),
            creado_at=now,
        )
        if await upsert_golden(g):
            insertados += 1
        else:
            duplicados += 1
    return insertados, duplicados
