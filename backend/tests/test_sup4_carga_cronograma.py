# backend/tests/test_sup4_carga_cronograma.py
"""SUP-4 (CEO 2026-08-22) — carga semanal del cronograma de pagos.

"Una manera de ir precisando el mes es que semanalmente, lunes podría ser, se cargue
nuevamente el cronograma y el loantape en COMPAS para que actualice info". Y sobre el
detalle: "cargar tal cantidad de detalle volverá más pesada la app y no es necesario,
necesito datos completos que tú puedes calcular para entregar".

Así que el parser NO guarda las ~9.900 cuotas: las AGREGA a dos series ligeras que el
motor ya consume, y de paso resuelve el mes en curso:

  1. **Serie semanal** de lo ya originado: recaudo pendiente y nº de créditos pagando
     por semana global (ancla del motor: miércoles 2026-03-04 = semana 1).
  2. **Colocaciones reales por mes** (la cuota 0 es el desembolso) → con ellas la
     rampa del MES EN CURSO queda en el REMANENTE hacia la meta (criterio CEO: agosto
     vive con la meta de 70 y se cierra con lo real logrado).

Reglas: las cuotas PAGADAS no se proyectan; las PARCIALES cuentan solo su saldo; lo
VENCIDO sin pagar se reporta aparte (es mora real medida, no proyección). Regla 7:
encabezados que no cuadran → error que LISTA esperado vs encontrado.
"""

from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from app.cartera_previa.cronograma import (
    EncabezadosNoReconocidos,
    ResumenCronograma,
    parsear_cronograma,
)
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
HOY = date(2026, 8, 22)


