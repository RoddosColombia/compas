# backend/app/auth/mfa.py
"""Núcleo criptográfico de MFA (Spec §8.1 / DoD #11).

- **TOTP** (pyotp): secreto base32, URI otpauth para QR, verificación con ventana
  ±1 paso (tolerancia de reloj).
- **Cifrado del secreto en reposo** (Fernet/AES): el `mfa_secret` NUNCA se guarda en
  claro; se descifra solo para verificar. Clave desde `settings.mfa_enc_key`.
- **Códigos de respaldo**: hasheados con bcrypt (como las contraseñas) y de UN SOLO
  USO (consumirlos los elimina de la lista).

Funciones puras: la clave se pasa explícita (como `tokens` con el JWT secret), sin
estado global → fácil de testear y sin acoplar a Settings.
"""

import secrets

import pyotp
from cryptography.fernet import Fernet

from app.auth import passwords

_ISSUER = "COMPAS RODDOS"
_BACKUP_BYTES = 4  # 8 hex chars por código


# ── TOTP ────────────────────────────────────────────────────────────────
def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    """URI otpauth:// para el QR de enrolamiento (Google/Microsoft Authenticator)."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=_ISSUER)


def verify_totp(secret: str, code: str, *, valid_window: int = 1) -> bool:
    """valid_window=1 tolera ±1 paso (30s) de desfase de reloj."""
    if not code or not code.strip().isdigit():
        return False
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=valid_window)


# ── Cifrado del secreto en reposo ────────────────────────────────────────
def encrypt_secret(secret: str, key: str) -> str:
    return Fernet(key).encrypt(secret.encode()).decode()


def decrypt_secret(token: str, key: str) -> str:
    """Lanza cryptography.fernet.InvalidToken si la clave no corresponde."""
    return Fernet(key).decrypt(token.encode()).decode()


# ── Códigos de respaldo (bcrypt, un solo uso) ────────────────────────────
def generate_backup_codes(n: int) -> tuple[list[str], list[str]]:
    """Devuelve (claros, hasheados). Los claros se muestran UNA vez al usuario; solo
    los hasheados se persisten."""
    plain = [secrets.token_hex(_BACKUP_BYTES) for _ in range(n)]
    hashed = [passwords.hash_password(c) for c in plain]
    return plain, hashed


def consume_backup_code(code: str, hashed: list[str]) -> tuple[bool, list[str]]:
    """Si `code` coincide con alguno de los hashes, devuelve (True, lista SIN ese hash);
    si no, (False, lista intacta). El consumo garantiza el uso único."""
    for i, h in enumerate(hashed):
        if passwords.verify_password(code, h):
            return True, hashed[:i] + hashed[i + 1 :]
    return False, hashed
