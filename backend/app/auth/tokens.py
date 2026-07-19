# backend/app/auth/tokens.py
"""JWT access/refresh endurecido (Spec §4 / §8.1; cripto Kimi Bajas 3/4).

- `algorithms=['HS256']` explícito en decode (defensa alg=none).
- `leeway=30s`; `jti` uuid4 (≥128 bits) en access y refresh.
- Claims: sub (usuario_id), tv (token_version), type (access|refresh), jti, iat, exp;
  el refresh añade family_id. Tiempos UTC-aware (regla A-04)."""

from datetime import timedelta
from uuid import uuid4

import jwt

from app.core.time import now_utc

ALGO = "HS256"
LEEWAY = 30
ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=30)


class TokenError(Exception):
    """Token inválido (firma, expiración, tipo o algoritmo)."""


def _new_jti() -> str:
    return uuid4().hex


def create_access_token(
    secret: str,
    *,
    sub: str,
    tv: int,
    jti: str | None = None,
    ttl: timedelta = ACCESS_TTL,
) -> str:
    now = now_utc()
    claims = {
        "sub": sub,
        "tv": tv,
        "type": "access",
        "jti": jti or _new_jti(),
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(claims, secret, algorithm=ALGO)


def create_refresh_token(
    secret: str,
    *,
    sub: str,
    tv: int,
    family_id: str,
    jti: str | None = None,
    ttl: timedelta = REFRESH_TTL,
) -> str:
    now = now_utc()
    claims = {
        "sub": sub,
        "tv": tv,
        "type": "refresh",
        "family_id": family_id,
        "jti": jti or _new_jti(),
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(claims, secret, algorithm=ALGO)


def decode_token(
    secret: str, token: str, *, expected_type: str, verify_exp: bool = True
) -> dict:
    """`verify_exp=False` (solo para logout, Kimi H-6): decodifica con firma válida
    un access ya expirado para extraer jti/exp y denegarlo hasta su exp natural."""
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[ALGO],
            leeway=LEEWAY,
            options={"verify_exp": verify_exp},
        )
    except jwt.PyJWTError as e:
        raise TokenError(str(e)) from e
    if claims.get("type") != expected_type:
        raise TokenError(f"tipo inesperado: {claims.get('type')} != {expected_type}")
    return claims
