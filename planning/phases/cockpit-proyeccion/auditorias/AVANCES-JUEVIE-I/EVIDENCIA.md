# EVIDENCIA — AVANCES JUE-VIE (2026-07-23/24) · Ronda I

Código y salidas de tests reales que respaldan la SOLICITUD del mismo paquete. Todo
extraído del repo en `main` (vía `git show` / `git diff` y lectura directa de los
archivos). Es un documento forense: nada aquí está inventado ni parafraseado sobre el
código real.

## 0. Salidas de tests reales

Resultados ya ejecutados por el orquestador (no se re-corren en la sesión de auditoría
por ser lentos / requerir cluster):

- **Backend, 9 áreas críticas** —
  `pytest tests/test_proyeccion_motor.py tests/test_proyeccion_endpoints.py tests/test_caja_saldos_guards.py tests/test_pagos_semana.py tests/test_rubros_endpoints.py tests/test_domain_rubro.py tests/test_control_por_cuenta.py tests/test_audit_events.py tests/test_rbac_permissions.py`
  → **`129 passed, 1108 warnings in 194.79s`**.
- **Motor puro aislado** — `pytest tests/test_proyeccion_motor.py`
  → **`18 passed in 0.06s`**.
- **Frontend `npm run build`** — **verde**: `✓ built in 5.51s`,
  bundle `index-CwFTorO1.js 410.90 kB (gzip 122.39 kB)`.
- **Frontend `npx vitest run`** — **`Test Files 17 passed (17)` · `Tests 49 passed (49)`**.
- **Suites `*realmongo`** (`test_caja_saldos_realmongo.py`, `test_pagos_marcar_realmongo.py`):
  requieren `COMPAS_TEST_MONGO_URI` (cluster), **NO disponible** en la sesión de
  auditoría; corren verdes en CI al mergear. Se declara tal cual — no se maquilla.

## 1. Motor de proyección C7 — código íntegro (VERBATIM)

El motor es el centro de la auditoría. Los tres archivos van completos, sin recortes.

### backend/app/proyeccion/motor.py

```python
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
    costo_moto: Decimal = Decimal("0")  # costo Auteco del modelo (para el lote)


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


def inventario_auteco_mensual(
    lote_por_mes: list[Decimal],
    adelanto_por_mes: list[Decimal],
    plazo_auteco_dias: int,
    base_auteco_dias: int,
    tasa_auteco: Decimal,
) -> tuple[list[Decimal], list[Decimal]]:
    """Pago de inventario Auteco (fila 29, saldo rodante) y fondeo (fila 30).

    ANTI-DOBLE-CONTEO (el fix del artefacto): el lote se paga UNA sola vez, desfasado
    `delayPago = INT(plazo/30)` meses. La recurrencia arranca del saldo del mes previo
    pisado a 0 (`max(pago[m-1], 0)`), neteando el lote que vence y su adelanto.
    Fondeo = costo de mantener el lote entre `delayBase` y `delayPago` (mesesInterés).
    Series de egreso (valores negativos = salida de caja)."""
    n = len(lote_por_mes)
    delay_pago = plazo_auteco_dias // 30
    delay_base = base_auteco_dias // 30
    meses_interes = max(0, delay_pago - delay_base)

    def lote(i: int) -> Decimal:
        return lote_por_mes[i] if 0 <= i < n else Decimal("0")

    def adel(i: int) -> Decimal:
        return adelanto_por_mes[i] if 0 <= i < n else Decimal("0")

    pago_inv: list[Decimal] = [Decimal("0")] * n
    for m in range(n):
        if m < delay_pago:
            pago_inv[m] = Decimal("0")
        elif m == delay_pago:
            sum_ade = sum((adel(k) for k in range(delay_pago + 1)), Decimal("0"))
            pago_inv[m] = -lote(0) - sum_ade
        else:
            prev = pago_inv[m - 1] if pago_inv[m - 1] > 0 else Decimal("0")
            pago_inv[m] = prev - lote(m - delay_pago) - adel(m)

    fondeo: list[Decimal] = [Decimal("0")] * n
    for m in range(n):
        if m < delay_pago:
            if m == delay_base + 1:
                fondeo[m] = -(lote(m - delay_base) + adel(m - delay_base)) * tasa_auteco
        else:
            fondeo[m] = -lote(m - delay_pago) * tasa_auteco * meses_interes

    return [_cop(v) for v in pago_inv], [_cop(v) for v in fondeo]


def _lote_por_mes(
    colocacion_por_mes: list[int], modelos: list[ModeloProyeccion]
) -> list[Decimal]:
    """Valor facturado del lote por mes (split FRACCIONARIO en valor, como el artefacto:
    `motos × mix × costo`, no por unidades enteras)."""
    out: list[Decimal] = []
    for total in colocacion_por_mes:
        v = sum(
            (Decimal(total) * md.mix * md.costo_moto for md in modelos), Decimal("0")
        )
        out.append(v)
    return out


def _adelanto_por_mes(
    colocacion_por_mes: list[int], adelanto_auteco: Decimal
) -> list[Decimal]:
    """Adelanto Auteco por mes: 0 el primer mes; luego `-motos × adelanto/moto`."""
    out: list[Decimal] = []
    for m, total in enumerate(colocacion_por_mes):
        out.append(Decimal("0") if m == 0 else -Decimal(total) * adelanto_auteco)
    return out


def cartera_activa_mensual(
    colocacion_por_mes: list[int],
    modelos: list[ModeloProyeccion],
    mes_inicio: tuple[int, int],
    dia_cobro: int = DIA_COBRO_DEFECTO,
    ancla: date = ANCLA_SEMANA,
) -> list[int]:
    """Motos activas (pagando) al CIERRE de cada mes = activos en la última semana de
    cobro del mes. Alimenta el GPS (costo por moto activa)."""
    meses = _meses_del_horizonte(mes_inicio, len(colocacion_por_mes))
    altas = _altas_por_modelo(colocacion_por_mes, modelos, meses, dia_cobro, ancla)
    out: list[int] = []
    for y, m in meses:
        semanas_g = _semanas_globales_del_mes(y, m, dia_cobro, ancla)
        w_ref = semanas_g[-1] if semanas_g else 0
        cartera = sum(
            _activos_en_semana(altas[i], w_ref, md.plazo_semanas)
            for i, md in enumerate(modelos)
        )
        out.append(cartera)
    return out


# Presets de escenario (réplica de `escMora` del artefacto): mora / recuperación.
PRESETS_ESCENARIO: dict[str, dict[str, Decimal]] = {
    "pesimista": {"pct_mora": Decimal("0.06"), "pct_recuperacion": Decimal("0.30")},
    "base": {"pct_mora": Decimal("0.03"), "pct_recuperacion": Decimal("0.40")},
    "optimista": {"pct_mora": Decimal("0.015"), "pct_recuperacion": Decimal("0.60")},
}


@dataclass(frozen=True)
class ParametrosMotor:
    """Drivers del motor (réplica del objeto `p` del artefacto). Los porcentajes de
    mora/default son del escenario ACTIVO; `overrides_*` permiten editarlos mes a mes
    (índice de mes → pct). Todo monto es Decimal (regla 1)."""

    mes_inicio: tuple[int, int]
    horizonte_meses: int
    modelos: list[ModeloProyeccion]
    motos_base: int
    crec_pct_mensual: Decimal
    rampa: list[int] | None
    adelanto_auteco: Decimal
    plazo_auteco_dias: int
    base_auteco_dias: int
    tasa_auteco: Decimal
    gastos_fijos: Decimal
    gps_moto: Decimal
    costo_moto_nueva: Decimal
    deuda: Decimal
    tasa_deuda: Decimal
    mes_inicio_deuda: int
    meses_deuda: int
    pct_mora: Decimal
    pct_recuperacion: Decimal
    pct_default: Decimal
    pct_provision: Decimal
    overrides_mora: dict[int, Decimal] | None
    overrides_default: dict[int, Decimal] | None
    caja_inicial: Decimal
    caja_minima: Decimal


@dataclass(frozen=True)
class MesProyeccion:
    mes: str  # 'YYYY-MM' (día 1)
    motos: int
    cartera: int
    recaudo_credito: Decimal  # Vía 1
    cuotas_iniciales: Decimal  # Vía 2
    ingreso_bruto: Decimal
    neto: Decimal
    provision: Decimal  # informativo (P&G/NIIF 9), NO en el flujo
    gastos_fijos: Decimal
    gps: Decimal
    costo_nueva: Decimal
    adelanto: Decimal
    pago_inventario: Decimal
    fondeo: Decimal
    int_deuda: Decimal
    egresos: Decimal
    flujo: Decimal
    caja: Decimal
    estado: str  # 'ok' | 'critico' | 'negativo'


@dataclass(frozen=True)
class ResultadoProyeccion:
    meses: list[MesProyeccion]
    piso_caja: Decimal
    mes_mas_ajustado: str
    meses_bajo_minimo: int
    caja_final: Decimal
    capital_requerido: Decimal
    runway_meses: Decimal | None


def _estado_caja(caja: Decimal, caja_minima: Decimal) -> str:
    if caja < 0:
        return "negativo"
    if caja < caja_minima:
        return "critico"
    return "ok"


def proyectar(p: ParametrosMotor) -> ResultadoProyeccion:
    """El corazón de COCK-01: proyecta el flujo de caja mes a mes replicando la
    formulación del Dashboard Artefacto, con recaudo discriminado (2 vías), caja veraz
    (provisión fuera del flujo) y horizonte configurable. Compute-only, todo Decimal."""
    meses_ym = _meses_del_horizonte(p.mes_inicio, p.horizonte_meses)
    colocacion = colocacion_mensual(
        p.motos_base, p.crec_pct_mensual, p.horizonte_meses, p.rampa
    )
    recaudo = recaudo_credito_mensual(colocacion, p.modelos, p.mes_inicio)
    iniciales = cuotas_iniciales_mensual(colocacion, p.modelos)
    cartera = cartera_activa_mensual(colocacion, p.modelos, p.mes_inicio)
    lote = _lote_por_mes(colocacion, p.modelos)
    adelanto = _adelanto_por_mes(colocacion, p.adelanto_auteco)
    pago_inv, fondeo = inventario_auteco_mensual(
        lote, adelanto, p.plazo_auteco_dias, p.base_auteco_dias, p.tasa_auteco
    )
    ov_mora = p.overrides_mora or {}
    ov_def = p.overrides_default or {}

    filas: list[MesProyeccion] = []
    caja = _cop(p.caja_inicial)
    for m, (y, mo) in enumerate(meses_ym):
        bruto = recaudo[m] + iniciales[m]
        ajuste = neto_por_mora(
            bruto,
            ov_mora.get(m, p.pct_mora),
            p.pct_recuperacion,
            ov_def.get(m, p.pct_default),
            p.pct_provision,
        )
        gastos_fijos = _cop(-p.gastos_fijos)
        gps = _cop(-Decimal(cartera[m]) * p.gps_moto)
        costo_nueva = _cop(-Decimal(colocacion[m]) * p.costo_moto_nueva)
        int_deuda = (
            _cop(-p.deuda * p.tasa_deuda)
            if p.mes_inicio_deuda <= m < p.meses_deuda
            else Decimal("0.00")
        )
        egresos = _cop(
            gastos_fijos
            + gps
            + costo_nueva
            + int_deuda
            + adelanto[m]
            + pago_inv[m]
            + fondeo[m]
        )
        flujo = _cop(ajuste.neto + egresos)
        # primer mes: caja fija (= caja inicial); el flujo de ese mes no la mueve.
        if m > 0:
            caja = _cop(caja + flujo)
        filas.append(
            MesProyeccion(
                mes=f"{y:04d}-{mo:02d}",
                motos=colocacion[m],
                cartera=cartera[m],
                recaudo_credito=_cop(recaudo[m]),
                cuotas_iniciales=_cop(iniciales[m]),
                ingreso_bruto=_cop(bruto),
                neto=ajuste.neto,
                provision=ajuste.provision,
                gastos_fijos=gastos_fijos,
                gps=gps,
                costo_nueva=costo_nueva,
                adelanto=_cop(adelanto[m]),
                pago_inventario=pago_inv[m],
                fondeo=fondeo[m],
                int_deuda=int_deuda,
                egresos=egresos,
                flujo=flujo,
                caja=caja,
                estado=_estado_caja(caja, p.caja_minima),
            )
        )

    cajas = [f.caja for f in filas]
    piso = min(cajas)
    idx_piso = cajas.index(piso)
    bajo_min = sum(1 for c in cajas if c < p.caja_minima)
    caja_final = cajas[-1]
    capital_req = _cop(max(Decimal("0"), p.caja_minima - piso))
    # runway = meses de caja al ritmo de quema promedio (si hay quema neta).
    flujos = [f.flujo for f in filas]
    prom_flujo = sum(flujos, Decimal("0")) / Decimal(len(flujos))
    runway = (
        _cop(caja_final / -prom_flujo) if prom_flujo < 0 and caja_final > 0 else None
    )
    return ResultadoProyeccion(
        meses=filas,
        piso_caja=piso,
        mes_mas_ajustado=filas[idx_piso].mes,
        meses_bajo_minimo=bajo_min,
        caja_final=caja_final,
        capital_requerido=capital_req,
        runway_meses=runway,
    )
```

