# backend/tests/test_auth_hibp.py
"""HIBP k-anonymity (Spec §8.1): nunca se envía la contraseña ni su hash completo,
solo el prefijo de 5 hex del SHA-1; el sufijo se compara localmente."""

import hashlib

from app.auth import passwords


def _sha1_upper(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest().upper()  # noqa: S324 — HIBP usa SHA-1


async def test_pwned_true_cuando_el_sufijo_aparece():
    pwd = "password"
    h = _sha1_upper(pwd)
    prefix, suffix = h[:5], h[5:]

    async def fetch(p):
        assert p == prefix  # k-anonymity: solo el prefijo sale
        return f"{suffix}:99999\nAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:1"

    assert await passwords.password_pwned(pwd, fetch=fetch) is True


async def test_pwned_false_cuando_no_aparece():
    async def fetch(_p):
        return "0000000000000000000000000000000000A:5\nBBBB:2"

    assert await passwords.password_pwned("clave-unica-larga-xyz", fetch=fetch) is False


async def test_pwned_solo_envia_prefijo_de_5():
    capturado = {}

    async def fetch(p):
        capturado["p"] = p
        return ""

    await passwords.password_pwned("otra-clave", fetch=fetch)
    assert len(capturado["p"]) == 5
    assert capturado["p"] == capturado["p"].upper()


async def test_pwned_cuenta_prefijada_en_la_linea():
    # Formato real de la API: "SUFIJO:conteo" con conteo > 0.
    pwd = "123456"
    h = _sha1_upper(pwd)

    async def fetch(_p):
        return f"{h[5:]}:24230577"

    assert await passwords.password_pwned(pwd, fetch=fetch) is True
