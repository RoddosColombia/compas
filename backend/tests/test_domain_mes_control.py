# backend/tests/test_domain_mes_control.py
"""MesControl (Spec §1.3): mes normalizado al día 1, estados, saldos Decimal,
inmutabilidad de meses cerrados (regla 4 de CLAUDE.md)."""

from decimal import Decimal

import pytest
from app.domain.bancos import Banco
from app.domain.mes_control import (
    EstadoMes,
    MesCerradoError,
    MesControl,
    SaldoBanco,
)
from pydantic import ValidationError


def test_mes_valido():
    m = MesControl(mes="2026-07-01", saldo_inicial_caja=Decimal("675967053.19"))
    assert m.estado is EstadoMes.SUGERIDO  # default
    assert m.saldo_inicial_caja == Decimal("675967053.19")


@pytest.mark.parametrize("malo", ["2026-07-15", "2026-7-1", "2026/07/01", "julio"])
def test_mes_debe_ser_primer_dia_formato_estricto(malo):
    with pytest.raises(ValidationError):
        MesControl(mes=malo, saldo_inicial_caja=Decimal("0"))


def test_saldo_no_admite_float():
    with pytest.raises(ValidationError):
        MesControl(mes="2026-07-01", saldo_inicial_caja=675967053.19)


def test_saldos_banco():
    m = MesControl(
        mes="2026-07-01",
        saldo_inicial_caja=Decimal("0"),
        saldos_banco=[
            SaldoBanco(
                banco="bancolombia", saldo=Decimal("100.00"), fecha_reporte="2026-07-31"
            )
        ],
    )
    assert m.saldos_banco[0].banco is Banco.BANCOLOMBIA


@pytest.mark.parametrize("malo", ["Bancolombia", "BANCOLOMBIA", "nequi", "davivienda"])
def test_saldos_banco_rechaza_banco_no_enum(malo):
    # B-2: sin enum, 'Bancolombia'/'bancolombia'/'BANCOLOMBIA' serían 3 bancos.
    with pytest.raises(ValidationError):
        SaldoBanco(banco=malo, saldo=Decimal("1"), fecha_reporte="2026-07-31")


def test_estado_enum_completo():
    assert {e.value for e in EstadoMes} == {
        "sugerido",
        "propuesto",
        "definido",
        "en_ejecucion",
        "cerrado",
    }


def test_mes_cerrado_es_inmutable():
    m = MesControl(mes="2026-06-01", estado="cerrado", saldo_inicial_caja=Decimal("0"))
    with pytest.raises(MesCerradoError):
        m.assert_editable()


def test_mes_abierto_es_editable():
    m = MesControl(
        mes="2026-07-01", estado="en_ejecucion", saldo_inicial_caja=Decimal("0")
    )
    m.assert_editable()  # no lanza
