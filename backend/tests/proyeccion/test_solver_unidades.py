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
