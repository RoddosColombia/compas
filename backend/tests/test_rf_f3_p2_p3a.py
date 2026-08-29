# backend/tests/test_rf_f3_p2_p3a.py
"""RF-F3 · P2 (valle enriquecido: entrada/salida/duración) + P3a (estado ámbar por mes).

P2 caracteriza el SEGMENTO del valle, no solo el fondo puntual: entrada = primer mes
que cruza `caja_atencion` cayendo; salida = primer mes que vuelve a superarla; duración
= meses entre ambos (inclusive). Cuando el caller NO pasa `caja_atencion`, la semántica
actual se preserva (esos 3 campos quedan en None).

P3a introduce el nivel intermedio `atencion` (ámbar) entre `ok` y `critico`. Igual que
arriba: sin `caja_atencion`, `_estado_caja` sigue idéntico → golden-master intacto.
"""

from decimal import Decimal

from app.proyeccion.motor import MesProyeccion, _estado_caja
from app.proyeccion.valles import detectar_valles

MIN = Decimal("30000000")
ATN = Decimal("100000000")


def _mes(idx: int, caja: Decimal) -> MesProyeccion:
    """Un mes-esqueleto para pruebas de valles: solo caja importa; los demás campos
    quedan en cero. mes se codifica 'YYYY-MM' con año fijo para que ordenen igual."""
    y, m = 2026 + idx // 12, (idx % 12) + 1
    return MesProyeccion(
        mes=f"{y}-{m:02d}",
        motos=0,
        cartera=0,
        recaudo_credito=Decimal("0"),
        cuotas_iniciales=Decimal("0"),
        ingreso_bruto=Decimal("0"),
        neto=Decimal("0"),
        provision=Decimal("0"),
        gastos_fijos=Decimal("0"),
        gps=Decimal("0"),
        costo_nueva=Decimal("0"),
        adelanto=Decimal("0"),
        pago_inventario=Decimal("0"),
        fondeo=Decimal("0"),
        int_deuda=Decimal("0"),
        egresos=Decimal("0"),
        flujo=Decimal("0"),
        caja=caja,
        estado=_estado_caja(caja, MIN),
        iva=Decimal("0"),
        aval=Decimal("0"),
        mora=Decimal("0"),
        recuperacion=Decimal("0"),
        default=Decimal("0"),
    )


# ─────────────────────── P3a — _estado_caja con atención ───────────────────────


def test_p3a_sin_atencion_preserva_comportamiento():
    """Sin caja_atencion la semántica NO cambia: es lo que asegura el golden-master."""
    assert _estado_caja(Decimal("500000000"), MIN) == "ok"
    assert _estado_caja(Decimal("20000000"), MIN) == "critico"
    assert _estado_caja(Decimal("-1"), MIN) == "negativo"


def test_p3a_con_atencion_introduce_ambar():
    """Entre crítico y atención → 'atencion'. Por encima de atención → 'ok'."""
    assert _estado_caja(Decimal("500000000"), MIN, ATN) == "ok"
    assert _estado_caja(Decimal("60000000"), MIN, ATN) == "atencion"  # entre 30M y 100M
    assert (
        _estado_caja(Decimal("100000000"), MIN, ATN) == "atencion"
    )  # justo en atención
    assert _estado_caja(Decimal("20000000"), MIN, ATN) == "critico"  # bajo mínimo
    assert _estado_caja(Decimal("-1"), MIN, ATN) == "negativo"


# ─────────────────────── P2 — valle con entrada/salida/duración ───────────────────────


def _cajas(pattern: list[int]) -> list[MesProyeccion]:
    return [_mes(i, Decimal(str(v * 1_000_000))) for i, v in enumerate(pattern)]


def test_p2_valle_enriquecido_con_atencion():
    """Serie que baja desde 150 hasta 50 y vuelve a subir: el fondo en el mes 3, la
    entrada al cruzar 100 (=ATN), la salida al volver a superarlo."""
    #                    0    1    2    3    4    5
    meses = _cajas([150, 120, 80, 50, 90, 130])
    v = detectar_valles(meses, MIN, caja_atencion=ATN)
    assert len(v) == 1
    valle = v[0]
    assert valle.caja == Decimal("50000000")  # fondo
    assert valle.entrada == meses[2].mes  # 80 < 100 (primer cruce hacia abajo)
    assert valle.salida == meses[5].mes  # 130 > 100 (primer cruce hacia arriba)
    assert valle.duracion == 3  # meses 2..4 bajo atención = 3 meses


def test_p2_sin_atencion_preserva_campos_none():
    """Sin caja_atencion los nuevos campos van en None (compat)."""
    meses = _cajas([150, 120, 80, 50, 90, 130])
    v = detectar_valles(meses, MIN)  # sin caja_atencion
    assert len(v) == 1
    assert v[0].entrada is None
    assert v[0].salida is None
    assert v[0].duracion is None


def test_p2_valle_en_el_borde_izquierdo():
    """Si arranca YA bajo atención, entrada = primer mes de la serie."""
    #                    0   1   2   3
    meses = _cajas([70, 60, 80, 130])
    v = detectar_valles(meses, MIN, caja_atencion=ATN)
    assert len(v) == 1
    assert v[0].entrada == meses[0].mes
    assert v[0].salida == meses[3].mes
    assert v[0].duracion == 3


def test_p2_valle_que_no_sale_del_umbral():
    """Si la serie termina bajo atención, salida = None (aún no salió)."""
    #                    0   1   2   3
    meses = _cajas([150, 90, 50, 60])
    v = detectar_valles(meses, MIN, caja_atencion=ATN)
    assert len(v) == 1
    assert v[0].entrada == meses[1].mes
    assert v[0].salida is None
    assert v[0].duracion == 3  # los 3 meses bajo atención (1, 2, 3)


def test_p2_dos_valles_separados_no_se_fusionan():
    """Dos valles distintos con recuperación intermedia por encima de atención."""
    #                    0    1   2   3    4    5   6   7    8
    meses = _cajas([200, 80, 60, 90, 150, 130, 70, 50, 130])
    v = detectar_valles(meses, MIN, caja_atencion=ATN)
    assert len(v) == 2
    assert v[0].caja == Decimal("60000000") and v[0].duracion == 3  # meses 1..3
    assert v[1].caja == Decimal("50000000") and v[1].duracion == 2  # meses 6..7
