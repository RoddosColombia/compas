# backend/tests/test_e1_anclaje.py
"""E1 · P2 — capa de anclaje (función pura sobre snapshots).

B1 (sin ancla → base bit a bit) · B2 (cerrado → ejecutado real + re-acumulación) ·
B3 (Regla A, incl. ejecutado>definido) · B4 (futuro con presupuesto → definido) ·
B5 (futuro sin presupuesto → motor) · B6 (invariante neto + egresos == flujo al peso) ·
A3 (fixture real de julio 2026 verificando B2 + B6 sobre la realidad de producción)."""

import json
from decimal import Decimal
from pathlib import Path

from app.proyeccion.ejecucion.lectura import RubroInfo, mapear_a_conceptos
from app.proyeccion.ejecucion.service import (
    CERRADO,
    EN_EJECUCION,
    PRESUPUESTO,
    AnclaMes,
    anclar,
)
from app.proyeccion.motor import MesProyeccion, ResultadoProyeccion

_CAJA_MIN = Decimal("0.00")

# Plan de cuentas sintético (los 13 códigos del mapeo deben existir → B12 no dispara).
_PLAN = [
    ("0110", "ingresos_operativos", "Recaudo de cartera", True),
    ("0120", "ingresos_operativos", "Cuotas iniciales", False),
    ("0130", "ingresos_operativos", "RODANTE", False),
    ("0140", "ingresos_operativos", "Otros ingresos", False),
    ("1010", "costo_producto", "Producto", False),
    ("1020", "costo_producto", "SOAT/Matrículas", False),
    ("1030", "costo_producto", "Seguros (Hunter)", False),
    ("2010", "operacion", "Arriendos", False),
    ("3010", "nomina", "Sueldos empleados", False),
    ("4010", "deudas_obligaciones", "Préstamos", False),
    ("4020", "deudas_obligaciones", "Tarjetas", False),
    ("4030", "deudas_obligaciones", "Garantía cupo (Auteco)", False),
    ("4050", "deudas_obligaciones", "Proveedores", False),
    ("4060", "deudas_obligaciones", "Inventario Auteco", False),
    ("5060", "otros", "Impuestos", False),
]


def _rubros():
    return [
        RubroInfo(id=cod, codigo=cod, grupo=gr, nombre=nom, es_sistema=sis)
        for (cod, gr, nom, sis) in _PLAN
    ]


def _mp(
    mes,
    *,
    neto,
    gastos_fijos=Decimal("0.00"),
    gps=Decimal("0.00"),
    costo_nueva=Decimal("0.00"),
    int_deuda=Decimal("0.00"),
    iva=Decimal("0.00"),
    adelanto=Decimal("0.00"),
    pago_inventario=Decimal("0.00"),
    fondeo=Decimal("0.00"),
    caja=Decimal("0.00"),
):
    """MesProyeccion con los egresos ya NEGATIVOS. egresos/flujo derivados."""
    egresos = (
        gastos_fijos
        + gps
        + costo_nueva
        + int_deuda
        + iva
        + adelanto
        + pago_inventario
        + fondeo
    )
    return MesProyeccion(
        mes=mes,
        motos=0,
        cartera=0,
        recaudo_credito=Decimal("0.00"),
        cuotas_iniciales=Decimal("0.00"),
        ingreso_bruto=neto,
        neto=neto,
        provision=Decimal("0.00"),
        gastos_fijos=gastos_fijos,
        gps=gps,
        costo_nueva=costo_nueva,
        adelanto=adelanto,
        pago_inventario=pago_inventario,
        fondeo=fondeo,
        int_deuda=int_deuda,
        iva=iva,
        egresos=egresos,
        flujo=neto + egresos,
        caja=caja,
        estado="ok",
    )


def _resultado(filas: list[MesProyeccion]) -> ResultadoProyeccion:
    return ResultadoProyeccion(
        meses=filas,
        piso_caja=min(f.caja for f in filas),
        mes_mas_ajustado=filas[0].mes,
        meses_bajo_minimo=0,
        caja_final=filas[-1].caja,
        capital_requerido=Decimal("0.00"),
        runway_meses=None,
    )


def _serie_coherente(caja_inicial, datos):
    """Serie con caja re-acumulada como el motor (m0 fija = caja_inicial)."""
    filas, caja = [], caja_inicial
    for i, (mes, kw) in enumerate(datos):
        f = _mp(mes, **kw)
        caja = caja_inicial if i == 0 else caja + f.flujo
        filas.append(_mp(mes, caja=caja, **kw))
    return _resultado(filas)


def _invariante_ok(res):
    """B6: neto + egresos == flujo al peso en TODA la serie."""
    return all(f.neto + f.egresos == f.flujo for f in res.meses)


