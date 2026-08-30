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

# Compartida con verificador.py (import directo, NUNCA redefinir ahí): ambos deben
# reconocer EXACTAMENTE el mismo token o se abre un hueco — verificado-pero-no-
# sustituido (fuga de placeholder) o sustituido-pero-no-verificado (hueco de
# seguridad real). Tolerante a espacios internos ("[[ caja_hoy ]]") — hardening
# FINAL-REVIEW: sin '\s*' un token espaciado no calzaba en NINGUNA de las dos regex
# (antes duplicadas), así que pasaba el veredicto (nada que marcar inválido) y
# además se filtraba crudo al usuario (nada que sustituir).
RE_TOKEN = re.compile(r"\[\[\s*(\w+)\s*\]\]")


def _money_es(d: Decimal) -> str:
    # COP para display: parte entera con separador de miles es-CO ('.'), sin centavos.
    # FINAL-REVIEW M1: el signo va ANTES del '$' ("-$5.000.000"), no después
    # ("$-5.000.000") — rebanada 3 produce negativos con regularidad (desvío
    # bajo-presupuesto, delta de caja a la baja) y esto llega al CEO seguido.
    entero = int(d)
    signo = "-" if entero < 0 else ""
    return signo + "$" + f"{abs(entero):,}".replace(",", ".")


def _meses_es(d: Decimal) -> str:
    return f"{d:.1f}".replace(".", ",") + " meses"


def _unidades_es(d: Decimal) -> str:
    return f"{int(d)} motos"


def _pct_es(d: Decimal) -> str:
    return f"{d:.1f}".replace(".", ",") + "%"


def formatear(r: ResultadoCFO, hoy: date | None = None) -> str:
    """Valor concept-bound listo para prosa, con su contexto server-bound."""
    if r.concepto == "runway":
        return _meses_es(r.valor)
    if r.unidad == "unidades":
        return _unidades_es(r.valor)
    if r.unidad == "%":
        return _pct_es(r.valor)
    base = _money_es(r.valor)
    ref = r.evidencia.ref or ""
    if ref.startswith("quiebre:"):
        mes = ref.split(":", 1)[1]
        ctx = "no cruzas el umbral" if mes == "nunca" else f"cruzas el umbral en {mes}"
        return f"{base} ({ctx})"
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

    return RE_TOKEN.sub(_repl, texto)
