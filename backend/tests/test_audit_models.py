# backend/tests/test_audit_models.py
"""Cobertura de los validadores de AuditLog y del Literal de APP_ENV (Kimi P-2)."""

from datetime import UTC, datetime

import pytest
from app.audit.events import AuditEvento
from app.audit.models import AuditLog
from pydantic import ValidationError


def test_cast_evento_acepta_str_del_catalogo():
    # H-04: el validator before castea str -> AuditEvento (para lecturas desde Mongo).
    log = AuditLog(evento="user.login", entidad="user")
    assert log.evento is AuditEvento.user_login


def test_cast_evento_rechaza_str_fuera_del_catalogo():
    with pytest.raises(ValidationError):
        AuditLog(evento="evento.inventado", entidad="user")


def test_timestamp_naive_es_rechazado():
    # H-05: nunca naive (regla A-04).
    with pytest.raises(ValidationError):
        AuditLog(
            evento=AuditEvento.mes_creado,
            entidad="mes",
            timestamp=datetime(2026, 7, 18, 12, 0, 0),  # naive
        )


def test_timestamp_aware_es_aceptado():
    log = AuditLog(
        evento=AuditEvento.mes_creado,
        entidad="mes",
        timestamp=datetime(2026, 7, 18, 12, 0, 0, tzinfo=UTC),
    )
    assert log.timestamp.tzinfo is not None


def test_app_env_literal_rechaza_typo():
    # Baja: un typo en APP_ENV falla al validar Settings, no en runtime.
    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(app_env="prod")  # no está en el Literal
