# backend/tests/cfo/vigilante/test_paquete.py
"""FABS · vigilante — Task 2: generar_y_entregar_paquete. Monkeypatch de los
servicios reales (consultar/crear_cliente/crear_cliente_telegram) a nivel del
módulo `paquete`; auditoría verificada contra mongomock vía `service.configure_audit`
(AuditLog es un BaseModel, no un Document — no se puede `AuditLog.find_one`)."""

import pytest
import pytest_asyncio
from app.audit import service as audit_service
from app.cfo.vigilante import paquete as P
from app.cfo.vigilante.modelos import PaqueteVigilante
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


class _Resp:
    def __init__(self, abstuvo=False, cifras=("x",)):
        self.texto = "Caja hoy $10.000.000"
        self.texto_crudo = "Caja hoy [[caja_hoy]]"
        self.abstuvo = abstuvo
        self.motivo = None
        self.conceptos_usados = ["caja_hoy"]
        self.cifras = list(cifras)


@pytest_asyncio.fixture
async def db():
    """DB mongomock con las clases de dominio inicializadas (incl. PaqueteVigilante)."""
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


@pytest.mark.asyncio
async def test_genera_guarda_audita_envia(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")

    async def fake_consultar(*a, **k):
        return _Resp()

    monkeypatch.setattr(P, "consultar", fake_consultar)
    monkeypatch.setattr(P, "crear_cliente", lambda: object())

    enviados = []

    class FakeTg:
        async def enviar(self, chat_id, texto):
            enviados.append((chat_id, texto))

    monkeypatch.setattr(P, "crear_cliente_telegram", lambda: FakeTg())

    pq = await P.generar_y_entregar_paquete()

    assert pq is not None and pq.estado == "borrador"
    borrador = await PaqueteVigilante.find_one(PaqueteVigilante.estado == "borrador")
    assert borrador is not None
    assert enviados and enviados[0][0] == 999
    assert "Caja hoy $10.000.000" in enviados[0][1]

    doc = await audit_col.find_one({"evento": "vigilante.paquete.generado"})
    assert doc is not None
    assert doc["entidad_id"] == pq.semana
    assert doc["metadata"]["conceptos_usados"] == ["caja_hoy"]


@pytest.mark.asyncio
async def test_idempotente_una_por_semana(db, monkeypatch):
    async def fake_consultar(*a, **k):
        return _Resp()

    monkeypatch.setattr(P, "consultar", fake_consultar)
    monkeypatch.setattr(P, "crear_cliente", lambda: object())
    monkeypatch.setattr(P, "crear_cliente_telegram", lambda: None)
    monkeypatch.delenv("VIGILANTE_REVISOR_TELEGRAM_ID", raising=False)

    a = await P.generar_y_entregar_paquete()
    b = await P.generar_y_entregar_paquete()

    assert a is not None and b is None  # segunda misma semana: no duplica


@pytest.mark.asyncio
async def test_abstiene_sin_cifras_no_guarda(db, monkeypatch):
    async def fake_consultar(*a, **k):
        return _Resp(abstuvo=True, cifras=())

    monkeypatch.setattr(P, "consultar", fake_consultar)
    monkeypatch.setattr(P, "crear_cliente", lambda: object())
    monkeypatch.setattr(P, "crear_cliente_telegram", lambda: None)

    assert await P.generar_y_entregar_paquete() is None
    assert await PaqueteVigilante.find_one({}) is None


@pytest.mark.asyncio
async def test_sin_revisor_configurado_no_envia_pero_guarda(db, monkeypatch):
    async def fake_consultar(*a, **k):
        return _Resp()

    monkeypatch.setattr(P, "consultar", fake_consultar)
    monkeypatch.setattr(P, "crear_cliente", lambda: object())
    llamado = {"v": False}

    def _no_debe_llamarse():
        llamado["v"] = True
        return None

    monkeypatch.setattr(P, "crear_cliente_telegram", _no_debe_llamarse)
    monkeypatch.delenv("VIGILANTE_REVISOR_TELEGRAM_ID", raising=False)

    pq = await P.generar_y_entregar_paquete()

    assert pq is not None and pq.estado == "borrador"
    assert llamado["v"] is False  # sin revisor no se llega a crear el cliente Telegram
