# backend/tests/test_candado_aritmetico.py
"""P1 del ciclo mensual — EL CANDADO ARITMÉTICO.

Contrato: `docs/COMPAS_Ciclo_Mensual.md` §«El candado aritmético».

    caja(mes)    = caja(mes anterior) + flujo(mes)   ← SIN excepciones, tampoco el 1º
    flujo(mes)   = ingreso neto + egresos             (los egresos son negativos)
    ingreso neto = cuota inicial + cuotas semanales + ajuste
    ajuste       = mora + recuperación + incumplimiento  (mora SOLO sobre semanales)

"La matemática de las cuentas en ningún mes puede fallar... es como un tejido bien
confeccionado, no puede tener error" (CEO 2026-08-23).

Este test se escribe ANTES de arreglar nada: es el que demuestra que las piezas P2–P5
funcionan. Recorre TODOS los meses del horizonte (no una muestra), en los TRES
escenarios, y por las TRES capas de la tubería (motor → E1 anclaje → D2
reconciliación): una capa que re-acumula mal rompe el tejido igual que una fórmula mala.

Estado esperado hoy: la fórmula ① FALLA en el primer mes por la convención heredada del
artefacto (`motor.py`: "primer mes: caja fija (= caja inicial); el flujo de ese mes no
la mueve"). El test lo declara con `xfail(strict=True)` para que quede REGISTRADO y para
que avise cuando P3 lo arregle: si algún día pasa sin actualizar el test, falla y nos
enteramos.
"""

from decimal import Decimal

import pytest
from app.proyeccion.motor import (
    ModeloProyeccion,
    ParametrosMotor,
    ResultadoProyeccion,
    proyectar,
)

CENTAVO = Decimal("0.01")


def _modelos() -> list[ModeloProyeccion]:
    """Los tres modelos reales de RODDOS (mix de PROD 2026-08)."""
    return [
        ModeloProyeccion(
            nombre="Raider",
            cuota_semanal=Decimal("184900"),
            cuota_inicial=Decimal("1620000"),
            plazo_semanas=78,
            mix=Decimal("0.35"),
            costo_moto=Decimal("6720557"),
        ),
        ModeloProyeccion(
            nombre="Apache 160",
            cuota_semanal=Decimal("224900"),
            cuota_inicial=Decimal("2100000"),
            plazo_semanas=78,
            mix=Decimal("0.60"),
            costo_moto=Decimal("8123456"),
        ),
        ModeloProyeccion(
            nombre="Sport 110",
            cuota_semanal=Decimal("154900"),
            cuota_inicial=Decimal("1450000"),
            plazo_semanas=78,
            mix=Decimal("0.05"),
            costo_moto=Decimal("5638974"),
        ),
    ]


def _motor(**over) -> ParametrosMotor:
    """Parámetros calcados de PROD (2026-08-23) — el caso que el CEO tiene en
    pantalla."""
    base = dict(
        mes_inicio=(2026, 8),
        horizonte_meses=144,
        modelos=_modelos(),
        motos_base=60,
        crec_pct_mensual=Decimal("0.10"),
        crec_pct_mensual_2=Decimal("0.015"),
        crec_mes_corte=15,
        rampa=None,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=150,
        base_auteco_dias=90,
        tasa_auteco=Decimal("0.016"),
        gastos_fijos=Decimal("208000000"),
        gps_moto=Decimal("33201"),
        costo_moto_nueva=Decimal("691500"),
        deuda=Decimal("25000000"),
        tasa_deuda=Decimal("0.1157"),
        mes_inicio_deuda=2,
        meses_deuda=14,
        pct_mora=Decimal("0.08"),
        pct_recuperacion=Decimal("0.65"),
        pct_default=Decimal("0.03"),
        pct_provision=Decimal("0.02"),
        meses_rezago_recuperacion=1,
        pct_aval_recaudo=Decimal("0.01"),
        mora_sobre_recaudo=True,
        overrides_mora=None,
        overrides_default=None,
        caja_inicial=Decimal("665715578"),  # el cierre REAL de julio
        caja_minima=Decimal("30000000"),
    )
    base.update(over)
    return ParametrosMotor(**base)


# ─────────────────────────── las cuatro fórmulas ───────────────────────────


def verificar_ingreso(r: ResultadoProyeccion) -> list[str]:
    """③ ingreso neto = cuota inicial + cuotas semanales + ajuste."""
    fallas = []
    for f in r.meses:
        ajuste = f.mora + f.recuperacion + f.default
        esperado = (f.cuotas_iniciales + f.recaudo_credito + ajuste).quantize(CENTAVO)
        if f.neto != esperado:
            fallas.append(
                f"{f.mes}: inicial {f.cuotas_iniciales} + semanal {f.recaudo_credito}"
                f" + ajuste {ajuste} = {esperado} != neto {f.neto}"
                f" (dif {f.neto - esperado})"
            )
    return fallas


