# backend/tests/cfo/telegram/test_webhook_publicar_alerta.py
"""FABS · vigilante Task 7 — comando "publicar alerta" en el webhook. Generaliza
`_publicar_aviso` por `tipo`: el revisor responde "publicar alerta" al borrador
`tipo="alerta_caja"` -> se difunde a TODO el comité y se audita
`vigilante.alerta.publicada`. El comando "publicar" (sin "alerta") sigue
publicando SOLO el paquete (`tipo="paquete_lunes"`), sin tocar la alerta.

DB: mongomock con las clases de dominio inicializadas (mismo patrón que
test_webhook_publicar.py). Auditoría: verificada contra la colección cruda
`audit_log` vía `audit_service.configure_audit`."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.audit import service as audit_service
from app.cfo.telegram import webhook
from app.cfo.telegram.modelos import VinculoTelegram
from app.cfo.vigilante.modelos import AvisoVigilante
from app.core.time import now_utc
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=client["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield client


@pytest.fixture
def audit_col():
    client = AsyncMongoMockClient()
    audit_service.configure_audit(client, "compas_test_audit")
    yield client["compas_test_audit"]["audit_log"]
    audit_service.reset_audit()


class FakeTg:
    def __init__(self):
        self.enviados = []

    async def enviar(self, chat_id, texto):
        self.enviados.append((chat_id, texto))


async def _vinc(tid, uid):
    await VinculoTelegram(
        telegram_id=tid, user_id=uid, creado_por="a", creado_at=now_utc()
    ).insert()


@pytest.mark.asyncio
async def test_publicar_alerta_difunde_al_comite(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _vinc(999, "rev")
    await _vinc(888, "com")
    await AvisoVigilante(
        tipo="alerta_caja",
        periodo="2026-08-30",
        texto="LA ALERTA",
        texto_crudo="c",
        estado="borrador",
        generado_at=datetime.now(UTC),
    ).insert()
    tg = FakeTg()
    upd = {
        "update_id": 1,
        "message": {
            "from": {"id": 999},
            "chat": {"id": 999},
            "text": "publicar alerta",
        },
    }
    await webhook.procesar_update(upd, cliente_telegram=tg)
    assert {c for c, t in tg.enviados if t == "LA ALERTA"} == {999, 888}
    got = await AvisoVigilante.find_one(AvisoVigilante.periodo == "2026-08-30")
    assert got.estado == "publicado"
    assert (
        await audit_col.find_one({"evento": "vigilante.alerta.publicada"}) is not None
    )


@pytest.mark.asyncio
async def test_publicar_alerta_no_toca_el_paquete(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _vinc(999, "rev")
    await AvisoVigilante(
        tipo="paquete_lunes",
        periodo="2026-08-31",
        texto="EL PAQUETE",
        texto_crudo="c",
        estado="borrador",
        generado_at=datetime.now(UTC),
    ).insert()
    tg = FakeTg()
    upd = {
        "update_id": 2,
        "message": {
            "from": {"id": 999},
            "chat": {"id": 999},
            "text": "publicar alerta",
        },
    }
    await webhook.procesar_update(upd, cliente_telegram=tg)
    assert any(
        "no hay" in t.lower() for _, t in tg.enviados
    )  # no había borrador de alerta
    pq = await AvisoVigilante.find_one(AvisoVigilante.tipo == "paquete_lunes")
    assert pq.estado == "borrador"  # el paquete intacto


@pytest.mark.asyncio
async def test_publicar_sin_alerta_no_publica_solo_por_prefijo(
    db, audit_col, monkeypatch
):
    """'publicar' (sin 'alerta') NUNCA debe publicar la alerta, incluso si es lo
    único con borrador pendiente — el enrutamiento es por comando exacto, no por
    disponibilidad de borradores."""
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _vinc(999, "rev")
    await AvisoVigilante(
        tipo="alerta_caja",
        periodo="2026-08-30",
        texto="LA ALERTA",
        texto_crudo="c",
        estado="borrador",
        generado_at=datetime.now(UTC),
    ).insert()
    tg = FakeTg()
    upd = {
        "update_id": 3,
        "message": {"from": {"id": 999}, "chat": {"id": 999}, "text": "publicar"},
    }
    await webhook.procesar_update(upd, cliente_telegram=tg)
    assert any("no hay" in t.lower() for _, t in tg.enviados)  # no había paquete
    alerta = await AvisoVigilante.find_one(AvisoVigilante.tipo == "alerta_caja")
    assert alerta.estado == "borrador"  # la alerta sigue intacta
