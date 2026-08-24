# backend/tests/test_sup6_base_mora.py
"""SUP-6 (CEO 2026-08-23) — "Tiene q ser calculado solo a las cuotas semanales no a las
cuotas iniciales."

La cuota inicial se paga DE CONTADO en el momento de la colocación: no puede caer en
mora ni incumplirse. Aplicarle mora/default (lo que hacía el motor) inventa una fuga
que en la vida real no existe. El modelo v9.1 de Fabián ya lo hacía bien
(`FC!17 = −L13×L6`, con L13 = "Recaudo cuotas mensuales") y el propio motor ya usaba
este criterio para el fondo AVAL (`aval = −recaudo × pct`, "la cuota inicial no se
asegura"). Esto lo hace consistente.

Editable, nunca clavado (regla del CEO: todo supuesto que mueva la proyección se edita):
`mora_sobre_recaudo`. El default del MOTOR es False = la semántica del artefacto, para
que el GOLDEN MASTER siga siendo bit a bit; el default del DOMINIO (lo que corre en
prod) es True = la regla del CEO.
"""

from decimal import Decimal

from app.proyeccion.motor import (
    ModeloProyeccion,
    ParametrosMotor,
    neto_por_mora,
    proyectar,
)


def _motor(**over) -> ParametrosMotor:
    base = dict(
        mes_inicio=(2026, 9),
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
        caja_inicial=Decimal("665715578"),
        caja_minima=Decimal("30000000"),
    )
    base.update(over)
    return ParametrosMotor(**base)


# ── la función pura ──


def test_base_mora_explicita_deja_la_inicial_fuera():
    """Con `base_mora` la mora/default/provisión se calculan sobre ESA base, pero el
    neto sigue partiendo del bruto (la inicial entra a caja completa)."""
    aj = neto_por_mora(
        bruto=Decimal("118341668"),  # recaudo 54.624.168 + inicial 63.717.500
        pct_mora=Decimal("0.08"),
        pct_recuperacion=Decimal("0.65"),
        pct_default=Decimal("0.03"),
        pct_provision=Decimal("0.02"),
        base_mora=Decimal("54624168"),  # solo las cuotas semanales
    )
    assert aj.mora == Decimal("-4369933.44")  # 54.624.168 × 8 %
    assert aj.default == Decimal("-1638725.04")  # 54.624.168 × 3 %
    assert aj.provision == Decimal("-1092483.36")  # 54.624.168 × 2 %
    # el neto NO pierde la cuota inicial
    assert aj.neto == Decimal("118341668") + aj.mora + aj.recuperacion + aj.default


def test_sin_base_mora_el_comportamiento_es_el_de_siempre():
    """Candado del golden: sin el parámetro, la base es el bruto (artefacto)."""
    aj = neto_por_mora(
        bruto=Decimal("118341668"),
        pct_mora=Decimal("0.08"),
        pct_recuperacion=Decimal("0.65"),
        pct_default=Decimal("0.03"),
    )
    assert aj.mora == Decimal("-9467333.44")  # 118.341.668 × 8 %


# ── el motor ──


def test_la_mora_del_motor_cae_solo_sobre_las_cuotas_semanales():
    r = proyectar(_motor(mora_sobre_recaudo=True))
    for f in r.meses:
        assert f.mora == -(f.recaudo_credito * Decimal("0.08")).quantize(
            Decimal("0.01")
        ), f.mes
        assert f.default == -(f.recaudo_credito * Decimal("0.03")).quantize(
            Decimal("0.01")
        ), f.mes


def test_la_cuota_inicial_entra_completa_a_la_caja():
    """La diferencia entre las dos bases es exactamente la mora+default que ya NO se le
    descuenta a la cuota inicial."""
    con = proyectar(_motor(mora_sobre_recaudo=True))
    sin = proyectar(_motor(mora_sobre_recaudo=False))
    f_con, f_sin = con.meses[3], sin.meses[3]
    inicial = f_con.cuotas_iniciales
    assert inicial > 0
    # mora + default que se dejan de aplicar a la inicial (la recuperación las sigue)
    esperado = (inicial * (Decimal("0.08") + Decimal("0.03"))).quantize(Decimal("0.01"))
    ganado = f_con.neto - f_sin.neto
    # el neto sube ese monto, menos/más la recuperación rezagada de esa misma mora
    assert ganado > 0
    assert ganado <= esperado + Decimal("0.01")


def test_el_default_del_motor_no_cambia_nada_golden():
    """Sin tocar el parámetro, la serie es idéntica (el golden master lo exige)."""
    a = proyectar(_motor())
    b = proyectar(_motor(mora_sobre_recaudo=False))
    assert [f.neto for f in a.meses] == [f.neto for f in b.meses]
    assert [f.caja for f in a.meses] == [f.caja for f in b.meses]


def test_la_invariante_del_neto_se_mantiene():
    """SUP-5: bruto + mora + recuperación + default == neto, con cualquier base."""
    for flag in (True, False):
        r = proyectar(_motor(mora_sobre_recaudo=flag))
        for f in r.meses:
            assert f.neto == (
                f.ingreso_bruto + f.mora + f.recuperacion + f.default
            ).quantize(Decimal("0.01")), (flag, f.mes)


# ── el dominio: la regla del CEO es el default de PROD y se puede editar ──


def test_el_dominio_arranca_con_la_regla_del_ceo():
    from app.domain.parametros_proyeccion import ParametrosProyeccion

    p = ParametrosProyeccion(
        vigente_desde="2026-08-01",
        caja_inicial=Decimal("665715578"),
        caja_minima=Decimal("30000000"),
        motos_base=60,
        crec_pct_mensual=Decimal("0.10"),
        horizonte_meses=144,
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
    )
    assert p.mora_sobre_recaudo is True  # la cuota inicial es de contado
    assert (
        p.model_copy(update={"mora_sobre_recaudo": False}).mora_sobre_recaudo is False
    )


def test_los_supuestos_visibles_declaran_la_base():
    """La pantalla tiene que decir SOBRE QUÉ se calcula la mora (SUP-5: nada oculto)."""
    from app.domain.parametros_proyeccion import ParametrosProyeccion
    from app.proyeccion.service import _supuestos_visibles

    p = ParametrosProyeccion(
        vigente_desde="2026-08-01",
        caja_inicial=Decimal("665715578"),
        caja_minima=Decimal("30000000"),
        motos_base=60,
        crec_pct_mensual=Decimal("0.10"),
        horizonte_meses=144,
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
    )
    assert _supuestos_visibles(p, "base")["mora_sobre_recaudo"] is True