def _xlsx(filas: list[list], encabezados: list[str] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Generado: 2026-08-19", "Usuario: andres", "Versión: 0.1.0"])
    ws.append(encabezados or ENCABEZADOS)
    for f in filas:
        ws.append(f)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cuota(
    credito="LB-2026-0001",
    n=1,
    fecha="2026-09-02",
    monto=179900,
    pagado=0,
    saldo=None,
    estado="pendiente",
):
    saldo = monto if saldo is None else saldo
    return [credito, n, fecha, monto, 150000, 29900, pagado, saldo, estado, 0]


# ── agregación: la app no engorda ──


def test_agrega_por_semana_global_del_motor():
    """2026-09-02 es miércoles: semana 27 desde el ancla (2026-03-04 = semana 1)."""
    r = parsear_cronograma(_xlsx([_cuota()]), hoy=HOY)
    assert isinstance(r, ResumenCronograma)
    assert r.serie == [
        {"semana_global": 27, "recaudo": Decimal("179900"), "n_activos": 1}
    ]


def test_dos_creditos_en_la_misma_semana_suman_y_cuentan_dos_activos():
    r = parsear_cronograma(
        _xlsx(
            [
                _cuota(credito="LB-1", fecha="2026-09-02"),
                _cuota(credito="LB-2", fecha="2026-09-04", monto=210000),
            ]
        ),
        hoy=HOY,
    )
    assert len(r.serie) == 1
    fila = r.serie[0]
    assert fila["recaudo"] == Decimal("389900")
    assert fila["n_activos"] == 2


def test_las_pagadas_no_se_proyectan():
    r = parsear_cronograma(
        _xlsx(
            [
                _cuota(
                    n=1, fecha="2026-09-02", estado="pagada", pagado=179900, saldo=0
                ),
                _cuota(n=2, fecha="2026-09-09"),
            ]
        ),
        hoy=HOY,
    )
    assert sum(f["recaudo"] for f in r.serie) == Decimal("179900")


def test_una_parcial_cuenta_solo_su_saldo():
    r = parsear_cronograma(
        _xlsx([_cuota(estado="parcial", pagado=100000, saldo=79900)]), hoy=HOY
    )
    assert r.serie[0]["recaudo"] == Decimal("79900")


def test_lo_vencido_sin_pagar_se_reporta_aparte_y_no_se_proyecta():
    """Es mora real MEDIDA: no se mete a la proyección ni se inventa cuándo entra."""
    r = parsear_cronograma(
        _xlsx(
            [
                _cuota(fecha="2026-07-01"),  # vencida sin pagar
                _cuota(n=2, fecha="2026-09-02"),
            ]
        ),
        hoy=HOY,
    )
    assert r.vencido_sin_pagar == Decimal("179900")
    assert r.creditos_en_mora == 1
    assert sum(f["recaudo"] for f in r.serie) == Decimal("179900")  # solo la futura


def test_la_cuota_cero_es_la_colocacion_no_recaudo_futuro():
    """La cuota 0 es el desembolso/cuota inicial: marca el MES de colocación y no
    entra a la serie de recaudo semanal."""
    r = parsear_cronograma(
        _xlsx(
            [
                _cuota(n=0, fecha="2026-08-05", monto=1460000, estado="pagada"),
                _cuota(n=1, fecha="2026-09-02"),
            ]
        ),
        hoy=HOY,
    )
    assert r.colocaciones_por_mes == {"2026-08": 1}
    assert sum(f["recaudo"] for f in r.serie) == Decimal("179900")


def test_cuenta_las_colocaciones_de_cada_mes():
    filas = []
    for i in range(3):
        filas.append(
            _cuota(credito=f"LB-{i}", n=0, fecha="2026-07-10", estado="pagada")
        )
    for i in range(2):
        filas.append(
            _cuota(credito=f"LB-1{i}", n=0, fecha="2026-08-04", estado="pagada")
        )
    r = parsear_cronograma(_xlsx(filas), hoy=HOY)
    assert r.colocaciones_por_mes == {"2026-07": 3, "2026-08": 2}


def test_totales_del_resumen():
    r = parsear_cronograma(
        _xlsx([_cuota(credito="LB-1"), _cuota(credito="LB-2", fecha="2026-10-07")]),
        hoy=HOY,
    )
    assert r.creditos == 2
    assert r.cuotas_futuras == 2
    assert r.recaudo_futuro == Decimal("359800")


# ── regla 7: fail-loud ──


def test_encabezados_desconocidos_fallan_listando():
    with pytest.raises(EncabezadosNoReconocidos) as e:
        parsear_cronograma(_xlsx([_cuota()], encabezados=["A", "B", "C"]), hoy=HOY)
    assert "crédito" in str(e.value).lower()
    assert "fecha programada" in str(e.value).lower()


def test_una_fila_ilegible_no_frena_el_lote_y_se_reporta():
    r = parsear_cronograma(
        _xlsx([_cuota(), _cuota(credito="LB-2", fecha="no-es-fecha")]), hoy=HOY
    )
    assert len(r.errores) == 1
    assert "fecha" in r.errores[0].lower()
    assert sum(f["recaudo"] for f in r.serie) == Decimal("179900")  # la buena entró


def test_un_cronograma_sin_filas_devuelve_series_vacias():
    """El parser no opina: con encabezados válidos y cero filas devuelve vacío. Quien
    debe negarse a PISAR la cartera con eso es el servicio de carga (fail-closed), no
    el parser — ver `test_carga_vacia_no_pisa_la_cartera`."""
    r = parsear_cronograma(_xlsx([]), hoy=HOY)
    assert r.serie == []
    assert r.creditos == 0
    assert r.recaudo_futuro == Decimal("0")


# ── la rampa del mes en curso ──


def test_la_rampa_del_mes_en_curso_es_el_remanente_hacia_la_meta():
    """Criterio CEO: agosto EN CURSO con meta 70 y 35 colocadas ⇒ faltan 35."""
    from app.cartera_previa.cronograma import rampa_mes_en_curso

    assert rampa_mes_en_curso({"2026-08": 35}, mes=(2026, 8), meta=70) == {
        "2026-08": 35
    }


def test_si_ya_se_supero_la_meta_no_se_proyecta_de_mas():
    from app.cartera_previa.cronograma import rampa_mes_en_curso

    assert rampa_mes_en_curso({"2026-08": 80}, mes=(2026, 8), meta=70) == {"2026-08": 0}


def test_sin_colocaciones_reales_la_rampa_es_la_meta_completa():
    from app.cartera_previa.cronograma import rampa_mes_en_curso

    assert rampa_mes_en_curso({}, mes=(2026, 8), meta=70) == {"2026-08": 70}
