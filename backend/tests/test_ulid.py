# backend/tests/test_ulid.py
"""ULID (F-04): id_banco de transacciones manuales = 'MAN-'+ULID."""

from app.core.ulid import CROCKFORD, new_ulid


def test_largo_y_alfabeto():
    u = new_ulid()
    assert len(u) == 26
    assert all(c in CROCKFORD for c in u)


def test_unicos():
    lote = {new_ulid() for _ in range(2000)}
    assert len(lote) == 2000


def test_man_prefijo_cabe_en_40():
    assert len("MAN-" + new_ulid()) <= 40  # límite String(40) de id_banco (§1.5)
