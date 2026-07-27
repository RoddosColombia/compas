# backend/tests/test_impactos.py
"""Capa de impactos (D1): deltas declarativos sobre la serie que YA produjo el motor.
Post-proceso PURO — ni una línea del motor se toca. Regla de oro del sprint: `ajuste
cero == base bit a bit`, y todo delta se re-acumula en Decimal con la MISMA mecánica de
caja del motor (primer mes fijo; caja[m]=caja[m-1]+flujo[m]).
"""

from decimal import Decimal

from app.proyeccion.impactos import Ajuste, aplicar_impactos
from app.proyeccion.motor import ModeloProyeccion, ParametrosMotor, proyectar


def _params(**over):
    base = dict(
        mes_inicio=(2026, 7),
        horizonte_meses=6,
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


def _base():
    p = _params()
    return proyectar(p), p.caja_minima


# ── Regla de oro: ajuste cero == base bit a bit ─────────────────────────────


def test_ajuste_cero_identico_a_base_bit_a_bit():
    r, umbral = _base()
    aj = aplicar_impactos(r, [], umbral)
    assert len(aj.meses) == len(r.meses)
    for a, b in zip(aj.meses, r.meses, strict=True):
        assert a.mes == b.mes
        assert a.flujo == b.flujo  # bit a bit
        assert a.caja == b.caja
        assert a.estado == b.estado
    assert aj.kpis.piso_caja == r.piso_caja
    assert aj.kpis.mes_mas_ajustado == r.mes_mas_ajustado
    assert aj.kpis.meses_bajo_minimo == r.meses_bajo_minimo
    assert aj.kpis.caja_final == r.caja_final
    assert aj.kpis.capital_requerido == r.capital_requerido
    assert aj.kpis.runway_meses == r.runway_meses


# ── Gasto absoluto: mueve flujo y caja EXACTAMENTE valor × meses ─────────────


def test_gasto_absoluto_mueve_flujo_y_caja_exacto():
    r, umbral = _base()
    v = Decimal("3000")
    # desde el 2º mes (índice 1) hasta el final: 5 meses afectados (1..5)
    aj = aplicar_impactos(
        r,
        [Ajuste("Arriendo", "gasto", "absoluto", v, "2026-08", None)],
        umbral,
    )
    for i, (a, b) in enumerate(zip(aj.meses, r.meses, strict=True)):
        if i == 0:
            assert a.flujo == b.flujo  # antes de mes_inicio: intacto
        else:
            assert a.flujo == b.flujo - v  # +gasto => flujo baja en v
    # caja final cae EXACTO v × (meses afectados)
    assert aj.kpis.caja_final == r.caja_final - v * Decimal("5")


def test_gasto_absoluto_reduccion_sube_la_caja():
    r, umbral = _base()
    # un recorte de gasto = valor negativo => flujo sube
    aj = aplicar_impactos(
        r,
        [Ajuste("Recorte", "gasto", "absoluto", Decimal("-500"), "2026-07", None)],
        umbral,
    )
    # mes 0 es fijo (flujo[0] no mueve caja); desde el mes 1 sube 500/mes
    assert aj.kpis.caja_final == r.caja_final + Decimal("500") * Decimal("5")


# ── Porcentajes: sobre la línea correcta del motor ──────────────────────────


def test_gasto_porcentaje_sobre_gastos_fijos():
    r, umbral = _base()
    pct = Decimal("0.10")
    aj = aplicar_impactos(
        r,
        [Ajuste("Gasto +10%", "gasto", "porcentaje", pct, "2026-08", None)],
        umbral,
    )
    for i, (a, b) in enumerate(zip(aj.meses, r.meses, strict=True)):
        if i == 0:
            assert a.flujo == b.flujo
        else:
            # gastos_fijos del motor es NEGATIVO => delta negativo (más gasto)
            esperado = (b.flujo + (b.gastos_fijos * pct)).quantize(Decimal("0.01"))
            assert a.flujo == esperado


def test_ingreso_porcentaje_sobre_neto():
    r, umbral = _base()
    pct = Decimal("0.10")
    aj = aplicar_impactos(
        r,
        [Ajuste("Ventas +10%", "ingreso", "porcentaje", pct, "2026-08", None)],
        umbral,
    )
    for i, (a, b) in enumerate(zip(aj.meses, r.meses, strict=True)):
        if i == 0:
            assert a.flujo == b.flujo
        else:
            esperado = (b.flujo + (b.neto * pct)).quantize(Decimal("0.01"))
            assert a.flujo == esperado


def test_ingreso_absoluto_suma_al_flujo():
    r, umbral = _base()
    v = Decimal("2000")
    aj = aplicar_impactos(
        r,
        [Ajuste("Otro ingreso", "ingreso", "absoluto", v, "2026-08", None)],
        umbral,
    )
    assert aj.kpis.caja_final == r.caja_final + v * Decimal("5")


# ── Vigencia: antes de mes_inicio y después de mes_fin, intacto ─────────────


def test_vigencia_acotada_por_mes_inicio_y_mes_fin():
    r, umbral = _base()
    v = Decimal("1000")
    # solo sep-2026 (índice 2) y oct-2026 (índice 3)
    aj = aplicar_impactos(
        r,
        [Ajuste("Puntual", "gasto", "absoluto", v, "2026-09", "2026-10")],
        umbral,
    )
    for i, (a, b) in enumerate(zip(aj.meses, r.meses, strict=True)):
        if i in (2, 3):
            assert a.flujo == b.flujo - v
        else:
            assert a.flujo == b.flujo  # intacto fuera de la ventana


def test_mes_inicio_futuro_fuera_del_horizonte_no_hace_nada():
    r, umbral = _base()
    aj = aplicar_impactos(
        r,
        [Ajuste("Tarde", "gasto", "absoluto", Decimal("999"), "2030-01", None)],
        umbral,
    )
    for a, b in zip(aj.meses, r.meses, strict=True):
        assert a.flujo == b.flujo
        assert a.caja == b.caja


# ── Varios ajustes se suman en el mismo mes ─────────────────────────────────


def test_multiples_ajustes_se_suman():
    r, umbral = _base()
    aj = aplicar_impactos(
        r,
        [
            Ajuste("Arriendo", "gasto", "absoluto", Decimal("1000"), "2026-08", None),
            Ajuste("Ingreso", "ingreso", "absoluto", Decimal("400"), "2026-08", None),
        ],
        umbral,
    )
    # neto por mes afectado: -1000 + 400 = -600
    assert aj.kpis.caja_final == r.caja_final - Decimal("600") * Decimal("5")


def test_delta_por_mes_reportado():
    r, umbral = _base()
    aj = aplicar_impactos(
        r,
        [Ajuste("Arriendo", "gasto", "absoluto", Decimal("1000"), "2026-08", None)],
        umbral,
    )
    assert aj.delta_por_mes[0] == Decimal("0.00")
    assert all(d == Decimal("-1000.00") for d in aj.delta_por_mes[1:])
