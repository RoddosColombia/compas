# backend/tests/test_transaccion.py
"""Transaccion (Spec §1.5) + derivación de id_banco + mapper desde el parser.

Reglas cubiertas:
  - Regla 1: `valor` es Decimal (rechaza float), > 0 (el signo lo da tipo_flujo).
  - Regla 5: `id_banco` determinista para dedup — mismo movimiento → mismo id
    (dedup de solape); manual usa 'MAN-'+ULID (feature aparte).
  - Regla 7: Global66 conserva moneda/tasa; el id de Global66 es su referencia nativa.
  - Regla 3: schema strict, sin campos extra.

Parte pura (sin Mongo): modelo, `derivar_id_banco`, mapper. El comportamiento del
índice único parcial y la transacción multi-doc del flujo de carga se prueban en
tests marcados @requires_real_mongo (Incremento 2).
"""

from datetime import date
from decimal import Decimal

import pytest
from app.cargas.mapper import movimiento_a_transaccion
from app.domain.bancos import Banco
from app.domain.rubro import TipoFlujo
from app.domain.transaccion import (
    TRANSACCIONES_COLLECTION,
    Transaccion,
    derivar_id_banco,
)
from app.parsers.bank_parsers import MovimientoBancario, TipoMovimiento
from beanie import PydanticObjectId
from pydantic import ValidationError

_RUBRO = PydanticObjectId()
_MES = PydanticObjectId()


def _tx(**over):
    base = dict(
        fecha="2026-03-15",
        descripcion="PAGO PROVEEDOR",
        valor=Decimal("50000"),
        tipo_flujo=TipoFlujo.EGRESO,
        rubro_id=_RUBRO,
        mes_id=_MES,
        banco=Banco.BANCOLOMBIA,
        id_banco="abc123",
    )
    base.update(over)
    return Transaccion(**base)


# ── Modelo Transaccion ─────────────────────────────────────────────────


class TestModelo:
    def test_construccion_valida(self):
        t = _tx()
        assert t.valor == Decimal("50000")
        assert t.tipo_flujo is TipoFlujo.EGRESO
        assert t.tardia is False
        assert Transaccion.Settings.name == TRANSACCIONES_COLLECTION

    def test_valor_debe_ser_decimal_no_float(self):
        with pytest.raises(ValidationError):
            _tx(valor=50000.0)

    def test_valor_debe_ser_positivo(self):
        with pytest.raises(ValidationError):
            _tx(valor=Decimal("0"))
        with pytest.raises(ValidationError):
            _tx(valor=Decimal("-10"))

    def test_fecha_formato_invalido_falla(self):
        with pytest.raises(ValidationError):
            _tx(fecha="15/03/2026")

    def test_banco_manual_permitido(self):
        t = _tx(banco=Banco.MANUAL, id_banco="MAN-01HImanualULID")
        assert t.banco is Banco.MANUAL

    def test_rechaza_campo_extra(self):
        with pytest.raises(ValidationError):
            _tx(inventado="x")

    def test_id_banco_maximo_40(self):
        with pytest.raises(ValidationError):
            _tx(id_banco="x" * 41)

    def test_indice_unico_parcial_declarado(self):
        # Regla 5: (banco, id_banco) único con partialFilterExpression string.
        idx = {i.document["name"]: i.document for i in Transaccion.Settings.indexes}
        assert "banco_idbanco_unico" in idx
        u = idx["banco_idbanco_unico"]
        assert u.get("unique") is True
        assert u["partialFilterExpression"] == {"id_banco": {"$type": "string"}}


# ── derivar_id_banco ─────────────────────────────────────────────────────