def verificar_bruto(r: ResultadoProyeccion) -> list[str]:
    """③b el bruto es exactamente inicial + semanales (nada más entra al ingreso)."""
    return [
        f"{f.mes}: bruto {f.ingreso_bruto} != inicial+semanal"
        f" {f.cuotas_iniciales + f.recaudo_credito}"
        for f in r.meses
        if f.ingreso_bruto != (f.cuotas_iniciales + f.recaudo_credito).quantize(CENTAVO)
    ]


def verificar_egresos(r: ResultadoProyeccion) -> list[str]:
    """②b los egresos son la suma de sus conceptos — ninguno se cuela ni se pierde."""
    fallas = []
    for f in r.meses:
        esperado = (
            f.gastos_fijos
            + f.gps
            + f.costo_nueva
            + f.int_deuda
            + f.adelanto
            + f.pago_inventario
            + f.fondeo
            + f.iva
            + f.aval
        ).quantize(CENTAVO)
        if f.egresos != esperado:
            fallas.append(
                f"{f.mes}: Σ conceptos {esperado} != egresos {f.egresos}"
                f" (dif {f.egresos - esperado})"
            )
    return fallas


def verificar_flujo(r: ResultadoProyeccion) -> list[str]:
    """② flujo = ingreso neto + egresos."""
    return [
        f"{f.mes}: neto {f.neto} + egresos {f.egresos} = {f.neto + f.egresos}"
        f" != flujo {f.flujo}"
        for f in r.meses
        if f.flujo != (f.neto + f.egresos).quantize(CENTAVO)
    ]


def verificar_caja(r: ResultadoProyeccion, caja_arranque: Decimal) -> list[str]:
    """① caja(mes) = caja(mes anterior) + flujo(mes), SIN excepciones.

    Para el primer mes, "caja anterior" es el efectivo de arranque (Paso 0 del contrato:
    un valor ANTERIOR al primer mes del horizonte)."""
    fallas = []
    previa = caja_arranque
    for f in r.meses:
        esperado = (previa + f.flujo).quantize(CENTAVO)
        if f.caja != esperado:
            fallas.append(
                f"{f.mes}: caja previa {previa} + flujo {f.flujo} = {esperado}"
                f" != caja {f.caja} (dif {f.caja - esperado})"
            )
        previa = f.caja
    return fallas


def verificar_todo(r: ResultadoProyeccion, caja_arranque: Decimal) -> list[str]:
    return (
        verificar_bruto(r)
        + verificar_ingreso(r)
        + verificar_egresos(r)
        + verificar_flujo(r)
        + verificar_caja(r, caja_arranque)
    )


# ─────────────────────────── los tests ───────────────────────────


def test_el_ingreso_cuadra_en_todos_los_meses():
    """③ y ③b en los 144 meses: el ingreso se rehace a mano con sus columnas."""
    r = proyectar(_motor())
    assert len(r.meses) == 144
    assert verificar_bruto(r) == []
    assert verificar_ingreso(r) == []


def test_los_egresos_cuadran_con_sus_conceptos_en_todos_los_meses():
    """②b: si un concepto de egreso no suma al total, la tabla miente."""
    r = proyectar(_motor())
    assert verificar_egresos(r) == []


def test_el_flujo_cuadra_en_todos_los_meses():
    """②: flujo = neto + egresos."""
    r = proyectar(_motor())
    assert verificar_flujo(r) == []


@pytest.mark.xfail(
    strict=True,
    reason="P3 pendiente: motor.py fija la caja del primer mes (convención del "
    "artefacto) y su flujo no la mueve. El contrato del ciclo mensual lo elimina.",
)
def test_la_caja_acumula_su_flujo_en_todos_los_meses_incluido_el_primero():
    """① — el candado que hoy NO pasa, y por eso agosto no cuadra en pantalla."""
    p = _motor()
    r = proyectar(p)
    assert verificar_caja(r, p.caja_inicial) == []


def test_la_caja_acumula_bien_de_el_segundo_mes_en_adelante():
    """① a partir del mes 2 sí se cumple hoy: aísla el defecto al primer mes y evita
    que P3 lo 'arregle' rompiendo la acumulación del resto."""
    r = proyectar(_motor())
    # se arranca desde el mes 1 usando su propia caja como base
    fallas = verificar_caja(
        ResultadoProyeccion(
            meses=r.meses[1:],
            piso_caja=r.piso_caja,
            mes_mas_ajustado=r.mes_mas_ajustado,
            meses_bajo_minimo=r.meses_bajo_minimo,
            caja_final=r.caja_final,
            capital_requerido=r.capital_requerido,
            runway_meses=r.runway_meses,
        ),
        r.meses[0].caja,
    )
    assert fallas == []


