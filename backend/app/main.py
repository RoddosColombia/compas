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


# Red de seguridad del registro de modelos. Con skip_indexes=True esto debería
# tardar milisegundos; 30s es holgura, no una expectativa.
_BEANIE_TIMEOUT_S = 30.0


async def ensure_beanie(app: FastAPI, client, db_name: str) -> bool:
    """Inicializa Beanie una sola vez (idempotente). NO fatal: si Mongo está caído
    devuelve False y deja `app.state.beanie_ready=False`, sin tumbar la liveness.
    Readiness lo reintenta hasta que la BD responda.

    FIX 2026-09-03 (la causa real): el arranque NO se colgaba por DNS ni por
    allowlist — el ping a Mongo respondía en ~0.1s mientras `init_beanie`
    moría a los 15s. Lo que no cabía era la creación de índices de los 25
    Documents: decenas de `createIndexes` EN SERIE, Ohio -> mexico-central-1.
    Ahora `init_beanie_for` registra los modelos con `skip_indexes=True` (sin
    red) y los índices se construyen aparte, en segundo plano, sin bloquear
    el arranque ni la readiness. El timeout se mantiene como red de seguridad.

    Sigue siendo NO fatal: si falla, `beanie_ready=False` y el middleware
    lazy reintenta en el siguiente request."""
    if getattr(app.state, "beanie_ready", False):
        return True
    try:
        await asyncio.wait_for(
            mongo.init_beanie_for(client, db_name), timeout=_BEANIE_TIMEOUT_S
        )
        app.state.beanie_ready = True
        print("[ensure_beanie] init_beanie OK", file=sys.stderr, flush=True)
        return True
    except TimeoutError:
        # HOTFIX 2026-09-01: log honesto de qué está pasando (antes decíamos "falló
        # o timed out" sin distinguir; el CEO no puede saber si es allowlist, DNS,
        # auth o cluster dormido). Timeout puro = Mongo silencioso 15s+.
        msg = (
            f"[ensure_beanie] TIMEOUT tras {_BEANIE_TIMEOUT_S}s. Como ahora el "
            "registro de modelos NO crea índices (skip_indexes=True) y no toca la "
            "red, un timeout aquí ya no es 'Atlas lento': revisar (a) IP allowlist "
            "de Atlas, (b) cluster Free pausado, (c) DNS SRV. El estado real de la "
            "conexión se ve en /api/v1/health/ready (campo `mongo`)."
        )
        logger.warning(msg)
        print(msg, file=sys.stderr, flush=True)
        app.state.beanie_ready = False
        return False
    except Exception as e:  # noqa: BLE001 — degradación controlada
        # Cualquier otra excepción — imprimimos tipo + mensaje al stderr para
        # que el log de Render lo muestre en tiempo real y sepamos QUÉ falla.
        msg = f"[ensure_beanie] {type(e).__name__}: {e}"
        logger.warning(msg)
        print(msg, file=sys.stderr, flush=True)
        app.state.beanie_ready = False
        return False


async def _crear_indices_en_background(app: FastAPI) -> None:
    """Construye los índices de Beanie sin bloquear el arranque (fix 2026-09-03).

    Espera a que Beanie esté registrado (si el arranque quedó degradado, el
    middleware lazy lo resolverá en el primer request) y entonces corre
    `crear_indices`. Errores: se registran, no tumban el servicio."""
    for _ in range(60):  # hasta ~5 min esperando a que Beanie quede listo
        if getattr(app.state, "beanie_ready", False):
            break
        await asyncio.sleep(5)
    else:
        print(
            "[indices] Beanie nunca quedó listo — no se crearon índices.",
            file=sys.stderr,
            flush=True,
        )
        return
    try:
        await mongo.crear_indices(app.state.mongo_client, app.state.settings.mongodb_db)
        print("[indices] índices creados/verificados OK", file=sys.stderr, flush=True)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 — nunca fatal
        msg = (
            f"[indices] fallo al crear índices ({type(e).__name__}: {e}). "
            "La app sigue; las queries irán sin índice."
        )
        logger.warning(msg)
        print(msg, file=sys.stderr, flush=True)


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

    # A12 · índices EN SEGUNDO PLANO (fix 2026-09-03). Crear los índices es lo
    # que antes reventaba el arranque (decenas de round-trips cross-region). Ya
    # no bloquea a nadie: la app queda sirviendo y esta tarea los construye
    # detrás. `createIndexes` es idempotente, así que en arranques posteriores
    # es una comprobación barata. Si falla, se registra y la app sigue viva —
    # sin índices las queries son más lentas, pero funcionan.
    _mark("A12 · lanzando creación de índices en segundo plano")
    tarea_indices = asyncio.create_task(_crear_indices_en_background(app))

    try:
        yield
    finally:
        _mark("Z0 · shutdown")
        tarea_indices.cancel()
        audit_service.reset_audit()
        auth_repository.reset_auth()
        if audit_client is not client:
            audit_client.close()
        client.close()
        _mark("Z1 · shutdown OK")


_beanie_retry_lock = asyncio.Lock()


async def _asegurar_beanie_en_request(request):
    """HOTFIX 2026-09-01 (reintento lazy): si `beanie_ready=False` al llegar
    un request, intentamos init_beanie ANTES de servirlo. Lock global evita
    N reintentos concurrentes. Sin esto, el startup con Mongo caído dejaba
    el servicio inutilizable hasta el próximo deploy — ahora recuperamos en
    cuanto Mongo responde por primera vez.

    Solo se dispara cuando beanie_ready=False; una vez True se salta (el
    getattr es O(1)). Se salta también en /health (liveness) y en
    /api/v1/health/ready (readiness observacional F-03) — esos endpoints
    solo LEEN el estado, no lo cambian: el reintento pesado no encaja ahí."""
    if request.url.path in (
        "/health",
        "/api/v1/health/ready",
        "/",
        "/favicon.ico",
    ):
        return
    app = request.app
    if getattr(app.state, "beanie_ready", False):
        return
    # FIX 2026-09-03: si el lifespan no llegó a poblar app.state (arranque
    # abortado, o un TestClient montado sin lifespan), esto lanzaba
    # AttributeError DENTRO del middleware — o sea un 500 en CADA ruta,
    # incluidas las que no tocan la BD. Un reintento oportunista jamás puede
    # ser el que tumbe el request: si no hay con qué reintentar, se sigue.
    client = getattr(app.state, "mongo_client", None)
    settings = getattr(app.state, "settings", None)
    if client is None or settings is None:
        return

    async with _beanie_retry_lock:
        if getattr(app.state, "beanie_ready", False):
            return  # double-check tras adquirir el lock
        try:
            await ensure_beanie(app, client, settings.mongodb_db)
        except Exception as e:  # noqa: BLE001 — el reintento nunca tumba el request
            print(
                f"[reintento_beanie] {type(e).__name__}: {e}",
                file=sys.stderr,
                flush=True,
            )


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

    # HOTFIX 2026-09-01: reintento LAZY de Beanie si el startup lo dejó off.
    # Middleware ASGI puro (más liviano que middleware HTTP) porque solo lee
    # request.url.path; no necesita el request completo.
    @app.middleware("http")
    async def _reintento_beanie_mw(request, call_next):
        await _asegurar_beanie_en_request(request)
        return await call_next(request)

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
