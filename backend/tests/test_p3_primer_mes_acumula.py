# backend/tests/test_p3_primer_mes_acumula.py
"""P3 del ciclo mensual — EL PRIMER MES ACUMULA SU PROPIO FLUJO.

Contrato: `docs/COMPAS_Ciclo_Mensual.md` §«El candado aritmético».

    caja(mes) = caja(mes anterior) + flujo(mes)   ← SIN excepciones, tampoco el 1º

El motor heredó del artefacto de Excel la convención "primer mes: caja fija (= caja
inicial); el flujo de ese mes no la mueve" (`motor.py`), porque allá `caja_inicial`
significaba "la plata que tengo HOY", a mitad del mes en curso. Con P2 el arranque
pasó a ser el efectivo real del CIERRE ANTERIOR — un valor ANTERIOR al primer mes — así
que su flujo sí debe moverlo. Mientras no lo hiciera, agosto-2026 mostraba una caja
imposible de rehacer sumando: 665.715.578 con un flujo de +33.299.982 (el arranque
implícito habría sido 632.415.596, un número que no existe en ninguna parte).

Aditivo y certificable: el MOTOR conserva `primer_mes_acumula_flujo=False` (la semántica
del artefacto) para que el GOLDEN MASTER siga bit a bit; el SERVICIO —el producto— pasa
siempre True. Las tres capas post-motor (E1 anclaje, D2 reconciliación, D1 impactos)
comparten `reacumular`, así que el flag viaja con ellas o la caja del primer mes se
quedaría congelada al re-acumular.
"""

from decimal import Decimal

from app.proyeccion.impactos import reacumular
from app.proyeccion.motor import ModeloProyeccion, ParametrosMotor, proyectar

CENTAVO = Decimal("0.01")
ARRANQUE = Decimal("665715578")  # el cierre real de julio-2026


def _motor(**over) -> ParametrosMotor:
    base = dict(
        mes_inicio=(2026, 8),
        horizonte_meses=12,
        modelos=[
            ModeloProyeccion(
                nombre="Raider",
                cuota_semanal=Decimal("184900"),
                cuota_inicial=Decimal("1620000"),
                plazo_semanas=78,
                mix=Decimal("1"),
                costo_moto=Decimal("6720557"),
            )
        ],
        motos_base=60,
        crec_pct_mensual=Decimal("0.10"),
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
        overrides_mora=None,
        overrides_default=None,
        caja_inicial=ARRANQUE,
        caja_minima=Decimal("30000000"),
    )
    base.update(over)
    return ParametrosMotor(**base)


# ─────────────────────────────── el motor ───────────────────────────────


def test_el_primer_mes_acumula_su_flujo():
    r = proyectar(_motor(primer_mes_acumula_flujo=True))
    assert r.meses[0].caja == (ARRANQUE + r.meses[0].flujo).quantize(CENTAVO)


def test_el_default_conserva_la_semantica_del_artefacto():
    """Candado del golden master: sin el flag, la caja del primer mes es el arranque."""
    r = proyectar(_motor())
    assert r.meses[0].caja == ARRANQUE
    assert proyectar(_motor(primer_mes_acumula_flujo=False)).meses[0].caja == ARRANQUE


def test_la_serie_completa_cuadra_mes_a_mes():
    """El candado ① sin excepciones, en los 12 meses."""
    r = proyectar(_motor(primer_mes_acumula_flujo=True))
    previa = ARRANQUE
    for f in r.meses:
        assert f.caja == (previa + f.flujo).quantize(CENTAVO), f.mes
        previa = f.caja


def test_los_meses_2_en_adelante_no_se_mueven_de_su_relacion():
    """Activar el flag desplaza toda la curva por el flujo del primer mes, sin tocar
    ninguna otra cuenta: el mismo flujo, el mismo ingreso, el mismo egreso."""
    con = proyectar(_motor(primer_mes_acumula_flujo=True))
    sin = proyectar(_motor())
    delta = con.meses[0].flujo
    for a, b in zip(sin.meses, con.meses, strict=True):
        assert b.caja - a.caja == delta, a.mes
        assert a.flujo == b.flujo
        assert a.neto == b.neto
        assert a.egresos == b.egresos


