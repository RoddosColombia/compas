# backend/tests/test_sup5_variables_visibles.py
"""SUP-5 (CEO 2026-08-23) — la gráfica debe mostrar QUÉ compone el resultado.

"Quisiera que existieran ciertas referencias de las variables que componen este
resultado de proyección: cuánta mora se está teniendo, cuánto default, cuántas motos
vendidas mes a mes, que permita nutrir la gráfica para entender qué variables componen
este resultado."

Hoy la proyección expone el RESULTADO (caja, piso, ingreso, egresos) pero esconde el
POR QUÉ: la mora, la recuperación y el default viajan sumados dentro de `neto`, y los
supuestos del escenario en pantalla no se ven en ninguna parte.

Esto los saca a la luz, sin cambiar un solo cálculo:
  A. cada mes expone `mora`, `recuperacion` y `default` por separado (el motor ya los
     calculaba en `AjusteMora`; solo se guardaban sumados);
  B. la respuesta trae un bloque `supuestos` con los porcentajes EFECTIVOS del
     escenario que se está viendo — importa de verdad desde que cada escenario tiene
     su propia mora (SUP-2: pesimista 14 %, base 5 %, optimista 4 %);
  C. **honestidad**: en un mes ANCLADO a la ejecución real, la mora proyectada no
     aplica (el ingreso viene del libro) → esos meses la muestran en 0, no un número
     paramétrico que no pasó.
"""

from decimal import Decimal

from app.proyeccion.motor import ModeloProyeccion, ParametrosMotor, proyectar
from app.proyeccion.service import _supuestos_visibles


def _motor(**over) -> ParametrosMotor:
    base = dict(
        mes_inicio=(2026, 8),
        horizonte_meses=6,
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
        motos_base=70,
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
        pct_mora=Decimal("0.10"),
        pct_recuperacion=Decimal("0.50"),
        pct_default=Decimal("0.03"),
        pct_provision=Decimal("0.02"),
        overrides_mora=None,
        overrides_default=None,
        caja_inicial=Decimal("700000000"),
        caja_minima=Decimal("125000000"),
    )
    base.update(over)
    return ParametrosMotor(**base)


# ── A · las tres variables de cartera, por separado ──


def test_cada_mes_expone_mora_recuperacion_y_default():
    """Ya no van escondidas dentro de `neto`."""
    r = proyectar(_motor())
    m = r.meses[3]  # un mes con recaudo corriendo
    assert m.recaudo_credito > 0
    assert m.mora < 0  # la mora RESTA
    assert m.recuperacion > 0  # la recuperación devuelve
    assert m.default < 0  # el default resta y no vuelve


def test_las_tres_cuadran_con_el_neto_al_peso():
    """Candado de coherencia: bruto + mora + recuperación + default == neto. Si algún
    día se muestran y no suman, el usuario pierde la confianza en la pantalla."""
    r = proyectar(_motor())
    for m in r.meses:
        assert m.neto == (
            m.ingreso_bruto + m.mora + m.recuperacion + m.default
        ).quantize(Decimal("0.01"))


def test_la_mora_es_el_porcentaje_del_ingreso_bruto():
    """Trazable a mano: mora = −ingreso_bruto × pct (lo que el CEO puede verificar).

    ⚠ OJO — el bruto incluye las CUOTAS INICIALES. El modelo v9.1 de Fabián aplica la
    mora solo al recaudo de cuotas (`FC!17 = −L13×L6`, con L13 = "Recaudo cuotas
    mensuales"), porque la inicial se paga de contado y no puede caer en mora. Es una
    diferencia REAL de criterio, reportada al CEO: cambiarla movería el golden master,
    así que este test fija lo que el motor hace HOY, no lo que quizá deba hacer."""
    r = proyectar(_motor(pct_mora=Decimal("0.10")))
    m = r.meses[3]
    assert m.mora == -(m.ingreso_bruto * Decimal("0.10")).quantize(Decimal("0.01"))
    assert m.ingreso_bruto == m.recaudo_credito + m.cuotas_iniciales


def test_sin_mora_las_tres_lineas_quedan_en_cero():
    r = proyectar(_motor(pct_mora=Decimal("0"), pct_default=Decimal("0")))
    assert all(m.mora == 0 and m.recuperacion == 0 and m.default == 0 for m in r.meses)


# ── B · los supuestos del escenario en pantalla ──


def _params(**over):
    from app.domain.parametros_proyeccion import ParametrosProyeccion

    base = dict(
        vigente_desde="2026-08-01",
        caja_inicial=Decimal("100000000"),
        caja_minima=Decimal("125000000"),
        motos_base=70,
        crec_pct_mensual=Decimal("0.10"),
        horizonte_meses=24,
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
        pct_mora=Decimal("0.05"),
        pct_recuperacion=Decimal("0.65"),
        pct_default=Decimal("0.05"),
        pct_provision=Decimal("0.02"),
        pct_mora_pesimista=Decimal("0.14"),
        pct_recuperacion_pesimista=Decimal("0.50"),
        pct_mora_optimista=Decimal("0.04"),
        pct_recuperacion_optimista=Decimal("0.90"),
        pct_aval_recaudo=Decimal("0.01"),
        meses_rezago_recuperacion=1,
    )
    base.update(over)
    return ParametrosProyeccion(**base)


