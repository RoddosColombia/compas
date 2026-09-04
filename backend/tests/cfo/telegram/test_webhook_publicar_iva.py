# backend/tests/cfo/telegram/test_webhook_publicar_iva.py
"""FABS · vigilante Task 7 — comando "publicar iva" en el webhook. Generaliza
`_publicar_aviso` por `tipo`: el revisor responde "publicar iva" al borrador
`tipo="iva_tesoreria"` -> se difunde a TODO el comité y se audita
`vigilante.iva.publicado`. Otros comandos "publicar*" no tocan el borrador
de IVA; el match es exacto (una frase que solo CONTIENE "publicar iva" cae
al Q&A); dedup por update_id evita re-difundir."""

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
async def test_publicar_iva_difunde_al_comite(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _vinc(999, "rev")
    await _vinc(888, "com")
    await AvisoVigilante(
        tipo="iva_tesoreria",
        periodo="2026-08",
        texto="EL AVISO DE IVA",
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
            "text": "publicar iva",
        },
    }
    await webhook.procesar_update(upd, cliente_telegram=tg)
    assert {c for c, t in tg.enviados if t == "EL AVISO DE IVA"} == {999, 888}
    got = await AvisoVigilante.find_one(AvisoVigilante.periodo == "2026-08")
    assert got.estado == "publicado"
    assert await audit_col.find_one({"evento": "vigilante.iva.publicado"}) is not None


@pytest.mark.asyncio
async def test_publicar_iva_no_toca_otros_tipos(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _vinc(999, "rev")
    await AvisoVigilante(
        tipo="cierre_mensual",
        periodo="2026-07",
        texto="EL CIERRE",
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
            "text": "publicar iva",
        },
    }
    await webhook.procesar_update(upd, cliente_telegram=tg)
    assert any("no hay" in t.lower() for _, t in tg.enviados)  # sin borrador de iva
    cierre = await AvisoVigilante.find_one(AvisoVigilante.tipo == "cierre_mensual")
    assert cierre.estado == "borrador"  # el cierre intacto


@pytest.mark.asyncio
async def test_publicar_cierre_no_publica_iva_solo_por_prefijo(
    db, audit_col, monkeypatch
):
    """'publicar cierre' NUNCA debe publicar el aviso de IVA, incluso si es lo
    único con borrador pendiente — el enrutamiento es por comando exacto, no por
    disponibilidad de borradores."""
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _vinc(999, "rev")
    await AvisoVigilante(
        tipo="iva_tesoreria",
        periodo="2026-08",
        texto="EL AVISO DE IVA",
        texto_crudo="c",
        estado="borrador",
        generado_at=datetime.now(UTC),
    ).insert()
    tg = FakeTg()
    upd = {
        "update_id": 3,
        "message": {
            "from": {"id": 999},
            "chat": {"id": 999},
            "text": "publicar cierre",
        },
    }
    await webhook.procesar_update(upd, cliente_telegram=tg)
    assert any("no hay" in t.lower() for _, t in tg.enviados)  # no había cierre
    iva = await AvisoVigilante.find_one(AvisoVigilante.tipo == "iva_tesoreria")
    assert iva.estado == "borrador"  # el aviso de IVA sigue intacto


@pytest.mark.asyncio
async def test_frase_que_solo_contiene_publicar_iva_cae_a_qa(
    db, audit_col, monkeypatch
):
    """Match exacto: una frase que CONTIENE 'publicar iva' pero no es igual al
    comando no debe enrutar a `_publicar_aviso` (cae al Q&A normal)."""
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _vinc(999, "rev")
    await AvisoVigilante(
        tipo="iva_tesoreria",
        periodo="2026-08",
        texto="EL AVISO DE IVA",
        texto_crudo="c",
        estado="borrador",
        generado_at=datetime.now(UTC),
    ).insert()

    from app.cfo.agente.modelos import RespuestaCFO, UsoLLM

    async def _fake_consultar(pregunta, *, actor_id, cliente=None, historial=None):
        return RespuestaCFO(
            texto="respuesta del Q&A",
            abstuvo=True,
            texto_crudo="respuesta del Q&A",
            uso=UsoLLM(modelo="m", tokens_in=1, tokens_out=1, iteraciones=1),
        )

    monkeypatch.setattr("app.cfo.telegram.webhook.servicio.consultar", _fake_consultar)

    async def _fake_registrar(user_id, pregunta, texto_crudo, update_id, envio):
        return None

    monkeypatch.setattr(
        "app.cfo.telegram.webhook.hilos.registrar_turno", _fake_registrar
    )

    tg = FakeTg()
    upd = {
        "update_id": 4,
        "message": {
            "from": {"id": 999},
            "chat": {"id": 999},
            "text": "necesito publicar iva antes de fin de mes",
        },
    }
    await webhook.procesar_update(upd, cliente_telegram=tg)
    iva = await AvisoVigilante.find_one(AvisoVigilante.tipo == "iva_tesoreria")
    assert iva.estado == "borrador"  # no se publicó por contener la frase
    assert any("respuesta del Q&A" in t for _, t in tg.enviados)


@pytest.mark.asyncio
async def test_publicar_iva_dedup_no_redifunde(db, audit_col, monkeypatch):
    """Paridad de dedup con los otros comandos de publicar: si Telegram
    RE-entrega el mismo update_id de 'publicar iva', la 2ª pasada NO vuelve a
    difundir a todo el comité — reenvía la confirmación previa."""
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _vinc(999, "rev")
    await _vinc(888, "com")
    await AvisoVigilante(
        tipo="iva_tesoreria",
        periodo="2026-08",
        texto="EL AVISO DE IVA",
        texto_crudo="c",
        estado="borrador",
        generado_at=datetime.now(UTC),
    ).insert()

    tg = FakeTg()
    upd = {
        "update_id": 5,
        "message": {
            "from": {"id": 999},
            "chat": {"id": 999},
            "text": "publicar iva",
        },
    }
    await webhook.procesar_update(upd, cliente_telegram=tg)
    n_1 = sum(1 for _, t in tg.enviados if t == "EL AVISO DE IVA")
    assert n_1 == 2  # 1ª vez: difunde a todo el comité

    await webhook.procesar_update(upd, cliente_telegram=tg)
    n_2 = sum(1 for _, t in tg.enviados if t == "EL AVISO DE IVA")
    assert n_2 == 2  # NO re-difundió

    confirmaciones = [
        t for c, t in tg.enviados if c == 999 and "publicado al comité" in t
    ]
    assert len(confirmaciones) == 2
