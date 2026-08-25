# backend/app/cfo/agente/verificador.py
"""FABS · verificador cifra→concepto (EL control crítico, lección Deloitte + inc3
Pieza A: citación estructurada).

Contrato: el modelo NUNCA escribe una cifra cruda (monto/meses/%) en su respuesta —
cita el concepto con `[[concepto]]` (A2: `tools.py` ya no expone `valor` al modelo,
así que no tiene un número que copiar) y el servicio sustituye cada token por el
valor concept-bound DESPUÉS de este veredicto (A5; el texto sustituido nunca se
re-verifica). El veredicto es `ok=True` sii (1) NO hay ninguna cifra cruda en el
texto — cualquier número detectado es violación, sin excepción, ya no hay pool de
tolerancia que la respalde — y (2) todo token `[[X]]` referencia un concepto con
evidencia disponible ESTE turno (frescura por turno).

Esto cierra por construcción el hueco de inc2: la verificación agrupaba la evidencia
disponible solo por `unidad` (COP/meses), nunca por `concepto`, así que una cifra de
IVA mal-etiquetada como caja pasaba si el VALOR caía en tolerancia de CUALQUIER
ResultadoCFO en COP del turno. Ahora el modelo no puede mal-etiquetar un valor porque
no escribe valores — solo cita conceptos, y el concepto sí se valida.

Huecos de detección residuales (aceptados, sin cambio respecto a inc2 — a diferencia
de los porcentajes, que YA NO son un hueco: se atrapan siempre, ver `_RE_PORCENTAJE`
arriba): el contrato de este módulo es "ninguna cifra cruda DETECTADA + tokens
válidos", no una garantía matemática contra toda forma de número. Los regex de
`extraer_cifras` no parsean (b) un entero pelado de MENOS de 5 dígitos sin separador
(`"500"` en vez de `"$500"`, ver `_es_monto`) ni (c) números en palabras (`"mil
millones"`, `"cien mil"`) — solo dígitos, con separador o pelados de 5+. Tampoco se
caza la aritmética hecha en prosa sin cifra ("el doble de tu caja", "bastante más
que ayer"): no hay número que capturar. La mitigación de los tres es la misma que en
inc2 — la regla #1 del prompt (el modelo no calcula ni extrapola) y la abstención
honesta — no un regex más agresivo; quedan como radar del piloto para una eventual
CR de "verificación concept-aware" con más rigor antes de encender la compuerta.

Nota de formato "wire" (verificado empíricamente contra `caja.py`/`runway.py`/
`iva.py` + `tools.resultado_a_dict`, ronda 2 de revisión — corrige el supuesto de la
ronda 1, que asumía dígitos pelados SIN decimales): las 3 tools construyen `valor`
como `Decimal(money_str(x))` — primero cuantizan a 2 decimales con `money_str`
(p.ej. `"704722003.00"`, `"36204698.10"`, `"4.20"`) y ese string se reconstruye a
`Decimal`, que conserva la escala. El modelo ya no ve ese string (A2), pero
`extraer_cifras` sigue reconociendo esa forma: si algo lo sortea y una cifra cruda
llega al texto de todos modos (fuga, regresión de prompt, etc.), igual debe
atraparse — por eso las funciones de detección de este módulo quedan intactas. Ese
punto decimal colisiona con el separador de miles es-CO (`"704.722.003"`), así que
la normalización de montos (`_a_decimal_cop`) distingue los dos casos por REGLA DE
FORMA (ver su docstring) — no por conteo de dígitos, que ya no basta para
desambiguar."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.cfo.agente.conceptos import RE_TOKEN
from app.cfo.calc.evidencia import ResultadoCFO

# Un "número" = corrida de dígitos con posibles separadores . , y $ opcional.
_RE_NUM = re.compile(r"\$?\s?\d[\d.,]*\d|\$?\s?\d")
# Meses: número (decimal con , o .) seguido de 'mes'/'meses'.
_RE_MESES = re.compile(r"(\d+(?:[.,]\d+)?)\s*mes(?:es)?\b", re.IGNORECASE)
# Porcentaje: número (decimal con , o .) seguido de '%'. COMPAS no tiene concepto
# de "porcentaje" — ninguna tool lo calcula ni lo devuelve — así que cualquier %
# en la respuesta es una cifra auto-computada por el modelo, prohibida por regla
# #1 (ver su uso en `extraer_cifras`, FIX 1 FINAL-REVIEW inc2).
_RE_PORCENTAJE = re.compile(r"\d+(?:[.,]\d+)?\s*%")
# Unidades: entero seguido de 'moto(s)'/'motocicleta(s)'/'unidad(es)'. Cierra el
# hueco del entero pequeño para conteos de motos (inc4 tarea 3): "12 motos" tiene
# menos de 5 dígitos y sin separador, así que `_es_monto` lo dejaba pasar como
# inocuo (nº de cuenta/día). El modelo debe citar `[[unidades_extra]]`, nunca
# escribir el conteo — mismo contrato que COP/meses/%.
_RE_UNIDADES = re.compile(r"\d+\s*(?:motos?|motocicletas?|unidades?)\b", re.IGNORECASE)
# Cita de concepto: [[caja_hoy]] / [[runway]] / [[iva_cuatrimestre]]. El modelo cita,
# no escribe números (inc3 Pieza A). RE_TOKEN vive en conceptos.py (import directo,
# NUNCA redefinir aquí): debe ser BYTE-IDÉNTICA a la que usa sustituir_tokens, o un
# token válido para uno queda inválido/sin sustituir para el otro (fuga de
# placeholder o hueco de seguridad, ver docstring de RE_TOKEN en conceptos.py).


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
    tokens_invalidos: list[str]


def extraer_cifras(texto: str) -> list[tuple[Decimal, str, str]]:
    cifras: list[tuple[Decimal, str, str]] = []
    # Meses y % primero, y marcamos sus tramos para no re-capturar el número como
    # monto COP. Ya NO es solo defensivo (como en la ronda 1): un decimal de meses
    # como "4.20" también cumple `_es_monto` (tiene '.'), así que sin este guard se
    # contaría dos veces con la unidad equivocada (buscaría "4.20" en la evidencia
    # de COP, que nunca lo respalda, en vez de en la de meses). Lo mismo aplica a
    # "%" desde FIX 1 (FINAL-REVIEW inc2): "12,5 %" tiene ',' y calificaría como
    # monto COP si no se excluyera su tramo.
    #
    # El chequeo de solape es de INTERSECCIÓN de intervalos, no de contención del
    # punto de inicio: _RE_NUM permite un '\s?' inicial opcional, así que su match
    # puede empezar 1 char ANTES del tramo de meses (consume el espacio previo a
    # "4.2", p.ej. " 4.2" en vez de "4.2") — con una contención estricta ese match
    # queda FUERA del tramo registrado y el guard nunca dispara (hallazgo de ronda
    # 2 vía tests reales, no traza manual: test_runway_wire_punto_decimal_pasa et
    # al. daban RED con la contención simple).
    tramos: list[tuple[int, int]] = []  # meses y % → no re-contar como monto COP
    for m in _RE_MESES.finditer(texto):
        val = _a_decimal_meses(m.group(1))
        if val is not None:
            cifras.append((val, "meses", m.group(0)))
            tramos.append((m.start(1), m.end(1)))
    for m in _RE_PORCENTAJE.finditer(texto):
        # COMPAS no calcula porcentajes: no existe pool "pct", así que TODO %
        # queda huérfano → fuerza reintento/abstención (regla #1: el modelo no
        # extrapola ratios).
        val = _a_decimal_meses(m.group(0).rstrip("% ").strip()) or Decimal(0)
        cifras.append((val, "pct", m.group(0)))
        tramos.append((m.start(), m.end()))
    for m in _RE_UNIDADES.finditer(texto):
        # Conteo de motos/unidades: el valor no importa (el contrato exige token,
        # no comparación de valor — igual que 'pct'), pero marcamos el tramo para
        # que el entero no se re-cuente como monto COP pelado en el barrido de abajo.
        cifras.append((Decimal(0), "unidades", m.group(0)))
        tramos.append((m.start(), m.end()))
    for m in _RE_NUM.finditer(texto):
        if any(s < m.end() and m.start() < e for s, e in tramos):
            continue  # ya contado como meses o %
        raw = m.group(0)
        if not _es_monto(raw):
            continue  # año/día/ordinal pelado
        val = _a_decimal_cop(raw)
        if val is not None:
            cifras.append((val, "COP", raw.strip()))
    return cifras


def verificar(texto: str, resultados: list[ResultadoCFO]) -> Veredicto:
    """Contrato inc3 Pieza A (citación estructurada): el modelo NO escribe cifras,
    cita conceptos con `[[concepto]]`. Veredicto ok sii (1) NO hay ninguna cifra
    cruda (COP/meses/%) en el texto — cualquier número es violación, el modelo debió
    usar un token — y (2) todo token `[[X]]` referencia un concepto con evidencia
    disponible ESTE turno (frescura por turno). Esto cierra el hueco cifra→concepto
    de inc2 por construcción: el modelo no puede mal-etiquetar un valor porque no
    escribe valores. El servicio sustituye los tokens por el valor concept-bound
    DESPUÉS de este veredicto (el texto sustituido nunca se re-verifica)."""
    crudas = [token for _, _, token in extraer_cifras(texto)]
    disponibles = {
        r.concepto for r in resultados if r.disponible and r.valor is not None
    }
    tokens_invalidos = [
        m.group(0) for m in RE_TOKEN.finditer(texto) if m.group(1) not in disponibles
    ]
    ok = not crudas and not tokens_invalidos
    return Veredicto(
        ok=ok, cifras_sin_evidencia=crudas, tokens_invalidos=tokens_invalidos
    )
