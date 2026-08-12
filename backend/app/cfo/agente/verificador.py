# backend/app/cfo/agente/verificador.py
"""FABS · verificador cifra→evidencia (EL control crítico, lección Deloitte).

Toda cifra monetaria o con unidad que aparezca en la respuesta del modelo debe estar
dentro de tolerancia de ALGÚN valor devuelto por las tools de este turno (conjunto
cerrado de evidencias). Si una cifra no tiene respaldo, el veredicto es `ok=False` y
esa cifra no debe publicarse (regla #1). Heurística conservadora: exige evidencia a
los montos ($ / separador de miles / decimal / entero pelado de 5+) y a los números
con unidad de meses; ignora años, fechas y ordinales pequeños sin formato de dinero
(para no abstenerse de lo inocuo).

Nota de formato "wire" (verificado empíricamente contra `caja.py`/`runway.py`/
`iva.py` + `tools.resultado_a_dict`, ronda 2 de revisión — corrige el supuesto de la
ronda 1, que asumía dígitos pelados SIN decimales): las 3 tools NO devuelven enteros
pelados. Cada una construye `valor` como `Decimal(money_str(x))` — primero cuantizan
a 2 decimales con `money_str` (p.ej. `"704722003.00"`, `"36204698.10"`, `"4.20"`) y
ese string se reconstruye a `Decimal`, que conserva la escala. `tools.resultado_a_dict`
hace luego `str(r.valor)`, así que el modelo recibe literalmente `"704722003.00"` —
un PUNTO decimal de 2 cifras, no dígitos pelados sin separador. Ese punto colisiona
con el separador de miles es-CO (`"704.722.003"`), así que la normalización de
montos (`_a_decimal_cop`) distingue los dos casos por REGLA DE FORMA (ver su
docstring) — no por conteo de dígitos, que ya no basta para desambiguar."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.cfo.calc.evidencia import ResultadoCFO

_TOL_COP = Decimal("1")  # ±$1 COP por redondeo
_TOL_MESES = Decimal("0.1")  # ±0,1 meses

# Un "número" = corrida de dígitos con posibles separadores . , y $ opcional.
_RE_NUM = re.compile(r"\$?\s?\d[\d.,]*\d|\$?\s?\d")
# Meses: número (decimal con , o .) seguido de 'mes'/'meses'.
_RE_MESES = re.compile(r"(\d+(?:[.,]\d+)?)\s*mes(?:es)?\b", re.IGNORECASE)


def _a_decimal_cop(token: str) -> Decimal | None:
    """Normaliza un monto en CUALQUIER forma plausible a Decimal. Regla de
    separadores: si hay ',' es es-CO ('.'=miles, ','=decimal); si solo hay un '.'
    con 2 dígitos al final es el formato wire de str(Decimal(money_str)) ('.'=decimal,
    p.ej. '704722003.00'); en los demás casos los '.' son miles (grupos de 3)."""
    t = token.replace("$", "").replace(" ", "").strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif re.search(r"\.\d{2}$", t) and t.count(".") == 1:
        pass  # wire decimal: dejar el punto
    else:
        t = t.replace(".", "")  # miles
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def _a_decimal_meses(token: str) -> Decimal | None:
    """Meses: una sola marca decimal (coma es-CO o punto wire str(Decimal)); a
    diferencia de `_a_decimal_cop`, el punto NUNCA se descarta — aquí es decimal,
    no separador de miles (los valores de meses no tienen miles)."""
    t = token.replace(",", ".").strip()
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def _es_monto(raw: str) -> bool:
    """Un candidato numérico exige evidencia (es un MONTO) si lleva '$', un separador
    (miles/decimal), o es un entero pelado de >=5 dígitos. Excluye años de 4 dígitos,
    días y ordinales pequeños sin formato de dinero — para no abstenerse de lo inocuo.
    Sesgo conservador: preferimos un falso-positivo (dispara el reintento del servicio)
    antes que dejar pasar una cifra sin evidencia."""
    core = raw.replace("$", "").replace(" ", "")
    if "$" in raw or "," in core or "." in core:
        return True
    return core.isdigit() and len(core) >= 5


@dataclass(frozen=True)
class Veredicto:
    ok: bool
    cifras_sin_evidencia: list[str]


def extraer_cifras(texto: str) -> list[tuple[Decimal, str, str]]:
    cifras: list[tuple[Decimal, str, str]] = []
    # Meses primero, y marcamos sus tramos para no re-capturar el número como monto
    # COP. Ya NO es solo defensivo (como en la ronda 1): un decimal de meses como
    # "4.20" también cumple `_es_monto` (tiene '.'), así que sin este guard se
    # contaría dos veces con la unidad equivocada (buscaría "4.20" en la evidencia
    # de COP, que nunca lo respalda, en vez de en la de meses).
    #
    # El chequeo de solape es de INTERSECCIÓN de intervalos, no de contención del
    # punto de inicio: _RE_NUM permite un '\s?' inicial opcional, así que su match
    # puede empezar 1 char ANTES del tramo de meses (consume el espacio previo a
    # "4.2", p.ej. " 4.2" en vez de "4.2") — con una contención estricta ese match
    # queda FUERA del tramo registrado y el guard nunca dispara (hallazgo de ronda
    # 2 vía tests reales, no traza manual: test_runway_wire_punto_decimal_pasa et
    # al. daban RED con la contención simple).
    tramos_meses: list[tuple[int, int]] = []
    for m in _RE_MESES.finditer(texto):
        val = _a_decimal_meses(m.group(1))
        if val is not None:
            cifras.append((val, "meses", m.group(0)))
            tramos_meses.append((m.start(1), m.end(1)))
    for m in _RE_NUM.finditer(texto):
        if any(s < m.end() and m.start() < e for s, e in tramos_meses):
            continue  # ya contado como meses (intervalos se solapan)
        raw = m.group(0)
        if not _es_monto(raw):
            continue  # año/día/ordinal pelado
        val = _a_decimal_cop(raw)
        if val is not None:
            cifras.append((val, "COP", raw.strip()))
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