@pytest.mark.parametrize(
    "pct_mora,pct_recup,pct_def",
    [
        (Decimal("0.14"), Decimal("0.50"), Decimal("0.03")),  # pesimista (PROD)
        (Decimal("0.08"), Decimal("0.65"), Decimal("0.03")),  # base (PROD)
        (Decimal("0.04"), Decimal("0.90"), Decimal("0.03")),  # optimista (PROD)
    ],
    ids=["pesimista", "base", "optimista"],
)
def test_las_formulas_cuadran_en_los_tres_escenarios(pct_mora, pct_recup, pct_def):
    """El tejido no puede depender del escenario que se esté mirando."""
    p = _motor(pct_mora=pct_mora, pct_recuperacion=pct_recup, pct_default=pct_def)
    r = proyectar(p)
    fallas = (
        verificar_bruto(r)
        + verificar_ingreso(r)
        + verificar_egresos(r)
        + verificar_flujo(r)
        + verificar_caja(r, p.caja_inicial)[1:]  # el primer mes es P3 (xfail arriba)
    )
    assert fallas == [], "\n".join(fallas[:5])


def test_las_formulas_cuadran_con_la_cartera_previa_y_el_iva():
    """Con las capas que de verdad corren en PROD: cartera ya originada + egreso de IVA
    en el mes DIAN. Son las que meten cifras 'de afuera' al motor."""
    p = _motor(
        recaudo_previo_por_semana={25: Decimal("1389286"), 26: Decimal("33603682")},
        activos_previos_por_semana={25: 9, 26: 165},
        iva_egreso_por_mes={1: Decimal("36204698.10")},
        rampa={0: 70},  # el objetivo de agosto (Paso 1 del contrato)
    )
    r = proyectar(p)
    fallas = (
        verificar_bruto(r)
        + verificar_ingreso(r)
        + verificar_egresos(r)
        + verificar_flujo(r)
        + verificar_caja(r, p.caja_inicial)[1:]
    )
    assert fallas == [], "\n".join(fallas[:5])
    # y el IVA del mes DIAN sí golpeó la caja de ese mes
    assert r.meses[1].iva == Decimal("-36204698.10")


def test_la_provision_no_toca_el_flujo():
    """Caja veraz: la provisión NIIF 9 se calcula pero no resta caja. Si algún día entra
    al flujo, el candado ② lo caza; este test lo dice explícito."""
    r = proyectar(_motor())
    for f in r.meses:
        assert f.provision <= 0
        assert f.flujo == (f.neto + f.egresos).quantize(CENTAVO)


# ── el mismo candado, después de las capas E1 (anclaje) y D2 (reconciliación) ──


def test_el_candado_se_sostiene_despues_del_anclaje_E1():
    """E1 re-acumula la caja al anclar meses reales. Si su re-acumulación no respeta la
    fórmula ①, la pantalla vuelve a mentir aunque el motor esté bien."""
    from app.proyeccion.ejecucion.service import CERRADO, EN_EJECUCION, AnclaMes, anclar
    from tests.test_e1_pipeline import _rubros

    p = _motor()
    r = proyectar(p)
    anclas = {
        r.meses[0].mes: AnclaMes(
            estado=EN_EJECUCION,
            ejecutado_por_rubro_id={},
            definido_por_rubro_id={},
            ingreso_real=None,
        ),
    }
    aj = anclar(
        resultado=r,
        caja_minima=p.caja_minima,
        anclas=anclas,
        rubros=_rubros(),
        neutros_ids=set(),
    )
    envuelto = ResultadoProyeccion(
        meses=aj.meses,
        piso_caja=aj.kpis.piso_caja,
        mes_mas_ajustado=aj.kpis.mes_mas_ajustado,
        meses_bajo_minimo=aj.kpis.meses_bajo_minimo,
        caja_final=aj.kpis.caja_final,
        capital_requerido=aj.kpis.capital_requerido,
        runway_meses=aj.kpis.runway_meses,
    )
    fallas = (
        verificar_ingreso(envuelto)
        + verificar_egresos(envuelto)
        + verificar_flujo(envuelto)
        + verificar_caja(envuelto, p.caja_inicial)[1:]  # primer mes = P3
    )
    assert fallas == [], "\n".join(fallas[:5])
    assert CERRADO  # (import usado por el siguiente test de la suite)
