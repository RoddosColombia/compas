# backend/app/deps.py
"""Dependencias FastAPI compartidas.

El RBAC por dependencia (regla 9 / Spec §4.1) se añadirá en el Sprint 0b/S2;
por ahora solo exponemos el acceso al cliente Mongo para poder inyectar un
mock en los tests (dependency_overrides)."""

from typing import Any

from fastapi import Request


def get_mongo_client(request: Request) -> Any:
    """Devuelve el cliente Motor almacenado en app.state durante el lifespan."""
    return request.app.state.mongo_client
