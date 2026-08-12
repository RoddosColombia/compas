# backend/app/cfo/agente/verificador.py
"""FABS · verificador cifra→evidencia (EL control crítico, lección Deloitte).

Toda cifra monetaria o con unidad que aparezca en la respuesta del modelo debe estar
dentro de tolerancia de ALGÚN valor devuelto por las tools de este turno (conjunto
cerrado de evidencias). Si una cifra no tiene respaldo, el veredicto es `ok=False` y
esa cifra no debe publicarse (regla #1). Heurística conservadora: exige evidencia a
los montos ($ / separador de miles) y a los números con unidad de meses; ignora años,
fechas y ordinales pequeños sin formato de dinero (para no abstenerse de lo inocuo)."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.cfo.calc.evidencia import ResultadoCFO

_TOL_COP = Decimal("1")  # ±$1 COP por redondeo
_TOL_MESES = Decimal("0.1")  # ±0,1 meses

# Monto: prefijo $ (con o sin separadores) O número con separador de miles es-CO.
_RE_MONTO = re.compile(
    r"\$\s?\d+(?:\.\d{3})*(?:,\d{1,2})?"  # $50.000.000 · $0 · $1.234,56
    r"|(?<![\d.,])\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?"  # 704.722.003 (requiere separador)
)
# Meses: número (posible decimal con coma) seguido de 'mes'/'meses'.
_RE_MESES = re.compile(r"(\d+(?:,\d+)?)\s*mes(?:es)?\b", re.IGNORECASE)


def _a_decimal_es(token: str) -> Decimal | None:
    t = token.replace("$", "").replace(" ", "").strip()
    t = t.replace(".", "").replace(",", ".")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


@dataclass(frozen=True)
class Veredicto:
    ok: bool
    cifras_sin_evidencia: list[str]


def extraer_cifras(texto: str) -> list[tuple[Decimal, str, str]]:
    cifras: list[tuple[Decimal, str, str]] = []
    # Meses primero, y marcamos sus tramos para no re-capturar el número como monto.
    tramos_meses: list[tuple[int, int]] = []
    for m in _RE_MESES.finditer(texto):
        val = _a_decimal_es(m.group(1))
        if val is not None:
            cifras.append((val, "meses", m.group(0)))
            tramos_meses.append((m.start(1), m.end(1)))
    for m in _RE_MONTO.finditer(texto):
        # saltar si el número pertenece a un tramo de 'meses'
        if any(s <= m.start() < e for s, e in tramos_meses):
            continue
        val = _a_decimal_es(m.group(0))
        if val is not None:
            cifras.append((val, "COP", m.group(0)))
    return cifras


def verificar(texto: str, resultados: list[ResultadoCFO]) -> Veredicto:
    ev_cop = [
        r.valor
        for r in resultados
        if r.disponible and r.valor is not None and r.unidad == "COP"
    ]
    ev_meses = [
        r.valor
        for r in resultados
        if r.disponible and r.valor is not None and r.unidad == "meses"
    ]
    huerfanas: list[str] = []
    for valor, unidad, token in extraer_cifras(texto):
        pool = ev_cop if unidad == "COP" else ev_meses
        tol = _TOL_COP if unidad == "COP" else _TOL_MESES
        if not any(abs(valor - e) <= tol for e in pool):
            huerfanas.append(token)
    return Veredicto(ok=not huerfanas, cifras_sin_evidencia=huerfanas)