def test_los_kpis_se_recalculan_sobre_la_serie_nueva():
    """El piso y el capital requerido salen de la misma serie: si la curva se desplaza,
    ellos también (si no, la pantalla se desincroniza de su propia tabla)."""
    con = proyectar(_motor(primer_mes_acumula_flujo=True))
    sin = proyectar(_motor())
    assert con.piso_caja != sin.piso_caja
    assert con.piso_caja == min(f.caja for f in con.meses)


# ─────────── la re-acumulación que comparten E1, D2 y D1 ───────────


def test_reacumular_puede_mover_la_caja_del_primer_mes():
    """Con `primer_mes_acumula=True` un delta en el primer mes SÍ mueve su caja. El
    arranque se deriva de la propia serie (`caja[0] − flujo[0]`), exacto porque el motor
    la construyó con esa regla — sin parámetros nuevos que sincronizar."""
    r = proyectar(_motor(primer_mes_acumula_flujo=True))
    deltas = [Decimal("-50000000")] + [Decimal("0")] * (len(r.meses) - 1)
    aj = reacumular(r, deltas, Decimal("30000000"), primer_mes_acumula=True)
    assert aj.meses[0].flujo == (r.meses[0].flujo - Decimal("50000000")).quantize(
        CENTAVO
    )
    assert aj.meses[0].caja == (ARRANQUE + aj.meses[0].flujo).quantize(CENTAVO)
    # y el desplazamiento se propaga a toda la serie
    for a, b in zip(r.meses, aj.meses, strict=True):
        assert a.caja - b.caja == Decimal("50000000"), a.mes


def test_reacumular_sin_el_flag_deja_el_primer_mes_fijo():
    """Candado: el comportamiento por defecto no cambia (D1/D2/E1 y el golden)."""
    r = proyectar(_motor())
    deltas = [Decimal("-50000000")] + [Decimal("0")] * (len(r.meses) - 1)
    aj = reacumular(r, deltas, Decimal("30000000"))
    assert aj.meses[0].caja == r.meses[0].caja  # fijo


def test_reacumular_con_deltas_en_cero_es_la_base_bit_a_bit():
    """La regla de oro de D1: deltas en cero ⇒ la serie base, con o sin flag."""
    r = proyectar(_motor(primer_mes_acumula_flujo=True))
    ceros = [Decimal("0")] * len(r.meses)
    for flag in (True, False):
        aj = reacumular(r, ceros, Decimal("30000000"), primer_mes_acumula=flag)
        assert [f.caja for f in aj.meses] == [f.caja for f in r.meses]
        assert [f.flujo for f in aj.meses] == [f.flujo for f in r.meses]


def test_el_anclaje_E1_respeta_el_candado_en_el_primer_mes():
    """E1 re-acumula tras anclar. Si no propagara el flag, anclar el mes en curso
    cambiaría su flujo y dejaría su caja congelada — el descuadre de agosto."""
    from app.proyeccion.ejecucion.service import EN_EJECUCION, AnclaMes, anclar
    from tests.test_e1_pipeline import _rubros

    r = proyectar(_motor(primer_mes_acumula_flujo=True))
    ancla = AnclaMes(
        estado=EN_EJECUCION,
        ejecutado_por_rubro_id={},
        definido_por_rubro_id={"2010": Decimal("100000000")},
        ingreso_real=None,
    )
    aj = anclar(
        resultado=r,
        caja_minima=Decimal("30000000"),
        anclas={r.meses[0].mes: ancla},
        rubros=_rubros(),
        neutros_ids=set(),
        primer_mes_acumula=True,
    )
    previa = ARRANQUE
    for f in aj.meses:
        assert f.caja == (previa + f.flujo).quantize(CENTAVO), f.mes
        previa = f.caja
