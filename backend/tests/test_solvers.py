# backend/tests/test_solvers.py
"""Solvers de D1 §5 — búsquedas por bisección sobre `aplicar_impactos` (el motor corre
en ms; 30-40 iteraciones son gratis). Techo de gasto, goal seek y punto de quiebre.

Propiedades verificadas: monotonicidad, SOLUCIÓN VERIFICADA (re-aplicar el resultado
cumple/roza el objetivo), y casos sin solución (mensaje llano, no error).
"""

from decimal import Decimal

from app.proyeccion.impactos import Ajuste, aplicar_impactos
from app.proyeccion.motor import ModeloProyeccion, ParametrosMotor, proyectar
from app.proyeccion.solvers import goal_seek, punto_de_quiebre, techo_gasto


def _params(**over):
    base = dict(
        mes_inicio=(2026, 7),
        horizonte_meses=8,
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
        caja_inicial=Decimal("200000"),  # holgura clara: piso base 155.200 > umbral
        caja_minima=Decimal("10000"),
    )
    base.update(over)
    return ParametrosMotor(**base)


def _base(**over):
    p = _params(**over)
    return proyectar(p), p.caja_minima


# ── Techo de gasto ──────────────────────────────────────────────────────────


def test_techo_gasto_respeta_el_umbral_y_es_verificable():
    r, umbral = _base()
    res = techo_gasto(r, umbral, colchon=Decimal("0"))
    assert res.hay_holgura is True
    assert res.techo_mensual > 0
    # SOLUCIÓN VERIFICADA: aplicar el techo deja el piso en/sobre el umbral...
    mes0 = r.meses[0].mes
    con_techo = aplicar_impactos(
        r,
        [Ajuste("t", "gasto", "absoluto", res.techo_mensual, mes0, None)],
        umbral,
    )
    assert con_techo.kpis.piso_caja >= umbral
    # ...y un peso más lo perfora (es el MÁXIMO)
    un_peso_mas = aplicar_impactos(
        r,
        [
            Ajuste(
                "t", "gasto", "absoluto", res.techo_mensual + Decimal("100"), mes0, None
            )
        ],
        umbral,
    )
    assert un_peso_mas.kpis.piso_caja < umbral


def test_techo_gasto_con_colchon_es_mas_estricto():
    r, umbral = _base()
    sin = techo_gasto(r, umbral, colchon=Decimal("0"))
    con = techo_gasto(r, umbral, colchon=Decimal("5000"))
    assert con.techo_mensual < sin.techo_mensual  # más colchón => menos margen


def test_techo_gasto_sin_holgura_devuelve_cero():
    # umbral por encima del piso base => ya no hay espacio para gastar más
    r, _ = _base()
    piso_base = r.piso_caja
    res = techo_gasto(r, piso_base + Decimal("10000"), colchon=Decimal("0"))
    assert res.hay_holgura is False
    assert res.techo_mensual == Decimal("0.00")


# ── Goal seek ────────────────────────────────────────────────────────────────


def test_goal_seek_ingreso_para_no_bajar_de_un_piso():
    r, umbral = _base()
    objetivo = r.piso_caja + Decimal("20000")  # quiero un piso más alto
    res = goal_seek(r, umbral, variable="ingreso_absoluto", objetivo_caja=objetivo)
    assert res.alcanzable is True
    assert res.valor > 0
    mes0 = r.meses[0].mes
    con = aplicar_impactos(
        r, [Ajuste("v", "ingreso", "absoluto", res.valor, mes0, None)], umbral
    )
    assert con.kpis.piso_caja >= objetivo  # cumple el objetivo


def test_goal_seek_ya_cumplido_devuelve_cero():
    r, umbral = _base()
    res = goal_seek(r, umbral, variable="ingreso_absoluto", objetivo_caja=r.piso_caja)
    assert res.alcanzable is True
    assert res.valor == Decimal("0.00")


def test_goal_seek_gasto_absoluto_es_un_recorte():
    r, umbral = _base()
    objetivo = r.piso_caja + Decimal("15000")
    res = goal_seek(r, umbral, variable="gasto_absoluto", objetivo_caja=objetivo)
    assert res.alcanzable is True and res.valor > 0
    mes0 = r.meses[0].mes
    # el recorte se aplica como gasto negativo (sube la caja)
    con = aplicar_impactos(
        r, [Ajuste("recorte", "gasto", "absoluto", -res.valor, mes0, None)], umbral
    )
    assert con.kpis.piso_caja >= objetivo


def test_goal_seek_inalcanzable_da_mensaje_no_error():
    r, umbral = _base()
    # un piso astronómico: ni vendiendo hasta el tope se alcanza en el rango
    res = goal_seek(
        r, umbral, variable="ingreso_pct", objetivo_caja=Decimal("999999999999999")
    )
    assert res.alcanzable is False
    assert res.valor is None
    assert res.mensaje  # explicación llana, no excepción


# ── Punto de quiebre ─────────────────────────────────────────────────────────


def test_punto_de_quiebre_encuentra_el_gasto_que_perfora():
    r, umbral = _base()
    res = punto_de_quiebre(r, umbral)
    assert res.perfora is True
    assert res.valor > 0 and res.mes is not None
    mes0 = r.meses[0].mes
    con = aplicar_impactos(
        r, [Ajuste("q", "gasto", "absoluto", res.valor, mes0, None)], umbral
    )
    assert con.kpis.piso_caja < umbral  # a ese valor, perfora
