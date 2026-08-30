# backend/tests/cfo/vigilante/test_cimiento.py
"""FABS · vigilante (watchdog) — Task 1: cimiento. `PaqueteVigilante` (borrador
semanal del "paquete del lunes"), los 2 eventos de auditoría de su ciclo de vida
(generado/publicado) y el config que identifica al revisor por Telegram.
mongomock; patrón de fixture `db` de la suite (ver tests/cfo/test_calc_caja.py)."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.audit.events import CATALOGO_EVENTOS, AuditEvento
from app.cfo import config
from app.cfo.vigilante.modelos import PaqueteVigilante
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


def test_eventos_vigilante_en_catalogo():
    generado = AuditEvento("vigilante.paquete.generado")
    assert generado is AuditEvento.vigilante_paquete_generado
    assert "vigilante.paquete.publicado" in CATALOGO_EVENTOS


def test_config_revisor(monkeypatch):
    monkeypatch.delenv("VIGILANTE_REVISOR_TELEGRAM_ID", raising=False)
    assert config.vigilante_revisor_telegram_id() is None
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "12345")
    assert config.vigilante_revisor_telegram_id() == 12345


@pytest_asyncio.fixture
async def db():
    """DB mongomock con las clases de dominio inicializadas (incl. PaqueteVigilante
    vía DOMAIN_DOCUMENTS)."""
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=client["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield client


@pytest.mark.asyncio
async def test_paquete_persiste(db):  # `db` = harness Beanie (mongomock)
    pq = PaqueteVigilante(
        semana="2026-08-31",
        texto="hola",
        texto_crudo="[[x]]",
        estado="borrador",
        generado_at=datetime.now(UTC),
        conceptos_usados=["caja_hoy"],
    )
    await pq.insert()
    got = await PaqueteVigilante.find_one(PaqueteVigilante.semana == "2026-08-31")
    assert got is not None and got.estado == "borrador"
