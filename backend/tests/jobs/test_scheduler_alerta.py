# backend/tests/jobs/test_scheduler_alerta.py
"""FABS · vigilante — Task 6: job diario de la alerta de caja (8:00 Bogota).

`build_scheduler()` registra `vigilante_alerta_caja` (cron diario 8:00
America/Bogota). `_job_alerta_caja` es no-op si `CFO_ENABLED` está off o si
la alerta está apagada por config (`leer_alerta_caja_activa`)."""

import pytest
from app.jobs import scheduler as S


def test_job_alerta_registrado():
    sch = S.build_scheduler()
    job = sch.get_job("vigilante_alerta_caja")
    assert job is not None
    f = {x.name: str(x) for x in job.trigger.fields}
    assert f["hour"] == "8" and f["minute"] == "0"


@pytest.mark.asyncio
async def test_noop_con_flag_cfo_off(monkeypatch):
    monkeypatch.setattr("app.cfo.config.cfo_enabled", lambda: False)
    llamado = {"v": False}

    async def _no():
        llamado["v"] = True

    monkeypatch.setattr("app.cfo.vigilante.alerta.generar_y_entregar_alerta", _no)
    await S._job_alerta_caja()
    assert llamado["v"] is False


@pytest.mark.asyncio
async def test_noop_con_alerta_off(monkeypatch):
    monkeypatch.setattr("app.cfo.config.cfo_enabled", lambda: True)

    async def _off():
        return False

    monkeypatch.setattr("app.configuracion.service.leer_alerta_caja_activa", _off)
    llamado = {"v": False}

    async def _no():
        llamado["v"] = True

    monkeypatch.setattr("app.cfo.vigilante.alerta.generar_y_entregar_alerta", _no)
    await S._job_alerta_caja()
    assert llamado["v"] is False


@pytest.mark.asyncio
async def test_corre_cuando_todo_encendido(monkeypatch):
    monkeypatch.setattr("app.cfo.config.cfo_enabled", lambda: True)

    async def _on():
        return True

    monkeypatch.setattr("app.configuracion.service.leer_alerta_caja_activa", _on)
    llamado = {"v": False}

    async def _si():
        llamado["v"] = True

    monkeypatch.setattr("app.cfo.vigilante.alerta.generar_y_entregar_alerta", _si)
    await S._job_alerta_caja()
    assert llamado["v"] is True
