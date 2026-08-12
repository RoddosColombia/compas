"""FABS · feature flag. Apagado por defecto ⇒ COMPAS byte-idéntico. La doble barrera
(router condicional + guard 404) aterriza con el primer endpoint (incremento 2)."""

import os


def cfo_enabled() -> bool:
    return os.environ.get("CFO_ENABLED", "false").strip().lower() == "true"


def cfo_model() -> str:
    """Modelo Claude que orquesta y narra (nunca calcula). Barato por default
    (el modelo solo elige tools y redacta); override por env a un modelo mayor."""
    return os.environ.get("CFO_MODEL", "claude-haiku-4-5-20251001").strip()


def cfo_api_key() -> str | None:
    """API key de Anthropic (SOLO env var en Render; nunca en repo). Vacía ⇒ None
    ⇒ FABS se abstiene con motivo 'sin_api_key' (nunca crashea)."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return key or None


def cfo_max_iter() -> int:
    return int(os.environ.get("CFO_MAX_ITER", "3"))


def cfo_max_tokens() -> int:
    return int(os.environ.get("CFO_MAX_TOKENS", "1024"))


def cfo_timeout_s() -> float:
    return float(os.environ.get("CFO_TIMEOUT_S", "60"))
