# backend/tests/cfo/vigilante/test_disparadores.py
"""FABS · vigilante — Task 3: evaluador de disparadores. Cubre el disparador
proyectado (fake de proyeccion.service.proyectar_vigente) y el disparador real
(mes en ejecución + cierre.service.conciliacion), con abstención (regla 7) cuando
falta config, cuando no hay mes en ejecución, o cuando hay bancos sin reportar."""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.cfo.vigilante import disparadores as D
from app.core.time import today_bogota
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import EstadoMes, MesControl
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


def _proy(meses, piso, minima="1000", atencion="3000"):
    return {
        "caja_minima": minima, "caja_atencion": atencion, "piso_caja": piso,
        "meses": meses,
    }


@pytest_asyncio.fixture
async def db():
    """DB mongomock con las clases de dominio inicializadas (incl. MesControl vía
    DOMAIN_DOCUMENTS)."""
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=client["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield client


@pytest.mark.asyncio
async def test_proyectado_ambar_por_quiebre_en_atencion(monkeypatch):
    async def fake_proy(**k):
        return _proy([{"mes": "2026-09", "estado": "ok"},
                      {"mes": "2026-10", "estado": "atencion"}], piso="2500")
    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)
    monkeypatch.setattr(D, "_disparador_real", _sin_real)  # aísla el proyectado
    res = await D.evaluar_disparadores()
    assert res is not None
    d = next(x for x in res.disparos if x.tipo == "proyectado")
    assert d.severidad == "ambar"
    piso = next(r for r in res.resultados if r.concepto == "alerta_piso")
    assert piso.evidencia.ref == "quiebre:2026-10"


@pytest.mark.asyncio
async def test_proyectado_rojo_por_critico(monkeypatch):
    async def fake_proy(**k):
        return _proy([{"mes": "2026-09", "estado": "critico"}], piso="500")
    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)
    monkeypatch.setattr(D, "_disparador_real", _sin_real)
    res = await D.evaluar_disparadores()
    assert res.severidad == "rojo"


@pytest.mark.asyncio
async def test_sin_quiebre_y_sin_real_es_none(monkeypatch):
    async def fake_proy(**k):
        return _proy([{"mes": "2026-09", "estado": "ok"}], piso="9000")
    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)
    monkeypatch.setattr(D, "_disparador_real", _sin_real)
    assert await D.evaluar_disparadores() is None


@pytest.mark.asyncio
async def test_sin_config_proyeccion_abstiene(monkeypatch):
    from app.proyeccion.service import ProyeccionError

    async def fake_proy(**k):
        raise ProyeccionError("sin params", 409)
    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)
    assert await D.evaluar_disparadores() is None


async def _sin_real(*a, **k):  # helper: el disparador real no dispara
    return None, []


# --- disparador real -------------------------------------------------------


@pytest.mark.asyncio
async def test_real_rojo_por_consolidado_bajo_minima(db, monkeypatch):
    async def fake_proy(**k):
        return _proy([{"mes": "2026-09", "estado": "ok"}], piso="9000",
                      minima="1000", atencion="3000")
    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)

    await MesControl(
        mes="2026-08-01", estado=EstadoMes.EN_EJECUCION,
        saldo_inicial_caja=Decimal("100000"),
    ).insert()

    async def fake_conciliacion(mes):
        assert mes == "2026-08-01"
        return {
            "consolidado_reportado": "500",  # bajo caja_minima=1000
            "sin_dato": [],
        }
    monkeypatch.setattr(D, "conciliacion", fake_conciliacion)

    res = await D.evaluar_disparadores()
    assert res is not None
    d = next(x for x in res.disparos if x.tipo == "real")
    assert d.severidad == "rojo"
    disponible = next(r for r in res.resultados if r.concepto == "alerta_disponible_hoy")
    assert disponible.valor == Decimal("500")
    assert disponible.evidencia.ref == "disponible:hoy"
    assert disponible.evidencia.fecha_corte == today_bogota().isoformat()


@pytest.mark.asyncio
async def test_real_se_abstiene_si_hay_bancos_sin_dato(db, monkeypatch):
    async def fake_proy(**k):
        return _proy([{"mes": "2026-09", "estado": "ok"}], piso="9000",
                      minima="1000", atencion="3000")
    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)

    await MesControl(
        mes="2026-08-01", estado=EstadoMes.EN_EJECUCION,
        saldo_inicial_caja=Decimal("100000"),
    ).insert()

    async def fake_conciliacion(mes):
        return {
            "consolidado_reportado": "500",  # bajo minima, pero hay banco sin dato
            "sin_dato": ["bancolombia"],
        }
    monkeypatch.setattr(D, "conciliacion", fake_conciliacion)

    # sin proyectado y sin real: el resultado global es None (abstención total)
    assert await D.evaluar_disparadores() is None


@pytest.mark.asyncio
async def test_real_se_abstiene_sin_mes_en_ejecucion(db, monkeypatch):
    async def fake_proy(**k):
        return _proy([{"mes": "2026-09", "estado": "ok"}], piso="9000",
                      minima="1000", atencion="3000")
    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)

    def _no_deberia_llamarse(mes):
        raise AssertionError("conciliacion no debe llamarse sin mes en ejecución")
    monkeypatch.setattr(D, "conciliacion", _no_deberia_llamarse)

    # sin MesControl EN_EJECUCION sembrado: el disparador real se abstiene
    assert await D.evaluar_disparadores() is None