### backend/app/proyeccion/service.py

```python
# backend/app/proyeccion/service.py
"""Servicio de proyección (COCK-01) — orquesta el motor compute-only.

Carga los parámetros VIGENTES + el catálogo de modelos ACTIVOS, arma un
`ParametrosMotor`, aplica el escenario (presets de mora/recuperación) y llama a
`motor.proyectar()`. Serializa a JSON con montos como string (regla 1). No escribe
estado: es una lectura pura sobre la configuración vigente."""

from app.core.money import money_str
from app.domain.modelo_moto import ModeloMoto
from app.domain.parametros_proyeccion import ParametrosProyeccion
from app.modelos_moto import service as modelos_service
from app.parametros_proyeccion import service as parametros_service
from app.proyeccion.motor import (
    PRESETS_ESCENARIO,
    ModeloProyeccion,
    ParametrosMotor,
    ResultadoProyeccion,
    proyectar,
)

HORIZONTE_MAX = 180  # 15 años (tope de infraestructura)


class ProyeccionError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


def _modelo_a_motor(m: ModeloMoto) -> ModeloProyeccion:
    return ModeloProyeccion(
        nombre=m.nombre,
        cuota_semanal=m.cuota_semanal,
        cuota_inicial=m.cuota_inicial,
        plazo_semanas=m.plazo_semanas,
        mix=m.participacion_mix,
        costo_moto=m.costo_auteco,
    )


def _armar_parametros(
    params: ParametrosProyeccion,
    modelos: list[ModeloMoto],
    escenario: str,
    mes_inicio: tuple[int, int],
    horizonte_meses: int,
) -> ParametrosMotor:
    pct_mora, pct_recuperacion = params.pct_mora, params.pct_recuperacion
    # el escenario (preset) sobrescribe mora/recuperación; el resto queda de params.
    if escenario in PRESETS_ESCENARIO:
        pct_mora = PRESETS_ESCENARIO[escenario]["pct_mora"]
        pct_recuperacion = PRESETS_ESCENARIO[escenario]["pct_recuperacion"]
    return ParametrosMotor(
        mes_inicio=mes_inicio,
        horizonte_meses=horizonte_meses,
        modelos=[_modelo_a_motor(m) for m in modelos],
        motos_base=params.motos_base,
        crec_pct_mensual=params.crec_pct_mensual,
        rampa=None,
        adelanto_auteco=params.adelanto_auteco,
        plazo_auteco_dias=params.plazo_auteco_dias,
        base_auteco_dias=params.base_auteco_dias,
        tasa_auteco=params.tasa_auteco,
        gastos_fijos=params.gastos_fijos,
        gps_moto=params.gps_moto,
        costo_moto_nueva=params.costo_moto_nueva,
        deuda=params.deuda,
        tasa_deuda=params.tasa_deuda,
        mes_inicio_deuda=params.mes_inicio_deuda,
        meses_deuda=params.meses_deuda,
        pct_mora=pct_mora,
        pct_recuperacion=pct_recuperacion,
        pct_default=params.pct_default,
        pct_provision=params.pct_provision,
        overrides_mora=None,
        overrides_default=None,
        caja_inicial=params.caja_inicial,
        caja_minima=params.caja_minima,
    )


def _serializar(r: ResultadoProyeccion, escenario: str, caja_minima) -> dict:
    return {
        "escenario": escenario,
        "caja_minima": money_str(caja_minima),  # el umbral (para la curva del front)
        "piso_caja": money_str(r.piso_caja),
        "mes_mas_ajustado": r.mes_mas_ajustado,
        "meses_bajo_minimo": r.meses_bajo_minimo,
        "caja_final": money_str(r.caja_final),
        "capital_requerido": money_str(r.capital_requerido),
        "runway_meses": (
            money_str(r.runway_meses) if r.runway_meses is not None else None
        ),
        "meses": [
            {
                "mes": f.mes,
                "motos": f.motos,
                "cartera": f.cartera,
                "recaudo_credito": money_str(f.recaudo_credito),
                "cuotas_iniciales": money_str(f.cuotas_iniciales),
                "ingreso_bruto": money_str(f.ingreso_bruto),
                "neto": money_str(f.neto),
                "provision": money_str(f.provision),
                "gastos_fijos": money_str(f.gastos_fijos),
                "gps": money_str(f.gps),
                "costo_nueva": money_str(f.costo_nueva),
                "adelanto": money_str(f.adelanto),
                "pago_inventario": money_str(f.pago_inventario),
                "fondeo": money_str(f.fondeo),
                "int_deuda": money_str(f.int_deuda),
                "egresos": money_str(f.egresos),
                "flujo": money_str(f.flujo),
                "caja": money_str(f.caja),
                "estado": f.estado,
            }
            for f in r.meses
        ],
    }


async def proyectar_vigente(
    *, escenario: str, mes_inicio: tuple[int, int], horizonte_meses: int | None
) -> dict:
    """Proyección con los parámetros/modelos vigentes. Falla-cerrado si falta config
    (no se inventan cifras): 409 si no hay parámetros o no hay modelos activos."""
    params = await parametros_service.obtener_vigente()
    if params is None:
        raise ProyeccionError(
            "no hay parámetros de proyección configurados (cárguelos primero)", 409
        )
    modelos = await modelos_service.listar_modelos(activo=True)
    if not modelos:
        raise ProyeccionError("no hay modelos de moto activos", 409)
    horizonte = horizonte_meses or params.horizonte_meses
    if horizonte < 1 or horizonte > HORIZONTE_MAX:
        raise ProyeccionError(
            f"horizonte_meses debe estar en [1, {HORIZONTE_MAX}]", 422
        )
    pm = _armar_parametros(params, modelos, escenario, mes_inicio, horizonte)
    return _serializar(proyectar(pm), escenario, params.caja_minima)
```

### backend/tests/test_proyeccion_motor.py

