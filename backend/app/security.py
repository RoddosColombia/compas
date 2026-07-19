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
