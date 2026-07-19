# backend/app/auth/passwords.py
"""Hashing bcrypt + política de contraseñas (Spec §1.1 / §8.1).

Costo fijo rounds=12 (no solo longitud). Política de LONGITUD: 12 para admin/directivo,
10 para el resto. HIBP (k-anonymity) añadido en Sprint 0b / PR-2."""

import hashlib
import logging
from collections.abc import Awaitable, Callable

import bcrypt

from app.auth.roles import Role

logger = logging.getLogger("compas.auth")

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


async def password_acceptable(
    password: str,
    rol: Role,
    *,
    fetch: Callable[[str], Awaitable[str]] = _default_fetch,
) -> tuple[bool, str | None]:
    """Política completa (§8.1): longitud por rol + no estar en HIBP. Punto de
    integración para el alta/cambio de contraseña (módulo /users, futuro).

    HIBP es advisory: si la API no responde, NO bloqueamos el cambio (fail-open con
    log) — no dejamos al usuario sin poder operar por una caída de un tercero."""
    if not password_meets_policy(password, rol):
        return False, "La contraseña no cumple la longitud mínima."
    try:
        if await password_pwned(password, fetch=fetch):
            return False, "Contraseña presente en filtraciones conocidas (HIBP)."
    except Exception:  # noqa: BLE001 — HIBP caído no debe bloquear (advisory)
        logger.warning("HIBP no disponible; se omite la verificación.", exc_info=True)
    return True, None
