"""FABS · feature flag. Apagado por defecto ⇒ COMPAS byte-idéntico. La doble barrera
(router condicional + guard 404) aterriza con el primer endpoint (incremento 2)."""

import os


def cfo_enabled() -> bool:
    return os.environ.get("CFO_ENABLED", "false").strip().lower() == "true"