```python
# backend/tests/test_proyeccion_motor.py
"""Motor de proyección C7 (COCK-01) — NÚCLEO compute-only, réplica de las funciones
`simular()` / `calcularCredito()` del Dashboard Artefacto (la formulación limpia del
SIMULADOR 2030). Test de paridad celda-a-celda + reglas de CLAUDE.md (Decimal, TZ).

Verdad de base: la semana 1 del 'Modelo Pagos' es el miércoles 2026-03-04; desde ahí
el cobro es semanal (miércoles). Meses conocidos: jul-2026 = 5 miércoles (1,8,15,22,29);
jun-2026 = 4; ago-2026 = 4.
"""

from datetime import date
from decimal import Decimal

from app.proyeccion.motor import (
    PRESETS_ESCENARIO,
    ModeloProyeccion,
    ParametrosMotor,
    colocacion_mensual,
    cuotas_iniciales_mensual,
    dias_de_cobro_del_mes,
    indice_semana,
    inventario_auteco_mensual,
    neto_por_mora,
    proyectar,
    recaudo_credito_mensual,
    semanas_de_cobro,
)


def test_julio_2026_tiene_cinco_miercoles():
    dias = dias_de_cobro_del_mes(2026, 7)
    assert dias == [
        date(2026, 7, 1),
        date(2026, 7, 8),
        date(2026, 7, 15),
        date(2026, 7, 22),
        date(2026, 7, 29),
    ]
    assert semanas_de_cobro(2026, 7) == 5


def test_junio_y_agosto_2026_tienen_cuatro_miercoles():
    assert semanas_de_cobro(2026, 6) == 4  # 3,10,17,24
    assert semanas_de_cobro(2026, 8) == 4  # 5,12,19,26


def test_marzo_2026_arranca_el_4():
    # La semana 1 del Modelo Pagos es el miércoles 2026-03-04.
    assert dias_de_cobro_del_mes(2026, 3)[0] == date(2026, 3, 4)


# ── Colocación mensual: crecimiento ENCADENADO con redondeo (C10=ROUND(C9×(1+g))) ──


def test_colocacion_encadenada_suma_uno_por_mes_al_uno_por_ciento():
    # 50 @ 1% mensual encadenado → 50,51,52,53,54 (NO 50×1.01^k).
    serie = colocacion_mensual(
        motos_base=50, crec_pct_mensual=Decimal("0.01"), horizonte_meses=5
    )
    assert serie == [50, 51, 52, 53, 54]


def test_colocacion_respeta_rampa_de_meses_reales_y_reinicia_en_base():
    # Meses reales (rampa) mandan; el primer mes post-rampa arranca en la base.
    serie = colocacion_mensual(
        motos_base=50,
        crec_pct_mensual=Decimal("0.01"),
        horizonte_meses=5,
        rampa=[20, 48],
    )
    assert serie == [20, 48, 50, 51, 52]


def test_colocacion_crecimiento_cero_es_constante():
    serie = colocacion_mensual(
        motos_base=30, crec_pct_mensual=Decimal("0"), horizonte_meses=4
    )
    assert serie == [30, 30, 30, 30]


# ── Índice de semana global (ancla = miércoles 2026-03-04 = semana 1) ──


def test_indice_semana_ancla_y_julio():
    assert indice_semana(date(2026, 3, 4)) == 1
    assert indice_semana(date(2026, 3, 11)) == 2
    # 2026-07-01 está a 119 días del ancla → semana 18.
    assert indice_semana(date(2026, 7, 1)) == 18


# ── Recaudo por 2 vías: cuota-a-cuota (Vía 1) + cuotas iniciales (Vía 2) ──


def _modelo_unico(cuota_semanal, cuota_inicial, plazo):
    return ModeloProyeccion(
        nombre="Test",
        cuota_semanal=Decimal(cuota_semanal),
        cuota_inicial=Decimal(cuota_inicial),
        plazo_semanas=plazo,
        mix=Decimal("1"),
    )


def test_recaudo_credito_cuota_a_cuota_cruza_meses():
    # 1 moto colocada en jul-2026 (semana 18 = jul 1), cuota 100, plazo 6 semanas.
    # Paga semanas 18-23: jul 1,8,15,22,29 (5) + ago 5 (1) → jul=500, ago=100.
    modelos = [_modelo_unico(100, 0, 6)]
    recaudo = recaudo_credito_mensual(
        colocacion_por_mes=[1, 0, 0, 0],
        modelos=modelos,
        mes_inicio=(2026, 7),
    )
    assert recaudo == [Decimal("500"), Decimal("100"), Decimal("0"), Decimal("0")]


def test_cuotas_iniciales_por_colocacion():
    # Vía 2: colocación × cuota inicial, por mes. 2 motos × 1000 = 2000 el primer mes.
    modelos = [_modelo_unico(100, 1000, 6)]
    iniciales = cuotas_iniciales_mensual(colocacion_por_mes=[2, 3], modelos=modelos)
    assert iniciales == [Decimal("2000"), Decimal("3000")]


def test_dos_modelos_split_por_mix_base_absorbe_resto():
    # models[0] es la base (absorbe el resto); models[1] = round(total×mix).
    # total=10, mix Apache=0.30 → apache=3, raider(base)=7.
    # iniciales = 7×1000 + 3×2000 = 13000.
    base = ModeloProyeccion(
        "Raider", Decimal("100"), Decimal("1000"), 78, Decimal("0.70")
    )
    apache = ModeloProyeccion(
        "Apache", Decimal("120"), Decimal("2000"), 78, Decimal("0.30")
    )
    iniciales = cuotas_iniciales_mensual([10], [base, apache])
    assert iniciales == [Decimal("13000")]


# ── Mora / default: CAJA VERAZ (provisión NIIF 9 NO resta caja — decisión CEO) ──


def test_neto_por_mora_caja_veraz_excluye_provision():
    # bruto=1000, mora 3%, recuperación 40%, default 3%, provisión 2%.
    #   mora = -30 · recu = +12 (40% de 30) · def = -30
    #   neto = 1000 - 30 + 12 - 30 = 952  (la provisión NO entra)
    a = neto_por_mora(
        bruto=Decimal("1000"),
        pct_mora=Decimal("0.03"),
        pct_recuperacion=Decimal("0.40"),
        pct_default=Decimal("0.03"),
        pct_provision=Decimal("0.02"),
    )
    assert a.mora == Decimal("-30")
    assert a.recuperacion == Decimal("12.00")
    assert a.default == Decimal("-30")
    assert a.neto == Decimal("952.00")
    # provisión se calcula para P&G/NIIF 9 pero NO afecta el neto de caja.
    assert a.provision == Decimal("-20")
    # prueba de no-regresión: si la provisión entrara al flujo, neto sería 932.
    assert a.neto != Decimal("932.00")


def test_neto_por_mora_sin_ajustes_es_el_bruto():
    a = neto_por_mora(
        bruto=Decimal("1000"),
        pct_mora=Decimal("0"),
        pct_recuperacion=Decimal("0"),
        pct_default=Decimal("0"),
        pct_provision=Decimal("0"),
    )
    assert a.neto == Decimal("1000.00")
    assert a.provision == Decimal("0.00")


# ── Inventario Auteco: saldo rodante (fila 29) + fondeo (fila 30) ──
# Anti-doble-conteo: cada lote se paga UNA vez, desfasado delayPago meses.


def test_inventario_auteco_saldo_rodante_y_fondeo():
    # lote constante 10.000/mes, adelanto 0 el mes 0 y -1.000 en adelante.
    # plazo 150d → delayPago=5; base 90d → delayBase=3; mesesInterés=2; tasa 1%.
    lote = [Decimal("10000")] * 8
    adelanto = [Decimal("0")] + [Decimal("-1000")] * 7
    pago_inv, fondeo = inventario_auteco_mensual(
        lote_por_mes=lote,
        adelanto_por_mes=adelanto,
        plazo_auteco_dias=150,
        base_auteco_dias=90,
        tasa_auteco=Decimal("0.01"),
    )
    # m<5: sin pago. m=5: -(lote[0]) - Σ adelanto[0..5] = -10000 -(-5000) = -5000.
    # m=6: max(-5000,0) - lote[1] - adelanto[6] = 0 -10000 +1000 = -9000. m=7 igual.
    assert pago_inv == [
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("-5000.00"),
        Decimal("-9000.00"),
        Decimal("-9000.00"),
    ]
    # fondeo: m=4 (=delayBase+1): -(lote[1]+adelanto[1])×1% = -(9000)×0.01 = -90.
    # m>=5: -(lote[m-5])×1%×2 = -10000×0.02 = -200.
    assert fondeo == [
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("-90.00"),
        Decimal("-200.00"),
        Decimal("-200.00"),
        Decimal("-200.00"),
    ]


# ── proyectar(): ensamblaje del flujo + caja acumulada + KPIs ──


def _params_simple(**over):
    base = dict(
        mes_inicio=(2026, 7),
        horizonte_meses=4,
        modelos=[
            ModeloProyeccion(
                "Raider",
                cuota_semanal=Decimal("100"),
                cuota_inicial=Decimal("1000"),
                plazo_semanas=6,
                mix=Decimal("1"),
                costo_moto=Decimal("5000"),
            )
        ],
        motos_base=2,
        crec_pct_mensual=Decimal("0"),
        rampa=None,
        adelanto_auteco=Decimal("100"),
        plazo_auteco_dias=60,
        base_auteco_dias=30,
        tasa_auteco=Decimal("0"),
        gastos_fijos=Decimal("1000"),
        gps_moto=Decimal("0"),
        costo_moto_nueva=Decimal("0"),
        deuda=Decimal("0"),
        tasa_deuda=Decimal("0"),
        mes_inicio_deuda=0,
        meses_deuda=0,
        pct_mora=Decimal("0"),
        pct_recuperacion=Decimal("0"),
        pct_default=Decimal("0"),
        pct_provision=Decimal("0"),
        overrides_mora=None,
        overrides_default=None,
        caja_inicial=Decimal("50000"),
        caja_minima=Decimal("10000"),
    )
    base.update(over)
    return ParametrosMotor(**base)


def test_proyectar_ingreso_discriminado_y_etiquetas():
    r = proyectar(_params_simple())
    assert [m.mes for m in r.meses] == ["2026-07", "2026-08", "2026-09", "2026-10"]
    for m in r.meses:
        # las 2 vías se muestran SEPARADAS y suman el bruto (requisito CEO)
        assert m.ingreso_bruto == m.recaudo_credito + m.cuotas_iniciales
        assert m.cuotas_iniciales == Decimal("2000.00")  # 2 motos × 1000


def test_proyectar_caja_acumulada_primer_mes_fijo():
    r = proyectar(_params_simple())
    # el primer mes la caja es fija (= caja inicial); el flujo de ese mes no la mueve
    assert r.meses[0].caja == Decimal("50000.00")
    # desde el 2º mes: caja[m] = caja[m-1] + flujo[m]
    for i in range(1, len(r.meses)):
        assert r.meses[i].caja == r.meses[i - 1].caja + r.meses[i].flujo


def test_proyectar_kpis_piso_y_mes_mas_ajustado():
    r = proyectar(_params_simple())
    cajas = [m.caja for m in r.meses]
    assert r.piso_caja == min(cajas)
    idx = cajas.index(min(cajas))
    assert r.mes_mas_ajustado == r.meses[idx].mes
    assert r.meses_bajo_minimo == sum(1 for c in cajas if c < Decimal("10000"))
    assert r.caja_final == r.meses[-1].caja


def test_proyectar_flujo_es_neto_menos_egresos():
    r = proyectar(_params_simple())
    for m in r.meses:
        # flujo = neto + egresos (egresos vienen como valores negativos)
        assert m.flujo == m.neto + m.egresos


def test_presets_escenario_y_efecto_en_caja():
    # el escenario pesimista (más mora, menos recuperación) deja MENOS caja final.
    assert PRESETS_ESCENARIO["base"]["pct_mora"] == Decimal("0.03")
    assert PRESETS_ESCENARIO["pesimista"]["pct_mora"] == Decimal("0.06")
    pes = PRESETS_ESCENARIO["pesimista"]
    opt = PRESETS_ESCENARIO["optimista"]
    r_pes = proyectar(_params_simple(**pes, pct_default=Decimal("0.03")))
    r_opt = proyectar(_params_simple(**opt, pct_default=Decimal("0.03")))
    assert r_pes.caja_final < r_opt.caja_final
```

## 2. C4 — Ajuste diario de caja (CR-S6) — diff real

Commit `670ba4e feat(caja): C4 ajuste diario de caja — PATCH /meses/{mes}/saldos (CR-S6) (#27)`.

### Diff resumen

`git show --stat --format="" 670ba4e` (archivos):

```
 backend/app/api/v1/__init__.py                     |   2 +
 backend/app/audit/events.py                        |  13 +-
 backend/app/auth/permissions.py                    |   2 +
 backend/app/caja/__init__.py                       |   0
 backend/app/caja/router.py                         |  86 +++++
 backend/app/caja/service.py                        | 198 +++++++++++
 backend/tests/test_audit_events.py                 |  12 +-
 backend/tests/test_caja_saldos_guards.py           | 239 ++++++++++++++
 backend/tests/test_caja_saldos_realmongo.py        | 367 +++++++++++++++++++++
 backend/tests/test_rbac_permissions.py             |   2 +
 docs/COMPAS_Control_Desarrollo.xlsx                | Bin 27297 -> 27474 bytes
 .../auditorias/PLAN-I/RESPUESTA.md                 |  51 +++
 .../auditorias/PR1-I/EVIDENCIA.md                  | 197 +++++++++++
 .../auditorias/PR1-I/SOLICITUD.md                  |  58 ++++
 14 files changed, 1218 insertions(+), 9 deletions(-)
```

### backend/app/caja/service.py (íntegro)

```python
# backend/app/caja/service.py
"""C4 — reporte diario de saldos por banco (CR-S6, GO Kimi PLAN-I 9.3).

MARCADO PARA AUDITORÍA KIMI (B-1 atomicidad posicional + D2 guardas de fecha +
saga O1 + regla 2/regla 1).

El norte del producto define DOS entradas diarias: los movimientos del banco (C2/C3)
y **el valor de la caja disponible** — este servicio es el segundo. `reportar_saldos`
hace UPSERT del saldo reportado por banco sobre `mc.saldos_banco` (la estructura que
la conciliación §M-3 y el cierre §M-2 ya consumen: cero cambios en superficie
crítica) y devuelve la conciliación al instante (D4, "que la información siempre
cuadre").

- **B-1 (Kimi):** el upsert es un update ATÓMICO POSICIONAL por banco
  (`saldos_banco.$` para existente, `$push` con filtro `$ne` para nuevo), NO un
  read-modify-write de la lista entera — dos reportes concurrentes sobre bancos
  distintos no se pisan (lost update imposible).
- **D2:** `fecha_reporte` en `YYYY-MM-DD`, dentro de `[mc.mes, hoy(Bogotá)]` y
  **sin retroceso por banco** (retrasarla re-incluiría movimientos viejos como
  "posteriores" en `calculado(b)` sin rastro — fail-loud, regla 7).
- **D3:** solo meses `en_ejecucion` (el reporte es del mes OPERANDO; regla 4 congela
  los cerrados; los futuros reciben su saldo por apertura/arrastre F-14).
- **O1:** un evento `saldo_banco.reportado` por banco (metadata con valores y fechas
  anterior→nuevo). Fail-closed: write→emit por banco; si el emit cae, se restaura el
  estado previo de ESE banco (posicional o `$pull` si era nuevo) y propaga."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from bson import Decimal128

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cierre.service import conciliacion
from app.core.money import money_str
from app.core.time import today_bogota
from app.domain.bancos import Banco
from app.domain.mes_control import EstadoMes, MesControl, SaldoBanco

_FECHA_LEN = 10  # 'YYYY-MM-DD'
_MAX_REINTENTOS = 3  # contención posicional↔push (carrera del banco nuevo)


class CajaError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


@dataclass(frozen=True)
class ReporteBanco:
    """Un reporte de saldo para un banco (el router ya validó banco y Decimal)."""

    banco: Banco
    saldo: Decimal
    fecha_reporte: str


def _valida_fecha_formato(v: str) -> None:
    if len(v) != _FECHA_LEN:
        raise CajaError(f"fecha_reporte debe ser 'YYYY-MM-DD': {v}", 422)
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError as e:
        raise CajaError(f"fecha_reporte inválida: {v}", 422) from e


async def _upsert_saldo(col, mes: str, r: ReporteBanco) -> None:
    """Update atómico posicional por banco (B-1): sin read-modify-write de la lista."""
    dec = Decimal128(r.saldo)
    for _ in range(_MAX_REINTENTOS):
        res = await col.update_one(
            {"mes": mes, "saldos_banco.banco": r.banco.value},
            {
                "$set": {
                    "saldos_banco.$.saldo": dec,
                    "saldos_banco.$.fecha_reporte": r.fecha_reporte,
                }
            },
        )
        if res.matched_count == 1:
            return
        # el banco no está aún → push SOLO si sigue ausente (filtro $ne)
        res2 = await col.update_one(
            {"mes": mes, "saldos_banco.banco": {"$ne": r.banco.value}},
            {
                "$push": {
                    "saldos_banco": {
                        "banco": r.banco.value,
                        "saldo": dec,
                        "fecha_reporte": r.fecha_reporte,
                    }
                }
            },
        )
        if res2.matched_count == 1:
            return
        # matched_count==0: el banco apareció concurrentemente → reintentar posicional
    raise CajaError(
        "no se pudo aplicar el reporte de saldo (contención); reintentar", 409
    )


async def _restaurar(col, mes: str, banco: Banco, previo: SaldoBanco | None) -> None:
    """Compensación O1 POR BANCO (B-1): restaura el saldo previo o retira el nuevo."""
    if previo is None:
        await col.update_one(
            {"mes": mes}, {"$pull": {"saldos_banco": {"banco": banco.value}}}
        )
    else:
        await col.update_one(
            {"mes": mes, "saldos_banco.banco": banco.value},
            {
                "$set": {
                    "saldos_banco.$.saldo": Decimal128(previo.saldo),
                    "saldos_banco.$.fecha_reporte": previo.fecha_reporte,
                }
            },
        )


async def reportar_saldos(
    *, mes: str, reportes: list[ReporteBanco], usuario_id: str
) -> dict:
    mc = await MesControl.find_one(MesControl.mes == mes)
    if mc is None:
        raise CajaError(f"el mes {mes[:7]} no existe", 404)
    if mc.estado is not EstadoMes.EN_EJECUCION:  # D3
        raise CajaError(
            f"solo se reportan saldos de un mes en ejecución "
            f"(está en '{mc.estado.value}')",
            409,
        )

    vigentes = {sb.banco: sb for sb in mc.saldos_banco}
    hoy = today_bogota().isoformat()
    # D2: validar TODO antes de escribir (todo-o-nada en validación).
    for r in reportes:
        _valida_fecha_formato(r.fecha_reporte)
        if r.fecha_reporte < mc.mes:
            raise CajaError(
                f"fecha_reporte {r.fecha_reporte} es anterior al mes {mes[:7]} "
                "(contaría todo el mes como posterior)",
                422,
            )
        if r.fecha_reporte > hoy:
            raise CajaError(
                f"fecha_reporte {r.fecha_reporte} está en el futuro (hoy {hoy})", 422
            )
        prev = vigentes.get(r.banco)
        if prev is not None and r.fecha_reporte < prev.fecha_reporte:
            raise CajaError(
                f"no-retroceso: {r.banco.value} ya reportó {prev.fecha_reporte}; "
                f"{r.fecha_reporte} es anterior (regla 7)",
                422,
            )

    col = MesControl.get_pymongo_collection()
    # write→emit POR BANCO: cada banco queda con su escritura Y su evento consistentes;
    # si el emit de un banco cae, se restaura ESE banco (los previos quedan íntegros).
    for r in reportes:
        prev = vigentes.get(r.banco)
        await _upsert_saldo(col, mc.mes, r)
        try:
            await emit_audit(
                AuditEvento.saldo_banco_reportado,
                entidad="mes",
                entidad_id=str(mc.id),
                actor_id=usuario_id,
                metadata={
                    "mes": mes[:7],
                    "banco": r.banco.value,
                    "saldo_anterior": money_str(prev.saldo) if prev else None,
                    "saldo_nuevo": money_str(r.saldo),
                    "fecha_reporte_anterior": prev.fecha_reporte if prev else None,
                    "fecha_reporte_nueva": r.fecha_reporte,
                },
            )
        except Exception:
            await _restaurar(col, mc.mes, r.banco, prev)
            raise

    mc = await MesControl.get(mc.id)
    return {
        "mes": mes[:7],
        "saldos_banco": [
            {
                "banco": sb.banco.value,
                "saldo": money_str(sb.saldo),
                "fecha_reporte": sb.fecha_reporte,
            }
            for sb in mc.saldos_banco
        ],
        # D4: la conciliación al instante, misma función que el GET (misma verdad).
        "conciliacion": await conciliacion(mes),
    }
```

