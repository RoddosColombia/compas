# backend/tests/jobs/test_scheduler_iva.py
"""FABS · vigilante — Task 7: 4o job diario, provision de IVA como tesoreria
(7:45 Bogota).

`build_scheduler()` registra `vigilante_iva_tesoreria` (cron diario 7:45
America/Bogota). `_job_iva_tesoreria` es no-op si `CFO_ENABLED` esta off o si
la alerta de IVA esta apagada por config (`leer_alerta_iva_activa`)."""

import pytest
from app.jobs import scheduler as S


def test_job_iva_registrado():
    sch = S.build_scheduler()
    job = sch.get_job("vigilante_iva_tesoreria")
    assert job is not None
    f = {x.name: str(x) for x in job.trigger.fields}
    assert f["hour"] == "7" and f["minute"] == "45"


@pytest.mark.asyncio
async def test_noop_con_flag_cfo_off(monkeypatch):
    monkeypatch.setattr("app.cfo.config.cfo_enabled", lambda: False)
    llamado = {"v": False}

    async def _no():
        llamado["v"] = True

    monkeypatch.setattr("app.cfo.vigilante.iva.generar_y_entregar_iva", _no)
    await S._job_iva_tesoreria()
    assert llamado["v"] is False


@pytest.mark.asyncio
async def test_noop_con_alerta_iva_off(monkeypatch):
    monkeypatch.setattr("app.cfo.config.cfo_enabled", lambda: True)

    async def _off():
        return False

    monkeypatch.setattr("app.configuracion.service.leer_alerta_iva_activa", _off)
    llamado = {"v": False}

    async def _no():
        llamado["v"] = True

    monkeypatch.setattr("app.cfo.vigilante.iva.generar_y_entregar_iva", _no)
    await S._job_iva_tesoreria()
    assert llamado["v"] is False


@pytest.mark.asyncio
async def test_corre_cuando_todo_encendido(monkeypatch):
    monkeypatch.setattr("app.cfo.config.cfo_enabled", lambda: True)

    async def _on():
        return True

    monkeypatch.setattr("app.configuracion.service.leer_alerta_iva_activa", _on)
    llamado = {"v": False}

    async def _si():
        llamado["v"] = True

    monkeypatch.setattr("app.cfo.vigilante.iva.generar_y_entregar_iva", _si)
    await S._job_iva_tesoreria()
    assert llamado["v"] is True