# ─────────────────────────────── B1 ───────────────────────────────
def test_b1_sin_ancla_es_base_bit_a_bit():
    res = _serie_coherente(
        Decimal("1000000.00"),
        [
            (
                "2026-08",
                {"neto": Decimal("500000.00"), "gastos_fijos": Decimal("-200000.00")},
            ),
            (
                "2026-09",
                {"neto": Decimal("400000.00"), "gastos_fijos": Decimal("-150000.00")},
            ),
            (
                "2026-10",
                {"neto": Decimal("600000.00"), "gastos_fijos": Decimal("-100000.00")},
            ),
        ],
    )
    out = anclar(
        resultado=res,
        caja_minima=_CAJA_MIN,
        anclas={},
        rubros=_rubros(),
        neutros_ids=set(),
    )
    assert out.meses == res.meses  # idéntico, bit a bit
    assert _invariante_ok(out)


# ─────────────────────────────── B2 ───────────────────────────────
def test_b2_cerrado_ejecutado_real_y_reacumula():
    # Base: ago(caja 1.000.000 fija) · sep(flujo 250.000→caja 1.250.000) ·
    # oct(flujo 500.000→caja 1.750.000).
    res = _serie_coherente(
        Decimal("1000000.00"),
        [
            (
                "2026-08",
                {"neto": Decimal("500000.00"), "gastos_fijos": Decimal("-200000.00")},
            ),
            (
                "2026-09",
                {"neto": Decimal("400000.00"), "gastos_fijos": Decimal("-150000.00")},
            ),
            (
                "2026-10",
                {"neto": Decimal("600000.00"), "gastos_fijos": Decimal("-100000.00")},
            ),
        ],
    )
    # sep (m1) cerrado: gasto real = Arriendos 350.000, ingreso real 300.000. Ancla en
    # m>0 para ver la re-acumulación de los meses SIGUIENTES.
    ancla = AnclaMes(
        estado=CERRADO,
        ejecutado_por_rubro_id={"2010": Decimal("350000")},
        definido_por_rubro_id={},
        ingreso_real=Decimal("300000"),
    )
    out = anclar(
        resultado=res,
        caja_minima=_CAJA_MIN,
        anclas={"2026-09": ancla},
        rubros=_rubros(),
        neutros_ids=set(),
    )
    sep = out.meses[1]
    assert sep.neto == Decimal("300000.00")  # ingreso real
    assert sep.gastos_fijos == Decimal("-350000.00")  # ejecutado real (negativo)
    assert sep.flujo == Decimal("-50000.00")  # 300000 - 350000
    # ago (m0) intacto; sep y oct re-acumulados desde el nuevo flujo de sep.
    assert out.meses[0].caja == Decimal("1000000.00")  # m0 fija
    assert sep.caja == Decimal("950000.00")  # 1.000.000 + (-50.000)
    assert out.meses[2].caja == Decimal("1450000.00")  # 950.000 + flujo_oct 500.000
    assert _invariante_ok(out)


# ─────────────────────────────── B3 ───────────────────────────────
def test_b3_regla_a_incluye_ejecutado_mayor_que_definido():
    res = _serie_coherente(
        Decimal("1000000.00"),
        [
            (
                "2026-08",
                {
                    "neto": Decimal("500000.00"),
                    "gastos_fijos": Decimal("-100000.00"),
                    "gps": Decimal("-50000.00"),
                },
            ),
        ],
    )
    # en ejecución: gastos_fijos ejec 300.000 > definido 200.000 → vale el ejecutado;
    # gps ejec 10.000 < definido 40.000 → vale el definido. Regla A por concepto.
    ancla = AnclaMes(
        estado=EN_EJECUCION,
        ejecutado_por_rubro_id={"2010": Decimal("300000"), "1030": Decimal("10000")},
        definido_por_rubro_id={"2010": Decimal("200000"), "1030": Decimal("40000")},
        ingreso_real=None,  # el ingreso NO se ancla en ejecución
    )
    out = anclar(
        resultado=res,
        caja_minima=_CAJA_MIN,
        anclas={"2026-08": ancla},
        rubros=_rubros(),
        neutros_ids=set(),
    )
    ago = out.meses[0]
    assert ago.gastos_fijos == Decimal("-300000.00")  # max(ejec, definido) = ejec
    assert ago.gps == Decimal("-40000.00")  # max(ejec, definido) = definido
    assert ago.neto == Decimal("500000.00")  # sin anclar (motor)
    assert _invariante_ok(out)