> [nota: C4 NO introdujo ningún archivo de dominio nuevo. El modelo de saldos vive
> en `backend/app/domain/mes_control.py` (`MesControl`, `SaldoBanco`, `EstadoMes`),
> que ya existía y NO fue tocado por el commit `670ba4e` — no aparece en el diffstat.
> El servicio hace UPSERT sobre `mc.saldos_banco` sin cambiar ese esquema.]

### Tests (nombres)

`grep -n "def test_" backend/tests/test_caja_saldos_guards.py backend/tests/test_caja_saldos_realmongo.py`:

```
backend/tests/test_caja_saldos_guards.py:89:async def test_consulta_403(api):
backend/tests/test_caja_saldos_guards.py:96:async def test_directivo_403(api):
backend/tests/test_caja_saldos_guards.py:106:async def test_mes_inexistente_404(api):
backend/tests/test_caja_saldos_guards.py:112:async def test_estado_no_en_ejecucion_409(api):
backend/tests/test_caja_saldos_guards.py:125:async def test_banco_desconocido_422(api):
backend/tests/test_caja_saldos_guards.py:134:async def test_banco_manual_422(api):
backend/tests/test_caja_saldos_guards.py:144:async def test_saldo_no_decimal_422(api):
backend/tests/test_caja_saldos_guards.py:153:async def test_saldo_como_numero_422(api):
backend/tests/test_caja_saldos_guards.py:169:async def test_banco_repetido_en_body_422(api):
backend/tests/test_caja_saldos_guards.py:186:async def test_body_vacio_422(api):
backend/tests/test_caja_saldos_guards.py:196:async def test_fecha_antes_del_dia1_422(api):
backend/tests/test_caja_saldos_guards.py:206:async def test_fecha_futura_422(api):
backend/tests/test_caja_saldos_guards.py:216:async def test_fecha_mal_formada_422(api):
backend/tests/test_caja_saldos_guards.py:225:async def test_no_retroceso_por_banco_422(api):
backend/tests/test_caja_saldos_realmongo.py:102:    async def test_agrega_banco_nuevo(self, entorno):
backend/tests/test_caja_saldos_realmongo.py:115:    async def test_reemplaza_saldo_y_fecha_del_banco(self, entorno):
backend/tests/test_caja_saldos_realmongo.py:136:    async def test_correccion_mismo_dia_ok(self, entorno):
backend/tests/test_caja_saldos_realmongo.py:156:    async def test_no_toca_los_otros_bancos(self, entorno):
backend/tests/test_caja_saldos_realmongo.py:173:    async def test_dia1_ok(self, entorno):
backend/tests/test_caja_saldos_realmongo.py:186:    async def test_respuesta_trae_conciliacion(self, entorno):
backend/tests/test_caja_saldos_realmongo.py:216:    async def test_un_evento_por_banco_con_metadata(self, entorno):
backend/tests/test_caja_saldos_realmongo.py:262:    async def test_o1_emit_falla_restaura(self, entorno, monkeypatch):
backend/tests/test_caja_saldos_realmongo.py:292:    async def test_o1_banco_nuevo_se_retira_al_fallar(self, entorno, monkeypatch):
backend/tests/test_caja_saldos_realmongo.py:310:    async def test_concurrencia_bancos_distintos_no_se_pisan(self, entorno):
backend/tests/test_caja_saldos_realmongo.py:337:    async def test_reintento_mismo_body_converge(self, entorno):
backend/tests/test_caja_saldos_realmongo.py:362:    async def test_admin_ok(self, entorno):
```

## 3. C9 — Pagos de la semana (CR-S7) — diff real

Commit `be9512b feat(pagos): C9/S5-01 Pagos de la semana — PagoPlaneado + veredicto (CR-S7) (#29)`.

### Diff resumen

`git show --stat --format="" be9512b` (archivos):

```
 backend/app/api/v1/__init__.py                     |   2 +
 backend/app/audit/events.py                        |  14 +-
 backend/app/auth/permissions.py                    |   2 +
 backend/app/domain/__init__.py                     |   3 +
 backend/app/domain/pago_planeado.py                |  84 +++++
 backend/app/pagos/__init__.py                      |   0
 backend/app/pagos/router.py                        | 177 +++++++++++
 backend/app/pagos/service.py                       | 351 +++++++++++++++++++++
 backend/tests/test_audit_events.py                 |  12 +-
 backend/tests/test_db.py                           |   2 +-
 backend/tests/test_pagos_marcar_realmongo.py       | 171 ++++++++++
 backend/tests/test_pagos_semana.py                 | 298 +++++++++++++++++
 backend/tests/test_rbac_permissions.py             |   2 +
 docs/COMPAS_Control_Desarrollo.xlsx                | Bin 28081 -> 28222 bytes
 .../auditorias/PR1-I/EVIDENCIA.md                  | 143 +++++++++
 .../auditorias/PR1-I/SOLICITUD.md                  |  59 ++++
 16 files changed, 1312 insertions(+), 8 deletions(-)
```

### backend/app/domain/pago_planeado.py (íntegro)

```python
# backend/app/domain/pago_planeado.py
"""PagoPlaneado (C9/S5-01, CR-S7): una INTENCIÓN de pago programado.

MARCADO PARA AUDITORÍA KIMI (D1 coherencia de tipo + regla 1/2/4).

NO es un movimiento bancario (eso es Transaccion §1.5): es lo que el CEO planea
pagar, para responder "¿alcanza la caja para los pagos de esta semana?" (hoja
'Pagos semana' del Excel). Siempre EGRESO (un pago es salida de caja; los ingresos
esperados viven en `MesControl.ingresos_esperados_semana`). `acreedor`/`concepto`
son dato OPERATIVO que digita el usuario (persistente en Mongo, NO semilla, NO en
repo). Al `marcar-pagado` se enlaza a la Transaccion real que lo saldó
(`pagado_tx_id`)."""

import re
from datetime import datetime
from enum import StrEnum

from beanie import Document, PydanticObjectId
from pydantic import ConfigDict, Field, field_validator
from pymongo import IndexModel

from app.core.money import Money

PAGOS_PLANEADOS_COLLECTION = "pagos_planeados"

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class EstadoPago(StrEnum):
    PENDIENTE = "pendiente"
    PAGADO = "pagado"
    CANCELADO = "cancelado"


class PagoPlaneado(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    concepto: str = Field(max_length=300)
    acreedor: str = Field(max_length=200)
    monto: Money  # > 0
    fecha_programada: str  # 'YYYY-MM-DD'
    rubro_id: PydanticObjectId  # rubro EGRESO activo (D1)
    mes_id: PydanticObjectId
    estado: EstadoPago = EstadoPago.PENDIENTE
    pagado_tx_id: PydanticObjectId | None = None  # Transaccion que lo saldó (D5)
    creado_por: str | None = None
    creado_at: datetime | None = None

    class Settings:
        name = PAGOS_PLANEADOS_COLLECTION
        indexes = [
            IndexModel([("mes_id", 1), ("fecha_programada", 1)], name="por_mes_fecha"),
            IndexModel([("estado", 1)], name="por_estado"),
        ]

    @field_validator("fecha_programada")
    @classmethod
    def _fecha_str(cls, v: object) -> str:
        if not isinstance(v, str) or not _FECHA.match(v):
            raise ValueError("fecha_programada debe ser string 'YYYY-MM-DD'")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"fecha_programada inválida: {v}") from e
        return v

    @field_validator("monto")
    @classmethod
    def _monto_positivo(cls, v):
        if v <= 0:
            raise ValueError("monto debe ser > 0")
        return v

    @field_validator("estado", mode="before")
    @classmethod
    def _cast_estado(cls, v: object) -> object:
        return v if isinstance(v, EstadoPago) else EstadoPago(v)

    @field_validator("creado_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("datetime debe ser UTC-aware (regla 2)")
        return v
```

### backend/app/pagos/service.py (íntegro)

