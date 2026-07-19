# backend/tests/test_auth_passwords.py
"""Hashing y política de contraseñas (PR-2). Spec §1.1 / §8.1."""

import time

import pytest
from app.auth import passwords
from app.auth.roles import Role


def test_hash_y_verify_ok():
    h = passwords.hash_password("una-clave-larga-123")
    assert h != "una-clave-larga-123"
    assert passwords.verify_password("una-clave-larga-123", h)
    assert not passwords.verify_password("otra", h)


def test_bcrypt_cost_12():
    # Kimi Baja: fijar el costo (no solo longitud). bcrypt guarda el cost: $2b$12$
    h = passwords.hash_password("clave-larga-1234")
    assert h.split("$")[2] == "12"


def test_hash_latencia_bajo_1s():
    t0 = time.perf_counter()
    passwords.hash_password("clave-larga-1234")
    assert (time.perf_counter() - t0) < 1.0


@pytest.mark.parametrize(
    "rol,largo,ok",
    [
        (Role.admin, 12, True),
        (Role.admin, 11, False),
        (Role.directivo, 12, True),
        (Role.directivo, 11, False),
        (Role.financiero, 10, True),
        (Role.financiero, 9, False),
        (Role.consulta, 10, True),
        (Role.consulta, 9, False),
    ],
)
def test_politica_de_longitud_por_rol(rol, largo, ok):
    assert passwords.password_meets_policy("x" * largo, rol) is ok


def test_dummy_hash_para_anti_enumeracion():
    # verify contra el hash dummy nunca acierta, pero cuesta ~lo mismo (constant-time).
    assert passwords.verify_password("lo-que-sea", passwords.DUMMY_HASH) is False
