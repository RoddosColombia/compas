# backend/tests/test_scheduler_flag.py
"""Regla 6 de CLAUDE.md / STACK §2 / render.yaml:

  «RUN_SCHEDULER=false en el servicio web, SIEMPRE. Los jobs viven solo en
   el worker compas-jobs (1 instancia).»

Estos tests fijan ese contrato antes de que exista un solo job.
"""

import pytest
from app.config import Settings
from app.jobs.scheduler import ensure_worker_context
from fastapi.testclient import TestClient


def test_default_run_scheduler_es_false(monkeypatch):
    """Sin la env var, el default es false → el web nunca lo activa por accidente."""
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    assert Settings().run_scheduler is False


def test_web_se_niega_a_arrancar_con_run_scheduler_true(monkeypatch):
    """El lifespan del web falla en duro si alguien pone RUN_SCHEDULER=true
    en el servicio web (defensa contra un despliegue mal configurado)."""
    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("RUN_SCHEDULER", "true")
    get_settings.cache_clear()
    application = create_app()

    with pytest.raises(RuntimeError, match="RUN_SCHEDULER"):
        with TestClient(application):
            pass  # entrar al lifespan debe explotar

    get_settings.cache_clear()


def test_worker_lanza_si_run_scheduler_false():
    """El worker compas-jobs se niega a operar si RUN_SCHEDULER no es true."""
    with pytest.raises(RuntimeError, match="RUN_SCHEDULER"):
        ensure_worker_context(Settings(run_scheduler=False))


def test_worker_ok_si_run_scheduler_true():
    # No debe lanzar.
    ensure_worker_context(Settings(run_scheduler=True))
