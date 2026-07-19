# backend/app/auth/roles.py
"""Roles de COMPAS (Spec §1.1). Catálogo cerrado de 4 — no hay "superadmin"."""

from enum import StrEnum


class Role(StrEnum):
    admin = "admin"
    directivo = "directivo"
    financiero = "financiero"
    consulta = "consulta"
