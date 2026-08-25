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
    """Menor N entero en [0, cap_unidades] con piso(N) >= meta (caja_minima +
    colchon). Precondición: `piso` es NO-DECRECIENTE en N (más unidades extra nunca
    baja el piso) — la bisección asume esto, igual que `solvers._min_valor_que_cumple`
    ("piso_fn CRECIENTE en v"). La búsqueda queda ACOTADA a [0, cap_unidades]:
    `alcanzable=False` únicamente cuando ni siquiera `piso(cap_unidades)` alcanza la
    meta, y nunca se devuelve un N por encima del tope (Fix round 1: la fase de
    duplicado previa podía saltar por encima del cap sin haberlo probado, o saltarse
    el chequeo del cap por completo si el primer candidato ya cumplía)."""
    meta = caja_minima + colchon

    def piso(n: int) -> Decimal:
        return _piso_con_ajustes(proyectar_fn(n), ajustes, caja_minima)

    p0 = piso(0)
    if p0 >= meta:
        return UnidadesResultado(0, True, p0, meta)
    # oráculo de alcanzabilidad: ni siquiera el tope llega a la meta => no hay
    # solución dentro del rango permitido (evita una llamada redundante si el tope
    # es 0, caso en que ya es exactamente el p0 de arriba)
    p_hi = p0 if cap_unidades == 0 else piso(cap_unidades)
    if p_hi < meta:
        return UnidadesResultado(0, False, None, meta)
    lo, hi = 0, cap_unidades
    while hi - lo > 1:
        mid = (lo + hi) // 2
        p_mid = piso(mid)
        if p_mid >= meta:
            hi, p_hi = mid, p_mid
        else:
            lo = mid
    return UnidadesResultado(hi, True, p_hi, meta)  # hi <= cap, garantizado alcanzable