class TestDerivarIdBanco:
    def test_global66_usa_referencia_nativa(self):
        idb = derivar_id_banco(
            banco=Banco.GLOBAL66,
            fecha="2026-03-15",
            descripcion="X",
            valor=Decimal("1000"),
            tipo_flujo=TipoFlujo.EGRESO,
            referencia="TXN-002",
        )
        assert idb == "TXN-002"

    def test_bancolombia_es_huella_determinista(self):
        args = dict(
            banco=Banco.BANCOLOMBIA,
            fecha="2026-03-15",
            descripcion="COMPRA",
            valor=Decimal("50000"),
            tipo_flujo=TipoFlujo.EGRESO,
        )
        a = derivar_id_banco(**args)
        b = derivar_id_banco(**args)
        assert a == b  # determinista → dedup de solape
        assert len(a) <= 40
        assert a.endswith("|1")  # huella MD5 + ordinal de ocurrencia (A-01)

    def test_ordinal_distingue_identicos(self):
        # A-01: misma huella, distinta ocurrencia → id distinto (no colapsan).
        base = dict(
            banco=Banco.BANCOLOMBIA,
            fecha="2026-03-15",
            descripcion="ABONO",
            valor=Decimal("50000"),
            tipo_flujo=TipoFlujo.EGRESO,
        )
        assert derivar_id_banco(**base, ocurrencia=1) != derivar_id_banco(
            **base, ocurrencia=2
        )

    def test_huella_cambia_con_el_monto(self):
        base = dict(
            banco=Banco.BBVA,
            fecha="2026-03-15",
            descripcion="X",
            tipo_flujo=TipoFlujo.EGRESO,
        )
        assert derivar_id_banco(valor=Decimal("100"), **base) != derivar_id_banco(
            valor=Decimal("200"), **base
        )

    def test_huella_cambia_con_el_banco(self):
        base = dict(
            fecha="2026-03-15",
            descripcion="X",
            valor=Decimal("100"),
            tipo_flujo=TipoFlujo.EGRESO,
        )
        assert derivar_id_banco(banco=Banco.BANCOLOMBIA, **base) != derivar_id_banco(
            banco=Banco.BBVA, **base
        )


# ── mapper MovimientoBancario → Transaccion ──────────────────────────────


def _mov(**over):
    base = dict(
        fecha=date(2026, 3, 15),
        descripcion="COMPRA",
        monto=Decimal("50000"),
        tipo=TipoMovimiento.DEBITO,
        banco=Banco.BANCOLOMBIA,
    )
    base.update(over)
    return MovimientoBancario(**base)


class TestMapper:
    def test_debito_mapea_a_egreso(self):
        t = movimiento_a_transaccion(
            _mov(tipo=TipoMovimiento.DEBITO), rubro_id=_RUBRO, mes_id=_MES
        )
        assert t.tipo_flujo is TipoFlujo.EGRESO
        assert t.valor == Decimal("50000")  # magnitud positiva
        assert t.fecha == "2026-03-15"  # date → string YYYY-MM-DD
        assert t.rubro_id == _RUBRO
        assert t.tardia is False

    def test_credito_mapea_a_ingreso(self):
        t = movimiento_a_transaccion(
            _mov(tipo=TipoMovimiento.CREDITO), rubro_id=_RUBRO, mes_id=_MES
        )
        assert t.tipo_flujo is TipoFlujo.INGRESO

    def test_global66_conserva_moneda_y_usa_referencia(self):
        mov = _mov(
            banco=Banco.GLOBAL66,
            tipo=TipoMovimiento.CREDITO,
            moneda_original="COP",
            tasa_cambio=Decimal("1"),
            referencia="TXN-77",
        )
        t = movimiento_a_transaccion(mov, rubro_id=_RUBRO, mes_id=_MES)
        assert t.moneda_original == "COP"
        assert t.tasa_cambio == Decimal("1")
        assert t.id_banco == "TXN-77"

    def test_bancolombia_id_banco_es_huella(self):
        t = movimiento_a_transaccion(_mov(), rubro_id=_RUBRO, mes_id=_MES)
        esperado = derivar_id_banco(
            banco=Banco.BANCOLOMBIA,
            fecha="2026-03-15",
            descripcion="COMPRA",
            valor=Decimal("50000"),
            tipo_flujo=TipoFlujo.EGRESO,
        )
        assert t.id_banco == esperado

    def test_propaga_carga_id(self):
        cid = PydanticObjectId()
        t = movimiento_a_transaccion(_mov(), rubro_id=_RUBRO, mes_id=_MES, carga_id=cid)
        assert t.carga_id == cid
