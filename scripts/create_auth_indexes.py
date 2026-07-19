#!/usr/bin/env python
"""Crea (idempotente) los índices de auth. Kimi L4.

Sin estos índices: el TTL de login_throttle no existe → el contador por IP es
MONÓTONO para siempre (429 permanente); email/jti no serían únicos; el refresh no
expiraría. mongomock no exige índices, así que el CI verde NO lo detecta → este
script + un test @requires_real_mongo de existencia son el control real.

Fuente única de verdad: AUTH_INDEXES en app/auth/models.py (no duplicar aquí).

Uso:
    python scripts/create_auth_indexes.py "<MONGODB_URI>" [db=compas]
Lo corre el operador (RUNBOOK) y el CI de la Sesión 3.
"""

from __future__ import annotations

import sys

from pymongo import MongoClient

# El script vive en scripts/ (fuera del paquete); importamos el modelo por ruta.
sys.path.insert(0, "backend")
from app.auth.models import AUTH_INDEXES  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('Uso: python scripts/create_auth_indexes.py "<MONGODB_URI>" [db]')
    uri = sys.argv[1]
    db_name = sys.argv[2] if len(sys.argv) > 2 else "compas"
    db = MongoClient(uri)[db_name]

    for coleccion, indices in AUTH_INDEXES.items():
        for idx in indices:
            kwargs: dict = {"name": idx["name"]}
            if idx.get("unique"):
                kwargs["unique"] = True
            if "expireAfterSeconds" in idx:
                kwargs["expireAfterSeconds"] = idx["expireAfterSeconds"]
            db[coleccion].create_index(idx["keys"], **kwargs)
            print(f"[{coleccion}] índice {idx['name']} asegurado ({kwargs}).")

    print("Índices de auth OK (idempotente).")


if __name__ == "__main__":
    main()
