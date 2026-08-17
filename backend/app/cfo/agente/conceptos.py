"""FABS · conceptos citables + formateo server-bound + sustitución de tokens.

El modelo cita conceptos con `[[concepto]]` (sin ver valores); tras verificar, el
servicio sustituye cada token por el valor concept-bound, ya formateado es-CO y con
el contexto interpretativo que COMPAS computa (runway=duración; IVA=vencimiento+días,
D-1 del gate de diseño). Money=Decimal, formateo con `decimal`/`int`, cero float."""

import re
from datetime import date
from decimal import Decimal

from app.cfo.calc.evidencia import ResultadoCFO
from app.core.time import today_bogota

CONCEPTOS_CITABLES: frozenset[str] = frozenset(
    {"caja_hoy", "runway", "iva_cuatrimestre"}
)

_RE_TOKEN = re.compile(r"\[\[(\w+)\]\]")


def _money_es(d: Decimal) -> str:
    # COP para display: parte entera con separador de miles es-CO ('.'), sin centavos.
    entero = int(d)
    return "$" + f"{entero:,}".replace(",", ".")


def _meses_es(d: Decimal) -> str:
    return f"{d:.1f}".replace(".", ",") + " meses"


def formatear(r: ResultadoCFO, hoy: date | None = None) -> str:
    """Valor concept-bound listo para prosa, con su contexto server-bound."""
    if r.concepto == "runway":
        return _meses_es(r.valor)
    base = _money_es(r.valor)
    fecha = r.evidencia.fecha_corte
    if r.concepto == "iva_cuatrimestre":
        if fecha:
            dias = (date.fromisoformat(fecha) - (hoy or today_bogota())).days
            return f"{base} (vence el {fecha}, en {dias} días)"
        return base
    # caja_hoy (y cualquier otro COP con fecha de corte)
    return f"{base} (al {fecha})" if fecha else base


def sustituir_tokens(
    texto: str, resultados: list[ResultadoCFO], hoy: date | None = None
) -> str:
    por_concepto = {
        r.concepto: r for r in resultados if r.disponible and r.valor is not None
    }

    def _repl(m: re.Match) -> str:
        r = por_concepto.get(m.group(1))
        return formatear(r, hoy) if r is not None else m.group(0)

    return _RE_TOKEN.sub(_repl, texto)
