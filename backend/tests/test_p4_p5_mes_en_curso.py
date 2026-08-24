# backend/tests/test_p4_p5_mes_en_curso.py
"""P4 + P5 del ciclo mensual — EL MES EN CURSO ES EL OBJETIVO, Y ES UN MES COMPLETO.

Contrato: `docs/COMPAS_Ciclo_Mensual.md` §«Paso 1» y §«Regla de no-solape».

    "El mes en curso son proyecciones basadas en los objetivos planteados... el mes en
    curso dentro de la gráfica es basado en los objetivos propuestos para ese mes, es
    decir proyección." (CEO 2026-08-23)

Agosto-2026 mostraba 112.333.009 de ingreso cuando la realidad del mes son 196.984.210,
por DOS recortes al mismo mes:

  P5 — la carga del cronograma descartaba las cuotas PAGADAS, así que agosto entraba con
       2 semanas (34.992.968) en vez del mes completo. El mes en curso es un mes
       completo de proyección: su recaudo es el del MES, no el del resto del mes.
  P4 — la rampa del mes en curso proyectaba el REMANENTE hacia la meta (35), no la META
       (70), y el gasto se anclaba con la Regla A (ejecutado + lo que resta del
       presupuesto) en vez de mostrar el presupuesto.

Las dos van juntas: si solo se arregla P5, las 35 motos ya colocadas aportarían su
recaudo por la serie Y otra vez por la rampa del motor. La **regla de no-solape** lo
cierra: la cartera existente se corta al cierre del mes ANTERIOR; los créditos
originados dentro del mes en curso son parte del objetivo y los proyecta el motor.

Decisiones que este contrato SUPERA (autorizadas por el CEO): la Regla A / D-08 para el
mes en curso, y la automatización de la rampa de SUP-4.
"""

from datetime import date
from decimal import Decimal
from io import BytesIO

from app.cartera_previa.cronograma import parsear_cronograma, rampa_mes_en_curso
from openpyxl import Workbook

ENCABEZADOS = [
    "Crédito",
    "Cuota #",
    "Fecha Programada",
    "Monto Total",
    "Capital",
    "Interés",
    "Pagado",
    "Saldo",
    "Estado",
    "Mora",
]
HOY = date(2026, 8, 22)  # mes en curso = agosto, con 3 semanas ya corridas


