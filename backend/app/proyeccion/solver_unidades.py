# backend/app/proyeccion/solver_unidades.py
"""Solver de UNIDADES (inc4 FABS): ¿cuántas motos de más por mes para que el piso de
caja no baje del umbral, dado un escenario de ajustes? A diferencia de los solvers de
`solvers.py` (que bisectan un Ajuste sobre un ResultadoProyeccion FIJO), aquí cada
candidato N RE-CORRE el motor (las unidades fluyen por cartera/mora/GPS), vía la
`proyectar_fn` que inyecta el llamador. Motor intocable; bisección ENTERA."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.proyeccion.impactos import Ajuste, aplicar_impactos
from app.proyeccion.motor import ResultadoProyeccion


@dataclass(frozen=True)
class UnidadesResultado:
    unidades_extra: int
    alcanzable: bool
    piso_resultante: Decimal | None
    meta: Decimal


def _piso_con_ajustes(
    r: ResultadoProyeccion, ajustes: Sequence[Ajuste], caja_minima: Decimal
) -> Decimal:
    # aislado en su propia función para poder fakearlo en los tests del solver
    return aplicar_impactos(r, list(ajustes), caja_minima).kpis.piso_caja


def resolver_unidades_para_umbral(
    proyectar_fn: Callable[[int], ResultadoProyeccion],
    ajustes: Sequence[Ajuste],
    caja_minima: Decimal,
    *,
    colchon: Decimal = Decimal("0"),
    cap_unidades: int = 10_000,
) -> UnidadesResultado:
    meta = caja_minima + colchon

    def piso(n: int) -> Decimal:
        return _piso_con_ajustes(proyectar_fn(n), ajustes, caja_minima)

    if piso(0) >= meta:
        return UnidadesResultado(0, True, piso(0), meta)
    # duplicar hasta pasar el tope o cumplir
    lo, hi = 0, 1
    while piso(hi) < meta:
        lo, hi = hi, hi * 2
        if hi > cap_unidades:
            return UnidadesResultado(0, False, None, meta)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if piso(mid) >= meta:
            hi = mid
        else:
            lo = mid
    return UnidadesResultado(hi, True, piso(hi), meta)
