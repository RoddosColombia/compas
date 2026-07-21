# backend/app/core/ulid.py
"""ULID (F-04): identificador de 26 chars, ordenable por tiempo, Crockford base32.

Se usa para el `id_banco` sintético de transacciones manuales ('MAN-'+ULID):
único por construcción → dos manuales idénticos el mismo día no chocan en el
índice (banco, id_banco). Sin dependencia externa: 48 bits de timestamp (ms) +
80 bits aleatorios (spec ULID)."""

import secrets
import time

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    valor = (int(time.time() * 1000) & ((1 << 48) - 1)) << 80
    valor |= secrets.randbits(80)
    chars = []
    for _ in range(26):
        chars.append(CROCKFORD[valor & 0x1F])
        valor >>= 5
    return "".join(reversed(chars))
