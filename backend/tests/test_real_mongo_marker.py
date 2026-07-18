# backend/tests/test_real_mongo_marker.py
"""Verifica que el contrato del marker `requires_real_mongo` funciona:
los tests marcados se saltan por defecto (mongomock no sirve para ellos) y
solo corren con `pytest -m requires_real_mongo` contra un Mongo real.

Ver el comentario extenso en conftest.py."""

import pytest


@pytest.mark.requires_real_mongo
def test_placeholder_dedup_indice_unico_parcial():
    # Sprint 1: aquí irá el test del índice único parcial (banco, id_banco)
    # con partialFilterExpression {id_banco:{$type:'string'}} + DuplicateKeyError.
    # mongomock NO lo soporta → debe correr contra Mongo real.
    raise AssertionError(
        "Este test no debería ejecutarse sin `-m requires_real_mongo`."
    )
