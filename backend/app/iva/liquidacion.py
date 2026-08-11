# backend/app/iva/liquidacion.py
"""Liquidación de IVA por período (C11, PR-2a/2b) — NÚCLEO compute-only, sin I/O.

Réplica del diseño de docs/modelo/AUDITORIA-IVA-ARTIFACT-V2.md §5.2. Todo Decimal
(regla 1). El PERÍODO es CONFIGURABLE (decisión CEO 2026-07-25): default CUATRIMESTRAL
(ene-abr / may-ago / sep-dic — realidad actual de RODDOS), y bimestral (ene-feb /
mar-abr / … / nov-dic) habilitable cuando la DIAN lo exija por volumen de facturas.
Tarifa general 19%; el IVA descontable cuenta SOLO compras deducibles (incluye Auteco
—autorretenedor, pero su IVA SÍ es descontable— y otras compras). El saldo a favor se
ARRASTRA al siguiente período.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum

from app.core.time import today_bogota

_CENTAVO = Decimal("0.01")

_MESES_ABBR = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)


class Periodicidad(StrEnum):
    cuatrimestral = "cuatrimestral"  # 3 períodos/año (4 meses c/u) — default RODDOS
    bimestral = "bimestral"  # 6 períodos/año (2 meses c/u)


def _meses_por_periodo(periodicidad: Periodicidad) -> int:
    return 4 if periodicidad == Periodicidad.cuatrimestral else 2


def _cop(v: Decimal) -> Decimal:
    """Cuantiza a COP 2 decimales HALF_EVEN (misma política que money_str)."""
    return v.quantize(_CENTAVO, rounding=ROUND_HALF_EVEN)


def iva_desde_base(base_gravable: Decimal, tarifa: Decimal) -> Decimal:
    """IVA a partir de la base gravable (sin IVA): `base × tarifa`."""
    return _cop(base_gravable * tarifa)


def iva_desde_total(total: Decimal, tarifa: Decimal) -> Decimal:
    """IVA extraído de un total que YA incluye IVA: `total × tarifa/(1+tarifa)`
    (19/119 para tarifa 0.19). Verificado al peso: 1190 → 190."""
    if tarifa == 0:
        return Decimal("0.00")
    return _cop(total * tarifa / (Decimal("1") + tarifa))


def periodo_de(
    fecha: str, periodicidad: Periodicidad = Periodicidad.cuatrimestral
) -> tuple[int, int]:
    """(anio, índice de período 1..N) de una fecha 'YYYY-MM-DD' según la periodicidad.
    Cuatrimestral → 1..3 (C1=ene-abr…); bimestral → 1..6 (P1=ene-feb…)."""
    anio = int(fecha[:4])
    mes = int(fecha[5:7])
    return (anio, (mes - 1) // _meses_por_periodo(periodicidad) + 1)


def clave_dian(idx: int, periodicidad: Periodicidad) -> str:
    """Clave del período en `CALENDARIO_DIAN` = 'mesInicio_mesFin' (p. ej. 'ene_abr',
    'may_ago' cuatrimestral; 'ene_feb', 'mar_abr' bimestral). Derivada del rango de
    meses del período → una sola fuente de verdad, sin listas hardcodeadas."""
    meses = _meses_por_periodo(periodicidad)
    ini = (idx - 1) * meses
    fin = idx * meses - 1
    return f"{_MESES_ABBR[ini]}_{_MESES_ABBR[fin]}"


def etiqueta_periodo(anio: int, idx: int, periodicidad: Periodicidad) -> str:
    # 'C' cuatrimestral (2026-C1) · 'B' bimestral (2026-B1)
    prefijo = "C" if periodicidad == Periodicidad.cuatrimestral else "B"
    return f"{anio}-{prefijo}{idx}"


def proximo_pago(
    anio: int, idx: int, periodicidad: Periodicidad, calendario: dict
) -> dict | None:
    """Fecha DIAN del período (de `CALENDARIO_DIAN`) + días desde hoy (Bogotá). Sin
    fecha en el calendario → None: la UI omite la línea, no se inventa (R5, §3③)."""
    anio_cal = calendario.get(str(anio))
    fecha = anio_cal.get(clave_dian(idx, periodicidad)) if anio_cal else None
    if not fecha:
        return None
    y, m, d = (int(x) for x in fecha.split("-"))
    return {"fecha": fecha, "dias": (date(y, m, d) - today_bogota()).days}


def cuatrimestre_de(fecha: str) -> tuple[int, int]:
    """Compat: `periodo_de` con periodicidad cuatrimestral (el default histórico)."""
    return periodo_de(fecha, Periodicidad.cuatrimestral)


@dataclass(frozen=True)
class FacturaIva:
    """Subconjunto de `Factura` que afecta la liquidación (compute-only). `deducible`
    solo aplica a compras (si su IVA es descontable)."""

    tipo: str  # 'venta' | 'compra'
    fecha: str  # 'YYYY-MM-DD'
    iva_valor: Decimal
    deducible: bool = False


@dataclass(frozen=True)
class SaldoFavorDeclarado:
    """Saldo a favor de la declaración DIAN anterior a los datos de COMPAS (CEO
    2026-08-11). `aplica_desde` (YYYY-MM-DD) marca el período donde ENTRA como
    `saldo_favor_previo`; ahí REEMPLAZA el arrastre derivado — la declaración
    oficial ya incorpora todo lo anterior (sumarlos sería doble conteo)."""

    aplica_desde: str  # 'YYYY-MM-DD' (el período se deriva con la periodicidad)
    valor: Decimal


@dataclass(frozen=True)
class LiquidacionPeriodo:
    anio: int
    periodo: int  # índice del período (1..3 cuatrimestral | 1..6 bimestral)
    generado: Decimal  # Σ IVA de ventas del período
    descontable: Decimal  # Σ IVA de compras deducibles
    saldo: Decimal  # generado − descontable
    saldo_favor_previo: Decimal  # arrastre del período anterior
    neto_a_pagar: Decimal  # max(0, saldo − saldo_favor_previo)
    saldo_favor_nuevo: Decimal  # max(0, saldo_favor_previo − saldo) → sigue arrastrando


@dataclass(frozen=True)
class FondoMes:
    """Un mes del plan del fondo de provisión de IVA (informativo, NO es flujo de caja
    del motor)."""

    mes_idx: int  # índice de mes relativo a mes_inicio
    reserva: Decimal  # aporte al fondo ese mes
    pago: Decimal  # salida del fondo ese mes (pago DIAN)
    saldo: Decimal  # saldo acumulado del fondo al cierre del mes


def _meses_del_periodo(
    anio: int, periodo: int, periodicidad: Periodicidad
) -> list[tuple[int, int]]:
    """(anio, mes) de los meses calendario que componen el período."""
    meses = _meses_por_periodo(periodicidad)
    primero = (periodo - 1) * meses + 1
    return [(anio, primero + i) for i in range(meses)]


def plan_fondo_provision(
    liquidaciones: list["LiquidacionPeriodo"],
    calendario_dian: dict,
    *,
    mes_inicio: tuple[int, int],
    horizonte_meses: int,
    periodicidad: Periodicidad = Periodicidad.cuatrimestral,
) -> list[FondoMes]:
    """Plan de reserva de tesorería para el pago del IVA (P1.4, decisión CEO
    2026-07-25): el `neto_a_pagar` de cada período se REPARTE en partes iguales entre
    los meses del propio período, de modo que al llegar la fecha DIAN el fondo ya tiene
    el monto completo y el pago lo vacía (sin golpe seco). Serie informativa alineada al
    horizonte; NO entra al flujo del motor (el egreso real ya cae en la fecha DIAN vía
    `programar_egresos_iva`). Neto 0 (saldo a favor) no reserva."""
    y0, m0 = mes_inicio
    aportes = [Decimal("0")] * horizonte_meses
    for c in liquidaciones:
        if c.neto_a_pagar <= 0:
            continue
        meses = _meses_del_periodo(c.anio, c.periodo, periodicidad)
        cuota = c.neto_a_pagar / Decimal(len(meses))
        for anio, mes in meses:
            idx = (anio - y0) * 12 + (mes - m0)
            if 0 <= idx < horizonte_meses:
                aportes[idx] += _cop(cuota)

    pagos_por_idx = programar_egresos_iva(
        liquidaciones,
        calendario_dian,
        mes_inicio=mes_inicio,
        horizonte_meses=horizonte_meses,
        periodicidad=periodicidad,
    )

    fondo: list[FondoMes] = []
    saldo = Decimal("0")
    for m in range(horizonte_meses):
        reserva = aportes[m]
        pago = pagos_por_idx.get(m, Decimal("0"))
        saldo = saldo + reserva - pago
        fondo.append(
            FondoMes(
                mes_idx=m,
                reserva=_cop(reserva),
                pago=_cop(pago),
                saldo=_cop(saldo),
            )
        )
    return fondo


def programar_egresos_iva(
    liquidaciones: list[LiquidacionPeriodo],
    calendario_dian: dict,
    *,
    mes_inicio: tuple[int, int],
    horizonte_meses: int,
    periodicidad: Periodicidad = Periodicidad.cuatrimestral,
) -> dict[int, Decimal]:
    """Mapea el `neto_a_pagar` de cada período al ÍNDICE de mes (relativo a
    `mes_inicio`) de su fecha DIAN real, para inyectarlo como egreso al motor (PR-2b).

    `calendario_dian` = la clave CONFIGURACION `CALENDARIO_DIAN`
    (`{"2026": {"ene_abr": "2026-05-13", ...}}`; claves según la periodicidad). NO
    inventa fechas: si el año del período no está en el calendario administrable, ese
    egreso no se proyecta (el CEO extiende el calendario). Neto 0 (saldo a favor) no
    genera egreso; fechas fuera del horizonte se descartan."""
    out: dict[int, Decimal] = {}
    y0, m0 = mes_inicio
    for c in liquidaciones:
        if c.neto_a_pagar <= 0:
            continue
        anio_cal = calendario_dian.get(str(c.anio))
        if not anio_cal:
            continue
        fecha = anio_cal.get(clave_dian(c.periodo, periodicidad))
        if not fecha:
            continue
        idx = (int(fecha[:4]) - y0) * 12 + (int(fecha[5:7]) - m0)
        if 0 <= idx < horizonte_meses:
            out[idx] = out.get(idx, Decimal("0")) + c.neto_a_pagar
    return out


def liquidar(
    facturas: list[FacturaIva],
    periodicidad: Periodicidad = Periodicidad.cuatrimestral,
    saldo_declarado: SaldoFavorDeclarado | None = None,
) -> list[LiquidacionPeriodo]:
    """Liquida cada período en orden CRONOLÓGICO (el arrastre lo exige). Devuelve una
    `LiquidacionPeriodo` por período con facturas, según la periodicidad.

    `saldo_declarado`: al llegar al PRIMER período >= su `aplica_desde`, el arrastre
    se REEMPLAZA por el valor declarado (una sola vez; si ese período no tiene
    facturas, fluye al siguiente con datos). Los períodos anteriores no cambian."""
    grupos: dict[tuple[int, int], list[FacturaIva]] = {}
    for f in facturas:
        grupos.setdefault(periodo_de(f.fecha, periodicidad), []).append(f)

    clave_declarado = (
        periodo_de(saldo_declarado.aplica_desde, periodicidad)
        if saldo_declarado is not None
        else None
    )
    out: list[LiquidacionPeriodo] = []
    favor = Decimal("0")
    for anio, c in sorted(grupos):
        if clave_declarado is not None and (anio, c) >= clave_declarado:
            favor = saldo_declarado.valor  # reemplaza el derivado (doble conteo no)
            clave_declarado = None  # se consume una sola vez
        fs = grupos[(anio, c)]
        generado = sum((f.iva_valor for f in fs if f.tipo == "venta"), Decimal("0"))
        descontable = sum(
            (f.iva_valor for f in fs if f.tipo == "compra" and f.deducible),
            Decimal("0"),
        )
        saldo = generado - descontable
        neto = max(Decimal("0"), saldo - favor)
        nuevo_favor = max(Decimal("0"), favor - saldo)
        out.append(
            LiquidacionPeriodo(
                anio=anio,
                periodo=c,
                generado=_cop(generado),
                descontable=_cop(descontable),
                saldo=_cop(saldo),
                saldo_favor_previo=_cop(favor),
                neto_a_pagar=_cop(neto),
                saldo_favor_nuevo=_cop(nuevo_favor),
            )
        )
        favor = nuevo_favor
    return out
