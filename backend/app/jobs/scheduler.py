# backend/app/jobs/scheduler.py
"""Entrypoint del worker `compas-jobs` (regla 6 / STACK §2 / render.yaml).

Se arranca con:  python -m app.jobs.scheduler
y SOLO debe correr con RUN_SCHEDULER=true (worker de 1 instancia).

Sprint 0, Sesión 1: el scheduler arranca VACÍO (sin jobs). Los 8 jobs
financieros (recordatorio de carga 8:30, snapshot diario de caja, recálculo de
sugeridos, alertas IVA/vencimientos, reaper de cargas, dump nocturno,
archivado mensual, verificación referencial) se registran en sprints
posteriores. Todos serán idempotentes; jobstore en Mongo; coalesce=True y
misfire_grace_time por job; heartbeat a Better Stack por job (STACK §2, N-04).
"""

from __future__ import annotations

import logging

from app.config import Settings, get_settings

logger = logging.getLogger("compas.jobs")


def ensure_worker_context(settings: Settings) -> None:
    """Falla si RUN_SCHEDULER no es true. Garantiza que el scheduler solo
    corre en el worker, nunca en el web (regla 6)."""
    if not settings.run_scheduler:
        raise RuntimeError(
            "RUN_SCHEDULER debe ser true en el worker compas-jobs (regla 6). "
            "El servicio web nunca ejecuta jobs."
        )


def build_scheduler():
    """Construye el AsyncIOScheduler (import perezoso para no cargar APScheduler
    en los tests del contrato del flag). Sin jobs todavía."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler(timezone="America/Bogota")
    scheduler.add_job(
        _job_paquete_lunes,
        "cron",
        day_of_week="mon",
        hour=7,
        minute=0,
        id="vigilante_paquete_lunes",
        coalesce=True,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    return scheduler


async def _job_paquete_lunes() -> None:
    """Lunes 7:00 (America/Bogota). No-op si CFO_ENABLED está off; import perezoso para
    no acoplar el scheduler al dominio cfo en los tests del contrato del flag."""
    from app.cfo import config as cfo_config

    if not cfo_config.cfo_enabled():
        return
    from app.cfo.vigilante.paquete import generar_y_entregar_paquete

    try:
        await generar_y_entregar_paquete()
    except Exception:  # noqa: BLE001 — un job proactivo no revienta el worker
        logger.exception("fallo en el job del paquete del lunes")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    ensure_worker_context(settings)

    scheduler = build_scheduler()
    scheduler.start()
    logger.info(
        "compas-jobs arriba (0 jobs registrados — Sesión 1). TZ=%s", settings.tz
    )

    import asyncio

    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    main()
