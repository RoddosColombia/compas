# backend/tests/test_e1_guarda.py
"""E1 · P4 — guarda B10 (marca `cerrado_sospechoso`), función pura.

Un mes CERRADO con ejecución muy por debajo de lo definido probablemente está mal
cargado. NO se bloquea el anclaje (la confirmación ES el cierre — FIX-J); solo se MARCA
para la UI. Regla (tunable UMBRAL_SOSPECHA_EJECUTADO): sobre los 5 conceptos anclados
(sin Auteco, sin neto) E = Σ ejecutado, D = Σ definido; sospechoso si D>0 y E < 0.5×D
(estricto: E==0.5×D NO marca; D==0 NO marca). El régimen (AnclaMes.estado) NO cambia —
un sospechoso sigue siendo "cerrado" (así D2 lo sigue excluyendo, protege C-1); la marca
vive solo en el mapa."""

from decimal import Decimal

from app.proyeccion.ejecucion.guarda import (
    UMBRAL_SOSPECHA_EJECUTADO,
    es_ejecutado_anomalo,
    marcas_origen,
)
from app.proyeccion.ejecucion.lectura import RubroInfo
from app.proyeccion.ejecucion.service import AnclaMes

# Los 9 códigos del mapeo presentes (B12 no dispara). 4010 → int_deuda.
_PLAN = [
    ("0110", "ingresos_operativos", "Recaudo de cartera"),
    ("1010", "costo_producto", "Producto"),
    ("1020", "costo_producto", "SOAT"),
    ("1030", "costo_producto", "GPS"),
    ("4010", "deudas_obligaciones", "Préstamos"),
    ("4020", "deudas_obligaciones", "Tarjetas"),
    ("4030", "deudas_obligaciones", "Garantía cupo"),
    ("4050", "deudas_obligaciones", "Proveedores"),
    ("5060", "otros", "Impuestos"),
]


def _rubros():
    return [
        RubroInfo(id=c, codigo=c, grupo=g, nombre=n, es_sistema=False)
        for (c, g, n) in _PLAN
    ]


def _anomalo(ejec, defi):
    return es_ejecutado_anomalo(
        {"4010": Decimal(ejec)} if ejec is not None else {},
        {"4010": Decimal(defi)} if defi is not None else {},
        rubros=_rubros(),
        neutros_ids=set(),
    )


def test_umbral_por_defecto_es_medio():
    assert UMBRAL_SOSPECHA_EJECUTADO == Decimal("0.5")


def test_ejecutado_muy_bajo_es_anomalo():
    # E = 40, D = 100 → 40 < 50 → sospechoso
    assert _anomalo("40", "100") is True


def test_ejecutado_alto_es_limpio():
    # E = 80, D = 100 → 80 !< 50 → limpio
    assert _anomalo("80", "100") is False


def test_frontera_exacta_no_marca():
    # E = 50, D = 100 → 50 < 50 es falso (comparación estricta) → NO marca
    assert _anomalo("50", "100") is False


def test_sin_definido_no_marca():
    # D = 0 → no hay base de juicio → no marca (aunque E sea 0)
    assert _anomalo("0", None) is False
    assert _anomalo(None, None) is False


def test_marcas_origen_marca_solo_cerrado_anomalo():
    anclas = {
        "2026-05": AnclaMes(
            estado="cerrado",
            ejecutado_por_rubro_id={"4010": Decimal("40")},
            definido_por_rubro_id={"4010": Decimal("100")},
            ingreso_real=Decimal("0"),
        ),  # anómalo → cerrado_sospechoso
        "2026-06": AnclaMes(
            estado="cerrado",
            ejecutado_por_rubro_id={"4010": Decimal("90")},
            definido_por_rubro_id={"4010": Decimal("100")},
            ingreso_real=Decimal("0"),
        ),  # sano → cerrado
        "2026-07": AnclaMes(
            estado="en_ejecucion",
            ejecutado_por_rubro_id={"4010": Decimal("1")},
            definido_por_rubro_id={"4010": Decimal("100")},
            ingreso_real=None,
        ),  # en ejecución: nunca sospechoso
        "2026-08": AnclaMes(
            estado="presupuesto",
            ejecutado_por_rubro_id={},
            definido_por_rubro_id={"4010": Decimal("100")},
            ingreso_real=None,
        ),
    }
    marcas = marcas_origen(anclas, rubros=_rubros(), neutros_ids=set())
    assert marcas == {
        "2026-05": "cerrado_sospechoso",
        "2026-06": "cerrado",
        "2026-07": "en_ejecucion",
        "2026-08": "presupuesto",
    }
