# backend/tests/test_auth_service.py
"""Lógica de auth (PR-2) con mongomock: login/backoff/anti-enumeración,
token_version, rotación de refresh + detección de reuso, logout, rate limit IP.

La CONCURRENCIA real de la rotación (dos refresh simultáneos → exactamente una
rotación) va en test_auth_concurrency.py con @requires_real_mongo."""

import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository, service, tokens
from app.auth.models import User
from app.auth.roles import Role
from app.config import Settings
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


def _settings(**kw) -> Settings:
    base = dict(
        jwt_secret="x" * 40,
        cookie_secure=False,
        app_env="development",
        login_ip_max=1000,
    )
    base.update(kw)
    return Settings(**base)


@pytest_asyncio.fixture
async def client():
    c = AsyncMongoMockClient()
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")
    u = User(
        email="a@roddos.com", password_hash=passwords.hash_password(PWD), rol=Role.admin
    )
    await repository.create_user(u)
    yield c
    repository.reset_auth()
    reset_audit()


async def test_login_ok_emite_evento_y_da_tokens(client):
    s = _settings()
    pair = await service.login(s, email="A@Roddos.com", password=PWD, ip="1.1.1.1")
    claims = tokens.decode_token(
        s.jwt_secret, pair.access_token, expected_type="access"
    )
    assert claims["type"] == "access"
    audit = await client["compas_test"]["audit_log"].find_one({"evento": "user.login"})
    assert audit is not None


async def test_login_password_incorrecta_es_uniforme(client):
    s = _settings()
    with pytest.raises(service.AuthError) as ei:
        await service.login(s, email="a@roddos.com", password="mala", ip="1.1.1.1")
    assert ei.value.status == 401
    assert ei.value.detail == service._INVALID


async def test_login_email_desconocido_mismo_mensaje(client):
    s = _settings()
    with pytest.raises(service.AuthError) as ei:
        await service.login(s, email="nadie@roddos.com", password="x", ip="1.1.1.1")
    assert ei.value.detail == service._INVALID  # anti-enumeración


async def test_lockout_tras_5_fallos_y_evento_bloqueado(client):
    s = _settings(login_max_intentos=5, login_lock_min=15)
    for _ in range(5):
        with pytest.raises(service.AuthError):
            await service.login(s, email="a@roddos.com", password="mala", ip="1.1.1.1")
    # aun con la clave correcta, queda bloqueado (uniforme 401)
    with pytest.raises(service.AuthError):
        await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    ev = await client["compas_test"]["audit_log"].find_one({"evento": "user.bloqueado"})
    assert ev is not None


async def test_token_version_revoca_access(client):
    s = _settings()
    pair = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    u = await repository.get_user_by_email("a@roddos.com")
    await repository.set_token_version(u.id, u.token_version + 1)
    with pytest.raises(service.AuthError):
        await service.authenticate(s, access_token=pair.access_token)


async def test_refresh_rota_y_detecta_reuso(client):
    s = _settings()
    pair = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    # primer refresh: ok, nuevos tokens
    pair2 = await service.refresh(s, refresh_token=pair.refresh_token)
    assert pair2.access_token
    # REUSO del refresh viejo → detecta y revoca la familia
    with pytest.raises(service.AuthError):
        await service.refresh(s, refresh_token=pair.refresh_token)
    # el refresh "bueno" (pair2) también cae porque la familia quedó revocada
    with pytest.raises(service.AuthError):
        await service.refresh(s, refresh_token=pair2.refresh_token)


async def test_logout_revoca_access_y_refresh(client):
    s = _settings()
    pair = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    await service.logout(
        s, access_token=pair.access_token, refresh_token=pair.refresh_token
    )
    with pytest.raises(service.AuthError):
        await service.authenticate(s, access_token=pair.access_token)
    with pytest.raises(service.AuthError):
        await service.refresh(s, refresh_token=pair.refresh_token)


async def test_rate_limit_por_ip(client):
    s = _settings(login_ip_max=2)
    for _ in range(2):
        with pytest.raises(service.AuthError):
            await service.login(s, email="a@roddos.com", password="mala", ip="9.9.9.9")
    with pytest.raises(service.AuthError) as ei:
        await service.login(s, email="a@roddos.com", password=PWD, ip="9.9.9.9")
    assert ei.value.status == 429  # bloqueado por IP antes de validar credenciales


async def test_login_exitoso_libera_cupo_ip(client):
    # H1: el éxito borra el contador de la IP → una ráfaga legítima no se auto-bloquea.
    s = _settings(login_ip_max=3)
    await service.login(s, email="a@roddos.com", password=PWD, ip="5.5.5.5")
    doc = await client["compas_test"]["login_throttle"].find_one({"_id": "ip:5.5.5.5"})
    assert doc is None


async def test_lock_expirado_da_ventana_nueva(client):
    # L6: con el lock ya vencido, un login correcto entra (reset previo), no re-bloquea.
    from datetime import timedelta

    from app.core.time import now_utc

    await client["compas_test"]["users"].update_one(
        {"email": "a@roddos.com"},
        {
            "$set": {
                "failed_attempts": 5,
                "locked_until": now_utc() - timedelta(minutes=1),
            }
        },
    )
    s = _settings()
    pair = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    assert pair.access_token


async def test_refresh_idle_expira(client):
    from datetime import timedelta

    from app.core.time import now_utc

    s = _settings()
    pair = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    jti = tokens.decode_token(
        s.jwt_secret, pair.refresh_token, expected_type="refresh"
    )["jti"]
    await client["compas_test"]["refresh_sessions"].update_one(
        {"jti": jti}, {"$set": {"ultimo_uso": now_utc() - timedelta(hours=13)}}
    )
    with pytest.raises(service.AuthError):
        await service.refresh(s, refresh_token=pair.refresh_token)


async def test_refresh_max_vida_expira(client):
    from datetime import timedelta

    from app.core.time import now_utc

    s = _settings()
    pair = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    jti = tokens.decode_token(
        s.jwt_secret, pair.refresh_token, expected_type="refresh"
    )["jti"]
    await client["compas_test"]["refresh_sessions"].update_one(
        {"jti": jti}, {"$set": {"expires_at": now_utc() - timedelta(seconds=1)}}
    )
    with pytest.raises(service.AuthError):
        await service.refresh(s, refresh_token=pair.refresh_token)


async def test_tv_desincronizado_invalida_refresh(client):
    s = _settings()
    pair = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    u = await repository.get_user_by_email("a@roddos.com")
    await repository.set_token_version(u.id, u.token_version + 1)
    with pytest.raises(service.AuthError):
        await service.refresh(s, refresh_token=pair.refresh_token)


async def test_logout_con_access_expirado_lo_deniega(client):
    from datetime import timedelta

    s = _settings()
    expirado = tokens.create_access_token(
        s.jwt_secret, sub="507f1f77bcf86cd799439011", tv=1, ttl=timedelta(seconds=-60)
    )
    jti = tokens.decode_token(
        s.jwt_secret, expirado, expected_type="access", verify_exp=False
    )["jti"]
    await service.logout(
        s, access_token=expirado, refresh_token=None
    )  # H-6: no debe fallar
    assert await repository.denylist_contains(jti) is True
