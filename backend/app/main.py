# backend/app/main.py
"""Punto de entrada del servicio web FastAPI (compas-api).

Regla 6 de CLAUDE.md: el servicio web NUNCA arranca el scheduler. El lifespan
falla en duro si detecta RUN_SCHEDULER=true (defensa contra un despliegue mal
configurado)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_router
from app.audit import service as audit_service
from app.auth import repository as auth_repository
from app.config import get_settings
from app.db import mongo

logger = logging.getLogger("compas")

# Campos de dominio que NUNCA deben salir a Sentry (STACK §7, F-23).
_PII_KEYS = {
    "descripcion",
    "proveedor",
    "acreedor",
    "valor",
    "authorization",
    "password",
    "cookie",  # Kimi B-1: la cookie de refresh no debe viajar a Sentry
    "set-cookie",
}


def _scrub_pii(event: dict, _hint: dict) -> dict:
    """before_send de Sentry: elimina campos sensibles antes de enviar."""
    req = event.get("request", {})
    if isinstance(req.get("headers"), dict):
        req["headers"] = {
            k: v for k, v in req["headers"].items() if k.lower() not in _PII_KEYS
        }
    return event


def _init_sentry(settings) -> None:
    """Inicializa Sentry si hay DSN y el SDK está instalado (H3). send_default_pii=False
    + scrubbing. Import guardado: dev/tests sin el paquete no fallan."""
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN presente pero sentry_sdk no instalado.")
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        send_default_pii=False,
        before_send=_scrub_pii,
    )


async def ensure_beanie(app: FastAPI, client, db_name: str) -> bool:
    """Inicializa Beanie una sola vez (idempotente). NO fatal: si Mongo está caído
    devuelve False y deja `app.state.beanie_ready=False`, sin tumbar la liveness.
    Readiness lo reintenta hasta que la BD responda."""
    if getattr(app.state, "beanie_ready", False):
        return True
    try:
        await mongo.init_beanie_for(client, db_name)
        app.state.beanie_ready = True
        return True
    except Exception:  # noqa: BLE001 — degradación controlada, no crash de startup
        logger.warning("init_beanie falló (Mongo no disponible aún); se reintentará.")
        app.state.beanie_ready = False
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Regla 6: el web jamás corre el scheduler.
    if settings.run_scheduler:
        raise RuntimeError(
            "RUN_SCHEDULER=true en el servicio web: prohibido (regla 6). "
            "Los jobs viven solo en el worker compas-jobs."
        )

    # L3 (Kimi): fail-fast del secreto JWT fuera de dev — mismo principio que C-01.
    # Sin esto la app arranca "sana" (health no toca auth) y cada login da 500.
    if settings.app_env != "development" and (
        not settings.jwt_secret or len(settings.jwt_secret) < 32
    ):
        raise RuntimeError(
            "JWT_SECRET requerido y >= 32 bytes fuera de dev (Spec §8.1)."
        )

    _init_sentry(
        settings
    )  # H3: observabilidad de errores (incl. fallos del canal audit)

    # Cliente Motor perezoso (no conecta hasta el primer comando) → el web
    # arranca aunque Mongo esté caído; la liveness no depende de la BD.
    client = mongo.create_client(settings.mongodb_uri_compas)
    app.state.mongo_client = client
    app.state.settings = settings
    app.state.beanie_ready = False

    # init_beanie SÍ conecta (crea índices) → si Mongo está caído al arrancar,
    # colgaría/reventaría el startup y romperia la garantía "liveness sin BD".
    # Por eso es NO fatal aquí y se reintenta idempotentemente desde readiness.
    await ensure_beanie(app, client, settings.mongodb_db)

    # Conexión DEDICADA de auditoría (DoD #6). MONGODB_URI_AUDIT usa el usuario
    # `compas_audit` (audit_writer). FAIL-FAST fuera de dev (Kimi C-01): un warning
    # no es un control — degradar el canal de auditoría en prod es degradación
    # silenciosa de un requisito de primera clase. Solo dev cae a la conexión general.
    if settings.mongodb_uri_audit:
        audit_client = mongo.create_client(settings.mongodb_uri_audit)
    elif settings.app_env == "development":
        audit_client = client  # fallback SOLO en dev (sin separación de privilegios)
        logger.warning(
            "audit por conexión general (dev): sin separación de privilegios."
        )
    else:
        raise RuntimeError(
            "MONGODB_URI_AUDIT requerido fuera de dev: el canal de auditoría no "
            "puede degradarse silenciosamente (DoD #6, Kimi C-01)."
        )
    app.state.audit_client = audit_client
    audit_service.configure_audit(audit_client, settings.mongodb_db)

    # Auth usa la conexión GENERAL de la app (no la de auditoría).
    auth_repository.configure_auth(client, settings.mongodb_db)

    try:
        yield
    finally:
        audit_service.reset_audit()
        auth_repository.reset_auth()
        if audit_client is not client:
            audit_client.close()
        client.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="COMPAS API",
        version=__version__,
        lifespan=lifespan,
    )

    # CORS: origen exacto del frontend + credenciales (cookie de refresh). Spec §4.
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["health"])
    def liveness() -> dict[str, str]:
        """Liveness — SIN tocar la BD. Es el healthCheckPath de render.yaml."""
        return {"status": "ok", "service": "compas-api", "version": __version__}

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