```python
# backend/app/pagos/service.py
"""C9/S5-01 — Pagos de la semana (CR-S7, GO CEO 2026-07-23; Kimi retro 25-jul).

MARCADO PARA AUDITORÍA KIMI (D1 coherencia de tipo + regla 4 + regla 8 marcar-pagado
+ saga O1 + D4 reuso de _caja_libro).

- **CRUD de PagoPlaneado:** crear/editar/cancelar/listar. Cada mutación valida el mes
  (no cerrado, regla 4) y el rubro destino (EGRESO activo, D1). Auditoría fail-closed
  O1 (estándar C1/B-5): si el emit falla, compensa y propaga.
- **marcar-pagado (D5):** enlaza el pago a una Transaccion EXISTENTE (egreso, mismo
  mes, no cerrado) en TRANSACCIÓN MULTI-DOC (regla 8): pago→pagado + pagado_tx_id y
  tx.pago_planeado_id. La tx solo GANA el FK (inmutable §2.2). El matching automático
  queda fuera (manual explícito).
- **veredicto (D4):** GET pagos-semana reusa `_caja_libro` (la MISMA caja de la Vista
  Control) — una sola verdad de "caja disponible". caja_proyectada = caja_hoy −
  Σ pagos de [hoy, hoy+7d]. Vencidos (fecha < hoy) van aparte (D3, fail-loud)."""

from datetime import timedelta
from decimal import Decimal

from beanie import PydanticObjectId

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cierre.service import _caja_libro, _rubro_ajuste
from app.core.money import money_str
from app.core.time import now_utc, today_bogota
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.pago_planeado import EstadoPago, PagoPlaneado
from app.domain.rubro import Rubro, TipoFlujo
from app.domain.transaccion import Transaccion

_VENTANA_DIAS = 7  # D2: "la semana" = 7 días naturales rodantes desde hoy


class PagosError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


async def _mes(mes: str) -> MesControl:
    mc = await MesControl.find_one(MesControl.mes == mes)
    if mc is None:
        raise PagosError(f"el mes {mes[:7]} no existe", 404)
    return mc


async def _rubro_egreso_activo(rubro_id: str) -> Rubro:
    """D1: el destino debe ser un rubro EGRESO activo (un pago no calza en ingreso)."""
    try:
        oid = PydanticObjectId(rubro_id)
    except Exception as e:
        raise PagosError(f"rubro_id inválido: {rubro_id}", 422) from e
    r = await Rubro.get(oid)
    if r is None:
        raise PagosError("el rubro destino no existe", 404)
    if not r.activo:
        raise PagosError(f"el rubro '{r.nombre}' está inactivo", 422)
    if r.tipo_flujo is not TipoFlujo.EGRESO:
        raise PagosError(
            f"el rubro '{r.nombre}' es de ingreso; un pago es egreso (D1)", 422
        )
    return r


async def crear_pago(
    *,
    mes: str,
    concepto: str,
    acreedor: str,
    monto: Decimal,
    fecha_programada: str,
    rubro_id: str,
    usuario_id: str,
) -> PagoPlaneado:
    mc = await _mes(mes)
    if mc.estado is EstadoMes.CERRADO:  # regla 4
        raise PagosError(f"el mes {mes[:7]} está cerrado y es inmutable", 409)
    await _rubro_egreso_activo(rubro_id)
    if fecha_programada < mc.mes:
        raise PagosError(
            f"fecha_programada {fecha_programada} es anterior al mes {mes[:7]}", 422
        )
    pago = PagoPlaneado(
        concepto=concepto,
        acreedor=acreedor,
        monto=monto,
        fecha_programada=fecha_programada,
        rubro_id=PydanticObjectId(rubro_id),
        mes_id=mc.id,
        creado_por=usuario_id,
        creado_at=now_utc(),
    )
    await pago.insert()
    try:
        await emit_audit(
            AuditEvento.pago_planeado_creado,
            entidad="pago_planeado",
            entidad_id=str(pago.id),
            actor_id=usuario_id,
            metadata={
                "mes": mes[:7],
                "acreedor": acreedor,
                "monto": money_str(monto),
                "fecha_programada": fecha_programada,
                "rubro_id": rubro_id,
            },
        )
    except Exception:  # O1: sin auditoría no hay operación → compensar y propagar
        await pago.delete()
        raise
    return pago


async def _pago(pago_id: str) -> PagoPlaneado:
    try:
        oid = PydanticObjectId(pago_id)
    except Exception as e:
        raise PagosError(f"pago_id inválido: {pago_id}", 422) from e
    p = await PagoPlaneado.get(oid)
    if p is None:
        raise PagosError("el pago planeado no existe", 404)
    return p


async def _asegura_editable(p: PagoPlaneado) -> MesControl:
    if p.estado is not EstadoPago.PENDIENTE:
        raise PagosError(
            f"el pago está '{p.estado.value}'; solo se edita un pago pendiente", 409
        )
    mc = await MesControl.get(p.mes_id)
    if mc is not None and mc.estado is EstadoMes.CERRADO:  # regla 4
        raise PagosError("el mes del pago está cerrado y es inmutable", 409)
    return mc


async def editar_pago(
    *,
    pago_id: str,
    usuario_id: str,
    concepto: str | None = None,
    acreedor: str | None = None,
    monto: Decimal | None = None,
    fecha_programada: str | None = None,
    rubro_id: str | None = None,
) -> PagoPlaneado:
    p = await _pago(pago_id)
    mc = await _asegura_editable(p)
    prev = {
        "concepto": p.concepto,
        "acreedor": p.acreedor,
        "monto": money_str(p.monto),
        "fecha_programada": p.fecha_programada,
        "rubro_id": str(p.rubro_id),
    }
    if rubro_id is not None:
        await _rubro_egreso_activo(rubro_id)
        p.rubro_id = PydanticObjectId(rubro_id)
    if concepto is not None:
        p.concepto = concepto
    if acreedor is not None:
        p.acreedor = acreedor
    if monto is not None:
        if monto <= 0:
            raise PagosError("monto debe ser > 0", 422)
        p.monto = monto
    if fecha_programada is not None:
        if mc is not None and fecha_programada < mc.mes:
            raise PagosError(
                f"fecha_programada {fecha_programada} es anterior al mes", 422
            )
        p.fecha_programada = fecha_programada
    await p.save()
    try:
        await emit_audit(
            AuditEvento.pago_planeado_editado,
            entidad="pago_planeado",
            entidad_id=str(p.id),
            actor_id=usuario_id,
            metadata={"anterior": prev, "nuevo": _snapshot(p)},
        )
    except Exception:
        # O1: revertir los campos a su estado previo y propagar.
        p.concepto = prev["concepto"]
        p.acreedor = prev["acreedor"]
        p.monto = Decimal(prev["monto"])
        p.fecha_programada = prev["fecha_programada"]
        p.rubro_id = PydanticObjectId(prev["rubro_id"])
        await p.save()
        raise
    return p


async def cancelar_pago(*, pago_id: str, usuario_id: str) -> PagoPlaneado:
    p = await _pago(pago_id)
    await _asegura_editable(p)  # solo un pendiente en mes no cerrado se cancela
    p.estado = EstadoPago.CANCELADO
    await p.save()
    try:
        await emit_audit(
            AuditEvento.pago_planeado_cancelado,
            entidad="pago_planeado",
            entidad_id=str(p.id),
            actor_id=usuario_id,
            metadata={"acreedor": p.acreedor, "monto": money_str(p.monto)},
        )
    except Exception:
        p.estado = EstadoPago.PENDIENTE
        await p.save()
        raise
    return p


async def marcar_pagado(
    *, pago_id: str, transaccion_id: str, usuario_id: str
) -> PagoPlaneado:
    """D5: enlaza el pago a una Transaccion existente. Multi-doc (regla 8) + O1."""
    p = await _pago(pago_id)
    if p.estado is not EstadoPago.PENDIENTE:
        raise PagosError(
            f"el pago está '{p.estado.value}'; solo se marca pagado un pendiente", 409
        )
    try:
        tx_oid = PydanticObjectId(transaccion_id)
    except Exception as e:
        raise PagosError(f"transaccion_id inválido: {transaccion_id}", 422) from e
    tx = await Transaccion.get(tx_oid)
    if tx is None:
        raise PagosError("la transacción no existe", 404)
    if tx.tipo_flujo is not TipoFlujo.EGRESO:
        raise PagosError("la transacción debe ser un egreso", 422)
    if tx.mes_id != p.mes_id:
        raise PagosError("la transacción es de otro mes que el pago", 422)
    mc = await MesControl.get(p.mes_id)
    if mc is not None and mc.estado is EstadoMes.CERRADO:  # regla 4
        raise PagosError("el mes está cerrado y es inmutable", 409)

    client = MesControl.get_pymongo_collection().database.client

    async def _enlazar(session):
        # revalidar dentro de la sesión (TOCTOU, patrón S4-06)
        p_fresco = await PagoPlaneado.find_one(PagoPlaneado.id == p.id, session=session)
        if p_fresco is None or p_fresco.estado is not EstadoPago.PENDIENTE:
            raise PagosError("el pago cambió de estado (concurrencia); reintentar", 409)
        p.estado = EstadoPago.PAGADO
        p.pagado_tx_id = tx.id
        await p.save(session=session)
        tx.pago_planeado_id = p.id
        await tx.save(session=session)

    async with await client.start_session() as session:
        await session.with_transaction(_enlazar)

    try:
        await emit_audit(
            AuditEvento.pago_planeado_editado,
            entidad="pago_planeado",
            entidad_id=str(p.id),
            actor_id=usuario_id,
            metadata={
                "estado": {"anterior": "pendiente", "nuevo": "pagado"},
                "pagado_tx_id": str(tx.id),
            },
        )
    except Exception:

        async def _revertir(session):
            p.estado = EstadoPago.PENDIENTE
            p.pagado_tx_id = None
            await p.save(session=session)
            tx.pago_planeado_id = None
            await tx.save(session=session)

        async with await client.start_session() as session:
            await session.with_transaction(_revertir)
        raise
    return p


def _snapshot(p: PagoPlaneado) -> dict:
    return {
        "concepto": p.concepto,
        "acreedor": p.acreedor,
        "monto": money_str(p.monto),
        "fecha_programada": p.fecha_programada,
        "rubro_id": str(p.rubro_id),
    }


async def listar_pagos(
    *, mes: str, estado: EstadoPago | None = None
) -> list[PagoPlaneado]:
    mc = await _mes(mes)
    q = PagoPlaneado.find(PagoPlaneado.mes_id == mc.id)
    filas = await q.to_list()
    if estado is not None:
        filas = [p for p in filas if p.estado is estado]
    return sorted(filas, key=lambda p: (p.fecha_programada, str(p.id)))


async def pagos_semana(mes: str) -> dict:
    """D4: veredicto '¿alcanza la caja?'. Compute-only (sin estado, sin evento)."""
    mc = await _mes(mes)
    rubro_aj = await _rubro_ajuste()  # fail-loud si no está sembrado (como Control)
    caja_hoy = await _caja_libro(mc.id, rubro_aj.id, mc.saldo_inicial_caja)

    hoy = today_bogota()
    hoy_s = hoy.isoformat()
    fin_s = (hoy + timedelta(days=_VENTANA_DIAS)).isoformat()

    pendientes = [
        p
        for p in await PagoPlaneado.find(PagoPlaneado.mes_id == mc.id).to_list()
        if p.estado is EstadoPago.PENDIENTE
    ]
    semana = sorted(
        (p for p in pendientes if hoy_s <= p.fecha_programada <= fin_s),
        key=lambda p: (p.fecha_programada, str(p.id)),
    )
    vencidos = sorted(  # D3: pendientes con fecha pasada (fail-loud, aparte)
        (p for p in pendientes if p.fecha_programada < hoy_s),
        key=lambda p: (p.fecha_programada, str(p.id)),
    )
    total_semana = sum((p.monto for p in semana), Decimal("0"))
    caja_proyectada = caja_hoy - total_semana

    return {
        "mes": mes[:7],
        "caja_hoy": money_str(caja_hoy),
        "total_semana": money_str(total_semana),
        "caja_proyectada": money_str(caja_proyectada),
        "veredicto": "alcanza" if caja_proyectada >= 0 else "no_alcanza",
        "ventana": {"desde": hoy_s, "hasta": fin_s},
        "pagos": [_serializar(p) for p in semana],
        "vencidos": [_serializar(p) for p in vencidos],
    }


def _serializar(p: PagoPlaneado) -> dict:
    return {
        "id": str(p.id),
        "concepto": p.concepto,
        "acreedor": p.acreedor,
        "monto": money_str(p.monto),
        "fecha_programada": p.fecha_programada,
        "rubro_id": str(p.rubro_id),
        "estado": p.estado.value,
        "pagado_tx_id": str(p.pagado_tx_id) if p.pagado_tx_id else None,
    }
```

### Tests (nombres)

`grep -n "def test_" backend/tests/test_pagos_semana.py backend/tests/test_pagos_marcar_realmongo.py`:

```
backend/tests/test_pagos_semana.py:118:async def test_crear_ok(api):
backend/tests/test_pagos_semana.py:130:async def test_crear_consulta_403(api):
backend/tests/test_pagos_semana.py:140:async def test_crear_mes_inexistente_404(api):
backend/tests/test_pagos_semana.py:149:async def test_crear_mes_cerrado_409(api):
backend/tests/test_pagos_semana.py:159:async def test_crear_rubro_ingreso_422(api):
backend/tests/test_pagos_semana.py:170:async def test_crear_rubro_inactivo_422(api):
backend/tests/test_pagos_semana.py:180:async def test_crear_monto_cero_422(api):
backend/tests/test_pagos_semana.py:192:async def test_crear_monto_numero_422(api):
backend/tests/test_pagos_semana.py:217:async def test_editar_monto_ok(api):
backend/tests/test_pagos_semana.py:229:async def test_cancelar_ok_y_luego_editar_409(api):
backend/tests/test_pagos_semana.py:247:async def test_veredicto_alcanza(api):
backend/tests/test_pagos_semana.py:262:async def test_veredicto_no_alcanza(api):
backend/tests/test_pagos_semana.py:273:async def test_veredicto_excluye_fuera_de_ventana_y_lista_vencidos(api):
backend/tests/test_pagos_semana.py:289:async def test_marcar_pagado_pago_inexistente_404(api):
backend/tests/test_pagos_marcar_realmongo.py:115:    async def test_marcar_pagado_enlaza_ambos_docs(self, entorno):
backend/tests/test_pagos_marcar_realmongo.py:132:    async def test_marcar_pagado_o1_compensa(self, entorno, monkeypatch):
backend/tests/test_pagos_marcar_realmongo.py:159:    async def test_marcar_pagado_mes_cerrado_409(self, entorno):
```

