# backend/tests/migrations/test_espejo_agosto_global66.py
"""TDD de los helpers puros de la migración espejo agosto Global66 (sin Mongo)."""

import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from app.domain.bancos import Banco
from app.parsers.bank_parsers import MovimientoBancario, TipoMovimiento, parse_global66
from beanie import PydanticObjectId

_ROOT = Path(__file__).resolve().parents[3]
_MOD_PATH = _ROOT / "migrations" / "20260814_espejo_agosto_global66.py"
_SNAPSHOT = _ROOT / "docs" / "modelo" / "Global66_ago2026_clasificado.xlsx"


def _load_mod():
    spec = importlib.util.spec_from_file_location("espejo_agosto", _MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mig = _load_mod()


def _mov(ref, monto, tipo, desc="x"):
    return MovimientoBancario(
        fecha=date(2026, 8, 4),
        descripcion=desc,
        monto=Decimal(monto),
        tipo=tipo,
        banco=Banco.GLOBAL66,
        moneda_original="COP",
        tasa_cambio=Decimal("1"),
        referencia=ref,
    )


def test_nombre_rubro_alias_y_directo():
    assert mig.nombre_rubro_de_categoria("Operativo") == "Recaudo de cartera"
    assert mig.nombre_rubro_de_categoria("No operativo") == "Rendimientos bancarios"
    assert mig.nombre_rubro_de_categoria("Ajuste") == "Reversas y devoluciones"
    # directo (categoria == nombre del rubro), robusto a tildes/case
    assert mig.nombre_rubro_de_categoria("Impuestos") == "Impuestos"
    assert mig.nombre_rubro_de_categoria("Garantía cupo") == "Garantía cupo"


@pytest.mark.skipif(not _SNAPSHOT.is_file(), reason="snapshot no presente")
def test_verificar_totales_cuadra_con_footer():
    r = parse_global66(str(_SNAPSHOT))
    assert not r.errores
    sdeb, scred = mig.verificar_totales(r.movimientos)
    assert sdeb == mig.SIGMA_EGRESOS
    assert scred == mig.SIGMA_INGRESOS


def test_verificar_totales_falla_loud_si_no_cuadra():
    movs = [_mov("1", "100.00", TipoMovimiento.DEBITO)]  # no suma al footer
    with pytest.raises(SystemExit):
        mig.verificar_totales(movs)


@pytest.mark.skipif(not _SNAPSHOT.is_file(), reason="snapshot no presente")
def test_leer_clasificacion_desambigua_split_auteco():
    clasif = mig.leer_clasificacion(str(_SNAPSHOT))
    # ID 38009969 (Auteco) aparece 2 veces con distinto valor y categoría
    garantia = clasif.get(("38009969", "14000000.00", "debito"))
    prestamo = clasif.get(("38009969", "6123787.47", "debito"))
    assert garantia == "Garantía cupo"
    assert prestamo == "Préstamos"


def test_construir_docs_ocurrencia_split_y_rubro_exacto():
    movs = [
        _mov("38009969", "14000000.00", TipoMovimiento.DEBITO, "garantia"),
        _mov("38009969", "6123787.47", TipoMovimiento.DEBITO, "prestamo"),
    ]
    clasif = {
        ("38009969", "14000000.00", "debito"): "Garantía cupo",
        ("38009969", "6123787.47", "debito"): "Préstamos",
    }
    oid_g, oid_p = PydanticObjectId(), PydanticObjectId()
    rubros = {
        mig._norm("Garantía cupo"): {
            "_id": oid_g, "nombre": "Garantía cupo", "tipo_flujo": "egreso"
        },
        mig._norm("Préstamos"): {
            "_id": oid_p, "nombre": "Préstamos", "tipo_flujo": "egreso"
        },
    }
    docs = mig._construir_docs(movs, clasif, rubros, PydanticObjectId())
    ids = {d.id_banco for d, _ in docs}
    assert ids == {"38009969|1", "38009969|2"}  # ocurrencia distinta, no colapsa
    por_valor = {str(d.valor): d.rubro_id for d, _ in docs}
    assert por_valor["14000000.00"] == oid_g
    assert por_valor["6123787.47"] == oid_p


def test_construir_docs_falla_loud_categoria_sin_rubro():
    movs = [_mov("77", "500.00", TipoMovimiento.DEBITO)]
    clasif = {("77", "500.00", "debito"): "Categoria Inexistente"}
    with pytest.raises(SystemExit):
        mig._construir_docs(movs, clasif, {}, PydanticObjectId())


def test_construir_docs_falla_loud_tipo_incoherente():
    # un ingreso (crédito) mapeado a un rubro de egreso → aborta
    movs = [_mov("88", "1000.00", TipoMovimiento.CREDITO)]
    clasif = {("88", "1000.00", "credito"): "Impuestos"}
    rubros = {
        mig._norm("Impuestos"): {
            "_id": PydanticObjectId(), "nombre": "Impuestos", "tipo_flujo": "egreso"
        }
    }
    with pytest.raises(SystemExit):
        mig._construir_docs(movs, clasif, rubros, PydanticObjectId())
