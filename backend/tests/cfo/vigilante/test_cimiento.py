# backend/tests/cfo/vigilante/test_cimiento.py
"""FABS · vigilante (watchdog) — Task 1: cimiento. `AvisoVigilante(tipo)` generaliza
el borrador (paquete del lunes / alerta de caja) con `(tipo, periodo)` como clave
de idempotencia, los eventos de auditoría de su ciclo de vida (generado/publicado
para ambos tipos) y el config que identifica al revisor por Telegram.
mongomock; patrón de fixture `db` de la suite (ver tests/cfo/test_calc_caja.py)."""

import pytest
import pytest_asyncio
from app.audit.events import CATALOGO_EVENTOS, AuditEvento
from app.cfo import config
from app.cfo.vigilante.modelos import CFO_AVISOS_COLLECTION, AvisoVigilante
from app.core.time import now_bogota
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


def test_eventos_vigilante_en_catalogo():
    generado = AuditEvento("vigilante.paquete.generado")
    assert generado is AuditEvento.vigilante_paquete_generado
    assert "vigilante.paquete.publicado" in CATALOGO_EVENTOS
    assert "vigilante.alerta.generada" in CATALOGO_EVENTOS
    assert "vigilante.alerta.publicada" in CATALOGO_EVENTOS


def test_config_revisor(monkeypatch):
    monkeypatch.delenv("VIGILANTE_REVISOR_TELEGRAM_ID", raising=False)
    assert config.vigilante_revisor_telegram_id() is None
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "12345")
    assert config.vigilante_revisor_telegram_id() == 12345


@pytest_asyncio.fixture
async def db():
    """DB mongomock con las clases de dominio inicializadas (incl. AvisoVigilante
    vía DOMAIN_DOCUMENTS)."""
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=client["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield client


@pytest.mark.asyncio
async def test_aviso_persiste_con_tipo_y_periodo(db):
    a = AvisoVigilante(
        tipo="alerta_caja",
        periodo="2026-08-30",
        texto="hola",
        texto_crudo="[[x]]",
        estado="borrador",
        generado_at=now_bogota(),
    )
    await a.insert()
    got = await AvisoVigilante.find_one(AvisoVigilante.periodo == "2026-08-30")
    assert got is not None and got.tipo == "alerta_caja" and got.estado == "borrador"
    assert AvisoVigilante.get_settings().name == CFO_AVISOS_COLLECTION


@pytest.mark.asyncio
async def test_indice_unico_tipo_periodo(db):
    from pymongo.errors import DuplicateKeyError

    base = dict(
        periodo="2026-08-31",
        texto="t",
        texto_crudo="c",
        estado="borrador",
        generado_at=now_bogota(),
    )
    await AvisoVigilante(tipo="alerta_caja", **base).insert()
    # mismo (tipo, periodo) colisiona; distinto tipo NO
    await AvisoVigilante(tipo="paquete_lunes", **base).insert()
    with pytest.raises(DuplicateKeyError):
        await AvisoVigilante(tipo="alerta_caja", **base).insert()
