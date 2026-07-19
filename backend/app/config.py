# backend/app/config.py
"""Configuración de la app vía Pydantic Settings.

Regla 12 de CLAUDE.md / STACK §5.1: las env vars son SOLO para secretos y
conexiones. Las reglas de negocio parametrizables (umbrales, calendario DIAN)
NO viven aquí: van en la colección `configuracion` (Spec §1.10), y se
implementan desde el Sprint 0b.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignora env vars ajenas (Render/OS inyectan muchas)
        case_sensitive=False,
    )

    # ── Entorno ────────────────────────────────────────────────────────
    # Literal (Kimi Baja): un typo en APP_ENV falla al validar, no en runtime.
    app_env: Literal["development", "staging", "production"] = "development"
    # Zona horaria única de la app (regla 2). La región cloud es otra cosa
    # (se hereda de SISMO; ver RUNBOOK §0).
    tz: str = "America/Bogota"

    # ── Scheduler (regla 6) ────────────────────────────────────────────
    # false en el servicio web SIEMPRE; true SOLO en el worker compas-jobs.
    run_scheduler: bool = False

    # ── Conexión a Mongo (secreto: sync=false en render.yaml) ──────────
    mongodb_uri_compas: str = "mongodb://localhost:27017"
    mongodb_db: str = "compas"
    # Segunda cadena a la MISMA database `compas`, usuario `compas_audit`
    # (rol audit_writer). Inmutabilidad del audit_log (DoD #6; errata E-7 en
    # docs/COMPAS_ERRATA_PENDIENTE_v1_1_3.md). Opcional en dev; obligatoria fuera.
    mongodb_uri_audit: str | None = None

    # ── Auth / sesiones (Spec §4/§8.1) ────────────────────────────────
    access_ttl_min: int = 15  # access token (memoria SPA)
    refresh_ttl_days: int = 30  # vida máxima de la familia de refresh
    refresh_idle_hours: int = 12  # idle máximo del refresh
    login_max_intentos: int = 5  # backoff por cuenta
    login_lock_min: int = 15  # bloqueo tras superar intentos
    login_ip_max: int = 20  # rate limit por IP en la ventana
    login_ip_window_min: int = 15
    cookie_secure: bool = True  # false solo para pruebas locales sin TLS
    frontend_origin: str = "https://compas.roddos.com"  # CORS + verificación de Origin

    # ── Secretos (opcionales en dev/skeleton; obligatorios en prod) ────
    jwt_secret: str | None = None
    sentry_dsn: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    s3_bucket: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Instancia única de Settings (cacheada). Los tests que cambian env vars
    deben llamar `get_settings.cache_clear()`."""
    return Settings()
