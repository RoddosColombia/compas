from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO


def test_resultado_ok_con_evidencia():
    r = ResultadoCFO(
        concepto="caja_hoy",
        valor=Decimal("704722003.00"),
        unidad="COP",
        disponible=True,
        evidencia=Evidencia(
            fuente="caja.service.caja_diaria", fecha_corte="2026-08-04", ref="2026-08"
        ),
    )
    assert r.valor == Decimal("704722003.00")
    assert r.evidencia.fecha_corte == "2026-08-04"
    assert r.detalle == {}


def test_abstencion_valor_none_disponible_false():
    r = ResultadoCFO(
        concepto="runway",
        valor=None,
        unidad="meses",
        disponible=False,
        evidencia=Evidencia(fuente="proyeccion", fecha_corte=None, ref="sin-config"),
    )
    assert r.valor is None and r.disponible is False


def test_rechaza_campo_extra_strict():
    with pytest.raises(ValidationError):
        Evidencia(fuente="x", fecha_corte=None, ref="y", inventado=1)