# ─────────────────────────────── B4 ───────────────────────────────
def test_b4_futuro_con_presupuesto_usa_definido():
    res = _serie_coherente(
        Decimal("1000000.00"),
        [
            (
                "2026-11",
                {"neto": Decimal("500000.00"), "gastos_fijos": Decimal("-999999.00")},
            ),
        ],
    )
    ancla = AnclaMes(
        estado=PRESUPUESTO,
        ejecutado_por_rubro_id={},
        definido_por_rubro_id={"2010": Decimal("250000")},
        ingreso_real=None,
    )
    out = anclar(
        resultado=res,
        caja_minima=_CAJA_MIN,
        anclas={"2026-11": ancla},
        rubros=_rubros(),
        neutros_ids=set(),
    )
    assert out.meses[0].gastos_fijos == Decimal("-250000.00")  # definido, no el motor
    assert out.meses[0].neto == Decimal("500000.00")  # ingreso del motor
    assert _invariante_ok(out)


# ─────────────────────────────── B5 ───────────────────────────────
def test_b5_futuro_sin_presupuesto_es_el_motor():
    res = _serie_coherente(
        Decimal("1000000.00"),
        [
            (
                "2026-08",
                {"neto": Decimal("500000.00"), "gastos_fijos": Decimal("-200000.00")},
            ),
            (
                "2026-12",
                {"neto": Decimal("400000.00"), "gastos_fijos": Decimal("-123456.00")},
            ),
        ],
    )
    # solo ago anclado; dic NO está en anclas → queda intacto (motor).
    ancla = AnclaMes(
        estado=CERRADO,
        ejecutado_por_rubro_id={"2010": Decimal("200000")},
        definido_por_rubro_id={},
        ingreso_real=Decimal("500000"),
    )
    out = anclar(
        resultado=res,
        caja_minima=_CAJA_MIN,
        anclas={"2026-08": ancla},
        rubros=_rubros(),
        neutros_ids=set(),
    )
    assert out.meses[1].gastos_fijos == Decimal("-123456.00")  # dic intacto
    assert _invariante_ok(out)


# ─────────────────────────────── B6 + A3 ───────────────────────────────
def test_a3_fixture_julio_real_b2_y_b6():
    fx = json.loads(
        (
            Path(__file__).resolve().parent
            / "fixtures"
            / "e1_julio_2026_ejecutado.json"
        ).read_text(encoding="utf-8")
    )
    rubros = [
        RubroInfo(
            id=r["id"],
            codigo=r["codigo"],
            grupo=r["grupo"],
            nombre=r["nombre"],
            es_sistema=r["es_sistema"],
        )
        for r in fx["rubros"]
    ]
    ejecutado = {k: Decimal(v) for k, v in fx["egresos_por_rubro_id"].items()}
    neutros = set(fx["neutros_ids"])
    ingreso_real = Decimal(fx["_meta"]["controles"]["ingreso_real"])

    # oráculo: el mapeo P1 (ya auditado) sobre el ejecutado real de julio.
    esperado = mapear_a_conceptos(
        rubros=rubros, valor_por_rubro_id=ejecutado, neutros_ids=neutros
    )

    # serie sintética con julio; el motor trae pago_inventario/fondeo (Auteco) que E1
    # debe CONSERVAR.
    res = _serie_coherente(
        Decimal("800000000.00"),
        [
            (
                "2026-07",
                {
                    "neto": Decimal("111111.00"),
                    "gastos_fijos": Decimal("-1.00"),
                    "pago_inventario": Decimal("-5000000.00"),
                    "fondeo": Decimal("-80000.00"),
                },
            ),
        ],
    )
    ancla = AnclaMes(
        estado=CERRADO,
        ejecutado_por_rubro_id=ejecutado,
        definido_por_rubro_id={},
        ingreso_real=ingreso_real,
    )
    out = anclar(
        resultado=res,
        caja_minima=_CAJA_MIN,
        anclas={"2026-07": ancla},
        rubros=rubros,
        neutros_ids=neutros,
    )
    jul = out.meses[0]

    # B2: ingreso real + ejecutado real al peso (los 5 conceptos E1).
    assert jul.neto == ingreso_real  # 179.710.080,31
    assert jul.gastos_fijos == -esperado.conceptos["gastos_fijos"]
    assert jul.gps == -esperado.conceptos["gps"]
    assert jul.costo_nueva == -esperado.conceptos["costo_nueva"]
    assert jul.int_deuda == -esperado.conceptos["int_deuda"]
    assert jul.iva == -esperado.conceptos["iva"]
    # Auteco conservado del motor (E1 NO lo toca).
    assert jul.pago_inventario == Decimal("-5000000.00")
    assert jul.fondeo == Decimal("-80000.00")
    # B6: invariante al peso sobre la realidad.
    assert jul.neto + jul.egresos == jul.flujo
    assert _invariante_ok(out)
