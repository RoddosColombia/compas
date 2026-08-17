# backend/app/cfo/agente/tools.py
"""FABS · tools de SOLO LECTURA que el modelo puede invocar. Cada tool envuelve un
concepto de `app.cfo.calc` y devuelve su ResultadoCFO completo (incl. disponible y
evidencia). El dispatcher es cerrado: una tool desconocida es error, nunca se inventa.
Serialización para el modelo (`resultado_a_dict`): sin `valor` ni `detalle` (inc3 Pieza
A) — el modelo cita conceptos con [[token]] y el servicio sustituye el valor
concept-bound tras verificar. El `ResultadoCFO` completo (con `valor`) sigue viajando
por el loop sin serializar."""

from collections.abc import Awaitable, Callable

from app.cfo.calc import caja, iva, runway
from app.cfo.calc.evidencia import ResultadoCFO

DISPATCH: dict[str, Callable[[], Awaitable[ResultadoCFO]]] = {
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


async def ejecutar_tool(nombre: str) -> ResultadoCFO:
    return await DISPATCH[nombre]()


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
