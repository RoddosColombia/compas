"""FABS · lote semilla de goldens (origen='semilla'). Valores editables/corregibles por
el CEO. El set completo (240+60, con Fabián) llega en un incremento posterior.
IMPORTANTE: los `valor_esperado` se sustituyen por los reales calculados a mano desde
PROD antes de dar por cerrado el incremento (ver Task 11)."""

from decimal import Decimal

from app.cfo.datos.repositorios import upsert_golden
from app.cfo.goldens.modelo import CFOGolden
from app.core.time import now_bogota

# Placeholder de estructura; los valores reales de PROD se fijan en la Task 11.
SEMILLA: list[dict] = [
    {
        "concepto": "runway",
        "valor_esperado": None,
        "tolerancia": Decimal("0.1"),
        "unidad": "meses",
        "nota": "abstención: sin parámetros vigentes",
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
