"""Capa de impactos (D1) — FORMULACIÓN POSTERIOR sobre la salida del motor.

Un `Ajuste` es un delta declarativo sobre la serie mensual que YA produjo el motor:
"+$3.000.000 en arriendos desde sep-2026", "ingreso -10% desde ene-2027". Se aplica
como post-proceso PURO (ni una línea del motor cambia) y la caja se re-acumula en
Decimal con la MISMA mecánica del motor: `caja[m] = caja[m-1] + flujo[m]`.

Límite honesto (spec §2): los ajustes son efectos DIRECTOS de caja. No pasan por
mora/recuperación ni recalculan cartera/GPS/inventario — eso sería tocar el motor. El
porcentaje de gasto se aplica sobre `gastos_fijos` del mes; el de ingreso, sobre el
`neto` (ingreso post-mora).

P3 del ciclo mensual: con `primer_mes_acumula=True` (lo que pasa el servicio) un ajuste
en el PRIMER mes del horizonte también mueve su caja — el candado no admite excepciones.
El default False conserva la convención del artefacto (primer mes fijo = caja inicial),
que es la que certifica el golden master.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Literal

from app.proyeccion.kpis import KpisResultado, calcular_kpis
from app.proyeccion.motor import (
    MesProyeccion,
    ResultadoProyeccion,
    _cop,
    _estado_caja,
)

Naturaleza = Literal["gasto", "ingreso"]
Modo = Literal["absoluto", "porcentaje"]

_CERO = Decimal("0.00")


@dataclass(frozen=True)
class Ajuste:
    """Delta declarativo sobre la serie del motor. `valor` es Decimal: monto COP para
    `absoluto`, fracción (0.10 = 10%) para `porcentaje`. Convención de signo: para
    gasto, valor POSITIVO = más gasto (la caja baja), negativo = recorte; para ingreso,
    positivo = más ingreso."""

    nombre: str
    naturaleza: Naturaleza
    modo: Modo
    valor: Decimal
    mes_inicio: str  # 'YYYY-MM'
    mes_fin: str | None = None  # None = hasta el final del horizonte
    rubro_id: str | None = None  # trazabilidad/vistas; no afecta el cálculo


@dataclass(frozen=True)
class ResultadoAjustado:
    meses: list[MesProyeccion]  # serie ajustada (flujo/caja/estado nuevos)
    kpis: KpisResultado
    delta_por_mes: list[Decimal]  # delta de flujo aplicado por mes (trazabilidad)


def _delta_flujo(fila: MesProyeccion, ajuste: Ajuste) -> Decimal:
    """Delta de FLUJO que el ajuste imprime en el mes (positivo sube la caja)."""
    if ajuste.naturaleza == "gasto":
        if ajuste.modo == "absoluto":
            return _cop(-ajuste.valor)  # más gasto => flujo baja
        # porcentaje sobre gastos_fijos (que el motor entrega NEGATIVO)
        return _cop(fila.gastos_fijos * ajuste.valor)
    # ingreso
    if ajuste.modo == "absoluto":
        return _cop(ajuste.valor)
    # porcentaje sobre el neto (ingreso post-mora del motor)
    return _cop(fila.neto * ajuste.valor)


def aplicar_impactos(
    resultado: ResultadoProyeccion,
    ajustes: list[Ajuste],
    caja_minima: Decimal,
    primer_mes_acumula: bool = False,
) -> ResultadoAjustado:
    """Aplica los ajustes sobre la serie del motor y re-acumula la caja. Con `ajustes`
    vacío devuelve la serie base bit a bit (regla de oro del sprint). P3:
    `primer_mes_acumula` viaja a `reacumular` (un ajuste en el mes en curso también
    mueve su caja)."""
    base = resultado.meses
    n = len(base)
    meses_idx = {fila.mes: i for i, fila in enumerate(base)}

    # 1) delta de flujo por mes (suma de todos los ajustes vigentes ese mes)
    deltas = [_CERO] * n
    for aj in ajustes:
        i0 = _indice_desde(base, meses_idx, aj.mes_inicio)
        i1 = _indice_hasta(base, meses_idx, aj.mes_fin)
        if i0 is None or i1 is None or i0 > i1:
            continue  # ventana fuera del horizonte
        for m in range(i0, i1 + 1):
            deltas[m] = _cop(deltas[m] + _delta_flujo(base[m], aj))

    return reacumular(resultado, deltas, caja_minima, primer_mes_acumula)


def reacumular(
    resultado: ResultadoProyeccion,
    deltas: list[Decimal],
    caja_minima: Decimal,
    primer_mes_acumula: bool = False,
) -> ResultadoAjustado:
    """Aplica un delta de flujo por mes YA calculado y re-acumula la caja con la MISMA
    regla del motor (caja[m]=caja[m-1]+flujo[m]). Lo comparten la capa de impactos
    (deltas de ajustes), la reconciliación de obligaciones (deltas de netear el
    paramétrico y sumar el calendario real) y el anclaje E1. Deltas todos cero => base
    bit a bit.

    P3 del ciclo mensual: con `primer_mes_acumula` el delta del PRIMER mes también mueve
    su caja. El efectivo de arranque se DERIVA de la propia serie base
    (`caja[0] − flujo[0]`), exacto porque el motor la construyó con esa misma regla —
    así no hay un segundo parámetro que pueda desincronizarse del motor. False conserva
    la convención del artefacto (primer mes fijo), la que exige el golden master."""
    base = resultado.meses
    filas: list[MesProyeccion] = []
    caja_prev = (
        _cop(base[0].caja - base[0].flujo) if primer_mes_acumula and base else _CERO
    )
    for m, fila in enumerate(base):
        flujo = _cop(fila.flujo + deltas[m])
        caja = _cop(caja_prev + flujo) if m > 0 or primer_mes_acumula else fila.caja
        caja_prev = caja
        filas.append(
            replace(
                fila,
                flujo=flujo,
                caja=caja,
                estado=_estado_caja(caja, caja_minima),
            )
        )
    kpis = calcular_kpis(
        [f.caja for f in filas],
        [f.flujo for f in filas],
        [f.mes for f in filas],
        caja_minima,
    )
    return ResultadoAjustado(meses=filas, kpis=kpis, delta_por_mes=deltas)


def _indice_desde(
    base: list[MesProyeccion], idx: dict[str, int], mes: str
) -> int | None:
    """Índice del mes_inicio. Anterior al horizonte => clampa a 0; posterior al último
    mes => None (no aplica)."""
    if mes in idx:
        return idx[mes]
    if mes < base[0].mes:
        return 0
    if mes > base[-1].mes:
        return None
    # cae entre meses existentes (no debería, meses son contiguos): primer mes >= mes
    for i, fila in enumerate(base):
        if fila.mes >= mes:
            return i
    return None


def _indice_hasta(
    base: list[MesProyeccion], idx: dict[str, int], mes: str | None
) -> int | None:
    """Índice del mes_fin (inclusive). None = hasta el final. Anterior al horizonte =>
    None (ventana vacía); posterior => último mes."""
    if mes is None:
        return len(base) - 1
    if mes in idx:
        return idx[mes]
    if mes > base[-1].mes:
        return len(base) - 1
    if mes < base[0].mes:
        return None
    for i in range(len(base) - 1, -1, -1):
        if base[i].mes <= mes:
            return i
    return None
