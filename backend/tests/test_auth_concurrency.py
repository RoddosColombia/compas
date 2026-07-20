# backend/tests/test_auth_concurrency.py
"""Concurrencia de la rotación de refresh contra Mongo REAL (Kimi A-02/H-4).

mongomock NO garantiza la atomicidad de findOneAndUpdate bajo concurrencia real, así
que este test corre contra un mongod REAL en el CI de la Sesión 3.

Criterio (H-4): dos rotaciones SIMULTÁNEAS del mismo jti → exactamente UNA gana
(el filtro atómico {jti, rotado:False, revocado:False} solo matchea una vez).

Sin `COMPAS_TEST_MONGO_URI` se salta (no falla): el CI la provee."""

import asyncio
import os
from datetime import timedelta

import pytest
from app.auth import repository
from app.auth.models import RefreshSession
from app.core.time import now_utc
from motor.motor_asyncio import AsyncIOMotorClient

pytestmark = pytest.mark.requires_real_mongo


@pytest.fixture
async def real_client():
    uri = os.environ.get("COMPAS_TEST_MONGO_URI")
    if not uri:
        pytest.skip("COMPAS_TEST_MONGO_URI no configurado")
    client = AsyncIOMotorClient(uri, tz_aware=True)
    repository.configure_auth(client, "compas_test_concur")
    await client["compas_test_concur"]["refresh_sessions"].delete_many({})
    yield client
    repository.reset_auth()
    await client.drop_database("compas_test_concur")
    client.close()


async def test_rotacion_exactamente_una_bajo_concurrencia(real_client):
    jti = "jti-concurrencia"
    await repository.create_refresh_session(
        RefreshSession(
            jti=jti,
            usuario_id="u",
            family_id="f",
            expires_at=now_utc() + timedelta(days=30),
        )
    )
    # Dos rotaciones concurrentes del MISMO jti.
    ganadores = await asyncio.gather(
        repository.rotate_refresh_session(jti),
        repository.rotate_refresh_session(jti),
    )
    assert sum(1 for g in ganadores if g) == 1  # exactamente una ganó la carrera
