"""FABS · composicion (inc4 rebanada 4a): % de participacion de cada grupo de
gasto sobre el gasto real total de una ventana. Envuelve
proyeccion.service.composicion_gasto_real (que ya agrega el egreso REAL por
RubroGrupo); NO recalcula, NO importa dominio ni el proyector interno
(aislamiento S1). El % lo computa esta capa, Decimal puro, cuantizado a 0.1."""

from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.proyeccion import service as proy_service
from app.proyeccion.service import ProyeccionError

_UNIDAD_COP = "COP"
_UNIDAD_PCT = "%"
_FUENTE = "proyeccion.service.composicion_gasto_real"
_SUF = {
    "costo_producto": "costo_producto",
    "operacion": "operacion",
    "nomina": "nomina",
    "deudas_obligaciones": "deudas",
    "otros": "otros",
}
_CIEN = Decimal("100")
_CUANTO_PCT = Decimal("0.1")


def _abstencion(concepto: str, ref: str) -> list[ResultadoCFO]:
    return [
        ResultadoCFO(
            concepto=concepto,
            valor=None,
            unidad=_UNIDAD_COP,
            disponible=False,
            evidencia=Evidencia(fuente=_FUENTE, fecha_corte=None, ref=ref),
        )
    ]


async def composicion_gasto(*, ventana: str) -> list[ResultadoCFO]:
    try:
        c = await proy_service.composicion_gasto_real(ventana=ventana)
    except ProyeccionError:
        return _abstencion("composicion", "sin-config")
    if c.total <= 0:
        return _abstencion("composicion", "sin-gasto")

    ref = f"{c.ventana}:{'|'.join(c.meses)}"
    evidencia = Evidencia(fuente=_FUENTE, fecha_corte=None, ref=ref)
    out: list[ResultadoCFO] = [
        ResultadoCFO(
            concepto="gasto_total_comp",
            valor=c.total,
            unidad=_UNIDAD_COP,
            disponible=True,
            evidencia=evidencia,
        )
    ]
    for grupo, suf in _SUF.items():
        cop = c.por_grupo.get(grupo, Decimal("0"))
        pct = (cop / c.total * _CIEN).quantize(_CUANTO_PCT)
        out.append(
            ResultadoCFO(
                concepto=f"cop_{suf}",
                valor=cop,
                unidad=_UNIDAD_COP,
                disponible=True,
                evidencia=evidencia,
            )
        )
        out.append(
            ResultadoCFO(
                concepto=f"pct_{suf}",
                valor=pct,
                unidad=_UNIDAD_PCT,
                disponible=True,
                evidencia=evidencia,
            )
        )
    return out
