# backend/app/proyeccion/solver_unidades.py
"""Solver de UNIDADES (inc4 FABS): ¿cuántas motos de más por mes para que el piso de
caja no baje del umbral, dado un escenario de ajustes? A diferencia de los solvers de
`solvers.py` (que bisectan un Ajuste sobre un ResultadoProyeccion FIJO), aquí cada
candidato N RE-CORRE la proyección completa (las unidades fluyen por cartera/mora/GPS),
vía la `proyectar_fn` ASYNC que inyecta el llamador. Motor intocable; bisección ENTERA.

Fix round 1 (revisión Opus del Task 6 de inc4): `proyectar_fn` corre el PIPELINE
COMPLETO (motor → E1 anclaje → D2 reconciliación, vía `service._resultado_con`), el
mismo que usa `impacto_escenario`/`proyectar_impactos` — no solo el motor paramétrico.
Eso exige I/O (Mongo) por candidato, así que `proyectar_fn` y por lo tanto este
resolver son ASYNC (antes era síncrono; el motor-only no necesitaba I/O)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
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
    # aislado en su propia función para poder fakearlo en los tests del solver.
    # primer_mes_acumula=True: la MISMA convención que usa el resto del servicio (P3
    # del ciclo mensual — service._resultado_con/proyectar_impactos SIEMPRE lo pasan
    # así). Sin esto, un ajuste que arranca en el PRIMER mes del horizonte (el caso
    # más común aquí: motos_para_evitar_umbral ancla el horizonte al mes de HOY) no
    # movería la caja de ese mes en este solver pero SÍ la movería en
    # impacto_escenario — los dos números dejarían de reconciliar (Fix round 1).
    return aplicar_impactos(
        r, list(ajustes), caja_minima, primer_mes_acumula=True
    ).kpis.piso_caja


async def resolver_unidades_para_umbral(
    proyectar_fn: Callable[[int], Awaitable[ResultadoProyeccion]],
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
    el chequeo del cap por completo si el primer candidato ya cumplía).

    `proyectar_fn` es ASYNC (corre el pipeline completo — I/O de Mongo por candidato,
    Fix round 1) y este resolver la `await`ea directo: el LLAMADOR (`cfo.calc.
    escenario.motos_para_evitar_umbral`) es quien debe `await resolver_unidades_para_
    umbral(...)`. La bisección en sí (el algoritmo, los invariantes de arriba) es
    IDÉNTICA a la versión síncrona anterior — solo se le agregó `async`/`await`."""
    meta = caja_minima + colchon

    async def piso(n: int) -> Decimal:
        return _piso_con_ajustes(await proyectar_fn(n), ajustes, caja_minima)

    p0 = await piso(0)
    if p0 >= meta:
        return UnidadesResultado(0, True, p0, meta)
    # oráculo de alcanzabilidad: ni siquiera el tope llega a la meta => no hay
    # solución dentro del rango permitido (evita una llamada redundante si el tope
    # es 0, caso en que ya es exactamente el p0 de arriba)
    p_hi = p0 if cap_unidades == 0 else await piso(cap_unidades)
    if p_hi < meta:
        return UnidadesResultado(0, False, None, meta)
    lo, hi = 0, cap_unidades
    while hi - lo > 1:
        mid = (lo + hi) // 2
        p_mid = await piso(mid)
        if p_mid >= meta:
            hi, p_hi = mid, p_mid
        else:
            lo = mid
    return UnidadesResultado(hi, True, p_hi, meta)  # hi <= cap, garantizado alcanzable
