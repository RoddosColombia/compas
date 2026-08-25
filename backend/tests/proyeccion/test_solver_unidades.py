# backend/tests/proyeccion/test_solver_unidades.py
from dataclasses import dataclass
from decimal import Decimal

from app.proyeccion.solver_unidades import resolver_unidades_para_umbral


# Fake mínimo de ResultadoProyeccion: el solver solo necesita que aplicar_impactos
# corra sobre él. Para aislar el solver de aplicar_impactos, monkeypatcheamos el piso.
@dataclass
class _R:  # sustituto de ResultadoProyeccion para el fake
    piso: Decimal


def _piso_lineal(n: int) -> _R:
    # piso sube 1.000.000 por unidad extra, arranca en -5.000.000 (bajo el umbral 0)
    return _R(piso=Decimal(-5_000_000) + Decimal(1_000_000) * n)


def test_encuentra_minimo_de_unidades(monkeypatch):
    # aplicar_impactos(r, ajustes, caja_minima).kpis.piso_caja == r.piso (fake)
    monkeypatch.setattr(
        "app.proyeccion.solver_unidades._piso_con_ajustes",
        lambda r, ajustes, caja_minima: r.piso,
    )
    res = resolver_unidades_para_umbral(
        _piso_lineal, ajustes=[], caja_minima=Decimal("0")
    )
    assert res.alcanzable is True
    assert res.unidades_extra == 5  # -5M + 5*1M = 0 >= umbral 0
    assert res.piso_resultante == Decimal("0")


def test_ya_cumple_con_cero(monkeypatch):
    monkeypatch.setattr(
        "app.proyeccion.solver_unidades._piso_con_ajustes",
        lambda r, ajustes, caja_minima: r.piso,
    )
    res = resolver_unidades_para_umbral(
        lambda n: _R(piso=Decimal(10_000_000)), ajustes=[], caja_minima=Decimal("0")
    )
    assert res.unidades_extra == 0 and res.alcanzable is True


def test_no_alcanzable_dentro_del_tope(monkeypatch):
    monkeypatch.setattr(
        "app.proyeccion.solver_unidades._piso_con_ajustes",
        lambda r, ajustes, caja_minima: r.piso,
    )
    # piso jamás sube (aunque haya más unidades) → no alcanzable
    res = resolver_unidades_para_umbral(
        lambda n: _R(piso=Decimal(-1)),
        ajustes=[],
        caja_minima=Decimal("0"),
        cap_unidades=100,
    )
    assert res.alcanzable is False and res.unidades_extra == 0


# ---------------------------------------------------------------------------
# Fix round 1 — regresión: la búsqueda debe quedar ACOTADA a [0, cap_unidades].
# ---------------------------------------------------------------------------


def test_minimo_en_el_borde_del_cap_es_alcanzable(monkeypatch):
    # Escalón: piso < meta para n<10, piso == meta desde n=10 — el mínimo real
    # CAE justo en el cap. Bug original: la fase de duplicado saltaba 8→16 y
    # declaraba "no alcanzable" aunque 10 <= cap_unidades=10 (Escenario A).
    monkeypatch.setattr(
        "app.proyeccion.solver_unidades._piso_con_ajustes",
        lambda r, ajustes, caja_minima: r.piso,
    )
    res = resolver_unidades_para_umbral(
        lambda n: _R(piso=Decimal("0") if n >= 10 else Decimal("-1")),
        ajustes=[],
        caja_minima=Decimal("0"),
        cap_unidades=10,
    )
    assert res.alcanzable is True
    assert res.unidades_extra == 10
    assert res.piso_resultante == Decimal("0")


def test_minimo_en_mitad_superior_del_cap_default_es_alcanzable(monkeypatch):
    # Lineal con cero en n=9000 (> cap_unidades/2 = 5000, usando el cap DEFAULT
    # 10.000, sin pasarlo explícito). Reproduce el Escenario A al valor LITERAL
    # del default: la duplicación 8192→16384 se pasaba del cap y perdía el 9000,
    # que sí era alcanzable.
    monkeypatch.setattr(
        "app.proyeccion.solver_unidades._piso_con_ajustes",
        lambda r, ajustes, caja_minima: r.piso,
    )
    res = resolver_unidades_para_umbral(
        lambda n: _R(piso=Decimal(1_000) * (n - 9000)),
        ajustes=[],
        caja_minima=Decimal("0"),
    )
    assert res.alcanzable is True
    assert res.unidades_extra == 9000
    assert res.piso_resultante == Decimal("0")


def test_cap_cero_bloquea_unidad_que_si_alcanzaria(monkeypatch):
    # true N=1 (piso(0) < meta <= piso(1)) pero cap_unidades=0 prohíbe CUALQUIER
    # unidad extra. Bug original (Escenario B): el chequeo del cap vivía DENTRO
    # del while de duplicado, que nunca se ejecutaba porque piso(1) ya cumplía
    # la meta en el primer chequeo — el cap quedaba sin aplicar.
    monkeypatch.setattr(
        "app.proyeccion.solver_unidades._piso_con_ajustes",
        lambda r, ajustes, caja_minima: r.piso,
    )
    res = resolver_unidades_para_umbral(
        lambda n: _R(piso=Decimal("-1") + Decimal("2") * n),
        ajustes=[],
        caja_minima=Decimal("0"),
        cap_unidades=0,
    )
    assert res.alcanzable is False
    assert res.unidades_extra == 0
