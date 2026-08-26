# backend/app/cfo/agente/tools.py
"""FABS · tools de SOLO LECTURA que el modelo puede invocar. Cada tool envuelve uno o
más conceptos de `app.cfo.calc` y devuelve su(s) ResultadoCFO completo(s) (incl.
disponible y evidencia). El dispatcher es cerrado: una tool desconocida es error,
nunca se inventa. Serialización para el modelo (`resultado_a_dict`): sin `valor` ni
`detalle` (inc3 Pieza A) — el modelo cita conceptos con [[token]] y el servicio
sustituye el valor concept-bound tras verificar. El `ResultadoCFO` completo (con
`valor`) sigue viajando por el loop sin serializar.

`ejecutar_tool` (inc4 T4) acepta una `entrada` opcional (parámetros de la tool, p. ej.
el escenario de un impacto) y SIEMPRE devuelve `list[ResultadoCFO]`: las calcs de un
solo concepto (las 3 de cero args de hoy) se normalizan a `[r]`; las calcs de varios
conceptos (escenarios, inc4 más adelante) ya devuelven su propia lista y pasan
intacta. Se decide por la firma de la calc registrada en DISPATCH: sin parámetros se
llama sin `entrada` (las 3 tools actuales); con parámetros se le pasa `entrada`."""

import inspect
from collections.abc import Awaitable, Callable

from app.cfo.calc import caja, iva, runway
from app.cfo.calc.evidencia import ResultadoCFO

CalcSinArgs = Callable[[], Awaitable[ResultadoCFO]]
CalcConArgs = Callable[[dict], Awaitable[list[ResultadoCFO]]]

DISPATCH: dict[str, CalcSinArgs | CalcConArgs] = {
    "caja_disponible_hoy": caja.caja_hoy,
    "runway_meses": runway.runway,
    "iva_del_cuatrimestre": iva.iva_cuatrimestre,
}

TOOLS_SCHEMA: list[dict] = [
    {
        "name": "caja_disponible_hoy",
        "description": (
            "Caja disponible HOY en COP: último saldo real de la serie diaria de "
            "COMPAS, con su fecha de corte. Si no hay datos, disponible=false."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "runway_meses",
        "description": (
            "Meses de caja restantes al ritmo de quema actual (KPI runway de la "
            "proyección vigente). Sin quema neta o sin configuración, disponible=false."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "iva_del_cuatrimestre",
        "description": (
            "IVA neto a pagar del cuatrimestre fiscal vigente en COP, con la fecha "
            "límite DIAN. Solo válido con periodicidad cuatrimestral; si no, "
            "disponible=false."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
]


async def ejecutar_tool(nombre: str, entrada: dict | None = None) -> list[ResultadoCFO]:
    # Dispatcher cerrado: `nombre` desconocido → KeyError, jamás se inventa una tool.
    calc = DISPATCH[nombre]
    if inspect.signature(calc).parameters:
        resultado = await calc(entrada or {})
    else:
        resultado = await calc()
    # Normaliza a lista: las calcs de un solo concepto (hoy: las 3 de cero args)
    # devuelven UN ResultadoCFO; las de varios conceptos ya devuelven su lista.
    return resultado if isinstance(resultado, list) else [resultado]


def resultado_a_dict(r: ResultadoCFO) -> dict:
    # El modelo NO ve valores: cita conceptos con [[token]] y el servicio sustituye el
    # valor concept-bound tras verificar (inc3 Pieza A). Sin `valor` no puede fabricar,
    # mal-etiquetar ni calcular.
    return {
        "concepto": r.concepto,
        "disponible": r.disponible,
        "unidad": r.unidad,
        "evidencia": {
            "fuente": r.evidencia.fuente,
            "fecha_corte": r.evidencia.fecha_corte,
            "ref": r.evidencia.ref,
        },
    }
