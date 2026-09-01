# backend/app/main.py
"""Punto de entrada del servicio web FastAPI (compas-api).

Regla 6 de CLAUDE.md: el servicio web NUNCA arranca el scheduler. El lifespan
falla en duro si detecta RUN_SCHEDULER=true (defensa contra un despliegue mal
configurado)."""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_router
from app.audit import service as audit_service
from app.auth import repository as auth_repository
from app.config import get_settings
from app.db import mongo
from app.security import SecurityHeadersMiddleware

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
    Readiness lo reintenta hasta que la BD responda.

    HOTFIX 2026-09-01 (Render startup hang): antes solo dependíamos del
    server_selection_timeout de Motor (30s), pero en Render los deploys se
    colgaban indefinidamente en `init_beanie_for` — probablemente por el DNS
    SRV lookup de Atlas o algún handshake que no respeta el timeout. Ahora
    envolvemos con `asyncio.wait_for(..., timeout=15)` para forzar el hard
    limit: si Mongo no responde en 15s, degradamos y seguimos. La liveness
    (/health) queda igual; los endpoints que usan Beanie devolverán 503 hasta
    que readiness reintente exitosamente."""
    if getattr(app.state, "beanie_ready", False):
        return True
    try:
        await asyncio.wait_for(
            mongo.init_beanie_for(client, db_name), timeout=15.0
        )
        app.state.beanie_ready = True
        return True
    except (Exception, asyncio.TimeoutError):  # noqa: BLE001 — degradación controlada
        logger.warning(
            "init_beanie falló o timed out (Mongo no disponible aún); se reintentará."
        )
        app.state.beanie_ready = False
        return False


def _mark(step: str) -> None:
    """HOTFIX 2026-09-01: prints al stderr con flush inmediato para localizar
    dónde se cuelga el startup en Render (uvicorn oculta logs de la app hasta
    completar startup; stderr + flush sí se muestra en tiempo real)."""
    print(f"[lifespan] {step}", file=sys.stderr, flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _mark("A0 · get_settings()")
    settings = get_settings()
    _mark(f"A1 · settings OK · app_env={settings.app_env}")

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

    # MFA_ENC_KEY: sin ella el mfa_secret no se puede descifrar → MFA inservible.
    # Fail-fast fuera de dev (mismo principio que JWT/audit).
    if settings.app_env != "development" and not settings.mfa_enc_key:
        raise RuntimeError(
            "MFA_ENC_KEY requerida fuera de dev: cifra el secreto TOTP (DoD #11)."
        )

    _mark("A2 · pre-sentry")
    _init_sentry(
        settings
    )  # H3: observabilidad de errores (incl. fallos del canal audit)
    _mark("A3 · sentry OK")

    # Cliente Motor perezoso (no conecta hasta el primer comando) → el web
    # arranca aunque Mongo esté caído; la liveness no depende de la BD.
    _mark("A4 · mongo.create_client(uri_compas)")
    client = mongo.create_client(settings.mongodb_uri_compas)
    app.state.mongo_client = client
    app.state.settings = settings
    app.state.beanie_ready = False
    _mark("A5 · client creado")

    # init_beanie SÍ conecta (crea índices) → si Mongo está caído al arrancar,
    # colgaría/reventaría el startup y romperia la garantía "liveness sin BD".
    # Por eso es NO fatal aquí y se reintenta idempotentemente desde readiness.
    _mark("A6 · pre-ensure_beanie (con timeout 15s)")
    ok = await ensure_beanie(app, client, settings.mongodb_db)
    _mark(f"A7 · ensure_beanie retornó ok={ok}")

    # Conexión DEDICADA de auditoría (DoD #6). MONGODB_URI_AUDIT usa el usuario
    # `compas_audit` (audit_writer). FAIL-FAST fuera de dev (Kimi C-01): un warning
    # no es un control — degradar el canal de auditoría en prod es degradación
    # silenciosa de un requisito de primera clase. Solo dev cae a la conexión general.
    _mark("A8 · pre-audit_client")
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
    _mark("A9 · audit_client creado")
    audit_service.configure_audit(audit_client, settings.mongodb_db)
    _mark("A10 · audit configurado")

    # Auth usa la conexión GENERAL de la app (no la de auditoría).
    auth_repository.configure_auth(client, settings.mongodb_db)
    _mark("A11 · auth configurado — startup COMPLETO")

    try:
        yield
    finally:
        _mark("Z0 · shutdown")
        audit_service.reset_audit()
        auth_repository.reset_auth()
        if audit_client is not client:
            audit_client.close()
        client.close()
        _mark("Z1 · shutdown OK")


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
    # Cabeceras de seguridad en TODA respuesta (Spec §8.3 / DoD #12). Se añade DESPUÉS
    # de CORS a propósito (Kimi B-1): el último add_middleware es la capa MÁS EXTERNA,
    # así Security envuelve también las respuestas de CORS (preflight, rechazos).
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/health", tags=["health"])
    def liveness() -> dict[str, str]:
        """Liveness — SIN tocar la BD. Es el healthCheckPath de render.yaml."""
        return {"status": "ok", "service": "compas-api", "version": __version__}

    app.include_router(api_router, prefix="/api/v1")

    # FABS (agente CFO) — solo con el flag encendido (doble barrera; apagado ⇒
    # ausente). El router cfo ya trae el prefix /api/v1/cfo completo, así que se
    # monta directo en `app` (no en api_router) para no duplicar el prefijo.
    from app.cfo.config import cfo_enabled

    if cfo_enabled():
        from app.cfo.router import router as cfo_router
        from app.cfo.telegram.router import router as cfo_telegram_router

        app.include_router(cfo_router)
        app.include_router(cfo_telegram_router)

    return app


app = create_app()
