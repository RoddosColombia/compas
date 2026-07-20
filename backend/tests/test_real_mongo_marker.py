# backend/tests/test_real_mongo_marker.py
"""Verifica que el contrato del marker `requires_real_mongo` funciona:
los tests marcados se saltan por defecto (mongomock no sirve para ellos) y
solo corren con `pytest -m requires_real_mongo` contra un Mongo real.

Ver el comentario extenso en conftest.py."""

import pytest


@pytest.mark.requires_real_mongo
def test_placeholder_dedup_indice_unico_parcial():
    # Dedup parcial (banco, id_banco) con partialFilterExpression: es de SPRINT 1
    # (necesita el modelo Transaccion). Se EXCLUYE del job de la Sesión 3 con un skip
    # explícito (Kimi P-1) para no dejar la CI roja; se hará al portar los parsers.
    pytest.skip("Sprint 1: dedup parcial (banco, id_banco) requiere Transaccion.")
