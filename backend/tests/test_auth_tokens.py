# backend/tests/test_auth_tokens.py
"""JWT access/refresh (PR-2). Cripto endurecida (Kimi): HS256 explícito, leeway,
jti uuid4 en ambos, claims token_version/type/family_id."""

from datetime import timedelta

import jwt
import pytest
from app.auth import tokens

SECRET = "x" * 40  # >= 32 bytes


def test_access_token_claims():
    tok = tokens.create_access_token(SECRET, sub="u1", tv=1)
    claims = tokens.decode_token(SECRET, tok, expected_type="access")
    assert claims["sub"] == "u1"
    assert claims["tv"] == 1
    assert claims["type"] == "access"
    assert len(claims["jti"]) >= 32  # uuid4 hex


def test_refresh_token_lleva_family_id_y_jti():
    tok = tokens.create_refresh_token(SECRET, sub="u1", tv=1, family_id="fam1")
    claims = tokens.decode_token(SECRET, tok, expected_type="refresh")
    assert claims["type"] == "refresh"
    assert claims["family_id"] == "fam1"
    assert claims["jti"]


def test_decode_rechaza_tipo_incorrecto():
    tok = tokens.create_access_token(SECRET, sub="u1", tv=1)
    with pytest.raises(tokens.TokenError):
        tokens.decode_token(SECRET, tok, expected_type="refresh")


def test_decode_rechaza_firma_invalida():
    tok = tokens.create_access_token(SECRET, sub="u1", tv=1)
    with pytest.raises(tokens.TokenError):
        tokens.decode_token(
            "otro-secreto-distinto-de-32-bytes-abcd", tok, expected_type="access"
        )


def test_decode_rechaza_expirado():
    tok = tokens.create_access_token(
        SECRET, sub="u1", tv=1, ttl=timedelta(seconds=-120)
    )
    with pytest.raises(tokens.TokenError):
        tokens.decode_token(SECRET, tok, expected_type="access")


def test_algoritmo_fijado_hs256_no_none():
    # Defensa contra el ataque alg=none: decode exige HS256.
    payload = {"sub": "u1", "type": "access", "tv": 1, "jti": "x"}
    tok_none = jwt.encode(payload, key="", algorithm="none")
    with pytest.raises(tokens.TokenError):
        tokens.decode_token(SECRET, tok_none, expected_type="access")
