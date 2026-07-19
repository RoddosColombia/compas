# EVIDENCIA — sprint0b-dominio-mfa · PR3-I

Rama `sprint0b-pr3-cabeceras`, commit `40e760f`. Código real + salidas.

## 1. pytest

```
171 passed, 9 skipped, 9 warnings in ~134s
(+5 vs PR-2: test_security_headers.py)
```

## 2. ruff

```
All checks passed!
```

## 3. app/security.py

```python
# backend/app/security.py
"""Cabeceras de seguridad HTTP (Spec §8.3 / DoD #12).

Middleware que fija en TODA respuesta (incluye errores) un conjunto endurecido:
- **CSP estricta** sin `unsafe-inline`/`unsafe-eval`. La API sirve JSON (no HTML),
  así que `default-src 'none'` es correcto; `frame-ancestors 'none'` corta clickjacking.
- **HSTS** solo fuera de dev (en http local sería inútil y podría pinnear localhost).
- `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options`.

Cloudflare también añade HSTS en el borde; esto es defensa en profundidad. La SPA fija
sus propias cabeceras en `frontend/vercel.json` (Kimi B-01)."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings

# CSP para una API JSON: nada por defecto, sin marcos, sin base-uri.
_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
_HSTS = "max-age=31536000; includeSubDomains; preload"

_BASE_HEADERS = {
    b"content-security-policy": _CSP.encode(),
    b"x-content-type-options": b"nosniff",
    b"referrer-policy": b"no-referrer",
    b"x-frame-options": b"DENY",
}


class SecurityHeadersMiddleware:
    """ASGI puro: inyecta las cabeceras en el evento http.response.start de cada
    respuesta (más robusto que BaseHTTPMiddleware para respuestas de error)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Leído por request (cacheado): permite decidir HSTS según el entorno.
        hsts = get_settings().app_env != "development"

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                existentes = {k.lower() for k, _ in headers}
                for k, v in _BASE_HEADERS.items():
                    if k not in existentes:
                        headers.append((k, v))
                if hsts and b"strict-transport-security" not in existentes:
                    headers.append((b"strict-transport-security", _HSTS.encode()))
            await send(message)

        await self.app(scope, receive, send_wrapper)

```

## 4. frontend/vercel.json

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        {
          "key": "Content-Security-Policy",
          "value": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self' https://api.compas.roddos.com; frame-ancestors 'none'; base-uri 'none'; object-src 'none'; form-action 'self'"
        },
        { "key": "Strict-Transport-Security", "value": "max-age=31536000; includeSubDomains; preload" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "Referrer-Policy", "value": "no-referrer" },
        { "key": "X-Frame-Options", "value": "DENY" }
      ]
    }
  ]
}

```

## 5. tests/test_security_headers.py

```python
# backend/tests/test_security_headers.py
"""Cabeceras de seguridad (Spec §8.3 / DoD #12): presentes en TODA respuesta.

Este test ES el control de CI del DoD #12."""

from fastapi.testclient import TestClient


def test_cabeceras_presentes_en_liveness(app):
    with TestClient(app) as client:
        r = client.get("/health")
    h = r.headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["Referrer-Policy"] == "no-referrer"
    assert h["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert "default-src 'none'" in h["Content-Security-Policy"]


def test_csp_estricta_sin_unsafe_inline(app):
    with TestClient(app) as client:
        r = client.get("/health")
    assert "unsafe-inline" not in r.headers["Content-Security-Policy"]
    assert "unsafe-eval" not in r.headers["Content-Security-Policy"]


def test_hsts_ausente_en_dev(app):
    # En dev (http local) NO fijamos HSTS: evita pinnear localhost.
    with TestClient(app) as client:
        r = client.get("/health")
    assert "Strict-Transport-Security" not in r.headers


def test_hsts_presente_fuera_de_dev(app, monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("MFA_ENC_KEY", "k" * 44)
    # Fuera de dev el lifespan exige MONGODB_URI_AUDIT (C-01); create_client está
    # parcheado a mongomock por el fixture, así que el valor da igual.
    monkeypatch.setenv("MONGODB_URI_AUDIT", "mongodb://localhost:27017")
    from app.config import get_settings

    get_settings.cache_clear()
    with TestClient(app) as client:
        r = client.get("/health")
    hsts = r.headers.get("Strict-Transport-Security", "")
    assert "max-age=" in hsts and "includeSubDomains" in hsts
    get_settings.cache_clear()


def test_cabeceras_tambien_en_404(app):
    # Las cabeceras van en TODA respuesta, no solo en 200.
    with TestClient(app) as client:
        r = client.get("/no-existe")
    assert r.status_code == 404
    assert r.headers["X-Content-Type-Options"] == "nosniff"

```

## 6. diff main.py

```diff
diff --git a/backend/app/main.py b/backend/app/main.py
index b2b6775..cd3621a 100644
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -17,6 +17,7 @@ from app.audit import service as audit_service
 from app.auth import repository as auth_repository
 from app.config import get_settings
 from app.db import mongo
+from app.security import SecurityHeadersMiddleware
 
 logger = logging.getLogger("compas")
 
@@ -159,6 +160,9 @@ def create_app() -> FastAPI:
         lifespan=lifespan,
     )
 
+    # Cabeceras de seguridad en TODA respuesta (Spec §8.3 / DoD #12).
+    app.add_middleware(SecurityHeadersMiddleware)
+
     # CORS: origen exacto del frontend + credenciales (cookie de refresh). Spec §4.
     settings = get_settings()
     app.add_middleware(

```
