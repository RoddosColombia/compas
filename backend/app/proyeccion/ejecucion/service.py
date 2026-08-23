# backend/app/proyeccion/ejecucion/service.py
"""E1 · P2 — capa de ANCLAJE de la proyección a la ejecución real (post-motor puro).

La jerarquía del plan §1: para cada mes del horizonte, la serie se arma con la mejor
fuente disponible según `MesControl.estado`.

    Cerrado              → gasto/costo = ejecutado real · ingreso = real recaudado
    En ejecución         → Regla A (D-08): ejecutado + max(0, definido − ejecutado) por
                           concepto · ingreso = motor (NO se ancla; converge al cerrar)
    Futuro c/presupuesto → el presupuesto DEFINIDO vigente · ingreso = motor
    Futuro s/presupuesto → el motor paramétrico (como hoy)

Mecánica (idéntica a la reconciliación D2, `obligaciones/reconciliacion.py`): se calcula
el delta de FLUJO que el anclaje imprime en cada mes, se re-acumula la caja con
`impactos.reacumular` (motor intacto, primer mes fijo), y LUEGO se reescriben los campos
POR CONCEPTO de los meses anclados — reescribir conceptos dentro de `reacumular` sería
incorrecto (D1 lo comparte). Con `anclas` vacío la serie es la base bit a bit (golden).

**E1 NO toca Auteco.** `pago_inventario`, `fondeo` (y `adelanto`) se conservan del
motor; esa vía es D2 (obligaciones). La precedencia de P3 evita el doble conteo. E1
ancla el resto: `neto` (solo cerrado), `gastos_fijos`, `gps`, `costo_nueva`,
`int_deuda`, `iva`.

**Composición con COCK-09 (rolling forecast):** COCK-09 ancla la caja inicial (el punto
de partida del horizonte, un escalar); E1 ancla las LÍNEAS de los meses
cerrado/en-ejecución y re-acumula desde ahí. Magnitudes ortogonales — sin doble anclaje.

Función PURA sobre snapshots (sin Mongo): el llamador (P3) arma
`anclas`/`rubros`/`neutros_ids` desde `control.service`, `MesControl` y transacciones.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from app.proyeccion.ejecucion.lectura import RubroInfo, mapear_a_conceptos
from app.proyeccion.impactos import ResultadoAjustado, reacumular
from app.proyeccion.motor import MesProyeccion, ResultadoProyeccion, _cop

_CERO = Decimal("0.00")

# Conceptos de EGRESO que E1 ancla (el resto —adelanto/pago_inventario/fondeo— es del
# motor / D2). Son los de `mapear_a_conceptos` menos los de Auteco.
_EGRESOS_ANCLADOS = ("gastos_fijos", "gps", "costo_nueva", "int_deuda", "iva")

# Estados que anclan y con qué regla (los demás → sin ancla → motor intacto).
CERRADO = "cerrado"
EN_EJECUCION = "en_ejecucion"
PRESUPUESTO = "presupuesto"  # futuro con presupuesto definido vigente
_ANCLABLES = (CERRADO, EN_EJECUCION, PRESUPUESTO)


@dataclass(frozen=True)
class AnclaMes:
    """Insumos para anclar UN mes del horizonte. `estado` decide la regla (§1).

    - `ejecutado_por_rubro_id`: Σ egresos por rubro del mes (magnitud POSITIVA). Usado
      por cerrado y en-ejecución.
    - `definido_por_rubro_id`: presupuesto DEFINIDO vigente por rubro (POSITIVO). Usado
      por en-ejecución (Regla A) y futuro-con-presupuesto. `{}` si no aplica.
    - `ingreso_real`: neto recaudado del mes (POSITIVO), SOLO para cerrado (se ancla el
      ingreso). None en los demás (el ingreso queda del motor).
    """

    estado: str
    ejecutado_por_rubro_id: dict[str, Decimal]
    definido_por_rubro_id: dict[str, Decimal]
    ingreso_real: Decimal | None


def _conceptos_egreso(
    valor_por_rubro_id: dict[str, Decimal],
    *,
    rubros: list[RubroInfo],
    neutros_ids: set[str],
) -> dict[str, Decimal]:
    """Mapea rubro→concepto (reusa P1) y devuelve SOLO los conceptos de egreso que E1
    ancla, en magnitud POSITIVA. Auteco (`pago_inventario`/`fondeo`) se ignora aquí."""
    r = mapear_a_conceptos(
        rubros=rubros, valor_por_rubro_id=valor_por_rubro_id, neutros_ids=neutros_ids
    )
    return {c: r.conceptos[c] for c in _EGRESOS_ANCLADOS}


def _egresos_anclados_del_mes(
    ancla: AnclaMes, *, rubros: list[RubroInfo], neutros_ids: set[str]
) -> dict[str, Decimal]:
    """Los 5 conceptos de egreso anclados del mes (magnitud POSITIVA), por estado.

    P4 del ciclo mensual (CEO 2026-08-23) — **la Regla A / D-08 queda SOLO para meses
    cerrados**. Un mes EN EJECUCIÓN muestra su PRESUPUESTO, igual que un mes futuro con
    presupuesto: la gráfica del mes en curso es la proyección del objetivo, y lo
    ejecutado se lee aparte como desviación (el termómetro de P6). Antes se mezclaba
    (`ejecutado + max(0, definido − ejecutado)`), así que la misma fila tenía el gasto
    medio real y el ingreso 100 % paramétrico — dos universos en una sola cuenta."""
    if ancla.estado == CERRADO:
        return _conceptos_egreso(
            ancla.ejecutado_por_rubro_id, rubros=rubros, neutros_ids=neutros_ids
        )
    return _conceptos_egreso(
        ancla.definido_por_rubro_id, rubros=rubros, neutros_ids=neutros_ids
    )


def _es_anclable(ancla: AnclaMes) -> bool:
    """Si este mes se ancla o se deja al motor paramétrico.

    Un mes CERRADO se ancla siempre (su verdad es el libro). Un mes que se ancla al
    PRESUPUESTO (en ejecución o futuro definido) necesita tener presupuesto: sin él,
    anclar dejaría el gasto del mes en CERO, que es peor que la estimación del motor.
    Fail-safe explícito, no silencioso."""
    if ancla.estado == CERRADO:
        return True
    if ancla.estado not in _ANCLABLES:
        return False
    return bool(ancla.definido_por_rubro_id)


def _fila_anclada(
    fila: MesProyeccion, ancla: AnclaMes, egr: dict[str, Decimal]
) -> MesProyeccion:
    """Fila con los conceptos anclados escritos (egresos NEGATIVOS), el `neto` real si
    el mes es cerrado, y `egresos`/`flujo` recalculados. Conserva del motor `adelanto`,
    `pago_inventario`, `fondeo` (Auteco → D2) y los componentes de ingreso."""
    neto = fila.neto if ancla.ingreso_real is None else _cop(ancla.ingreso_real)
    gastos_fijos = _cop(-egr["gastos_fijos"])
    gps = _cop(-egr["gps"])
    costo_nueva = _cop(-egr["costo_nueva"])
    int_deuda = _cop(-egr["int_deuda"])
    iva = _cop(-egr["iva"])
    egresos = _cop(
        gastos_fijos
        + gps
        + costo_nueva
        + int_deuda
        + iva
        + fila.adelanto
        + fila.pago_inventario
        + fila.fondeo
        # P1 del ciclo mensual (candado aritmético, 2026-08-23): el fondo de AVAL es
        # un egreso que E1 NO ancla (sale del recaudo, no de un rubro del libro), así
        # que se CONSERVA del motor, igual que Auteco. Faltaba: todo mes anclado
        # perdía el aval de sus egresos en silencio — en PROD, agosto-2026 son
        # 546.241,68 que desaparecían de la cuenta.
        + fila.aval
    )
    flujo = _cop(neto + egresos)
    return replace(
        fila,
        neto=neto,
        gastos_fijos=gastos_fijos,
        gps=gps,
        costo_nueva=costo_nueva,
        int_deuda=int_deuda,
        iva=iva,
        egresos=egresos,
        flujo=flujo,
    )


def anclar(
    *,
    resultado: ResultadoProyeccion,
    caja_minima: Decimal,
    anclas: dict[str, AnclaMes],
    rubros: list[RubroInfo],
    neutros_ids: set[str],
) -> ResultadoAjustado:
    """Ancla la serie del motor a la ejecución real (§1) y re-acumula la caja. `anclas`
    mapea 'YYYY-MM'→AnclaMes; los meses fuera del dict quedan intactos (motor). Con
    `anclas` vacío devuelve la base bit a bit (== golden, B1)."""
    base = resultado.meses
    n = len(base)
    idx = {fila.mes: i for i, fila in enumerate(base)}

    # 1) fila anclada + delta de flujo por mes (solo los anclables del horizonte).
    ancladas: dict[int, MesProyeccion] = {}
    deltas = [_CERO] * n
    for mes, ancla in anclas.items():
        if mes not in idx or not _es_anclable(ancla):
            continue  # fuera del horizonte, no anclable o sin presupuesto → motor
        m = idx[mes]
        egr = _egresos_anclados_del_mes(ancla, rubros=rubros, neutros_ids=neutros_ids)
        nueva = _fila_anclada(base[m], ancla, egr)
        ancladas[m] = nueva
        deltas[m] = _cop(nueva.flujo - base[m].flujo)

    # 2) re-acumular caja/flujo/estado con la mecánica del motor (D2/D1 la comparten).
    ajustado = reacumular(resultado, deltas, caja_minima)

    # 3) reescribir los campos POR CONCEPTO de los meses anclados (reacumular solo tocó
    #    flujo/caja/estado). Así `neto + Σ egresos == flujo` al peso en la serie (B6).
    filas = list(ajustado.meses)
    for m, nueva in ancladas.items():
        # SUP-5 · honestidad: la mora paramétrica solo se borra cuando el INGRESO dejó
        # de ser del motor (mes cerrado: `ingreso_real` reemplaza el neto). En un mes EN
        # EJECUCIÓN el ingreso sigue siendo paramétrico, así que su mora SÍ explica la
        # cifra y debe verse — borrarla dejaba la columna «Ajuste mora/default» con un
        # valor que ninguna fila del desglose sustentaba.
        ingreso_es_del_libro = anclas[filas[m].mes].ingreso_real is not None
        cartera = (
            {
                "mora": Decimal("0.00"),
                "recuperacion": Decimal("0.00"),
                "default": Decimal("0.00"),
            }
            if ingreso_es_del_libro
            else {}
        )
        filas[m] = replace(
            filas[m],
            neto=nueva.neto,
            gastos_fijos=nueva.gastos_fijos,
            gps=nueva.gps,
            costo_nueva=nueva.costo_nueva,
            int_deuda=nueva.int_deuda,
            iva=nueva.iva,
            egresos=nueva.egresos,
            **cartera,
        )
    return replace(ajustado, meses=filas)
