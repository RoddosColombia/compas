# backend/app/auth/models.py
"""Esquemas de auth (Pydantic strict). Spec §1.1 / §2.3.

Como en audit, son Pydantic planos: la persistencia va por repositorios con Motor
crudo (no Beanie ODM). Tiempos UTC-aware (regla A-04)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.roles import Role
from app.core.time import now_utc

USERS_COLLECTION = "users"
REFRESH_SESSIONS_COLLECTION = "refresh_sessions"
JWT_DENYLIST_COLLECTION = "jwt_denylist"
LOGIN_THROTTLE_COLLECTION = "login_throttle"

AUTH_INDEXES = {
    USERS_COLLECTION: [{"keys": [("email", 1)], "name": "email_unico", "unique": True}],
    REFRESH_SESSIONS_COLLECTION: [
        {"keys": [("jti", 1)], "name": "jti_unico", "unique": True},
        {"keys": [("family_id", 1)], "name": "por_familia"},
        # TTL familia (refresh_ttl_days): mecanismo expireAfterSeconds:0 + expires_at
        {"keys": [("expires_at", 1)], "name": "ttl_familia", "expireAfterSeconds": 0},
    ],
    JWT_DENYLIST_COLLECTION: [
        {"keys": [("jti", 1)], "name": "jti_unico", "unique": True},
        {"keys": [("expires_at", 1)], "name": "ttl_por_tipo", "expireAfterSeconds": 0},
    ],
    LOGIN_THROTTLE_COLLECTION: [
        {"keys": [("expires_at", 1)], "name": "ttl_ventana", "expireAfterSeconds": 0},
    ],
}


class User(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: str | None = None
    email: str  # normalizado strip().lower() en el servicio; unicidad por índice
    password_hash: str
    rol: Role
    token_version: int = 1
    activo: bool = True
    failed_attempts: int = 0
    locked_until: datetime | None = None
    # ── MFA (Spec §8.1 / DoD #11) ──
    mfa_habilitado: bool = False
    mfa_secret: str | None = None  # CIFRADO en reposo (Fernet); nunca en claro
    mfa_backup_codes: list[str] = Field(default_factory=list)  # hashes bcrypt, un uso
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    @field_validator("email", mode="before")
    @classmethod
    def _normaliza_email(cls, v: object) -> object:
        # L5: normalizar en ESCRITURA (no solo en login); si no, A@Roddos.com
        # queda inlogueable. Unicidad por el índice sobre el valor normalizado.
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("rol", mode="before")
    @classmethod
    def _cast_rol(cls, v: object) -> Role:
        return v if isinstance(v, Role) else Role(v)  # str→Role al leer de Mongo

    @field_validator("locked_until", "created_at", "updated_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("datetime debe ser UTC-aware (regla A-04)")
        return v


class RefreshSession(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    jti: str
    usuario_id: str
    family_id: str
    family_created_at: datetime = Field(default_factory=now_utc)  # inmutable, heredado
    ultimo_uso: datetime = Field(default_factory=now_utc)
    expires_at: datetime  # family_created_at + refresh_ttl_days (para el TTL)
    rotado: bool = False
    revocado: bool = False
