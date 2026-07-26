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
    _adelanto_por_mes,
    _lote_por_mes,
    cartera_activa_mensual,
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


def test_proyectar_enhebra_overrides_de_escenario():
    # el escenario del artefacto: mes 0 en_cartera (sin cohorte nueva) + iniciales
    # override; adelanto override en el mes 1. proyectar() debe pasarlos al motor.
    r = proyectar(
        _params_simple(
            en_cartera_meses={0},
            iniciales_override={0: Decimal("26110000")},
            adelanto_override={1: Decimal("-999")},
        )
    )
    assert r.meses[0].cuotas_iniciales == Decimal("26110000.00")  # override
    assert r.meses[0].recaudo_credito == Decimal(
        "0.00"
    )  # en_cartera: sin cohorte nueva
    assert r.meses[1].adelanto == Decimal("-999.00")  # override


def test_presets_escenario_y_efecto_en_caja():
    # el escenario pesimista (más mora, menos recuperación) deja MENOS caja final.
    assert PRESETS_ESCENARIO["base"]["pct_mora"] == Decimal("0.03")
    assert PRESETS_ESCENARIO["pesimista"]["pct_mora"] == Decimal("0.06")
    pes = PRESETS_ESCENARIO["pesimista"]
    opt = PRESETS_ESCENARIO["optimista"]
    r_pes = proyectar(_params_simple(**pes, pct_default=Decimal("0.03")))
    r_opt = proyectar(_params_simple(**opt, pct_default=Decimal("0.03")))
    assert r_pes.caja_final < r_opt.caja_final


# ── Cartera previa: recaudo + activos de los 111 créditos preexistentes ──
# (PR-1 "Fidelidad": réplica de recaudoPrevio(w)/activosPrevios(w) del artefacto,
# líneas 451/473 — un TERCER sumando del recaudo de crédito, NO una tercera vía.)


def test_recaudo_credito_suma_cartera_previa_por_semana():
    # 1 moto nueva colocada jul-2026 (semana 18), cuota 100, plazo 6 → jul=500, ago=100.
    # jul cobra semanas 18-22; ago cobra 23-26 (ago 5,12,19,26).
    # previa: w18=1000, w22=2000 (ambas en jul) → previa jul=3000; w23=5000 (ago).
    modelos = [_modelo_unico(100, 0, 6)]
    previa = {18: Decimal("1000"), 22: Decimal("2000"), 23: Decimal("5000")}
    recaudo = recaudo_credito_mensual(
        colocacion_por_mes=[1, 0, 0, 0],
        modelos=modelos,
        mes_inicio=(2026, 7),
        recaudo_previo_por_semana=previa,
    )
    assert recaudo == [
        Decimal("3500"),  # 500 nuevas + 3000 previa
        Decimal("5100"),  # 100 nuevas + 5000 previa
        Decimal("0"),
        Decimal("0"),
    ]


def test_recaudo_credito_sin_previa_no_cambia():
    # sin serie previa (default), el recaudo es el de siempre (no-regresión).
    modelos = [_modelo_unico(100, 0, 6)]
    recaudo = recaudo_credito_mensual(
        colocacion_por_mes=[1, 0, 0, 0], modelos=modelos, mes_inicio=(2026, 7)
    )
    assert recaudo == [Decimal("500"), Decimal("100"), Decimal("0"), Decimal("0")]


def test_cartera_activa_suma_activos_previos_en_semana_de_referencia():
    # cartera al cierre = activos nuevos en la última semana de cobro + activos previos.
    # 1 moto jul (semana 18, plazo 6): activa en w_ref jul=22 (16<18<=22) → 1; ago
    # w_ref=26 (20<18<=26 es falso) → 0. previa: w22=30, w26=25.
    modelos = [_modelo_unico(100, 0, 6)]
    activos_previos = {22: 30, 26: 25}
    cartera = cartera_activa_mensual(
        colocacion_por_mes=[1, 0, 0, 0],
        modelos=modelos,
        mes_inicio=(2026, 7),
        activos_previos_por_semana=activos_previos,
    )
    assert cartera[0] == 31  # 1 nueva + 30 previa
    assert cartera[1] == 25  # 0 nuevas + 25 previa


