# backend/app/auth/passwords.py
"""Hashing bcrypt + política de contraseñas (Spec §1.1 / §8.1).

Costo fijo rounds=12 (no solo longitud). Política de LONGITUD: 12 para admin/directivo,
10 para el resto. HIBP y expiración quedan para Sprint 0b (fuera de PR-2)."""

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
