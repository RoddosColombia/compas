# backend/app/proyeccion/motor.py
"""Motor de proyección C7 (COCK-01) — NÚCLEO compute-only.

Réplica en Python de las funciones `simular()` / `calcularCredito()` del
`docs/modelo/Dashboard Artefacto.jsx` (la formulación LIMPIA y corregida del SIMULADOR
2030). Funciones PURAS (sin I/O), auditables celda-a-celda como `presupuesto/motor.py`.

Principios (CLAUDE.md + decisiones CEO 2026-07-23):
  - Dinero = Decimal, nunca float (regla 1).
  - Fechas América/Bogotá, `YYYY-MM-DD`, meses al día 1 (regla 2). Aquí solo se opera
    con fechas de calendario (`datetime.date`), sin horas ni timezone: el cobro es un
    día del calendario, no un instante.
  - CAJA VERAZ: la provisión NIIF 9 NO resta caja (va a P&G); mora/default sí, y son
    editables mes a mes con default al % del escenario.

Primera pieza: SEMANAS EXACTAS de cobro. El recaudo de crédito depende de cuántos días
de cobro (por defecto miércoles) caen en cada mes — jul-2026 = 5, no "4 fijas". Réplica
de `miercolesDelMes` del artefacto.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

_CENTAVO = Decimal("0.01")


def _cop(v: Decimal) -> Decimal:
    """Cuantiza a COP 2 decimales HALF_EVEN (misma política que money_str)."""
    return v.quantize(_CENTAVO, rounding=ROUND_HALF_EVEN)

# Día de la semana de cobro, convención date.weekday(): 0=lunes … 6=domingo.
# Miércoles = 2 (la semana 1 del 'Modelo Pagos' es el miércoles 2026-03-04).
DIA_COBRO_DEFECTO = 2

# Ancla de numeración de semanas: miércoles 2026-03-04 = semana 1 (celda N4 del
# 'Modelo Pagos'). Alinea las cohortes de ventas con la numeración del simulador.
ANCLA_SEMANA = date(2026, 3, 4)


@dataclass(frozen=True)
class ModeloProyeccion:
    """Modelo de moto para el motor (subconjunto de campos de la entidad ModeloMoto
    que afectan la proyección de ingreso). `mix` = participación 0..1; el PRIMER
    modelo de la lista es la BASE y absorbe el resto del split (como Raider en el
    artefacto: `raider = total − round(total × pctApache)`)."""

    nombre: str
    cuota_semanal: Decimal
    cuota_inicial: Decimal
    plazo_semanas: int
    mix: Decimal


def dias_de_cobro_del_mes(
    anio: int, mes: int, dia_cobro: int = DIA_COBRO_DEFECTO
) -> list[date]:
    """Días de cobro (por defecto miércoles) que caen DENTRO del mes calendario.

    Réplica de `miercolesDelMes`: primer día de cobro >= día 1 del mes, luego cada 7
    días mientras siga en el mes. Es el driver de las 'semanas exactas'."""
    d = date(anio, mes, 1)
    # avanzar hasta el primer `dia_cobro` (weekday) en o después del día 1
    d += timedelta(days=(dia_cobro - d.weekday()) % 7)
    dias: list[date] = []
    while d.month == mes:
        dias.append(d)
        d += timedelta(days=7)
    return dias


def semanas_de_cobro(anio: int, mes: int, dia_cobro: int = DIA_COBRO_DEFECTO) -> int:
    """Número de días de cobro del mes = 'semanas exactas' del mes (4 o 5)."""
    return len(dias_de_cobro_del_mes(anio, mes, dia_cobro))


def colocacion_mensual(
    motos_base: int,
    crec_pct_mensual: Decimal,
    horizonte_meses: int,
    rampa: list[int] | None = None,
) -> list[int]:
    """Serie de motos colocadas por mes (unidades enteras).

    Réplica del encadenamiento de la columna C del SIMULADOR: `C10 = ROUND(C9 × (1 +
    crec))` mes a mes (con 1% da 50,51,52,53…, distinto de `ROUND(50 × 1.01^k)`).
    `rampa` = colocación REAL de los primeros meses (override); el primer mes
    post-rampa reinicia en `motos_base` y de ahí crece encadenado. `crec_pct_mensual`
    es fracción (0.01 = 1%). Redondeo half-up (Math.floor(x+0.5) del artefacto)."""
    rampa = rampa or []
    serie: list[int] = []
    encadenada = motos_base
    for m in range(horizonte_meses):
        if m < len(rampa):
            serie.append(rampa[m])
            continue
        if m == len(rampa):
            encadenada = motos_base
        else:
            crudo = Decimal(encadenada) * (Decimal(1) + crec_pct_mensual)
            encadenada = int(crudo.quantize(Decimal(1), rounding=ROUND_HALF_UP))
        serie.append(encadenada)
    return serie


def indice_semana(fecha: date, ancla: date = ANCLA_SEMANA) -> int:
    """Semana global (1-based) de una fecha desde el ancla. Réplica de
    `semanaDeFecha`: `floor((fecha − ancla)/7) + 1`."""
    return (fecha - ancla).days // 7 + 1


def _meses_del_horizonte(mes_inicio: tuple[int, int], n: int) -> list[tuple[int, int]]:
    anio0, mes0 = mes_inicio
    meses: list[tuple[int, int]] = []
    for i in range(n):
        t = (mes0 - 1) + i
        meses.append((anio0 + t // 12, t % 12 + 1))
    return meses


def _semanas_globales_del_mes(
    anio: int, mes: int, dia_cobro: int, ancla: date
) -> list[int]:
    """Índices de semana global de los días de cobro reales del mes."""
    dias = dias_de_cobro_del_mes(anio, mes, dia_cobro)
    return [indice_semana(d, ancla) for d in dias]


def _split_por_mix(total: int, modelos: list[ModeloProyeccion]) -> list[int]:
    """Reparte `total` motos entre modelos por `mix`. El modelo 0 (base) absorbe el
    resto; los demás = round(total × mix). Suma exactamente `total`."""
    counts = [0] * len(modelos)
    resto = total
    for i in range(1, len(modelos)):
        c = int((Decimal(total) * modelos[i].mix).quantize(Decimal(1), ROUND_HALF_UP))
        counts[i] = c
        resto -= c
    counts[0] = resto
    return counts


def _distribuir(nm: int, semanas_g: list[int], altas: dict[int, int]) -> None:
    """Reparte `nm` motos entre las semanas del mes (réplica de `distribuir` del
    artefacto): `mpw = max(1, round(nm/nw))` por semana, el resto en la última."""
    if nm <= 0:
        return
    nw = len(semanas_g)
    mpw = max(1, int((Decimal(nm) / Decimal(nw)).quantize(Decimal(1), ROUND_HALF_UP)))
    pd = nm
    for iw in range(nw):
        if pd <= 0:
            break
        mw = pd if iw == nw - 1 else min(mpw, pd)
        w = semanas_g[iw]
        altas[w] = altas.get(w, 0) + mw
        pd -= mw


def _altas_por_modelo(
    colocacion_por_mes: list[int],
    modelos: list[ModeloProyeccion],
    meses: list[tuple[int, int]],
    dia_cobro: int,
    ancla: date,
) -> list[dict[int, int]]:
    """altas[i][w] = motos del modelo i colocadas en la semana global w."""
    altas: list[dict[int, int]] = [dict() for _ in modelos]
    for mi, (y, m) in enumerate(meses):
        total = colocacion_por_mes[mi]
        if total <= 0:
            continue
        counts = _split_por_mix(total, modelos)
        semanas_g = _semanas_globales_del_mes(y, m, dia_cobro, ancla)
        for i_modelo, nm in enumerate(counts):
            _distribuir(nm, semanas_g, altas[i_modelo])
    return altas


def _activos_en_semana(altas: dict[int, int], w: int, plazo: int) -> int:
    """Motos activas (pagando) en la semana w = colocadas en (w − plazo, w]."""
    return sum(v for wk, v in altas.items() if w - plazo < wk <= w)


def recaudo_credito_mensual(
    colocacion_por_mes: list[int],
    modelos: list[ModeloProyeccion],
    mes_inicio: tuple[int, int],
    dia_cobro: int = DIA_COBRO_DEFECTO,
    ancla: date = ANCLA_SEMANA,
) -> list[Decimal]:
    """Vía 1 — recaudo de crédito por mes (motor cuota-a-cuota). Cada moto colocada
    abre una ventana de `plazo_semanas` cuotas semanales; el recaudo del mes = Σ de las
    cuotas activas de todas las ventas vivas en las semanas de cobro reales del mes."""
    meses = _meses_del_horizonte(mes_inicio, len(colocacion_por_mes))
    altas = _altas_por_modelo(colocacion_por_mes, modelos, meses, dia_cobro, ancla)
    recaudo: list[Decimal] = []
    for y, m in meses:
        semanas_g = _semanas_globales_del_mes(y, m, dia_cobro, ancla)
        total_mes = Decimal(0)
        for w in semanas_g:
            for i_modelo, md in enumerate(modelos):
                act = _activos_en_semana(altas[i_modelo], w, md.plazo_semanas)
                total_mes += Decimal(act) * md.cuota_semanal
        recaudo.append(total_mes)
    return recaudo


def cuotas_iniciales_mensual(
    colocacion_por_mes: list[int], modelos: list[ModeloProyeccion]
) -> list[Decimal]:
    """Vía 2 — cuotas iniciales por mes = Σ_modelo (colocación_modelo × cuota_inicial).
    Se muestra SIEMPRE separada del recaudo de crédito (requisito CEO)."""
    out: list[Decimal] = []
    for total in colocacion_por_mes:
        counts = _split_por_mix(total, modelos)
        v = sum(
            (n * md.cuota_inicial for n, md in zip(counts, modelos, strict=True)),
            Decimal(0),
        )
        out.append(v)
    return out


@dataclass(frozen=True)
class AjusteMora:
    """Ajustes de cartera sobre el ingreso bruto de un mes. CAJA VERAZ (decisión CEO
    2026-07-23): `neto` = bruto + mora + recuperación + default. La `provision` (NIIF
    9) se calcula para P&G / economía unitaria pero NO entra al flujo de caja."""

    mora: Decimal
    recuperacion: Decimal
    default: Decimal
    neto: Decimal
    provision: Decimal


def neto_por_mora(
    bruto: Decimal,
    pct_mora: Decimal,
    pct_recuperacion: Decimal,
    pct_default: Decimal,
    pct_provision: Decimal = Decimal("0"),
) -> AjusteMora:
    """Aplica mora/recuperación/default al bruto (réplica FC filas 17-20 del artefacto,
    MENOS la provisión, que sale del flujo por 'caja veraz'). Los porcentajes son el
    valor del escenario por defecto; el motor los deja editar mes a mes."""
    mora = -bruto * pct_mora
    recuperacion = -mora * pct_recuperacion  # recupera parte de la mora
    default = -bruto * pct_default
    provision = -bruto * pct_provision
    neto = bruto + mora + recuperacion + default
    return AjusteMora(
        mora=_cop(mora),
        recuperacion=_cop(recuperacion),
        default=_cop(default),
        neto=_cop(neto),
        provision=_cop(provision),
    )