def test_recaudo_omite_cohortes_en_cartera():
    # motos marcadas en_cartera (ya viven en la previa) NO crean cohortes nuevas:
    # su recaudo llega por la serie previa, no por aquí (réplica del `continue` del
    # artefacto). Sin previa y con la única colocación en_cartera → recaudo 0.
    modelos = [_modelo_unico(100, 0, 6)]
    recaudo = recaudo_credito_mensual(
        colocacion_por_mes=[2, 0, 0, 0],
        modelos=modelos,
        mes_inicio=(2026, 7),
        en_cartera_meses={0},
    )
    assert recaudo == [Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")]


def test_cartera_omite_cohortes_en_cartera():
    modelos = [_modelo_unico(100, 0, 6)]
    cartera = cartera_activa_mensual(
        colocacion_por_mes=[2, 0, 0, 0],
        modelos=modelos,
        mes_inicio=(2026, 7),
        en_cartera_meses={0},
    )
    assert cartera[0] == 0  # las 2 motos en_cartera no cuentan como cohorte nueva


def test_iniciales_rampa_con_apache_override_es_entero():
    # mes de RAMPA: split ENTERO con el apache override. total=48, apache=17 →
    # raider(base)=31; iniciales = 31×1000 + 17×2000 = 65000.
    raider = ModeloProyeccion(
        "Raider", Decimal("100"), Decimal("1000"), 78, Decimal("0.70")
    )
    apache = ModeloProyeccion(
        "Apache", Decimal("120"), Decimal("2000"), 78, Decimal("0.30")
    )
    iniciales = cuotas_iniciales_mensual(
        [48], [raider, apache], apache_por_mes={0: 17}, meses_rampa={0}
    )
    assert iniciales == [Decimal("65000")]


def test_iniciales_no_rampa_es_fraccionario():
    # mes NO-rampa (default): split FRACCIONARIO (réplica del artefacto, no entero).
    # 51 motos: 51×0.70×1000 + 51×0.30×2000 = 35700 + 30600 = 66300.
    raider = ModeloProyeccion(
        "Raider", Decimal("100"), Decimal("1000"), 78, Decimal("0.70")
    )
    apache = ModeloProyeccion(
        "Apache", Decimal("120"), Decimal("2000"), 78, Decimal("0.30")
    )
    iniciales = cuotas_iniciales_mensual([51], [raider, apache])
    assert iniciales[0] == Decimal("66300.00")


def test_iniciales_override_tiene_precedencia():
    raider = ModeloProyeccion(
        "Raider", Decimal("100"), Decimal("1000"), 78, Decimal("0.70")
    )
    apache = ModeloProyeccion(
        "Apache", Decimal("120"), Decimal("2000"), 78, Decimal("0.30")
    )
    iniciales = cuotas_iniciales_mensual(
        [48], [raider, apache], iniciales_override={0: Decimal("80810000")}
    )
    assert iniciales == [Decimal("80810000")]


def test_adelanto_primer_mes_cero_override_y_proyectado():
    # m0=0 (MAY); JUN override −80.81M; JUL proyectado −50×970000.
    adelanto = _adelanto_por_mes(
        [20, 48, 50],
        Decimal("970000"),
        adelanto_override={1: Decimal("-80810000")},
    )
    assert adelanto == [
        Decimal("0"),
        Decimal("-80810000"),
        Decimal("-48500000"),
    ]


def test_lote_override_rampa_entero_y_no_rampa_fraccionario():
    raider = ModeloProyeccion(
        "Raider",
        Decimal("5638974"),
        Decimal("0"),
        78,
        Decimal("0.70"),
        costo_moto=Decimal("5638974"),
    )
    apache = ModeloProyeccion(
        "Apache",
        Decimal("6818517"),
        Decimal("0"),
        78,
        Decimal("0.30"),
        costo_moto=Decimal("6818517"),
    )
    # m0 override; m1 rampa entero (48, apache 17): 31×5638974 + 17×6818517 = 290722983;
    # m2 no-rampa fraccionario: 50×0.7×5638974 + 50×0.3×6818517.
    lote = _lote_por_mes(
        [20, 48, 50],
        [raider, apache],
        apache_por_mes={1: 17},
        lote_override={0: Decimal("109816454")},
        meses_rampa={0, 1},
    )
    assert lote[0] == Decimal("109816454")
    assert lote[1] == Decimal("290722983")
    frac = Decimal("50") * Decimal("0.70") * Decimal("5638974") + Decimal(
        "50"
    ) * Decimal("0.30") * Decimal("6818517")
    assert lote[2] == frac


def test_proyectar_enhebra_cartera_previa_en_recaudo_y_cartera():
    # jul-2026 cobra semanas 18-22; previa de 1000/semana → +5000 al recaudo de crédito
    # de julio; 40 activos previos en w_ref=22 → +40 a la cartera de julio.
    previa_recaudo = {w: Decimal("1000") for w in (18, 19, 20, 21, 22)}
    previa_activos = {22: 40}
    r_sin = proyectar(_params_simple())
    r_con = proyectar(
        _params_simple(
            recaudo_previo_por_semana=previa_recaudo,
            activos_previos_por_semana=previa_activos,
        )
    )
    assert r_con.meses[0].recaudo_credito == r_sin.meses[0].recaudo_credito + Decimal(
        "5000.00"
    )
    assert r_con.meses[0].cartera == r_sin.meses[0].cartera + 40
