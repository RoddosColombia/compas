# backend/tests/test_audit_immutable.py
"""DoD #6 — inmutabilidad del audit_log verificada contra Mongo REAL.

mongomock NO evalúa privilegios de BD (haría placebo). Estos tests corren contra un
mongod REAL con auth + el rol `audit_writer` (usuario `compas_audit`, creado por
`scripts/create_audit_role.py`). Se validan en el CI de la Sesión 3, donde el job
`backend-real-mongo` es un required check BLOQUEANTE (Kimi P-2): si no, DoD #6 nunca
se verifica de verdad.

`COMPAS_TEST_AUDIT_URI` apunta al usuario `compas_audit` (insert+find sobre audit_log,
SIN update/remove). Sin la env var, se salta (no falla): el CI la provee."""

import os

import pytest
from app.core.time import now_utc
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure

pytestmark = pytest.mark.requires_real_mongo

_UNAUTHORIZED = 13  # código de OperationFailure cuando el rol no tiene la acción


def _doc() -> dict:
    return {
        "evento": "user.login",
        "entidad": "user",
        "entidad_id": "x",
        "actor_id": "x",
        "metadata": {},
        "timestamp": now_utc(),
    }


@pytest.fixture
async def audit_col():
    uri = os.environ.get("COMPAS_TEST_AUDIT_URI")
    if not uri:
        pytest.skip("COMPAS_TEST_AUDIT_URI no configurado (usuario compas_audit)")
    client = AsyncIOMotorClient(uri, tz_aware=True)
    yield client["compas"]["audit_log"]
    client.close()


async def test_insert_y_find_como_compas_audit_funcionan(audit_col):
    # POSITIVO: sin él, un rol roto sin insert pasaría el negativo y el audit moriría
    # en silencio (Kimi).
    res = await audit_col.insert_one(_doc())
    assert res.inserted_id is not None
    got = await audit_col.find_one({"_id": res.inserted_id})
    assert got is not None and got["evento"] == "user.login"


async def test_update_sobre_audit_log_falla(audit_col):
    # audit_writer NO tiene 'update' → OperationFailure 13 (Unauthorized).
    with pytest.raises(OperationFailure) as ei:
        await audit_col.update_one({}, {"$set": {"evento": "tamper"}})
    assert ei.value.code == _UNAUTHORIZED


async def test_remove_sobre_audit_log_falla(audit_col):
    # audit_writer NO tiene 'remove' → append-only real (regla 4 / DoD #6).
    with pytest.raises(OperationFailure) as ei:
        await audit_col.delete_one({})
    assert ei.value.code == _UNAUTHORIZED
