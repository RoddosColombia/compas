# backend/tests/jobs/test_scheduler_vigilante.py
"""FABS · vigilante — Task 3: primer job del scheduler (paquete del lunes 7:00).

`build_scheduler()` registra `vigilante_paquete_lunes` (cron lunes 7:00
America/Bogota). `_job_paquete_lunes` es no-op si `CFO_ENABLED=false`."""

import pytest
from app.jobs import scheduler as S


def test_registra_job_paquete_lunes():
    sched = S.build_scheduler()
    job = sched.get_job("vigilante_paquete_lunes")
    assert job is not None
    f = {x.name: str(x) for x in job.trigger.fields}
    assert f["day_of_week"] == "mon" and f["hour"] == "7" and f["minute"] == "0"


@pytest.mark.asyncio
async def test_wrapper_noop_con_flag_off(monkeypatch):
    monkeypatch.setenv("CFO_ENABLED", "false")
    llamado = {"n": 0}
    import app.cfo.vigilante.paquete as P

    async def fake():
        llamado["n"] += 1

    monkeypatch.setattr(P, "generar_y_entregar_paquete", fake)
    await S._job_paquete_lunes()
    assert llamado["n"] == 0
