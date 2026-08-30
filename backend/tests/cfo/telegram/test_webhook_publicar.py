# backend/tests/cfo/telegram/test_webhook_publicar.py
"""FABS · vigilante Task 4 — comando "publicar" en el webhook. El revisor
(VIGILANTE_REVISOR_TELEGRAM_ID) responde "publicar" al borrador que le llegó
el lunes -> se difunde a TODO el comité (todos los vínculos), el paquete pasa
a `estado="publicado"` y se audita `vigilante.paquete.publicado`. Cualquier
otro remitente, o cualquier otro texto (incluso uno que MENCIONE "publicar"
dentro de una frase), cae al camino normal de Q&A — el match es exacto.

DB: mongomock con las clases de dominio inicializadas (mismo patrón que
tests/cfo/vigilante/test_paquete.py — AvisoVigilante es un Document real).
Auditoría: verificada contra la colección cruda `audit_log` vía
`audit_service.configure_audit` (mismo patrón que tests/test_audit_emit.py),
NUNCA `AuditLog.find_one` (AuditLog es un BaseModel, no un Document)."""

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
    """DB mongomock con las clases de dominio inicializadas (incl. AvisoVigilante
    y VinculoTelegram)."""
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=client["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield client


@pytest.fixture
def audit_col():
    """Configura emit_audit contra una colección mongomock separada y la devuelve."""
    client = AsyncMongoMockClient()
    audit_service.configure_audit(client, "compas_test_audit")
    yield client["compas_test_audit"]["audit_log"]
    audit_service.reset_audit()


class FakeTg:
    def __init__(self):
        self.enviados: list[tuple[int, str]] = []

    async def enviar(self, chat_id, texto):
        self.enviados.append((chat_id, texto))


async def _sembrar_vinculo(telegram_id: int, user_id: str) -> None:
    await VinculoTelegram(
        telegram_id=telegram_id,
        user_id=user_id,
        creado_por="admin",
        creado_at=now_utc(),
    ).insert()


async def _sembrar_borrador(periodo: str = "2026-08-31") -> None:
    await AvisoVigilante(
        tipo="paquete_lunes",
        periodo=periodo,
        texto="EL PAQUETE",
        texto_crudo="[[x]]",
        estado="borrador",
        generado_at=datetime.now(UTC),
        conceptos_usados=[],
    ).insert()


@pytest.mark.asyncio
async def test_revisor_publica_difunde_a_todo_el_comite(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _sembrar_vinculo(999, "u_revisor")
    await _sembrar_vinculo(888, "u_comite")
    await _sembrar_borrador()

    tg = FakeTg()
    update = {
        "update_id": 1,
        "message": {"from": {"id": 999}, "chat": {"id": 999}, "text": "publicar"},
    }
    await webhook.procesar_update(update, cliente_telegram=tg)

    destinos_paquete = {c for c, t in tg.enviados if t == "EL PAQUETE"}
    assert destinos_paquete == {999, 888}  # difundido a todo el comité

    got = await AvisoVigilante.find_one(AvisoVigilante.periodo == "2026-08-31")
    assert got is not None
    assert got.estado == "publicado"
    assert got.publicado_at is not None

    doc = await audit_col.find_one({"evento": "vigilante.paquete.publicado"})
    assert doc is not None
    assert doc["metadata"]["periodo"] == "2026-08-31"
    assert doc["metadata"]["n_destinatarios"] == 2

    # el revisor recibe además la confirmación de publicación
    assert any("publicado al comité" in t for _, t in tg.enviados if _ == 999)


@pytest.mark.asyncio
async def test_publicar_reintentado_no_redifunde(db, audit_col, monkeypatch):
    """Paridad de dedup con el Q&A: si Telegram RE-entrega el mismo update_id del
    comando 'publicar', la 2ª pasada NO vuelve a difundir a todo el comité —
    reenvía la confirmación previa. Cierra el hallazgo Important de la review final."""
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _sembrar_vinculo(999, "u_revisor")
    await _sembrar_vinculo(888, "u_comite")
    await _sembrar_borrador()

    tg = FakeTg()
    update = {
        "update_id": 77,
        "message": {"from": {"id": 999}, "chat": {"id": 999}, "text": "publicar"},
    }
    await webhook.procesar_update(update, cliente_telegram=tg)
    n_difusiones_1 = sum(1 for _, t in tg.enviados if t == "EL PAQUETE")
    assert n_difusiones_1 == 2  # 1ª vez: difunde a todo el comité

    # Telegram re-entrega EXACTAMENTE el mismo update_id
    await webhook.procesar_update(update, cliente_telegram=tg)
    n_difusiones_2 = sum(1 for _, t in tg.enviados if t == "EL PAQUETE")
    assert n_difusiones_2 == 2  # NO re-difundió (sigue en 2, no 4)
    # el revisor recibe de nuevo la confirmación previa (no silencioso)
    confirmaciones = [
        t for c, t in tg.enviados if c == 999 and "publicado al comité" in t
    ]
    assert len(confirmaciones) == 2


@pytest.mark.asyncio
async def test_publicar_sin_borrador_avisa(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _sembrar_vinculo(999, "u_revisor")

    tg = FakeTg()
    update = {
        "update_id": 2,
        "message": {"from": {"id": 999}, "chat": {"id": 999}, "text": "publicar"},
    }
    await webhook.procesar_update(update, cliente_telegram=tg)

    assert any("no hay" in t.lower() for _, t in tg.enviados)
    assert await AvisoVigilante.find_one({}) is None


@pytest.mark.asyncio
async def test_publicar_de_no_revisor_cae_al_qa(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _sembrar_vinculo(888, "u_comite")  # 888 NO es el revisor
    await _sembrar_borrador()

    llamado = {"v": False}

    async def fake_consultar(pregunta, *, actor_id, cliente=None, historial=None):
        llamado["v"] = True
        from app.cfo.agente.modelos import RespuestaCFO, UsoLLM

        return RespuestaCFO(
            texto="respuesta Q&A",
            abstuvo=False,
            texto_crudo="respuesta Q&A",
            uso=UsoLLM(modelo="m", tokens_in=1, tokens_out=1, iteraciones=1),
        )

    monkeypatch.setattr("app.cfo.telegram.webhook.servicio.consultar", fake_consultar)

    tg = FakeTg()
    update = {
        "update_id": 3,
        "message": {"from": {"id": 888}, "chat": {"id": 888}, "text": "publicar"},
    }
    await webhook.procesar_update(update, cliente_telegram=tg)

    assert llamado["v"] is True  # cayó al Q&A, no a la difusión
    pq = await AvisoVigilante.find_one(AvisoVigilante.periodo == "2026-08-31")
    assert pq.estado == "borrador"  # nadie lo publicó
    assert not any(t == "EL PAQUETE" for _, t in tg.enviados)


@pytest.mark.asyncio
async def test_frase_que_menciona_publicar_cae_al_qa(db, audit_col, monkeypatch):
    """Match exacto (no substring): una pregunta que solo CONTIENE la palabra
    "publicar" no debe disparar el comando de difusión."""
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _sembrar_vinculo(999, "u_revisor")
    await _sembrar_borrador()

    llamado = {"v": False}

    async def fake_consultar(pregunta, *, actor_id, cliente=None, historial=None):
        llamado["v"] = True
        from app.cfo.agente.modelos import RespuestaCFO, UsoLLM

        return RespuestaCFO(
            texto="respuesta Q&A",
            abstuvo=False,
            texto_crudo="respuesta Q&A",
            uso=UsoLLM(modelo="m", tokens_in=1, tokens_out=1, iteraciones=1),
        )

    monkeypatch.setattr("app.cfo.telegram.webhook.servicio.consultar", fake_consultar)

    tg = FakeTg()
    update = {
        "update_id": 4,
        "message": {
            "from": {"id": 999},
            "chat": {"id": 999},
            "text": "¿debería publicar X?",
        },
    }
    await webhook.procesar_update(update, cliente_telegram=tg)

    assert llamado["v"] is True
    pq = await AvisoVigilante.find_one(AvisoVigilante.periodo == "2026-08-31")
    assert pq.estado == "borrador"