## 4. COCK-00 — Fundación plan de cuentas — diff real

Commits `c2c0faf feat(rubros): fundación plan de cuentas ARQUITECTURA_PRESUPUESTAL (armazón, sin datos) (#31)`
y `737bcb0 feat(rubros): código + Fijo/Variable en API y pantalla Categorías (#32)`.

### backend/app/domain/rubro.py (íntegro)

```python
# backend/app/domain/rubro.py
"""Rubro (Spec §1.2) + semilla real de la taxonomía del negocio.

La semilla NO es de juguete: es la taxonomía REAL de `docs/modelo/MODELO.md`
(destilada de la hoja 'Base real egresos' de `Flujo de pagos deudas.xlsx`) — re-seed
C1, GO Kimi PLAN-I 9.2. Son las 31 categorías reales de RODDOS en los 5 grupos + 3
rubros de sistema inmutables: 'Por clasificar' (Spec §1.2), 'Ajuste de conciliación'
(cierre de mes, Spec §2.2.6) y 'Recaudo' (tipo INGRESO, Kimi B-1/S0B-05: destino de
los abonos de cuotas, PRD M7). En total 34 rubros.

D3 (gate C1): las categorías viejas de la semilla anterior que ya existan en la BD
NO se tocan ($setOnInsert) ni se borran — el CEO las depura desde la app (C1). El
re-seed reporta las colisiones (B-4, ver `seed.py::seed_rubros_reporte`).
"""

from enum import StrEnum

from beanie import Document
from pydantic import ConfigDict, Field, field_validator
from pymongo import IndexModel

RUBROS_COLLECTION = "rubros"


class RubroGrupo(StrEnum):
    # Orden = jerarquía del plan de cuentas (ARQUITECTURA_PRESUPUESTAL.md):
    # 0000 ingresos, 1000 costo producto, 2000 operación, 3000 nómina,
    # 4000 deudas, 5000 otros. Ingresos PRIMERO (código 0000).
    INGRESOS_OPERATIVOS = "ingresos_operativos"
    COSTO_PRODUCTO = "costo_producto"
    OPERACION = "operacion"
    NOMINA = "nomina"
    DEUDAS_OBLIGACIONES = "deudas_obligaciones"
    OTROS = "otros"


class TipoFlujo(StrEnum):
    EGRESO = "egreso"
    INGRESO = "ingreso"


class TipoRubro(StrEnum):
    """Rigor del gasto (ARQUITECTURA_PRESUPUESTAL.md): Fijo = piso estructural
    (nómina, arriendos, deuda); Variable = discrecional/operativo. Los rubros de
    sistema pueden no tener tipo (None)."""

    FIJO = "fijo"
    VARIABLE = "variable"


class Rubro(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    grupo: RubroGrupo
    nombre: str = Field(max_length=80)
    tipo_flujo: TipoFlujo = TipoFlujo.EGRESO
    codigo: str | None = Field(default=None, max_length=8)  # jerárquico (p. ej. '2070')
    tipo: TipoRubro | None = None  # Fijo/Variable (None en sistema/no aplica)
    orden: int
    activo: bool = True
    es_sistema: bool = False

    class Settings:
        name = RUBROS_COLLECTION
        # Único por grupo (Spec §1.2). En Mongo real lanza DuplicateKeyError;
        # mongomock no lo exige → se prueba con @requires_real_mongo.
        indexes = [
            IndexModel(
                [("grupo", 1), ("nombre", 1)], name="grupo_nombre_unico", unique=True
            ),
            IndexModel([("orden", 1)], name="por_orden"),
        ]

    @field_validator("grupo", mode="before")
    @classmethod
    def _cast_grupo(cls, v: object) -> object:
        return v if isinstance(v, RubroGrupo) else RubroGrupo(v)

    @field_validator("tipo_flujo", mode="before")
    @classmethod
    def _cast_tipo(cls, v: object) -> object:
        return v if isinstance(v, TipoFlujo) else TipoFlujo(v)

    @field_validator("tipo", mode="before")
    @classmethod
    def _cast_tipo_rubro(cls, v: object) -> object:
        if v is None or isinstance(v, TipoRubro):
            return v
        return TipoRubro(v)


def _seed() -> list[dict]:
    """Plan de cuentas de ARQUITECTURA_PRESUPUESTAL.md (estructura del archivo de
    Arquitectura + taxonomía real de 'Base real egresos'/'Proyeccion ingresos').

    Cada fila trae `codigo` (jerárquico), `tipo` (Fijo/Variable) y `naturaleza`
    (tipo_flujo). `orden` sigue el código. Rubros de sistema (es_sistema=True):
    'Recaudo de cartera' (0110, destino INGRESO de la regla 'Abono' de C3),
    'Por clasificar' (5070) y 'Ajuste de conciliación' (cierre §2.2.6)."""
    F, V = TipoRubro.FIJO.value, TipoRubro.VARIABLE.value
    ING, EGR = TipoFlujo.INGRESO.value, TipoFlujo.EGRESO.value
    G = RubroGrupo
    # (grupo, [(codigo, nombre, tipo, naturaleza, es_sistema)])
    plan: list[tuple[RubroGrupo, list[tuple]]] = [
        (
            G.INGRESOS_OPERATIVOS,
            [
                ("0110", "Recaudo de cartera", V, ING, True),
                ("0120", "Cuotas iniciales", V, ING, False),
                ("0130", "RODANTE (crédito de repuestos)", V, ING, False),
                ("0140", "Otros ingresos", V, ING, False),
            ],
        ),
        (
            G.COSTO_PRODUCTO,
            [
                ("1010", "Producto", V, EGR, False),
                ("1020", "SOAT/Matrículas", V, EGR, False),
                ("1030", "Seguros (Hunter)", V, EGR, False),
            ],
        ),
        (
            G.OPERACION,
            [
                ("2010", "Arriendos", F, EGR, False),
                ("2020", "Tecnología y software", F, EGR, False),
                ("2030", "Mobiliario/planta/equipo", V, EGR, False),
                ("2040", "Servicios públicos y telecom", F, EGR, False),
                ("2050", "Mercado y aseo", V, EGR, False),
                ("2060", "Cafetería", V, EGR, False),
                ("2070", "Transporte/peajes/combustible/parqueo", V, EGR, False),
                ("2080", "Papelería", V, EGR, False),
                ("2090", "Marketing y publicidad", V, EGR, False),
                ("2100", "Gastos de representación", V, EGR, False),
                ("2110", "Viajes corporativos", V, EGR, False),
                ("2120", "Renting", F, EGR, False),
                ("2130", "Grúas y traslados", V, EGR, False),
                ("2140", "Freelance", V, EGR, False),
            ],
        ),
        (
            G.NOMINA,
            [
                ("3010", "Sueldos empleados", F, EGR, False),
                ("3020", "Sueldos directivos", F, EGR, False),
                ("3030", "Bonificaciones", V, EGR, False),
                ("3040", "Beneficios Heads", V, EGR, False),
                ("3050", "Dotación empleados", V, EGR, False),
                ("3060", "Planillas nuevas", V, EGR, False),
                ("3070", "Planillas anteriores", V, EGR, False),
            ],
        ),
        (
            G.DEUDAS_OBLIGACIONES,
            [
                ("4010", "Préstamos", F, EGR, False),
                ("4020", "Deudas tarjetas de crédito", F, EGR, False),
                ("4030", "Garantía cupo (Auteco)", F, EGR, False),
                ("4040", "Deudas impuestos", F, EGR, False),
                ("4050", "Deudas proveedores anteriores", F, EGR, False),
                ("4060", "Inventario Auteco (150 días)", V, EGR, False),
            ],
        ),
        (
            G.OTROS,
            [
                ("5010", "Otros gastos", V, EGR, False),
                ("5020", "Gastos notariales", V, EGR, False),
                ("5030", "Asuntos legales", F, EGR, False),
                ("5040", "Gastos bancarios", F, EGR, False),
                ("5050", "Gastos financieros", V, EGR, False),
                ("5060", "Impuestos", F, EGR, False),
                ("5070", "Por clasificar", V, EGR, True),
            ],
        ),
    ]
    filas: list[dict] = []
    orden = 0
    for grupo, rubros in plan:
        for codigo, nombre, tipo, naturaleza, sistema in rubros:
            orden += 1
            filas.append(
                {
                    "grupo": grupo.value,
                    "nombre": nombre,
                    "tipo_flujo": naturaleza,
                    "codigo": codigo,
                    "tipo": tipo,
                    "orden": orden,
                    "activo": True,
                    "es_sistema": sistema,
                }
            )
    # 'Ajuste de conciliación' (Spec §2.2.6): rubro de sistema del cierre; no está en
    # el plan de cuentas del negocio (sin código de gasto). Va al final.
    orden += 1
    filas.append(
        {
            "grupo": G.OTROS.value,
            "nombre": "Ajuste de conciliación",
            "tipo_flujo": EGR,
            "codigo": None,
            "tipo": None,
            "orden": orden,
            "activo": True,
            "es_sistema": True,
        }
    )
    return filas


SEMILLA_RUBROS: list[dict] = _seed()
```

### Diff API/servicio

`git show --stat --format="" 737bcb0` (archivos):

```
 backend/app/rubros/router.py               |  22 +++-
 backend/app/rubros/service.py              |  31 +++++-
 backend/tests/test_rubros_endpoints.py     |  46 ++++++++-
 frontend/src/lib/control.ts                |   6 +-
 frontend/src/lib/rubros.ts                 |  12 ++-
 frontend/src/pages/CategoriasPage.test.tsx |  20 ++--
 frontend/src/pages/CategoriasPage.tsx      | 157 +++++++++++++++++++++--------
 frontend/src/pages/ReglasPage.test.tsx     |  12 ++-
 8 files changed, 247 insertions(+), 59 deletions(-)
```

`git show 737bcb0 -- backend/app/rubros/service.py`:

