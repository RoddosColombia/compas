# backend/app/cfo/agente/verificador.py
"""FABS · verificador cifra→evidencia (EL control crítico, lección Deloitte).

Toda cifra monetaria o con unidad que aparezca en la respuesta del modelo debe estar
dentro de tolerancia de ALGÚN valor devuelto por las tools de este turno (conjunto
cerrado de evidencias). Si una cifra no tiene respaldo, el veredicto es `ok=False` y
esa cifra no debe publicarse (regla #1). Heurística conservadora: exige evidencia a
los montos ($ / separador de miles / dígitos pelados de 5+) y a los números con
unidad de meses; ignora años, fechas y ordinales pequeños sin formato de dinero
(para no abstenerse de lo inocuo).

Nota de formato "wire" (hallazgo de revisión sobre el commit inicial):
`tools.resultado_a_dict` serializa `valor` como `str(Decimal(...))` — dígitos
pelados sin separador de miles para COP (p.ej. "704722003") y con PUNTO decimal
para meses (p.ej. "4.2") — y el prompt (regla #1) exige que el modelo reproduzca
las cifras LITERALMENTE. La respuesta real del modelo llega mayoritariamente en
ese formato wire, no en es-CO con "$"/miles/coma. Por eso el regex de montos
también acepta una corrida de 5+ dígitos pelados, y el de meses acepta tanto coma
como punto decimal (con un normalizador propio — ver `_a_decimal_meses` — porque
para dinero el punto es separador de miles pero para meses el punto es decimal)."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.cfo.calc.evidencia import ResultadoCFO

_TOL_COP = Decimal("1")  # ±$1 COP por redondeo
_TOL_MESES = Decimal("0.1")  # ±0,1 meses

# Monto: prefijo $ (con o sin separadores) O número con separador de miles es-CO O
# corrida de 5+ dígitos pelados (formato wire str(Decimal), sin $ ni separadores;
# el umbral de 5 excluye años de 4 dígitos como 2026 — ver test_anio_no_marcado_*).
_RE_MONTO = re.compile(
    r"\$\s?\d+(?:\.\d{3})*(?:,\d{1,2})?"  # $50.000.000 · $0 · $1.234,56
    r"|(?<![\d.,])\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?"  # 704.722.003 (requiere separador)
    r"|(?<![\d.,])\d{5,}(?![\d.,])"  # 950000000 (wire pelado, ≥5 dígitos)
)
# Meses: número (decimal con coma O punto — wire str(Decimal) usa punto) + 'mes(es)'.
_RE_MESES = re.compile(r"(\d+(?:[.,]\d+)?)\s*mes(?:es)?\b", re.IGNORECASE)


def _a_decimal_es(token: str) -> Decimal | None:
    """Dinero es-CO: el punto es separador de MILES (se descarta) y la coma es el
    decimal. NUNCA usar esta función para 'meses' — ver `_a_decimal_meses`."""
    t = token.replace("$", "").replace(" ", "").strip()
    t = t.replace(".", "").replace(",", ".")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def _a_decimal_meses(token: str) -> Decimal | None:
    """Meses: una sola marca decimal (coma es-CO o punto wire str(Decimal)); a
    diferencia de `_a_decimal_es`, el punto NUNCA se descarta — aquí es decimal,
    no separador de miles (los valores de meses no tienen miles)."""
    t = token.replace(",", ".").strip()
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
    # (Guarda puramente defensiva: un decimal de meses no alcanza el umbral de 5+
    # dígitos de _RE_MONTO en la práctica, pero se mantiene por si cambia el formato.)
    tramos_meses: list[tuple[int, int]] = []
    for m in _RE_MESES.finditer(texto):
        val = _a_decimal_meses(m.group(1))
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
    """Nota de alcance para T10 (servicio.py — el orquestador que llama esta
    función): la evidencia se agrupa solo por `unidad` (COP / meses), NUNCA por
    `concepto`. Una cifra en COP que caiga en tolerancia de CUALQUIER ResultadoCFO
    en COP se considera respaldada, aunque sea el concepto equivocado (p.ej. una
    respuesta que confunda caja con IVA pero coincida en valor no se atraparía
    aquí). Verificación cifra→concepto (no solo cifra→valor) es un diseño
    PENDIENTE, requerido antes de confiar en citas estructuradas; no implementado
    en esta función a propósito — está fuera de la interfaz de este módulo
    (`extraer_cifras` devuelve unidad, no concepto). Requiere CR si se necesita."""
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
