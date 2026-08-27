# backend/app/reglas/semilla.py
"""RF-F1 (COMPAS 2.0) — reglas SEMILLA aprendidas de la curaduría histórica del CEO.

REGLA DE ORO (decisión CEO, ver histórico de cargas): el sistema **no adivina** la
clasificación. Estas reglas **replican** las decisiones que el CEO ya tomó a mano sobre
los movimientos reales: solo se propone un patrón cuando, en esa historia, **siempre**
(pureza) cayó en el mismo rubro y con **evidencia** suficiente. Un patrón ambiguo no se
propone jamás.

Función PURA (sin Mongo, testeable): entra el histórico clasificado, sale una lista de
`ReglaSemilla` (propuestas). La persistencia (como reglas `origen=APRENDIDA`, que exigen
tu aprobación antes de activarse) vive en el servicio, no aquí.

Contrato con C3: reusa `normalizar_texto` (única normalización, Kimi §3); cada patrón
respeta `PATRON_MIN` y la unicidad (patron_normalizado, tipo_flujo).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal

from beanie import PydanticObjectId

from app.domain.regla_clasificacion import PATRON_MIN, normalizar_texto
from app.domain.rubro import TipoFlujo

# Ruido bancario/genérico que nunca debe ser un patrón por sí solo (ya normalizado:
# minúsculas y sin tildes). No incluye palabras de dominio (arriendo, nómina, wava…).
STOPWORDS_DEFAULT: frozenset[str] = frozenset(
    {
        # verbos/sustantivos de operación bancaria
        "pago",
        "pagos",
        "abono",
        "abonos",
        "transferencia",
        "transf",
        "giro",
        "giros",
        "cargo",
        "cargos",
        "debito",
        "credito",
        "compra",
        "compras",
        "venta",
        "ventas",
        "retiro",
        "retiros",
        "deposito",
        "consignacion",
        "factura",
        "facturas",
        "recibo",
        "comprobante",
        "movimiento",
        "mov",
        "saldo",
        "valor",
        "cuenta",
        "cta",
        "referencia",
        "ref",
        "numero",
        "num",
        "nro",
        "pse",
        "banco",
        "bancaria",
        "efectivo",
        # conectores frecuentes (la mayoría ya cae por PATRON_MIN)
        "por",
        "para",
        "con",
        "del",
        "las",
        "los",
        "una",
        "unos",
        "unas",
        "que",
        "sus",
        "año",
        "mes",
        # meses
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    }
)

_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)  # secuencias de letras (sin dígitos)


@dataclass(frozen=True, slots=True)
class MovimientoClasificado:
    """Un movimiento que el CEO ya clasificó — la materia prima del aprendizaje."""

    descripcion: str
    rubro_id: PydanticObjectId
    tipo_flujo: TipoFlujo


@dataclass(frozen=True, slots=True)
class ReglaSemilla:
    """Propuesta de regla. No se persiste hasta que el CEO la apruebe."""

    patron: str
    patron_normalizado: str
    rubro_id: PydanticObjectId
    tipo_flujo: TipoFlujo
    evidencia: int
    pureza: Decimal
    prioridad: int


def _tokens(descripcion: str, stopwords: frozenset[str], min_long: int) -> set[str]:
    """Tokens candidatos de una descripción: letras normalizadas (sin tildes/dígitos),
    largo >= min_long, fuera de la stoplist. Set → 1 conteo por movimiento."""
    norm = normalizar_texto(descripcion)
    return {
        t for t in _TOKEN_RE.findall(norm) if len(t) >= min_long and t not in stopwords
    }


def tokens_de(
    descripcion: str,
    *,
    stopwords: frozenset[str] = STOPWORDS_DEFAULT,
    min_long: int = PATRON_MIN,
) -> set[str]:
    """Tokens candidatos de una descripción (público; la MISMA extracción que usa el
    generador). Sirve para armar ejemplos/reportes que casen con los patrones."""
    return _tokens(descripcion, stopwords, min_long)


def generar_reglas_semilla(
    movimientos: list[MovimientoClasificado],
    *,
    min_evidencia: int = 3,
    min_pureza: Decimal = Decimal("1"),
    stopwords: frozenset[str] = STOPWORDS_DEFAULT,
    min_long: int = PATRON_MIN,
) -> list[ReglaSemilla]:
    """Aprende patrones de `movimientos`. Un patrón se propone si, DENTRO de su
    `tipo_flujo`, apunta a un rubro dominante con `pureza >= min_pureza` y
    `evidencia >= min_evidencia`. Empates de dominancia = ambiguo = se descarta.

    Devuelve las reglas ordenadas por (evidencia desc, patrón), con `prioridad`
    creciente (más evidencia ⇒ prioridad menor ⇒ el motor la evalúa primero)."""
    # (tipo, token) -> Counter(rubro_id -> nº de movimientos)
    conteo: dict[tuple[TipoFlujo, str], Counter] = defaultdict(Counter)
    for m in movimientos:
        for token in _tokens(m.descripcion, stopwords, min_long):
            conteo[(m.tipo_flujo, token)][m.rubro_id] += 1

    candidatas: list[ReglaSemilla] = []
    for (tipo, token), rubros in conteo.items():
        total = sum(rubros.values())
        if total < min_evidencia:
            continue
        (rubro_top, n_top), *resto = rubros.most_common()
        if resto and resto[0][1] == n_top:
            continue  # empate de dominancia → ambiguo, no se adivina
        pureza = (Decimal(n_top) / Decimal(total)).quantize(Decimal("0.0001"))
        if pureza < min_pureza:
            continue
        candidatas.append(
            ReglaSemilla(
                patron=token,
                patron_normalizado=token,  # ya normalizado
                rubro_id=rubro_top,
                tipo_flujo=tipo,
                evidencia=total,
                pureza=pureza,
                prioridad=0,  # se asigna abajo
            )
        )

    candidatas.sort(key=lambda r: (-r.evidencia, r.patron_normalizado))
    return [
        ReglaSemilla(
            patron=c.patron,
            patron_normalizado=c.patron_normalizado,
            rubro_id=c.rubro_id,
            tipo_flujo=c.tipo_flujo,
            evidencia=c.evidencia,
            pureza=c.pureza,
            prioridad=100 + i,
        )
        for i, c in enumerate(candidatas)
    ]