def test_los_supuestos_visibles_son_los_del_escenario_en_pantalla():
    """Lo que se muestra tiene que ser lo que se USÓ: con SUP-2 cada escenario tiene
    su propia mora, así que la pantalla del pesimista debe decir 14 %, no 5 %."""
    p = _params()
    assert _supuestos_visibles(p, "base")["pct_mora"] == "0.05"
    assert _supuestos_visibles(p, "pesimista")["pct_mora"] == "0.14"
    assert _supuestos_visibles(p, "optimista")["pct_mora"] == "0.04"
    assert _supuestos_visibles(p, "pesimista")["pct_recuperacion"] == "0.50"


def test_los_supuestos_traen_los_drivers_de_colocacion_y_cartera():
    s = _supuestos_visibles(_params(), "base")
    assert s["motos_base"] == 70
    assert s["crec_pct_mensual"] == "0.10"
    assert s["pct_default"] == "0.05"
    assert s["pct_provision"] == "0.02"
    assert s["meses_rezago_recuperacion"] == 1
    assert s["pct_aval_recaudo"] == "0.01"


def test_los_supuestos_declaran_el_segundo_tramo_cuando_existe():
    s = _supuestos_visibles(
        _params(crec_pct_mensual_2=Decimal("0.03"), crec_mes_corte=18), "base"
    )
    assert s["crec_pct_mensual_2"] == "0.03"
    assert s["crec_mes_corte"] == 18
    sin = _supuestos_visibles(_params(), "base")
    assert sin["crec_pct_mensual_2"] is None


def test_los_montos_de_los_supuestos_viajan_como_string():
    """Regla 1: ningún monto/pct como float en el JSON."""
    s = _supuestos_visibles(_params(), "base")
    for k in ("pct_mora", "pct_recuperacion", "pct_default", "crec_pct_mensual"):
        assert isinstance(s[k], str)


# ── C · honestidad en los meses ya reales ──


def test_un_mes_anclado_no_muestra_mora_proyectada():
    """En un mes CERRADO el ingreso sale del libro: la mora paramétrica no pasó, así
    que no se muestra (sería inventarle una explicación a una cifra real)."""
    from app.proyeccion.ejecucion.service import CERRADO, AnclaMes, anclar
    from tests.test_e1_pipeline import _rubros  # la taxonomía que exige B12

    r = proyectar(_motor())
    mes = r.meses[0].mes
    ancla = AnclaMes(
        estado=CERRADO,
        ejecutado_por_rubro_id={},
        definido_por_rubro_id={},
        ingreso_real=Decimal("300000000"),
    )
    aj = anclar(
        resultado=r,
        caja_minima=Decimal("125000000"),
        anclas={mes: ancla},
        rubros=_rubros(),
        neutros_ids=set(),
    )
    fila = aj.meses[0]
    assert fila.mora == 0
    assert fila.recuperacion == 0
    assert fila.default == 0
    # y los meses NO anclados conservan su explicación
    assert aj.meses[3].mora < 0


def test_un_mes_EN_EJECUCION_si_muestra_su_mora():
    """El mes en curso ancla el GASTO (Regla A) pero su INGRESO sigue siendo del motor:
    su mora sí explica la cifra y tiene que verse.

    Defecto detectado con agosto-2026 en PROD (CEO 2026-08-23): la columna «Ajuste
    mora/default» mostraba −13.017.583 (= neto − bruto, que el motor sí calculó) y el
    desglose decía mora 0 / recuperación 0 / default 0. Dos cifras de la misma fila
    contándose distinto: eso es exactamente lo que no puede pasar."""
    from app.proyeccion.ejecucion.service import EN_EJECUCION, AnclaMes, anclar
    from tests.test_e1_pipeline import _rubros

    r = proyectar(_motor())
    mes = r.meses[0].mes
    ancla = AnclaMes(
        estado=EN_EJECUCION,
        ejecutado_por_rubro_id={},
        definido_por_rubro_id={},
        ingreso_real=None,  # el ingreso NO se ancla en un mes en ejecución
    )
    aj = anclar(
        resultado=r,
        caja_minima=Decimal("125000000"),
        anclas={mes: ancla},
        rubros=_rubros(),
        neutros_ids=set(),
    )
    fila = aj.meses[0]
    # la invariante de SUP-5 se sostiene: las tres explican el neto que se muestra
    assert fila.neto == (
        fila.ingreso_bruto + fila.mora + fila.recuperacion + fila.default
    ).quantize(Decimal("0.01"))
    assert fila.mora == r.meses[0].mora  # la del motor, intacta
