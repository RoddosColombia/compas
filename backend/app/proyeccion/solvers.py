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
class TechoVentanaResultado:
    """RF-F4 — Techo de gasto restringido a los primeros N meses (VENTANA) del
    horizonte, medido contra el umbral de ATENCIÓN (no el crítico). Bandera roja
    `perfora_atencion` cuando el valle DENTRO de la ventana perfora la atención
    aunque el horizonte completo cierre bien."""

    techo_mensual: Decimal
    valle_limitante_mes: str
    piso_resultante: Decimal
    referencia: Decimal  # el umbral contra el que se mide (atención si existe, o el
    # crítico como fallback — lo decide el caller vía `referencia=`)
    ventana: int  # meses efectivos de la ventana (recortada al horizonte real)
    hay_holgura: bool  # cabe algún gasto sin perforar la referencia
    perfora_atencion: bool  # el piso de la ventana (sin ajuste) < referencia


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


def _piso_ventana(
    r: ResultadoProyeccion,
    caja_minima: Decimal,
    ajustes: Sequence[Ajuste],
    n: int,
) -> tuple[Decimal, str]:
    """Piso y mes limitante mirando SOLO los primeros `n` meses (ventana). Reusa
    `aplicar_impactos` para la matemática — solo restringe la búsqueda."""
    aj = aplicar_impactos(r, list(ajustes), caja_minima)
    meses = aj.meses[:n]  # ventana
    fila = min(meses, key=lambda m: m.caja)
    return fila.caja, fila.mes


def techo_gasto_ventana(
    r: ResultadoProyeccion,
    caja_minima: Decimal,
    *,
    ventana: int = 9,
    referencia: Decimal | None = None,
    ajustes_previos: Sequence[Ajuste] = (),
) -> TechoVentanaResultado:
    """RF-F4 · Fundacional §2. Techo de gasto uniforme extra que NO perfora la
    `referencia` en los primeros `ventana` meses del horizonte.

    - `referencia = caja_atencion` (D-1) cuando el CEO lo tenga configurado; si es
      `None` cae al crítico (comportamiento equivalente al techo clásico).
    - La ventana se recorta al horizonte real si el caller pide más meses de los que
      hay (silencioso: no inventa meses).
    - **Bandera roja** `perfora_atencion` = True cuando el piso base (sin ajuste)
      dentro de la ventana ya está por debajo de la `referencia`. Es el aviso que
      pide la Fundacional: el valle cercano perfora la atención aunque el horizonte
      cierre bien.
    """
    if ventana < 1:
        raise ValueError("ventana debe ser >= 1")
    n = min(ventana, len(r.meses))
    ref = referencia if referencia is not None else caja_minima
    mes0 = _mes0(r)

    def piso(d: Decimal) -> Decimal:
        # Ajuste de gasto uniforme desde el mes 0 hasta el final de la VENTANA
        # (no todo el horizonte): así el techo mide "cuánto puedo gastar de más
        # DENTRO de la ventana" sin afectar meses fuera.
        mes_fin = r.meses[n - 1].mes if n < len(r.meses) else None
        aj = [
            *ajustes_previos,
            Ajuste("Techo·ventana", "gasto", "absoluto", d, mes0, mes_fin),
        ]
        return _piso_ventana(r, caja_minima, aj, n)[0]

    piso_base, _ = _piso_ventana(r, caja_minima, list(ajustes_previos), n)
    perfora = piso_base < ref

    techo = _max_valor_que_cumple(piso, ref)
    if techo is None:
        _, vm = _piso_ventana(r, caja_minima, list(ajustes_previos), n)
        return TechoVentanaResultado(
            techo_mensual=Decimal("0.00"),
            valle_limitante_mes=vm,
            piso_resultante=piso(Decimal("0")),
            referencia=ref,
            ventana=n,
            hay_holgura=False,
            perfora_atencion=perfora,
        )
    mes_fin = r.meses[n - 1].mes if n < len(r.meses) else None
    p, vm = _piso_ventana(
        r,
        caja_minima,
        [
            *ajustes_previos,
            Ajuste("Techo·ventana", "gasto", "absoluto", techo, mes0, mes_fin),
        ],
        n,
    )
    return TechoVentanaResultado(
        techo_mensual=techo,
        valle_limitante_mes=vm,
        piso_resultante=p,
        referencia=ref,
        ventana=n,
        hay_holgura=True,
        perfora_atencion=perfora,
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
