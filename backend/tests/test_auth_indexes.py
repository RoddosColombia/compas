# backend/tests/test_auth_indexes.py
"""Existencia de los índices de auth contra Mongo REAL (Kimi L4).

mongomock NO exige índices → un CI solo-mongomock daría verde aunque falten (y el TTL
del rate-limit por IP no expiraría: 429 permanente). Este test corre tras
`scripts/create_auth_indexes.py` en el CI de la Sesión 3."""

import pytest

pytestmark = pytest.mark.requires_real_mongo


def test_indices_de_auth_existen_tras_el_script():
    # Verificará: users.email único; refresh_sessions.jti único + family_id + TTL;
    # jwt_denylist.jti único + TTL; login_throttle TTL (expireAfterSeconds:0).
    raise AssertionError(
        "Pendiente CI Sesión 3: requiere mongod real + create_auth_indexes.py."
    )
