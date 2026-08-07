# backend/app/proyeccion/ejecucion/guarda.py
"""E1 · P4 — guarda B10: marca de anomalía del mes cerrado (función PURA).

Un mes CERRADO cuya ejecución quedó muy por debajo de lo definido probablemente está
mal cargado (faltan movimientos). Decisión CEO 2026-08-05: NO se bloquea el anclaje —la
confirmación del cierre ES la validación (FIX-J)—; el mes se ancla igual y solo se MARCA
`cerrado_sospechoso` para la UI. Sin flag en MesControl, sin evento nuevo.

Regla (tunable): sobre los 5 conceptos que E1 ancla (`gastos_fijos`, `gps`,
`costo_nueva`, `int_deuda`, `iva` — sin Auteco, sin `neto`), sea E = Σ ejecutado y
D = Σ definido. El mes es sospechoso si `D > 0` y `E < UMBRAL × D` (estricto:
`E == UMBRAL×D` NO marca; `D == 0` NO marca —no hay base de juicio—).

**Protege el fix C-1:** la marca NO cambia `AnclaMes.estado` (un sospechoso sigue siendo
`"cerrado"`, así el filtro de D2 lo sigue excluyendo). Vive solo en el mapa de marcas.
"""

from __future__ import annotations

from decimal import Decimal

from app.proyeccion.ejecucion.lectura import RubroInfo
from app.proyeccion.ejecucion.service import CERRADO, AnclaMes, _conceptos_egreso

UMBRAL_SOSPECHA_EJECUTADO = Decimal("0.5")


def es_ejecutado_anomalo(
    ejecutado_por_rubro_id: dict[str, Decimal],
    definido_por_rubro_id: dict[str, Decimal],
    *,
    rubros: list[RubroInfo],
    neutros_ids: set[str],
) -> bool:
    """True si el ejecutado del mes cerrado quedó sospechosamente bajo vs el definido
    (Σ de los 5 conceptos anclados). `D == 0` o `E >= UMBRAL×D` → no anómalo."""
    ejec = _conceptos_egreso(
        ejecutado_por_rubro_id, rubros=rubros, neutros_ids=neutros_ids
    )
    defi = _conceptos_egreso(
        definido_por_rubro_id, rubros=rubros, neutros_ids=neutros_ids
    )
    e_total = sum(ejec.values(), Decimal("0"))
    d_total = sum(defi.values(), Decimal("0"))
    return d_total > 0 and e_total < UMBRAL_SOSPECHA_EJECUTADO * d_total


def marcas_origen(
    anclas: dict[str, AnclaMes],
    *,
    rubros: list[RubroInfo],
    neutros_ids: set[str],
) -> dict[str, str]:
    """Marca de origen por mes anclado (vocabulario del shape de P5):
    `"cerrado"` | `"cerrado_sospechoso"` | `"en_ejecucion"` | `"presupuesto"`. Solo el
    régimen cerrado puede volverse sospechoso; los demás conservan su estado."""
    marcas: dict[str, str] = {}
    for mes, a in anclas.items():
        if a.estado == CERRADO and es_ejecutado_anomalo(
            a.ejecutado_por_rubro_id,
            a.definido_por_rubro_id,
            rubros=rubros,
            neutros_ids=neutros_ids,
        ):
            marcas[mes] = "cerrado_sospechoso"
        else:
            marcas[mes] = a.estado
    return marcas
