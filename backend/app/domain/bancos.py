# backend/app/domain/bancos.py
"""Bancos de RODDOS (CLAUDE.md: Bancolombia, BBVA, Global66).

Enum compartido para no tener texto libre ('Bancolombia' vs 'bancolombia' vs
'BANCOLOMBIA' serían tres bancos distintos en la conciliación — Kimi B-2). Lo usan
`SaldoBanco` (§1.3) y, en Sprint 1, `Transaccion` (§1.5) al portar los parsers."""

from enum import StrEnum


class Banco(StrEnum):
    BANCOLOMBIA = "bancolombia"
    BBVA = "bbva"
    GLOBAL66 = "global66"
