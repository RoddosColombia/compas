# backend/tests/test_auth_mfa_flow.py
"""Flujos MFA (Spec §8.1 / DoD #11) con mongomock: enrolamiento (setup→activate),
login en 2 pasos (challenge → verify), respaldo un-solo-uso, throttle y reset."""

import pyotp
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository, service
from app.auth.models import User
from app.auth.roles import Role
from app.config import Settings
from cryptography.fernet import Fernet
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"
ENC_KEY = Fernet.generate_key().decode()


def _settings(**kw) -> Settings:
    base = dict(
        jwt_secret="x" * 40,
        mfa_enc_key=ENC_KEY,
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
    await repository.create_user(
        User(
            email="a@roddos.com",
            password_hash=passwords.hash_password(PWD),
            rol=Role.admin,
        )
    )
    yield c
    repository.reset_auth()
    reset_audit()


async def _user():
    return await repository.get_user_by_email("a@roddos.com")


async def _enroll(s) -> str:
    """setup + activate; devuelve el secreto TOTP en claro (para calcular códigos)."""
    info = await service.mfa_setup(s, user=await _user(), password=PWD)
    secret = info["secret"]
    await service.mfa_activate(s, user=await _user(), code=pyotp.TOTP(secret).now())
    return secret


# ── Enrolamiento ─────────────────────────────────────────────────────────
async def test_setup_exige_password(client):
    s = _settings()
    with pytest.raises(service.AuthError):
        await service.mfa_setup(s, user=await _user(), password="mala")


async def test_setup_guarda_secreto_cifrado_sin_habilitar(client):
    s = _settings()
    info = await service.mfa_setup(s, user=await _user(), password=PWD)
    assert info["secret"] and info["otpauth_uri"].startswith("otpauth://")
    u = await _user()
    assert u.mfa_secret is not None and u.mfa_secret != info["secret"]  # cifrado
    assert u.mfa_habilitado is False  # aún no activado


async def test_activate_habilita_y_da_respaldos(client):
    s = _settings()
    info = await service.mfa_setup(s, user=await _user(), password=PWD)
    codes = await service.mfa_activate(
        s, user=await _user(), code=pyotp.TOTP(info["secret"]).now()
    )
    assert len(codes) == s.mfa_backup_codes
    assert (await _user()).mfa_habilitado is True


async def test_activate_codigo_malo_no_habilita(client):
    s = _settings()
    await service.mfa_setup(s, user=await _user(), password=PWD)
    with pytest.raises(service.AuthError):
        await service.mfa_activate(s, user=await _user(), code="000000")
    assert (await _user()).mfa_habilitado is False


# ── Login en 2 pasos ───────────────────────────────────────────────────────
async def test_login_con_mfa_devuelve_challenge(client):
    s = _settings()
    await _enroll(s)
    res = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    assert isinstance(res, service.MfaChallenge)
    # No se creó sesión ni se emitió login todavía.
    assert await client["compas_test"]["refresh_sessions"].count_documents({}) == 0


async def test_verify_totp_da_tokens_con_mfa_at(client):
    s = _settings()
    secret = await _enroll(s)
    ch = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    pair = await service.mfa_verify(
        s,
        challenge_token=ch.challenge_token,
        code=pyotp.TOTP(secret).now(),
        ip="1.1.1.1",
    )
    from app.auth import tokens

    claims = tokens.decode_token(
        s.jwt_secret, pair.access_token, expected_type="access"
    )
    assert "mfa_at" in claims
    log = await client["compas_test"]["audit_log"].find_one({"evento": "user.login"})
    assert log is not None


async def test_verify_codigo_malo_falla(client):
    s = _settings()
    await _enroll(s)
    ch = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    with pytest.raises(service.AuthError) as ei:
        await service.mfa_verify(
            s, challenge_token=ch.challenge_token, code="000000", ip="1.1.1.1"
        )
    assert ei.value.detail == service._INVALID


# ── Códigos de respaldo (un solo uso) ────────────────────────────────────
async def test_backup_code_un_solo_uso(client):
    s = _settings()
    info = await service.mfa_setup(s, user=await _user(), password=PWD)
    codes = await service.mfa_activate(
        s, user=await _user(), code=pyotp.TOTP(info["secret"]).now()
    )
    ch = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    pair = await service.mfa_verify(
        s, challenge_token=ch.challenge_token, code=codes[0], ip="1.1.1.1"
    )
    assert pair.access_token
    # El mismo código de respaldo ya no sirve.
    ch2 = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    with pytest.raises(service.AuthError):
        await service.mfa_verify(
            s, challenge_token=ch2.challenge_token, code=codes[0], ip="1.1.1.1"
        )


# ── Challenge de un solo uso (M1) ────────────────────────────────────────
async def test_challenge_no_reutilizable(client):
    s = _settings()
    secret = await _enroll(s)
    ch = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    # 1er canje: éxito
    await service.mfa_verify(
        s,
        challenge_token=ch.challenge_token,
        code=pyotp.TOTP(secret).now(),
        ip="1.1.1.1",
    )
    # Reusar el MISMO challenge (aunque el código TOTP sea válido) → replay → falla.
    with pytest.raises(service.AuthError):
        await service.mfa_verify(
            s,
            challenge_token=ch.challenge_token,
            code=pyotp.TOTP(secret).now(),
            ip="1.1.1.1",
        )
    # Solo se acuñó UNA familia de sesión.
    assert await client["compas_test"]["refresh_sessions"].count_documents({}) == 1


# ── Throttle ──────────────────────────────────────────────────────────────
async def test_verify_throttle_429(client):
    s = _settings(mfa_verify_max=3)
    await _enroll(s)
    ch = await service.login(s, email="a@roddos.com", password=PWD, ip="9.9.9.9")
    for _ in range(3):
        with pytest.raises(service.AuthError) as ei:
            await service.mfa_verify(
                s, challenge_token=ch.challenge_token, code="000000", ip="9.9.9.9"
            )
        assert ei.value.status == 401
    # El 4º supera el máximo → 429.
    with pytest.raises(service.AuthError) as ei:
        await service.mfa_verify(
            s, challenge_token=ch.challenge_token, code="000000", ip="9.9.9.9"
        )
    assert ei.value.status == 429


# ── Reset ─────────────────────────────────────────────────────────────────
async def test_reset_deshabilita_y_bump_token_version(client):
    s = _settings()
    await _enroll(s)
    antes = await _user()
    await service.mfa_reset(s, user_id=antes.id)
    despues = await _user()
    assert despues.mfa_habilitado is False
    assert despues.mfa_secret is None
    assert despues.token_version == antes.token_version + 1
