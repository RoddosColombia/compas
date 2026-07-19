# backend/tests/test_auth_concurrency.py
"""Concurrencia de la rotación de refresh contra Mongo REAL (Kimi A-02/H-4).

mongomock NO garantiza la atomicidad de findOneAndUpdate bajo concurrencia real, así
que este test corre contra un mongod REAL en el CI de la Sesión 3.

Criterio (H-4): dos refresh SIMULTÁNEOS del mismo jti → exactamente UNA rotación (un
solo par de tokens nuevo); el perdedor recibe 401 y la familia se revoca (reuso). Un
test aparte cubre el replay dentro del leeway cuando se implemente en el servidor."""

import pytest

pytestmark = pytest.mark.requires_real_mongo


def test_rotacion_exactamente_una_bajo_concurrencia():
    raise AssertionError("Pendiente CI Sesión 3: requiere mongod real (atomicidad).")