def _xlsx(filas: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Generado: 2026-08-19", "Usuario: andres", "Versión: 0.1.0"])
    ws.append(ENCABEZADOS)
    for f in filas:
        ws.append(f)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cuota(credito, n, fecha, monto, estado, saldo=None):
    return [
        credito,
        n,
        fecha,
        monto,
        monto,
        0,
        monto if estado == "pagada" else 0,
        saldo if saldo is not None else (0 if estado == "pagada" else monto),
        estado,
        0,
    ]


# ══════════════════════ P5 · el mes en curso es un mes COMPLETO ══════════════════════


def test_el_mes_en_curso_cuenta_sus_cuotas_YA_PAGADAS():
    """Antes se descartaban por 'pagada' y agosto perdía sus primeras 3 semanas."""
    filas = [
        _cuota("LB-001", 0, "2026-06-03", 1620000, "pagada"),  # originado en junio
        _cuota("LB-001", 8, "2026-08-05", 184900, "pagada"),  # ya cobrada
        _cuota("LB-001", 9, "2026-08-12", 184900, "pagada"),  # ya cobrada
        _cuota("LB-001", 10, "2026-08-19", 184900, "pagada"),  # ya cobrada
        _cuota("LB-001", 11, "2026-08-26", 184900, "pendiente"),
    ]
    r = parsear_cronograma(_xlsx(filas), HOY, mes_en_curso=(2026, 8))
    total_agosto = sum(f["recaudo"] for f in r.serie if 23 <= f["semana_global"] <= 26)
    assert total_agosto == Decimal("739600.00")  # las CUATRO cuotas del mes


def test_en_el_mes_en_curso_una_parcial_cuenta_su_cuota_COMPLETA():
    """El mes debe proyectar lo que le toca cobrar, no lo que le falta por cobrar."""
    filas = [
        _cuota("LB-001", 0, "2026-06-03", 1620000, "pagada"),
        _cuota("LB-001", 8, "2026-08-05", 184900, "parcial", saldo=100000),
    ]
    r = parsear_cronograma(_xlsx(filas), HOY, mes_en_curso=(2026, 8))
    assert sum(f["recaudo"] for f in r.serie) == Decimal("184900.00")


def test_en_un_mes_FUTURO_una_cuota_ya_pagada_no_se_proyecta():
    """Un prepago de septiembre ya entró: no va a llegar otra vez en septiembre."""
    filas = [
        _cuota("LB-001", 0, "2026-06-03", 1620000, "pagada"),
        _cuota("LB-001", 20, "2026-09-30", 184900, "pagada"),  # prepagada
        _cuota("LB-001", 21, "2026-10-07", 184900, "pendiente"),
    ]
    r = parsear_cronograma(_xlsx(filas), HOY, mes_en_curso=(2026, 8))
    assert sum(f["recaudo"] for f in r.serie) == Decimal("184900.00")


def test_en_un_mes_FUTURO_una_parcial_cuenta_solo_su_saldo():
    filas = [
        _cuota("LB-001", 0, "2026-06-03", 1620000, "pagada"),
        _cuota("LB-001", 20, "2026-09-30", 184900, "parcial", saldo=84900),
    ]
    r = parsear_cronograma(_xlsx(filas), HOY, mes_en_curso=(2026, 8))
    assert sum(f["recaudo"] for f in r.serie) == Decimal("84900.00")


def test_lo_vencido_de_meses_ANTERIORES_se_sigue_reportando_aparte():
    """Mora real medida: se reporta, no se proyecta (no se inventa cuándo entra)."""
    filas = [
        _cuota("LB-001", 0, "2026-06-03", 1620000, "pagada"),
        _cuota("LB-001", 4, "2026-07-08", 184900, "pendiente"),  # vencida, julio
        _cuota("LB-001", 11, "2026-08-26", 184900, "pendiente"),
    ]
    r = parsear_cronograma(_xlsx(filas), HOY, mes_en_curso=(2026, 8))
    assert r.vencido_sin_pagar == Decimal("184900")
    assert r.creditos_en_mora == 1
    assert sum(f["recaudo"] for f in r.serie) == Decimal("184900.00")


# ═══════════════ P5 · regla de NO-SOLAPE (el corte al cierre anterior) ═══════════════


def test_los_creditos_originados_EN_el_mes_en_curso_quedan_FUERA_de_la_serie():
    """Son parte del objetivo del mes: los proyecta el motor con la cuota nueva. Si
    entraran también por la serie, agosto contaría dos veces las motos ya colocadas."""
    filas = [
        # originado en julio → SÍ entra (cartera existente al cierre anterior)
        _cuota("LB-VIEJO", 0, "2026-07-01", 1620000, "pagada"),
        _cuota("LB-VIEJO", 6, "2026-08-12", 184900, "pagada"),
        # originado en AGOSTO → NO entra (es del objetivo del mes)
        _cuota("LB-NUEVO", 0, "2026-08-05", 1620000, "pagada"),
        _cuota("LB-NUEVO", 1, "2026-08-12", 184900, "pagada"),
        _cuota("LB-NUEVO", 2, "2026-08-19", 184900, "pendiente"),
        _cuota("LB-NUEVO", 3, "2026-09-02", 184900, "pendiente"),
    ]
    r = parsear_cronograma(_xlsx(filas), HOY, mes_en_curso=(2026, 8))
    # solo la cuota del crédito viejo
    assert sum(f["recaudo"] for f in r.serie) == Decimal("184900.00")
    # pero la COLOCACIÓN de agosto sí se cuenta (la necesita el termómetro de P6)
    assert r.colocaciones_por_mes["2026-08"] == 1


def test_un_desembolso_nunca_entra_al_recaudo():
    """La cuota 0 es la cuota inicial: la aporta el motor, no la serie."""
    filas = [
        _cuota("LB-001", 0, "2026-06-03", 1620000, "pagada"),
        _cuota("LB-001", 8, "2026-08-05", 184900, "pagada"),
    ]
    r = parsear_cronograma(_xlsx(filas), HOY, mes_en_curso=(2026, 8))
    assert sum(f["recaudo"] for f in r.serie) == Decimal("184900.00")


def test_un_credito_sin_cuota_cero_se_considera_preexistente():
    """Los créditos viejos pueden no traer su desembolso en el export: se asumen
    originados antes (regla 7: no se descarta plata sin razón explícita)."""
    filas = [_cuota("LB-ANTIGUO", 40, "2026-08-19", 184900, "pendiente")]
    r = parsear_cronograma(_xlsx(filas), HOY, mes_en_curso=(2026, 8))
    assert sum(f["recaudo"] for f in r.serie) == Decimal("184900.00")


# ═════════════════════ P4 · la rampa del mes en curso es la META ═════════════════════


def test_la_rampa_del_mes_en_curso_es_la_meta_no_el_remanente():
    """SUPERA la automatización de SUP-4: agosto proyecta las 70 de la meta, no las 35
    que faltaban. Lo ya logrado es lectura de desviación (P6), no insumo del motor."""
    assert rampa_mes_en_curso({"2026-08": 35}, (2026, 8), 70) == {"2026-08": 70}


def test_la_meta_manda_aunque_ya_se_haya_superado():
    """Si se colocaron 80 con meta 70, la gráfica sigue mostrando el objetivo; el
    'llevamos 80 de 70' es el termómetro."""
    assert rampa_mes_en_curso({"2026-08": 80}, (2026, 8), 70) == {"2026-08": 70}


def test_sin_colocaciones_la_rampa_sigue_siendo_la_meta():
    assert rampa_mes_en_curso({}, (2026, 8), 70) == {"2026-08": 70}


# ══════════ P4 · el gasto del mes en curso es el PRESUPUESTO, no la Regla A ══════════


def _ancla(estado, ejecutado, definido):
    from app.proyeccion.ejecucion.service import AnclaMes

    return AnclaMes(
        estado=estado,
        ejecutado_por_rubro_id=ejecutado,
        definido_por_rubro_id=definido,
        ingreso_real=None,
    )


def _taxonomia():
    """La taxonomía completa (B12 falla ruidoso si falta un código del mapeo) + el
    rubro `r1` de gasto fijo con el que se prueba."""
    from app.proyeccion.ejecucion.lectura import _CONCEPTO_POR_CODIGO, RubroInfo

    rubros = [
        RubroInfo(
            id=f"sys-{cod}",
            codigo=cod,
            grupo="otros",
            nombre=f"Rubro {cod}",
            es_sistema=True,
        )
        for cod in _CONCEPTO_POR_CODIGO
    ]
    rubros.append(
        RubroInfo(
            id="r1",
            codigo="2010",  # Arriendos → concepto `gastos_fijos`
            grupo="operacion",
            nombre="Arriendos",
            es_sistema=False,
        )
    )
    return rubros


def test_el_mes_en_curso_muestra_el_presupuesto_no_el_ejecutado_mas_resto():
    """Regla A (D-08) queda solo para meses cerrados. El ejecutado va al termómetro."""
    from app.proyeccion.ejecucion.service import _egresos_anclados_del_mes

    egr = _egresos_anclados_del_mes(
        _ancla(
            "en_ejecucion", {"r1": Decimal("150000000")}, {"r1": Decimal("208000000")}
        ),
        rubros=_taxonomia(),
        neutros_ids=set(),
    )
    assert egr["gastos_fijos"] == Decimal("208000000")  # el presupuesto, tal cual


def test_el_mes_en_curso_muestra_el_presupuesto_aunque_se_haya_gastado_MAS():
    """Antes la Regla A tomaba el máximo (el ejecutado); ahora manda el presupuesto: el
    sobregiro es desviación, no proyección."""
    from app.proyeccion.ejecucion.service import _egresos_anclados_del_mes

    egr = _egresos_anclados_del_mes(
        _ancla(
            "en_ejecucion", {"r1": Decimal("250000000")}, {"r1": Decimal("208000000")}
        ),
        rubros=_taxonomia(),
        neutros_ids=set(),
    )
    assert egr["gastos_fijos"] == Decimal("208000000")


def test_un_mes_en_curso_SIN_presupuesto_no_se_ancla():
    """Fail-safe: sin presupuesto definido no se ancla en 0 (eso borraría el gasto del
    mes); queda el motor paramétrico, que es la mejor fuente disponible."""
    from app.proyeccion.ejecucion.service import _es_anclable

    assert not _es_anclable(_ancla("en_ejecucion", {"r1": Decimal("150000000")}, {}))
    assert _es_anclable(_ancla("en_ejecucion", {}, {"r1": Decimal("208000000")}))
    # un mes CERRADO se ancla siempre (su verdad es el libro, no el presupuesto)
    assert _es_anclable(_ancla("cerrado", {}, {}))


def test_un_mes_cerrado_sigue_usando_el_ejecutado_real():
    """El contrato solo cambia el mes EN CURSO. El histórico es el libro (regla 4)."""
    from app.proyeccion.ejecucion.service import _egresos_anclados_del_mes

    egr = _egresos_anclados_del_mes(
        _ancla("cerrado", {"r1": Decimal("150000000")}, {"r1": Decimal("208000000")}),
        rubros=_taxonomia(),
        neutros_ids=set(),
    )
    assert egr["gastos_fijos"] == Decimal("150000000")
