"""Solvers de D1 §5 — búsquedas por bisección sobre `aplicar_impactos`.

El motor corre en milisegundos; una bisección de ~40 iteraciones es gratis. Todo es
FORMULACIÓN POSTERIOR pura (el motor no se toca). Tres respuestas:

- **Techo de gasto:** el mayor gasto mensual uniforme extra tal que NINGÚN valle baje de
  `umbral + colchon` (la respuesta a "¿cuánto puedo gastar de más?"). Auditable: se
  devuelve el valle limitante y los parámetros usados.
- **Goal seek:** cuánto debe valer una variable (ingreso %/absoluto, o recorte de gasto)
  para que el piso quede en/sobre un objetivo. "¿Cuánto debo vender/recortar?"
- **Punto de quiebre:** desde qué gasto extra el primer valle perfora el umbral.

Todos parten del ResultadoProyeccion base y aceptan `ajustes_previos` (los del escenario
en pantalla), de modo que el solver razona SOBRE el escenario, no sobre el vacío.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_UP, Decimal

from app.proyeccion.impactos import Ajuste, aplicar_impactos
from app.proyeccion.motor import ResultadoProyeccion

# Tope práctico de búsqueda (1 billón COP): si el objetivo no se alcanza aquí, no hay
# solución razonable (evita loops si la variable no mueve el piso).
_CAP = Decimal("1000000000000")
_PESO = Decimal("0.01")
_MAX_ITER = 80


@dataclass(frozen=True)
class TechoResultado:
    techo_mensual: Decimal
    valle_limitante_mes: str
    piso_resultante: Decimal
    meta: Decimal
    colchon: Decimal
    hay_holgura: bool


@dataclass(frozen=True)
class GoalSeekResultado:
    variable: str
    valor: Decimal | None  # None = sin solución en el rango
    alcanzable: bool
    piso_resultante: Decimal | None
    objetivo: Decimal
    mensaje: str


@dataclass(frozen=True)
class QuiebreResultado:
    valor: Decimal | None  # None = no perfora dentro del rango
    mes: str | None
    perfora: bool


def _piso_y_mes(
    r: ResultadoProyeccion, caja_minima: Decimal, ajustes: Sequence[Ajuste]
) -> tuple[Decimal, str]:
    aj = aplicar_impactos(r, list(ajustes), caja_minima)
    return aj.kpis.piso_caja, aj.kpis.mes_mas_ajustado


def _mes0(r: ResultadoProyeccion) -> str:
    return r.meses[0].mes


def _max_valor_que_cumple(piso_fn, meta: Decimal) -> Decimal | None:
    """Mayor `v >= 0` con `piso_fn(v) >= meta`, siendo piso_fn DECRECIENTE en v. None si
    ni con v=0 se cumple."""
    if piso_fn(Decimal("0")) < meta:
        return None
    lo, hi = Decimal("0"), Decimal("1")
    while piso_fn(hi) >= meta:
        lo, hi = hi, hi * 2
        if hi > _CAP:
            return _CAP  # sin límite práctico: el techo es enorme
    for _ in range(_MAX_ITER):
        if hi - lo <= _PESO:
            break
        mid = (lo + hi) / 2
        if piso_fn(mid) >= meta:
            lo = mid
        else:
            hi = mid
    return lo.quantize(_PESO, rounding=ROUND_DOWN)


def _min_valor_que_cumple(piso_fn, meta: Decimal) -> Decimal | None:
    """Menor `v >= 0` con `piso_fn(v) >= meta`, piso_fn CRECIENTE en v. Devuelve 0 si ya
    se cumple; None si no se alcanza dentro del tope."""
    if piso_fn(Decimal("0")) >= meta:
        return Decimal("0.00")
    lo, hi = Decimal("0"), Decimal("1")
    while piso_fn(hi) < meta:
        lo, hi = hi, hi * 2
        if hi > _CAP:
            return None
    for _ in range(_MAX_ITER):
        if hi - lo <= _PESO:
            break
        mid = (lo + hi) / 2
        if piso_fn(mid) >= meta:
            hi = mid
        else:
            lo = mid
    return hi.quantize(_PESO, rounding=ROUND_UP)


def techo_gasto(
    r: ResultadoProyeccion,
    caja_minima: Decimal,
    *,
    ajustes_previos: Sequence[Ajuste] = (),
    colchon: Decimal = Decimal("0"),
) -> TechoResultado:
    meta = caja_minima + colchon
    mes0 = _mes0(r)

    def piso(d: Decimal) -> Decimal:
        aj = [*ajustes_previos, Ajuste("Techo", "gasto", "absoluto", d, mes0, None)]
        return _piso_y_mes(r, caja_minima, aj)[0]

    techo = _max_valor_que_cumple(piso, meta)
    if techo is None:
        _, vm = _piso_y_mes(r, caja_minima, list(ajustes_previos))
        return TechoResultado(
            techo_mensual=Decimal("0.00"),
            valle_limitante_mes=vm,
            piso_resultante=piso(Decimal("0")),
            meta=meta,
            colchon=colchon,
            hay_holgura=False,
        )
    p, vm = _piso_y_mes(
        r,
        caja_minima,
        [*ajustes_previos, Ajuste("Techo", "gasto", "absoluto", techo, mes0, None)],
    )
    return TechoResultado(
        techo_mensual=techo,
        valle_limitante_mes=vm,
        piso_resultante=p,
        meta=meta,
        colchon=colchon,
        hay_holgura=True,
    )


def goal_seek(
    r: ResultadoProyeccion,
    caja_minima: Decimal,
    *,
    variable: str,
    objetivo_caja: Decimal,
    ajustes_previos: Sequence[Ajuste] = (),
) -> GoalSeekResultado:
    """`variable` ∈ {ingreso_pct, ingreso_absoluto, gasto_absoluto}. Para gasto_absoluto
    el resultado es el RECORTE (positivo) a hacer. Todas suben el piso al crecer; se
    busca el MÍNIMO valor que alcanza el objetivo."""
    mes0 = _mes0(r)

    def _ajuste(v: Decimal) -> Ajuste:
        if variable == "ingreso_pct":
            return Ajuste("Goal", "ingreso", "porcentaje", v, mes0, None)
        if variable == "ingreso_absoluto":
            return Ajuste("Goal", "ingreso", "absoluto", v, mes0, None)
        if variable == "gasto_absoluto":
            return Ajuste("Goal", "gasto", "absoluto", -v, mes0, None)  # recorte
        raise ValueError(f"variable no soportada: {variable}")

    def piso(v: Decimal) -> Decimal:
        return _piso_y_mes(r, caja_minima, [*ajustes_previos, _ajuste(v)])[0]

    valor = _min_valor_que_cumple(piso, objetivo_caja)
    if valor is None:
        return GoalSeekResultado(
            variable=variable,
            valor=None,
            alcanzable=False,
            piso_resultante=None,
            objetivo=objetivo_caja,
            mensaje=(
                "El objetivo no se alcanza moviendo solo esta variable en el rango "
                "razonable; revisa el objetivo o combina con otro ajuste."
            ),
        )
    mensaje = "Ya se cumple sin cambios." if valor == 0 else ""
    return GoalSeekResultado(
        variable=variable,
        valor=valor,
        alcanzable=True,
        piso_resultante=piso(valor),
        objetivo=objetivo_caja,
        mensaje=mensaje,
    )


def punto_de_quiebre(
    r: ResultadoProyeccion,
    caja_minima: Decimal,
    *,
    ajustes_previos: Sequence[Ajuste] = (),
) -> QuiebreResultado:
    """Menor gasto extra que hace que el primer valle PERFORE el umbral, y el mes donde
    queda el piso a ese valor. (Es el techo con la desigualdad invertida.)"""
    mes0 = _mes0(r)

    def piso(d: Decimal) -> Decimal:
        aj = [*ajustes_previos, Ajuste("Quiebre", "gasto", "absoluto", d, mes0, None)]
        return _piso_y_mes(r, caja_minima, aj)[0]

    # menor v con piso(v) < umbral: es 1 peso más que el máximo que aún cumple >= umbral
    techo = _max_valor_que_cumple(piso, caja_minima)
    if techo is None:
        _, vm = _piso_y_mes(r, caja_minima, list(ajustes_previos))
        return QuiebreResultado(valor=Decimal("0.00"), mes=vm, perfora=True)
    if techo >= _CAP:
        return QuiebreResultado(valor=None, mes=None, perfora=False)
    valor = (techo + _PESO).quantize(_PESO, rounding=ROUND_UP)
    _, mes = _piso_y_mes(
        r,
        caja_minima,
        [*ajustes_previos, Ajuste("Quiebre", "gasto", "absoluto", valor, mes0, None)],
    )
    return QuiebreResultado(valor=valor, mes=mes, perfora=True)
