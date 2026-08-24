# backend/app/parametros_proyeccion/sugerencias.py
"""P7 del ciclo mensual — SUGERENCIAS de supuestos a partir del gasto real.

Contrato: `docs/COMPAS_Ciclo_Mensual.md` §«Paso 4 · Recálculo» — "gasto hacia adelante =
informado por el promedio de gasto real de los meses cerrados".

Decisión del CEO (2026-08-23): promedio de los **3 meses cerrados** más recientes, y
**SUGIERE**. El supuesto vigente NO se toca: el CEO lo aprueba en Supuestos. Es la misma
regla que atraviesa toda la fase — la formulación no pisa el dato del CEO.

Dos decisiones que hacen la cifra comparable y honesta:

  · **Se promedia el CONCEPTO `gastos_fijos`, no el gasto total del mes.** Un mes real
    incluye Auteco, deudas y costo de producto, que el motor proyecta por otras vías;
    compararlos contra el supuesto de gastos fijos sería comparar peras con manzanas.
    El mapeo rubro→concepto es el MISMO de E1 (`ejecucion.lectura.mapear_a_conceptos`),
    así que la sugerencia y el anclaje hablan del mismo concepto.
  · **Se declara sobre cuántos meses y cuáles se promedió.** Con menos de 3 cerrados se
    promedia lo que hay y se dice; sin ningún mes cerrado no hay sugerencia (regla 7: no
    se inventa un promedio de la nada).

Módulo aditivo: nada de esto entra al motor ni escribe estado.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.control.service import _egresos_por_rubro
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.rubro import Rubro
from app.domain.rubros_neutros import _ids_rubros_neutros
from app.proyeccion.ejecucion.lectura import RubroInfo, mapear_a_conceptos

VENTANA_MESES = 3  # decisión CEO 2026-08-23
_CENTAVO = Decimal("0.01")


def promedio(
    por_mes: list[tuple[str, Decimal]], ventana: int = VENTANA_MESES
) -> dict | None:
    """Promedio de los últimos `ventana` meses de `por_mes` (ordenado ascendente por
    mes). `None` si no hay ni un mes. Devuelve el valor, los meses usados, cuántos
    fueron y el detalle — para que la pantalla muestre DE DÓNDE sale la cifra."""
    if not por_mes:
        return None
    usados = sorted(por_mes)[-ventana:]
    total = sum((v for _, v in usados), Decimal("0"))
    return {
        "valor": (total / len(usados)).quantize(_CENTAVO, rounding=ROUND_HALF_UP),
        "meses": [m for m, _ in usados],
        "n": len(usados),
        "detalle": [
            {"mes": m, "valor": v.quantize(_CENTAVO, rounding=ROUND_HALF_UP)}
            for m, v in usados
        ],
    }


async def _rubros_info() -> list[RubroInfo]:
    return [
        RubroInfo(
            id=str(r.id),
            codigo=r.codigo,
            grupo=r.grupo.value if hasattr(r.grupo, "value") else str(r.grupo),
            nombre=r.nombre,
            es_sistema=r.es_sistema,
        )
        async for r in Rubro.find_all()
    ]


async def gastos_fijos_reales_por_mes() -> list[tuple[str, Decimal]]:
    """El concepto `gastos_fijos` EJECUTADO de cada mes CERRADO, del más viejo al más
    nuevo. Solo meses cerrados: un mes en ejecución está a medias y su parcial
    ensuciaría el promedio."""
    cerrados = (
        await MesControl.find(MesControl.estado == EstadoMes.CERRADO)
        .sort(MesControl.mes)
        .to_list()
    )
    if not cerrados:
        return []
    rubros = await _rubros_info()
    neutros = {str(i) for i in await _ids_rubros_neutros()}
    out: list[tuple[str, Decimal]] = []
    for mc in cerrados:
        egresos = await _egresos_por_rubro(mc.id)
        r = mapear_a_conceptos(
            rubros=rubros, valor_por_rubro_id=egresos, neutros_ids=neutros
        )
        out.append((mc.mes[:7], r.conceptos["gastos_fijos"]))
    return out


async def sugerencias() -> dict:
    """Las sugerencias vigentes. Hoy solo `gastos_fijos` (P7); el shape queda abierto
    para las que vengan (GPS por moto, costo de alistamiento…)."""
    s = promedio(await gastos_fijos_reales_por_mes())
    return {"gastos_fijos": s}
