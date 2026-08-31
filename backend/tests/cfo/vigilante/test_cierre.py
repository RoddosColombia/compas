# backend/tests/cfo/vigilante/test_cierre.py
"""FABS · vigilante — Task 2: generar_y_entregar_cierre. Detecta el ÚLTIMO mes
CERRADO y lo comenta (reusa `consultar`, fakeado — nunca llama al LLM real);
idempotente por mes, jamás hace backfill. Auditoría verificada contra mongomock vía
`audit_service.configure_audit` (mismo patrón que test_paquete.py)."""

import pytest
import pytest_asyncio
from app.audit import service as audit_service
from app.cfo.agente.modelos import RespuestaCFO, UsoLLM
from app.cfo.vigilante import cierre as C
from app.cfo.vigilante.modelos import AvisoVigilante
from app.core.time import now_bogota
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import EstadoMes, MesControl
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


async def _sembrar_mes(mes: str, estado: EstadoMes) -> None:
    # MesControl es strict/extra-forbid: `mes` debe ser 'YYYY-MM-01' y
    # `saldo_inicial_caja` (Money) es obligatorio (sin default).
    from decimal import Decimal

    await MesControl(mes=mes, estado=estado, saldo_inicial_caja=Decimal("0")).insert()


def _resp(texto="Cerró bien.", abstuvo=False):
    # cifras usa su default (lista vacía). La rama de descarte es `abstuvo and not
    # resp.cifras`: con abstuvo=False el generador PROCEDE (no mira cifras); con
    # abstuvo=True y cifras vacío, ABSTIENE. No hace falta poblar cifras (evita
    # construir objetos Cifra reales y chocar con Pydantic strict).
    return RespuestaCFO(
        texto=texto,
        abstuvo=abstuvo,
        texto_crudo=texto,
        uso=UsoLLM(modelo="m", tokens_in=1, tokens_out=1, iteraciones=1),
    )


@pytest.mark.asyncio
async def test_comenta_el_ultimo_mes_cerrado(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _sembrar_mes("2026-06-01", EstadoMes.CERRADO)
    await _sembrar_mes("2026-07-01", EstadoMes.CERRADO)
    await _sembrar_mes("2026-08-01", EstadoMes.EN_EJECUCION)

    capturado = {}

    async def fake_consultar(prompt, *, actor_id, cliente=None, historial=None):
        capturado["prompt"] = prompt
        return _resp()

    monkeypatch.setattr(C, "consultar", fake_consultar)
    tg = FakeTg()
    monkeypatch.setattr(C, "crear_cliente_telegram", lambda: tg)

    aviso = await C.generar_y_entregar_cierre()
    assert aviso is not None
    assert (
        aviso.tipo == "cierre_mensual" and aviso.periodo == "2026-07"
    )  # el último CERRADO
    assert "2026-07" in capturado["prompt"]
    assert "publicar cierre" in tg.enviados[-1][1]
    doc = await audit_col.find_one({"evento": "vigilante.cierre.generado"})
    assert doc is not None and doc["metadata"]["periodo"] == "2026-07"


@pytest.mark.asyncio
async def test_idempotente_no_recomenta(db, audit_col, monkeypatch):
    await _sembrar_mes("2026-07-01", EstadoMes.CERRADO)
    await AvisoVigilante(
        tipo="cierre_mensual",
        periodo="2026-07",
        texto="ya",
        texto_crudo="ya",
        estado="borrador",
        generado_at=now_bogota(),
    ).insert()

    async def fake_consultar(*a, **k):
        raise AssertionError("no debe llamar a consultar si ya existe")

    monkeypatch.setattr(C, "consultar", fake_consultar)
    assert await C.generar_y_entregar_cierre() is None


@pytest.mark.asyncio
async def test_sin_mes_cerrado_es_none(db, audit_col, monkeypatch):
    await _sembrar_mes("2026-08-01", EstadoMes.EN_EJECUCION)
    assert await C.generar_y_entregar_cierre() is None


@pytest.mark.asyncio
async def test_abstencion_sin_cifras_no_guarda(db, audit_col, monkeypatch):
    await _sembrar_mes("2026-07-01", EstadoMes.CERRADO)

    async def fake_consultar(*a, **k):
        return _resp(abstuvo=True)  # cifras vacío por default → abstiene

    monkeypatch.setattr(C, "consultar", fake_consultar)
    assert await C.generar_y_entregar_cierre() is None
    assert await AvisoVigilante.find_one({}) is None
