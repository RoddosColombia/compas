# backend/tests/cfo/vigilante/test_alerta.py
"""FABS · vigilante — Task 5: generar_y_entregar_alerta. Monkeypatch de
evaluar_disparadores/crear_cliente_telegram a nivel del módulo `alerta`; auditoría
verificada contra mongomock vía `service.configure_audit` (AuditLog es un BaseModel,
no un Document — no se puede `AuditLog.find_one`)."""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.audit import service as audit_service
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.cfo.vigilante import alerta as A
from app.cfo.vigilante.disparadores import Disparo, ResultadoAlerta
from app.cfo.vigilante.modelos import AvisoVigilante
from app.core.time import now_bogota
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


def _res_rojo():
    return ResultadoAlerta(
        disparos=[Disparo("real", "rojo")],
        resultados=[
            ResultadoCFO(
                concepto="alerta_disponible_hoy",
                valor=Decimal("500"),
                unidad="COP",
                disponible=True,
                evidencia=Evidencia(
                    fuente="f", fecha_corte="2026-08-30", ref="disponible:hoy"
                ),
            ),
            ResultadoCFO(
                concepto="alerta_umbral_critico",
                valor=Decimal("1000"),
                unidad="COP",
                disponible=True,
                evidencia=Evidencia(fuente="f", fecha_corte=None, ref="umbral:critico"),
            ),
        ],
    )


class FakeTg:
    def __init__(self):
        self.enviados = []

    async def enviar(self, chat_id, texto):
        self.enviados.append((chat_id, texto))


def _async(v):
    async def _f():
        return v

    return _f()


@pytest.mark.asyncio
async def test_dispara_guarda_borrador_audita_y_envia(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    monkeypatch.setattr(A, "evaluar_disparadores", lambda: _async(_res_rojo()))
    tg = FakeTg()
    monkeypatch.setattr(A, "crear_cliente_telegram", lambda: tg)

    pq = await A.generar_y_entregar_alerta()
    assert pq is not None and pq.tipo == "alerta_caja" and pq.estado == "borrador"
    assert "publicar alerta" in tg.enviados[-1][1]
    assert "$500" in pq.texto
    doc = await audit_col.find_one({"evento": "vigilante.alerta.generada"})
    assert doc is not None and doc["metadata"]["severidad"] == "rojo"


@pytest.mark.asyncio
async def test_no_dispara_retira_borrador_pendiente(db, audit_col, monkeypatch):
    # había un borrador de ayer
    await AvisoVigilante(
        tipo="alerta_caja",
        periodo="2026-08-29",
        texto="viejo",
        texto_crudo="c",
        estado="borrador",
        generado_at=now_bogota(),
    ).insert()
    monkeypatch.setattr(A, "evaluar_disparadores", lambda: _async(None))
    out = await A.generar_y_entregar_alerta()
    assert out is None
    viejo = await AvisoVigilante.find_one(AvisoVigilante.periodo == "2026-08-29")
    assert viejo.estado == "superado"