```diff
diff --git a/backend/app/rubros/service.py b/backend/app/rubros/service.py
index 31dda03..f83736c 100644
--- a/backend/app/rubros/service.py
+++ b/backend/app/rubros/service.py
@@ -34,7 +34,7 @@ from pymongo.errors import DuplicateKeyError
 from app.audit.events import AuditEvento
 from app.audit.service import emit_audit
 from app.domain.presupuesto import PresupuestoLinea
-from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
+from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo, TipoRubro
 from app.domain.transaccion import Transaccion


@@ -88,8 +88,11 @@ async def crear_rubro(
     nombre: str,
     tipo_flujo: TipoFlujo,
     usuario_id: str,
+    codigo: str | None = None,
+    tipo: TipoRubro | None = None,
 ) -> Rubro:
-    """POST: crea con `orden` = máx(grupo)+1 y emite `rubro.creado` (fail-closed)."""
+    """POST: crea con `orden` = máx(grupo)+1 y emite `rubro.creado` (fail-closed).
+    `codigo` (jerárquico) y `tipo` (Fijo/Variable) son opcionales (ARQUITECTURA)."""
     if await Rubro.find_one(Rubro.grupo == grupo, Rubro.nombre == nombre) is not None:
         raise RubrosError(
             f"ya existe un rubro '{nombre}' en el grupo '{grupo.value}'", 409
@@ -99,6 +102,8 @@ async def crear_rubro(
         grupo=grupo,
         nombre=nombre,
         tipo_flujo=tipo_flujo,
+        codigo=codigo,
+        tipo=tipo,
         orden=(ultimo.orden if ultimo is not None else 0) + 1,
     )
     try:
@@ -119,6 +124,8 @@ async def crear_rubro(
                 "grupo": grupo.value,
                 "nombre": nombre,
                 "tipo_flujo": tipo_flujo.value,
+                "codigo": codigo,
+                "tipo": tipo.value if tipo is not None else None,
                 "orden": rubro.orden,
             },
         )
@@ -137,9 +144,12 @@ async def editar_rubro(
     orden: int | None = None,
     tipo_flujo: TipoFlujo | None = None,
     activo: bool | None = None,
+    codigo: str | None = None,
+    tipo: TipoRubro | None = None,
 ) -> Rubro:
-    """PATCH: edita nombre/orden/tipo_flujo y reactiva (B-3). Emite `rubro.editado`
-    con {campo: {anterior, nuevo}} (fail-closed B-5)."""
+    """PATCH: edita nombre/orden/tipo_flujo/codigo/tipo y reactiva (B-3). Emite
+    `rubro.editado` con {campo: {anterior, nuevo}} (fail-closed B-5). `codigo` y
+    `tipo` (Fijo/Variable) no afectan el cómputo → editables siempre."""
     rubro = await _obtener(rubro_id)
     if rubro.es_sistema:
         raise RubrosError(
@@ -149,6 +159,19 @@ async def editar_rubro(
     cambios: dict[str, dict] = {}
     previos: dict[str, object] = {}

+    if codigo is not None and codigo != rubro.codigo:
+        previos["codigo"] = rubro.codigo
+        cambios["codigo"] = {"anterior": rubro.codigo, "nuevo": codigo}
+        rubro.codigo = codigo
+
+    if tipo is not None and tipo is not rubro.tipo:
+        previos["tipo"] = rubro.tipo
+        cambios["tipo"] = {
+            "anterior": rubro.tipo.value if rubro.tipo is not None else None,
+            "nuevo": tipo.value,
+        }
+        rubro.tipo = tipo
+
     if activo is not None:
         if activo is False:
             raise RubrosError("la baja va por POST /rubros/{id}/desactivar (B-3)", 422)
```

### Tests (nombres)

`grep -n "def test_" backend/tests/test_domain_rubro.py backend/tests/test_rubros_endpoints.py`:

```
backend/tests/test_domain_rubro.py:27:def test_grupos_son_los_seis_del_plan_de_cuentas():
backend/tests/test_domain_rubro.py:35:def test_rubro_valido_con_codigo_y_tipo():
backend/tests/test_domain_rubro.py:51:def test_tipo_y_codigo_opcionales():
backend/tests/test_domain_rubro.py:57:def test_strict_rechaza_campo_extra():
backend/tests/test_domain_rubro.py:62:def test_nombre_max_80():
backend/tests/test_domain_rubro.py:70:def test_semilla_tiene_42_rubros():
backend/tests/test_domain_rubro.py:76:def test_semilla_reparto_por_grupo():
backend/tests/test_domain_rubro.py:90:def test_semilla_cubre_los_seis_grupos():
backend/tests/test_domain_rubro.py:94:def test_semilla_rubros_de_sistema():
backend/tests/test_domain_rubro.py:99:def test_semilla_ingresos_son_del_grupo_0000():
backend/tests/test_domain_rubro.py:110:def test_semilla_recaudo_de_cartera_es_sistema_e_ingreso():
backend/tests/test_domain_rubro.py:119:def test_semilla_codigos_unicos_donde_existen():
backend/tests/test_domain_rubro.py:125:def test_semilla_tipo_fijo_o_variable_en_los_reales():
backend/tests/test_domain_rubro.py:132:def test_semilla_nombres_unicos_por_grupo():
backend/tests/test_domain_rubro.py:140:def test_semilla_ordenes_unicos_y_consecutivos():
backend/tests/test_domain_rubro.py:145:def test_semilla_construye_modelos_validos():
backend/tests/test_domain_rubro.py:150:def test_semilla_arriendos_vive_en_operacion():
backend/tests/test_domain_rubro.py:159:def test_semilla_dotacion_vive_en_nomina():
backend/tests/test_domain_rubro.py:165:def test_semilla_incluye_rubros_nuevos_de_la_arquitectura():
backend/tests/test_rubros_endpoints.py:142:async def test_get_lista_ordenada(api):
backend/tests/test_rubros_endpoints.py:166:async def test_post_crea_con_codigo_y_tipo(api):
backend/tests/test_rubros_endpoints.py:187:async def test_patch_edita_tipo_fijo_variable(api):
backend/tests/test_rubros_endpoints.py:200:async def test_get_filtra_por_grupo_y_activo(api):
backend/tests/test_rubros_endpoints.py:214:async def test_get_grupo_invalido_422(api):
backend/tests/test_rubros_endpoints.py:230:async def test_get_200_los_cuatro_roles(api, email):
backend/tests/test_rubros_endpoints.py:239:async def test_post_crea_con_orden_max_grupo_mas_1_y_emite_creado(api):
backend/tests/test_rubros_endpoints.py:257:async def test_post_grupo_vacio_arranca_en_1(api):
backend/tests/test_rubros_endpoints.py:269:async def test_post_duplicado_409(api):
backend/tests/test_rubros_endpoints.py:280:async def test_post_mismo_nombre_en_otro_grupo_ok(api):
backend/tests/test_rubros_endpoints.py:292:async def test_post_grupo_invalido_422(api):
backend/tests/test_rubros_endpoints.py:306:async def test_patch_nombre_orden_emite_editado_con_cambios(api):
backend/tests/test_rubros_endpoints.py:327:async def test_patch_nombre_duplicado_409(api):
backend/tests/test_rubros_endpoints.py:337:async def test_patch_sin_cambios_422(api):
backend/tests/test_rubros_endpoints.py:350:async def test_patch_404_y_id_invalido_422(api):
backend/tests/test_rubros_endpoints.py:364:async def test_patch_tipo_flujo_con_transaccion_409(api):
backend/tests/test_rubros_endpoints.py:375:async def test_patch_tipo_flujo_con_linea_presupuesto_409(api):
backend/tests/test_rubros_endpoints.py:387:async def test_patch_tipo_flujo_sin_referencias_200(api):
backend/tests/test_rubros_endpoints.py:398:async def test_patch_nombre_editable_aun_con_referencias(api):
backend/tests/test_rubros_endpoints.py:414:async def test_patch_sistema_409(api, nombre):
backend/tests/test_rubros_endpoints.py:423:async def test_desactivar_sistema_409(api, nombre):
backend/tests/test_rubros_endpoints.py:435:async def test_desactivar_ok_emite_desactivado(api):
backend/tests/test_rubros_endpoints.py:447:async def test_desactivar_con_movimientos_200_historico_intacto(api):
backend/tests/test_rubros_endpoints.py:460:async def test_desactivar_ya_inactivo_409(api):
backend/tests/test_rubros_endpoints.py:469:async def test_reactivar_por_patch_activo_true_emite_editado(api):
backend/tests/test_rubros_endpoints.py:484:async def test_patch_activo_false_422_usa_desactivar(api):
backend/tests/test_rubros_endpoints.py:497:async def test_mutaciones_403_consulta_y_directivo(api, email):
backend/tests/test_rubros_endpoints.py:512:async def test_mutaciones_ok_financiero_y_admin(api, email):
backend/tests/test_rubros_endpoints.py:527:async def test_fail_closed_crear_compensa(api, monkeypatch):
backend/tests/test_rubros_endpoints.py:545:async def test_fail_closed_editar_compensa(api, monkeypatch):
backend/tests/test_rubros_endpoints.py:561:async def test_fail_closed_desactivar_compensa(api, monkeypatch):
```

## 5. Frontend cockpit — diffstat + muestras representativas

Las 40+ vistas del cockpit NO se pegan verbatim (sería ilegible). Aquí va el inventario
de archivos tocados + el sistema de diseño + la navegación única + una vista
representativa completa + el catálogo de componentes base.

### Inventario de archivos

Lista única de archivos `frontend/src/...` tocados en los commits
`a7b2101 b2fc416 f9307fa f66424d 9801fec ebb46c5 704607e 2f55aa6 6491131 41bde32`
(consolidada de sus `git show --stat`):

```
frontend/src/App.tsx
frontend/src/components/charts/CashCurve.test.tsx
frontend/src/components/charts/CashCurve.tsx
frontend/src/components/charts/ScenariosChart.tsx
frontend/src/components/layout/AppShell.tsx
frontend/src/components/layout/PageHeader.tsx
frontend/src/components/layout/Sidebar.test.tsx
frontend/src/components/layout/Sidebar.tsx
frontend/src/components/ui/alert-banner.test.tsx
frontend/src/components/ui/alert-banner.tsx
frontend/src/components/ui/button.tsx
frontend/src/components/ui/card.tsx
frontend/src/components/ui/kpi-tile.test.tsx
frontend/src/components/ui/kpi-tile.tsx
frontend/src/components/ui/scenario-chip.test.tsx
frontend/src/components/ui/scenario-chip.tsx
frontend/src/index.css
frontend/src/lib/modelosMoto.ts
frontend/src/lib/navegacion.ts
frontend/src/lib/parametros.ts
frontend/src/lib/proyeccion.ts
frontend/src/main.tsx
frontend/src/pages/CajaPage.tsx
frontend/src/pages/CargasPage.tsx
frontend/src/pages/CategoriasPage.tsx
frontend/src/pages/ControlPage.tsx
frontend/src/pages/DashboardsPage.test.tsx
frontend/src/pages/DashboardsPage.tsx
frontend/src/pages/DatosPage.test.tsx
frontend/src/pages/DatosPage.tsx
frontend/src/pages/EnConstruccion.tsx
frontend/src/pages/InicioPage.test.tsx
frontend/src/pages/InicioPage.tsx
frontend/src/pages/LoginPage.tsx
frontend/src/pages/MesesPage.tsx
frontend/src/pages/ProyeccionPage.test.tsx
frontend/src/pages/ProyeccionPage.tsx
frontend/src/pages/ReglasPage.tsx
frontend/src/pages/ReportesPage.test.tsx
frontend/src/pages/ReportesPage.tsx
frontend/src/pages/ScenariosPage.test.tsx
frontend/src/pages/ScenariosPage.tsx
```

### Sistema de diseño — tokens

Bloque `@theme` (tokens RODDOS) + `@media print` de `frontend/src/index.css` (íntegro —
el archivo entero son 76 líneas):

```css
@import "tailwindcss";

/* ── Identidad RODDOS — cockpit del Blueprint UX (decisión CEO) ──
   Fondo blanco; Cyber Cyan = acción/navegación; Growth Green = positivo;
   rojo = COLOR DE SISTEMA (solo perforación de caja / negativos), nunca decorativo.
   Tipografía: Montserrat (titulares + cifras, tabular-nums) sobre Raleway (cuerpo/UI).
   Tokens expuestos como variables Tailwind 4 (@theme) → clases utilitarias
   (bg-cyan, text-green, font-display, border-hairline, …). */
@theme {
  /* Marca */
  --color-cyan: #0fa9b8; /* Cyber Cyan — acción primaria + nav activa */
  --color-cyan-soft: #76e5ec;
  --color-cyan-tint: #ecfbfc; /* fondo tenue del ítem activo */
  --color-green: #12a312; /* Growth Green — positivo/éxito */
  --color-green-soft: #1dc91d;

  /* Sistema (semáforo) */
  --color-red: #e0524d; /* perforación de caja / negativo — reservado */
  --color-amber: #e8a83a; /* advertencia */

  /* Neutrales sobre blanco */
  --color-ink: #0f172a; /* texto principal (slate-900) */
  --color-ink-soft: #64748b; /* texto secundario (slate-500) */
  --color-ink-faint: #94a3b8; /* etiquetas/captions (slate-400) */
  --color-surface: #ffffff;
  --color-surface-muted: #f8fafc; /* fondos tenues (slate-50) */
  --color-hairline: #e2e8f0; /* bordes de 1px (slate-200) */

  /* Compat: alias del token histórico `brand` (verde) para no romper vistas previas */
  --color-brand: #12a312;
  --color-brand-soft: #1dc91d;
  --color-turq: #0fa9b8;
  --color-turq-soft: #76e5ec;
  --color-alert: #e0524d;
  --color-warn: #e8a83a;

  /* Tipografía */
  --font-sans: "Raleway", ui-sans-serif, system-ui, sans-serif;
  --font-display: "Montserrat", ui-sans-serif, system-ui, sans-serif;
}

:root {
  color-scheme: light;
}

body {
  background: var(--color-surface);
  color: var(--color-ink);
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

/* Cifras siempre alineadas en tablas y KPIs. */
.tabular {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum";
}

/* Impresión / export a PDF (Reportes): oculta el sidebar y los controles no
   imprimibles; el contenido fluye a página completa sobre blanco. */
@media print {
  aside,
  .no-print {
    display: none !important;
  }
  html,
  body {
    background: #ffffff;
  }
  main {
    overflow: visible !important;
    height: auto !important;
  }
}
```

