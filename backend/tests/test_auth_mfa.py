# backend/tests/test_auth_mfa.py
"""Núcleo criptográfico de MFA (Spec §8.1 / DoD #11): TOTP, cifrado del secreto en
reposo y códigos de respaldo de un solo uso. Todo puro (sin Mongo)."""

import pyotp
import pytest
from app.auth import mfa
from cryptography.fernet import Fernet


# ── TOTP ────────────────────────────────────────────────────────────────
def test_totp_secret_y_verify_ok():
    secret = mfa.new_totp_secret()
    code = pyotp.TOTP(secret).now()
    assert mfa.verify_totp(secret, code) is True


def test_totp_verify_rechaza_codigo_malo():
    secret = mfa.new_totp_secret()
    assert mfa.verify_totp(secret, "000000") is False
    assert mfa.verify_totp(secret, "abc") is False
    assert mfa.verify_totp(secret, "") is False


def test_totp_uri_para_qr():
    secret = mfa.new_totp_secret()
    uri = mfa.totp_uri(secret, "andres@roddos.com")
    assert uri.startswith("otpauth://totp/")
    assert "roddos.com" in uri  # el email va URL-encoded (@ → %40)
    assert secret in uri
    assert "RODDOS" in uri


# ── Cifrado del secreto en reposo (Fernet) ───────────────────────────────
def test_cifrado_round_trip():
    key = Fernet.generate_key().decode()
    secret = mfa.new_totp_secret()
    enc = mfa.encrypt_secret(secret, key)
    assert enc != secret  # no queda en claro
    assert mfa.decrypt_secret(enc, key) == secret


def test_descifrar_con_clave_distinta_falla():
    k1 = Fernet.generate_key().decode()
    k2 = Fernet.generate_key().decode()
    enc = mfa.encrypt_secret(mfa.new_totp_secret(), k1)
    with pytest.raises(Exception):  # noqa: B017 — InvalidToken de cryptography
        mfa.decrypt_secret(enc, k2)


# ── Códigos de respaldo (bcrypt, un solo uso) ────────────────────────────
def test_backup_genera_n_codigos():
    plain, hashed = mfa.generate_backup_codes(10)
    assert len(plain) == 10 and len(hashed) == 10
    assert len(set(plain)) == 10  # distintos
    # hasheados (bcrypt), no en claro
    assert all(not h.startswith(p) for p, h in zip(plain, hashed, strict=True))


def test_backup_consume_ok_y_un_solo_uso():
    plain, hashed = mfa.generate_backup_codes(3)
    ok, restantes = mfa.consume_backup_code(plain[0], hashed)
    assert ok is True and len(restantes) == 2
    # el mismo código ya no sirve contra los restantes
    ok2, _ = mfa.consume_backup_code(plain[0], restantes)
    assert ok2 is False


def test_backup_consume_codigo_desconocido():
    plain, hashed = mfa.generate_backup_codes(3)
    ok, restantes = mfa.consume_backup_code("no-existe", hashed)
    assert ok is False and len(restantes) == 3
