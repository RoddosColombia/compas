# backend/tests/jobs/test_scheduler_cierre.py
"""FABS · vigilante — Task 3: job diario del cierre mensual (7:30 Bogota).

`build_scheduler()` registra `vigilante_cierre_mensual` (cron diario 7:30
America/Bogota). `_job_cierre_mensual` es no-op si `CFO_ENABLED` está off."""

import pytest
from app.jobs import scheduler as S


def test_job_cierre_registrado():
    sch = S.build_scheduler()
    job = sch.get_job("vigilante_cierre_mensual")
    assert job is not None
    f = {x.name: str(x) for x in job.trigger.fields}
    assert f["hour"] == "7" and f["minute"] == "30"


@pytest.mark.asyncio
async def test_noop_con_flag_off(monkeypatch):
    monkeypatch.setattr("app.cfo.config.cfo_enabled", lambda: False)
    llamado = {"v": False}

    async def _no():
        llamado["v"] = True

    monkeypatch.setattr("app.cfo.vigilante.cierre.generar_y_entregar_cierre", _no)
    await S._job_cierre_mensual()
    assert llamado["v"] is False


@pytest.mark.asyncio
async def test_corre_con_flag_on(monkeypatch):
    monkeypatch.setattr("app.cfo.config.cfo_enabled", lambda: True)
    llamado = {"v": False}

    async def _si():
        llamado["v"] = True

    monkeypatch.setattr("app.cfo.vigilante.cierre.generar_y_entregar_cierre", _si)
    await S._job_cierre_mensual()
    assert llamado["v"] is True
