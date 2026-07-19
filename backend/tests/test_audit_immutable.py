# backend/tests/test_audit_immutable.py
"""DoD #6 — inmutabilidad del audit_log verificada contra Mongo REAL.

mongomock NO evalúa privilegios de BD (haría placebo). Estos tests corren contra
un mongod REAL con auth y el rol `audit_writer` (usuario `compas_audit`), y el
usuario general de la app SIN update/remove. Se validan en el CI de la Sesión 3.

Por decisión (CEO 18-jul): diferidos a CI. El marker @requires_real_mongo hace que
FALLEN (no skip) si se piden con `-m requires_real_mongo` sin un mongod con auth.

IMPORTANTE (Kimi Baja): en la Sesión 3, el job de CI que corre `-m requires_real_mongo`
DEBE ser un required check que BLOQUEE el merge — si no, DoD #6 nunca se verifica de
verdad y nadie lo nota. El mongod de CI debe tener auth habilitada + el rol audit_writer
cableado (sin auth, el test de permisos pasa en falso)."""

import pytest

pytestmark = pytest.mark.requires_real_mongo


def test_update_sobre_audit_log_falla_con_rol_app():
    # Con la conexión general de la app (sin update), un update_one sobre audit_log
    # debe lanzar OperationFailure (code 13, Unauthorized).
    raise AssertionError("Pendiente CI Sesión 3: requiere mongod real con roles.")


def test_remove_sobre_audit_log_falla_con_rol_app():
    raise AssertionError("Pendiente CI Sesión 3: requiere mongod real con roles.")


def test_insert_y_find_como_compas_audit_funcionan():
    # Test POSITIVO: sin él, un rol roto sin insert pasaría el negativo y el audit
    # moriría en silencio.
    raise AssertionError("Pendiente CI Sesión 3: requiere mongod real con roles.")
