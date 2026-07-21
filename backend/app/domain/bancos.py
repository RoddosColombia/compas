# backend/app/domain/bancos.py
"""Bancos de RODDOS (CLAUDE.md: Bancolombia, BBVA, Global66).

Enum compartido para no tener texto libre ('Bancolombia' vs 'bancolombia' vs
'BANCOLOMBIA' serían tres bancos distintos en la conciliación — Kimi B-2). Lo usan
`SaldoBanco` (§1.3, solo los 3 bancos reales) y `Transaccion` (§1.5), cuyo campo
`banco` admite además `manual` para las transacciones registradas a mano (F-04)."""

from enum import StrEnum


class Banco(StrEnum):
    BANCOLOMBIA = "bancolombia"
    BBVA = "bbva"
    GLOBAL66 = "global66"
    MANUAL = "manual"  # solo Transaccion §1.5 (id_banco 'MAN-'+ULID); no es banco real
