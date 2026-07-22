# backend/tests/test_motor_sugerido.py
"""Motor del sugerido — fórmula oficial §1.4.1 (F-07). NÚCLEO auditado por Kimi
celda a celda.

    prom_3m       = (E(M-1) + E(M-2) + E(M-3)) / 3
    tendencia_mes = (E(M-1) − E(M-3)) / 2
    sugerido      = prom_3m + tendencia_mes + prom_3m × crec_pct

E(i) = ejecutado del rubro en el mes i, SOLO meses 'cerrado'. `historia_incompleta`
= true si hay menos de 3 meses cerrados. Todo en Decimal (regla 1)."""

from decimal import Decimal

from app.presupuesto.motor import calcular_sugerido_historico


def test_ejemplo_oficial_del_spec():
    # Spec §1.4.1: E(abr)=48M, E(may)=61M, E(jun)=75M, crec 15% → jul = 84.033.333,33.
    r = calcular_sugerido_historico(
        ejecutados=[Decimal("75000000"), Decimal("61000000"), Decimal("48000000")],
        crec_pct=Decimal("0.15"),
    )
    assert r.prom_3m == Decimal("61333333.33")
    assert r.tendencia_mes == Decimal("13500000.00")
    assert r.monto_sugerido == Decimal("84033333.33")
    assert r.historia_incompleta is False


def test_componentes_son_decimal():
    r = calcular_sugerido_historico(
        ejecutados=[Decimal("100"), Decimal("100"), Decimal("100")],
        crec_pct=Decimal("0"),
    )
    for v in (r.prom_3m, r.tendencia_mes, r.monto_sugerido):
        assert isinstance(v, Decimal) and not isinstance(v, float)


def test_crec_cero_es_prom_mas_tendencia():
    r = calcular_sugerido_historico(
        ejecutados=[Decimal("120"), Decimal("100"), Decimal("80")],
        crec_pct=Decimal("0"),
    )
    assert r.prom_3m == Decimal("100.00")
    assert r.tendencia_mes == Decimal("20.00")  # (120−80)/2
    assert r.monto_sugerido == Decimal("120.00")


def test_tendencia_negativa_rubro_decreciente():
    r = calcular_sugerido_historico(
        ejecutados=[Decimal("80"), Decimal("100"), Decimal("120")],
        crec_pct=Decimal("0"),
    )
    assert r.tendencia_mes == Decimal("-20.00")  # (80−120)/2
    assert r.monto_sugerido == Decimal("80.00")  # 100 − 20


def test_dos_meses_historia_incompleta():
    # <3 cerrados → incompleta; tendencia = (reciente − antiguo)/(n−1) = /1.
    r = calcular_sugerido_historico(
        ejecutados=[Decimal("120"), Decimal("100")], crec_pct=Decimal("0")
    )
    assert r.historia_incompleta is True
    assert r.prom_3m == Decimal("110.00")  # promedio de los 2 disponibles
    assert r.tendencia_mes == Decimal("20.00")  # (120−100)/1


def test_un_mes_sin_tendencia():
    r = calcular_sugerido_historico(
        ejecutados=[Decimal("100")], crec_pct=Decimal("0.10")
    )
    assert r.historia_incompleta is True
    assert r.prom_3m == Decimal("100.00")
    assert r.tendencia_mes == Decimal("0.00")  # 1 mes: no hay tendencia
    assert r.monto_sugerido == Decimal("110.00")  # 100 + 0 + 100×0.10


def test_sin_historia_todo_cero():
    r = calcular_sugerido_historico(ejecutados=[], crec_pct=Decimal("0.15"))
    assert r.historia_incompleta is True
    assert r.prom_3m == Decimal("0.00")
    assert r.tendencia_mes == Decimal("0.00")
    assert r.monto_sugerido == Decimal("0.00")


def test_sugerido_negativo_se_pisa_a_cero():
    # Decisión Kimi D-4: caída fuerte → sugerido daría <0; se pisa a 0, pero
    # tendencia_mes queda NEGATIVA visible (no se clampa).
    r = calcular_sugerido_historico(
        ejecutados=[Decimal("0"), Decimal("50"), Decimal("100")],
        crec_pct=Decimal("0"),
    )
    # prom_3m=50; tendencia=(0−100)/2=−50; crudo=50+(−50)+0=0 → borde
    assert r.tendencia_mes == Decimal("-50.00")
    assert r.monto_sugerido == Decimal("0.00")


def test_sugerido_muy_negativo_clamp_a_cero_no_negativo():
    r = calcular_sugerido_historico(
        ejecutados=[Decimal("0"), Decimal("10"), Decimal("200")],
        crec_pct=Decimal("0"),
    )
    # prom_3m=70; tendencia=(0−200)/2=−100; crudo=70−100=−30 → se pisa a 0
    assert r.tendencia_mes == Decimal("-100.00")
    assert r.monto_sugerido == Decimal("0.00")


def test_mas_de_tres_meses_usa_solo_los_tres_recientes():
    # Si llegan >3 (defensa), la fórmula usa E(M-1..M-3) — los 3 más recientes.
    r = calcular_sugerido_historico(
        ejecutados=[
            Decimal("75000000"),
            Decimal("61000000"),
            Decimal("48000000"),
            Decimal("999"),
        ],
        crec_pct=Decimal("0.15"),
    )
    assert r.monto_sugerido == Decimal("84033333.33")
    assert r.historia_incompleta is False
