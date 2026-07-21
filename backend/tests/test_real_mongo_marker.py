# backend/tests/test_real_mongo_marker.py
"""Verifica que el contrato del marker `requires_real_mongo` funciona:
los tests marcados se saltan por defecto (mongomock no sirve para ellos) y
solo corren con `pytest -m requires_real_mongo` contra un Mongo real.

Ver el comentario extenso en conftest.py."""

import pytest


@pytest.mark.requires_real_mongo
def test_placeholder_dedup_indice_unico_parcial():
    # Dedup parcial (banco, id_banco) con partialFilterExpression: IMPLEMENTADO al
    # portar los parsers (Sprint 1). La cobertura real vive en
    # tests/test_transaccion_dedup.py (solape no duplica + coexistencia de 2 manuales).
    pytest.skip("Cubierto en test_transaccion_dedup.py (Transaccion, Sprint 1).")
