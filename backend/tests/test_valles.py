# backend/tests/test_valles.py
"""Valles de caja (D1 §3) — los HITOS de solvencia (decisión CEO #3). Un valle es un
mínimo local de la caja cuya cercanía al umbral lo hace relevante; se explica con los
egresos del mes que más se apartan de su promedio móvil. Detección pura sobre cualquier
serie de `MesProyeccion` (base o ajustada).
"""

from decimal import Decimal

from app.proyeccion.motor import MesProyeccion
from app.proyeccion.valles import detectar_valles

_Z = Decimal("0.00")


def _fila(mes: str, caja: str, **eg) -> MesProyeccion:
    d = dict(
        motos=0,
        cartera=0,
        recaudo_credito=_Z,
        cuotas_iniciales=_Z,
        ingreso_bruto=_Z,
        neto=_Z,
        provision=_Z,
        gastos_fijos=Decimal("-1000.00"),
        gps=_Z,
        costo_nueva=_Z,
        adelanto=_Z,
        pago_inventario=_Z,
        fondeo=_Z,
        int_deuda=_Z,
        iva=_Z,
        egresos=_Z,
        flujo=_Z,
        estado="ok",
    )
    d.update({k: Decimal(v) for k, v in eg.items()})
    return MesProyeccion(mes=mes, caja=Decimal(caja), **d)


def _serie(cajas: list[str], **por_mes) -> list[MesProyeccion]:
    filas = []
    for i, c in enumerate(cajas):
        eg = {k: v[i] for k, v in por_mes.items()}
        filas.append(_fila(f"2026-{i + 1:02d}", c, **eg))
    return filas


def test_detecta_un_valle_local_relevante():
    serie = _serie(["50000", "40000", "25000", "35000", "45000", "60000"])
    valles = detectar_valles(serie, Decimal("10000"))
    assert len(valles) == 1
    v = valles[0]
    assert v.mes == "2026-03"  # índice 2
    assert v.caja == Decimal("25000")
    assert v.distancia_al_umbral == Decimal("15000")  # 25000 - 10000
    assert v.meses_para_prepararse == 2


def test_valle_holgado_no_es_relevante():
    # mínimo 40000 > umbral(10000) × 3 = 30000 => ningún valle relevante
    serie = _serie(["50000", "45000", "40000", "45000", "50000"])
    assert detectar_valles(serie, Decimal("10000")) == []


def test_valle_que_perfora_es_relevante_y_distancia_negativa():
    serie = _serie(["50000", "8000", "20000"])
    valles = detectar_valles(serie, Decimal("10000"))
    assert len(valles) == 1
    assert valles[0].caja == Decimal("8000")
    assert valles[0].distancia_al_umbral == Decimal("-2000")  # perfora


def test_factor_atencion_configurable():
    serie = _serie(["50000", "45000", "28000", "45000", "50000"])
    # con factor 3: umbral×3 = 30000 => 28000 es valle
    assert len(detectar_valles(serie, Decimal("10000"))) == 1
    # con factor 2: umbral×2 = 20000 => 28000 ya NO es relevante
    assert detectar_valles(serie, Decimal("10000"), factor_atencion=Decimal("2")) == []


def test_causas_top3_por_desvio_del_promedio_movil():
    # valle en índice 3; ese mes el pago de lote se dispara sobre lo normal.
    serie = _serie(
        ["50000", "48000", "46000", "20000", "44000", "46000", "48000"],
        pago_inventario=[
            "-10000",
            "-10000",
            "-10000",
            "-50000",
            "-10000",
            "-10000",
            "-10000",
        ],
    )
    valles = detectar_valles(serie, Decimal("10000"))
    assert len(valles) == 1
    causas = valles[0].causas
    assert causas[0].concepto == "pago_inventario"
    assert causas[0].monto == Decimal("50000")  # magnitud del mes del valle
    # vecinos promedian 10000 => 40000 por encima = 4.0 (400%)
    assert causas[0].vs_promedio == Decimal("4.0000")
    assert causas[0].etiqueta  # lenguaje llano presente


def test_iva_como_causa_con_promedio_cero_no_revienta():
    serie = _serie(
        ["50000", "48000", "18000", "44000", "46000"],
        iva=["0", "0", "-30000", "0", "0"],
    )
    valles = detectar_valles(serie, Decimal("10000"))
    assert valles[0].causas[0].concepto == "iva"
    assert valles[0].causas[0].vs_promedio is None  # promedio 0 => relativo indefinido


def test_solo_egresos_por_encima_de_lo_normal_explican_el_valle():
    # un egreso MENOR que su promedio no es "causa" del hueco
    serie = _serie(
        ["50000", "48000", "22000", "44000", "46000"],
        pago_inventario=["-30000", "-30000", "-5000", "-30000", "-30000"],
        gastos_fijos=["-1000", "-1000", "-40000", "-1000", "-1000"],
    )
    valles = detectar_valles(serie, Decimal("10000"))
    conceptos = [c.concepto for c in valles[0].causas]
    assert "gastos_fijos" in conceptos  # subió sobre lo normal
    assert "pago_inventario" not in conceptos  # bajó => no explica el valle


def test_multiples_valles_en_orden_cronologico():
    serie = _serie(["50000", "20000", "45000", "18000", "40000"])
    valles = detectar_valles(serie, Decimal("10000"))
    assert [v.mes for v in valles] == ["2026-02", "2026-04"]