### Navegación única (regla 9)

`frontend/src/lib/navegacion.ts` íntegro — ÚNICA fuente del árbol del sidebar, derivada
de capacidades:

```typescript
// Navegación del cockpit — ÚNICA fuente del árbol del sidebar (regla 9: la
// navegación se deriva de un solo config de permisos; prohibido mapear rol→UI
// disperso). El Sidebar filtra cada ítem por la capacidad requerida.
//
// Árbol del Blueprint UX (3 grupos, 8 vistas):
//   Principal            → Inicio · Proyecciones
//   Planeación y control → Escenarios · Presupuesto · IVA
//   Operación            → Dashboards · Reportes · Datos

import {
  BarChart3,
  Database,
  FileText,
  Home,
  Layers,
  LineChart,
  Receipt,
  Wallet,
} from "lucide-react";
import type { ComponentType } from "react";

export interface ItemNav {
  label: string;
  path: string;
  icon: ComponentType<{ className?: string }>;
  cap: string;
}

export interface GrupoNav {
  titulo: string;
  items: ItemNav[];
}

export const NAVEGACION: GrupoNav[] = [
  {
    titulo: "Principal",
    items: [
      { label: "Inicio", path: "/inicio", icon: Home, cap: "dashboard:leer" },
      {
        label: "Proyecciones",
        path: "/proyeccion",
        icon: LineChart,
        cap: "dashboard:leer",
      },
    ],
  },
  {
    titulo: "Planeación y control",
    items: [
      {
        label: "Escenarios",
        path: "/escenarios",
        icon: Layers,
        cap: "dashboard:leer",
      },
      {
        label: "Presupuesto",
        path: "/control",
        icon: Wallet,
        cap: "dashboard:leer",
      },
      { label: "IVA", path: "/iva", icon: Receipt, cap: "dashboard:leer" },
    ],
  },
  {
    titulo: "Operación",
    items: [
      {
        label: "Dashboards",
        path: "/dashboards",
        icon: BarChart3,
        cap: "dashboard:leer",
      },
      {
        label: "Reportes",
        path: "/reportes",
        icon: FileText,
        cap: "dashboard:leer",
      },
      // Datos = captura (caja inicial, supuestos, cargas) → requiere gestión.
      {
        label: "Datos",
        path: "/datos",
        icon: Database,
        cap: "cargas:gestionar",
      },
    ],
  },
];
```

### Vista representativa

`frontend/src/pages/ProyeccionPage.tsx` íntegro — la vista HERO del cockpit (curva de
caja vs. umbral, KPIs del motor, ingreso discriminado):

```typescript
// frontend/src/pages/ProyeccionPage.tsx
//
// Proyecciones — la vista HERO del cockpit (Blueprint): la curva de caja proyectada
// contra el UMBRAL (caja mínima) es la protagonista, con la franja de KPIs del motor
// y el ingreso DISCRIMINADO (recaudo de crédito vs cuota inicial). Escenarios
// Pesimista/Base/Optimista + horizonte configurable. Todo lo calcula el motor (C7);
// el front solo presenta (montos con formatCOP, regla 1; .toNumber() SOLO para la
// geometría del SVG, nunca para cálculo financiero).

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { CashCurve } from "@/components/charts/CashCurve";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Card, CardTitle } from "@/components/ui/card";
import { KpiTile } from "@/components/ui/kpi-tile";
import { ScenarioChip } from "@/components/ui/scenario-chip";
import { formatCOP, parseMonto } from "@/lib/money";
import {
  ESCENARIO_LABEL,
  ESTADO_LABEL,
  type Escenario,
  type EstadoMes,
  type Proyeccion,
  obtenerProyeccion,
} from "@/lib/proyeccion";

const ESCENARIOS: Escenario[] = ["pesimista", "base", "optimista"];
const HORIZONTES = [12, 24, 36, 60, 120, 180];

const ESTADO_ESTILO: Record<EstadoMes, string> = {
  ok: "bg-green/10 text-green",
  critico: "bg-amber/10 text-amber",
  negativo: "bg-red/10 text-red",
};

export default function ProyeccionPage() {
  const [escenario, setEscenario] = useState<Escenario>("base");
  const [horizonte, setHorizonte] = useState(60);

  const q = useQuery({
    queryKey: ["proyeccion", escenario, horizonte],
    queryFn: () => obtenerProyeccion({ escenario, horizonteMeses: horizonte }),
  });

  const selectorHorizonte = (
    <label className="flex items-center gap-2 font-sans text-sm">
      <span className="text-ink-soft">Horizonte</span>
      <select
        className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
        value={horizonte}
        onChange={(e) => setHorizonte(Number(e.target.value))}
      >
        {HORIZONTES.map((h) => (
          <option key={h} value={h}>
            {h >= 12 ? `${h / 12} año${h > 12 ? "s" : ""}` : `${h} m`}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Proyecciones"
        descripcion="Caja proyectada mes a mes contra el umbral, por escenario."
        acciones={selectorHorizonte}
      />

      {/* Palancas: escenario */}
      <div className="flex flex-wrap items-center gap-2">
        {ESCENARIOS.map((e) => (
          <ScenarioChip
            key={e}
            label={ESCENARIO_LABEL[e]}
            active={escenario === e}
            onClick={() => setEscenario(e)}
          />
        ))}
      </div>

      {q.isLoading && (
        <p className="font-sans text-sm text-ink-soft">
          Calculando proyección…
        </p>
      )}
      {q.isError && (
        <AlertBanner variant="danger">
          No se pudo calcular la proyección. Verifica que haya modelos de moto y
          parámetros configurados.
        </AlertBanner>
      )}

      {q.data && <ProyeccionContenido data={q.data} />}
    </div>
  );
}

function ProyeccionContenido({ data }: { data: Proyeccion }) {
  const perforada = data.meses_bajo_minimo > 0;
  const requiereCapital = !parseMonto(data.capital_requerido).isZero();

  return (
    <>
      {/* Aviso de estado (rojo = perforación, reservado) */}
      {perforada ? (
        <AlertBanner variant="danger">
          La caja perfora el mínimo en {data.meses_bajo_minimo}{" "}
          {data.meses_bajo_minimo === 1 ? "mes" : "meses"}; el punto más
          ajustado es {data.mes_mas_ajustado} ({formatCOP(data.piso_caja)}).
        </AlertBanner>
      ) : (
        <AlertBanner variant="ok">
          La caja se mantiene por encima del mínimo en todo el horizonte.
        </AlertBanner>
      )}

      {/* Franja de KPIs del motor */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
        <KpiTile
          label="Piso de caja"
          value={formatCOP(data.piso_caja)}
          sub={`en ${data.mes_mas_ajustado}`}
          tono={perforada ? "peligro" : "neutro"}
        />
        <KpiTile label="Caja final" value={formatCOP(data.caja_final)} />
        <KpiTile
          label="Capital requerido"
          value={formatCOP(data.capital_requerido)}
          sub="para no cruzar el umbral"
          tono={requiereCapital ? "peligro" : "neutro"}
        />
        <KpiTile
          label="Meses bajo el mínimo"
          value={String(data.meses_bajo_minimo)}
          tono={perforada ? "peligro" : "neutro"}
        />
        <KpiTile
          label="Runway"
          value={data.runway_meses === null ? "—" : `${data.runway_meses} m`}
          sub={
            data.runway_meses === null ? "caja no decrece" : "al ritmo actual"
          }
        />
      </div>

      {/* Hero: la curva */}
      <Card>
        <div className="mb-3 flex items-center justify-between">
          <CardTitle>Caja proyectada vs. umbral</CardTitle>
          <p className="font-sans text-xs text-ink-faint">
            umbral {formatCOP(data.caja_minima)} · {data.meses.length} meses
          </p>
        </div>
        <CashCurve meses={data.meses} umbral={data.caja_minima} />
      </Card>

      {/* Tabla de cierre */}
      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full font-sans text-sm">
            <thead>
              <tr className="border-b border-hairline text-left text-ink-faint">
                <th className="px-4 py-2.5 font-semibold">Mes</th>
                <th className="px-4 py-2.5 text-right font-semibold">Motos</th>
                <th className="px-4 py-2.5 text-right font-semibold">
                  Recaudo crédito
                </th>
                <th className="px-4 py-2.5 text-right font-semibold">
                  Cuota inicial
                </th>
                <th className="px-4 py-2.5 text-right font-semibold">
                  Ingreso bruto
                </th>
                <th className="px-4 py-2.5 text-right font-semibold">Flujo</th>
                <th className="px-4 py-2.5 text-right font-semibold">Caja</th>
                <th className="px-4 py-2.5 font-semibold">Estado</th>
              </tr>
            </thead>
            <tbody>
              {data.meses.map((m) => (
                <tr
                  key={m.mes}
                  className="border-b border-hairline/60 last:border-0 hover:bg-surface-muted"
                >
                  <td className="px-4 py-2 font-medium text-ink">{m.mes}</td>
                  <td className="tabular px-4 py-2 text-right text-ink-soft">
                    {m.motos}
                  </td>
                  <td className="tabular px-4 py-2 text-right text-ink-soft">
                    {formatCOP(m.recaudo_credito)}
                  </td>
                  <td className="tabular px-4 py-2 text-right text-ink-soft">
                    {formatCOP(m.cuotas_iniciales)}
                  </td>
                  <td className="tabular px-4 py-2 text-right font-medium text-ink">
                    {formatCOP(m.ingreso_bruto)}
                  </td>
                  <td className="tabular px-4 py-2 text-right text-ink-soft">
                    {formatCOP(m.flujo)}
                  </td>
                  <td className="tabular px-4 py-2 text-right font-medium text-ink">
                    {formatCOP(m.caja)}
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={`rounded-full px-2 py-0.5 font-sans text-xs font-medium ${ESTADO_ESTILO[m.estado]}`}
                    >
                      {ESTADO_LABEL[m.estado]}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
```

### Componentes base del sistema

Catálogo de los componentes reutilizables del cockpit (derivado del encabezado de cada
archivo):

**`frontend/src/components/ui/`**
- `alert-banner.tsx` — franja de estado (Blueprint §3): `danger` (rojo, `role=alert`,
  perforación de caja) vs `ok`/`warn` (`role=status`, no urgente). Rojo reservado a danger.
- `button.tsx` — botón base shadcn/ui (cva + cn + Tailwind); semilla del pipeline de UI.
- `card.tsx` — superficie base del cockpit (blanco, borde hairline, esquinas suaves,
  sombra tenue). Contenedor presentacional.
- `kpi-tile.tsx` — baldosa de KPI: etiqueta discreta (Raleway) sobre cifra protagonista
  (Montserrat, tabular-nums). El backend entrega la cifra ya formateada.
- `scenario-chip.tsx` — pill de selección de escenario (toggle con `aria-pressed`):
  activo = pill tinta, inactivo = borde hairline.

**`frontend/src/components/layout/`**
- `AppShell.tsx` — marco del cockpit: sidebar fijo + lienzo de contenido; en móvil el
  sidebar es panel deslizable con botón de menú.
- `PageHeader.tsx` — encabezado estándar de cada vista: título (Montserrat) + contexto
  opcional + zona de acciones a la derecha.
- `Sidebar.tsx` — navegación fija: marca RODDOS, árbol de 3 grupos derivado de
  capacidades (regla 9), ítem activo = barra cian + fondo tenue, pie con rol + salir.

**`frontend/src/components/charts/`**
- `CashCurve.tsx` — curva de caja proyectada vs. umbral en SVG inline (sin librería de
  gráficos): trazo cian, área en tinte cian, umbral discontinuo en rojo, marcadores
  rojos en los meses de perforación.
- `ScenariosChart.tsx` — superpone las curvas de caja de varios escenarios contra el
  umbral (SVG inline, escala compartida para comparar); colores de marca (cyan base,
  green optimista, amber pesimista).

Código íntegro de las demás vistas en `main` (commits arriba); se omite verbatim por
legibilidad, no por falta de evidencia.
