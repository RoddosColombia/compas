# backend/tests/test_sentry_scrub.py
"""before_send de Sentry: no filtrar PII/credenciales (Kimi B-1 / STACK §7 / F-23)."""

from app.main import _scrub_pii


def test_scrub_elimina_cookie_y_authorization():
    event = {
        "request": {
            "headers": {
                "Cookie": "refresh=secreto",
                "Authorization": "Bearer token",
                "User-Agent": "ua",
            }
        }
    }
    out = _scrub_pii(event, {})
    headers = out["request"]["headers"]
    assert "Cookie" not in headers
    assert "Authorization" not in headers
    assert "User-Agent" in headers  # lo no sensible se conserva
