# backend/app/auth/passwords.py
"""Hashing bcrypt + política de contraseñas (Spec §1.1 / §8.1).

Costo fijo rounds=12 (no solo longitud). Política de LONGITUD: 12 para admin/directivo,
10 para el resto. HIBP (k-anonymity) añadido en Sprint 0b / PR-2."""

import hashlib
from collections.abc import Awaitable, Callable

import bcrypt

from app.auth.roles import Role

ROUNDS = 12
_LARGOS = {Role.admin: 12, Role.directivo: 12, Role.financiero: 10, Role.consulta: 10}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=ROUNDS)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def password_meets_policy(password: str, rol: Role) -> bool:
    return len(password) >= _LARGOS[rol]


# Hash dummy para comparar cuando el email no existe → login de tiempo/forma uniforme
# (anti-enumeración, Kimi M-04). Se computa una vez al importar.
DUMMY_HASH = hash_password("dummy-password-anti-enumeration-000")


# ── HIBP (Have I Been Pwned) — k-anonymity ───────────────────────────────
_HIBP_RANGE = "https://api.pwnedpasswords.com/range/"


async def _default_fetch(prefix: str) -> str:
    """GET al rango de HIBP. Solo viaja el prefijo de 5 hex del SHA-1 (k-anonymity):
    ni la contraseña ni el hash completo salen del backend."""
    import httpx

    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{_HIBP_RANGE}{prefix}", headers={"Add-Padding": "true"})
        r.raise_for_status()
        return r.text


async def password_pwned(
    password: str, *, fetch: Callable[[str], Awaitable[str]] = _default_fetch
) -> bool:
    """True si la contraseña aparece en filtraciones conocidas (HIBP). `fetch` se
    inyecta en tests. El SHA-1 aquí NO es para almacenar: es el protocolo de HIBP."""
    digest = hashlib.sha1(password.encode()).hexdigest().upper()  # noqa: S324
    prefix, suffix = digest[:5], digest[5:]
    cuerpo = await fetch(prefix)
    for linea in cuerpo.splitlines():
        parte = linea.split(":", 1)[0].strip().upper()
        if parte == suffix:
            return True
    return False
