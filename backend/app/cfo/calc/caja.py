# backend/app/cfo/calc/caja.py
"""FABS · concepto 'caja disponible hoy'. Lee la serie diaria real de COMPAS
(caja.service.caja_diaria) desde el ancla de caja inicial vigente hasta hoy (Bogotá) y
toma el último saldo, con su fecha de corte. Sin parámetros vigentes → abstención."""

from decimal import Decimal

from app.caja import service as caja_service
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.core.time import today_bogota
from app.parametros_proyeccion import service as params_service

_CONCEPTO = "caja_hoy"
_UNIDAD = "COP"
_FUENTE = "caja.service.caja_diaria"


async def caja_hoy() -> ResultadoCFO:
    """Caja disponible HOY: corre la serie diaria real desde `vigente_desde` (el
    ancla `caja_inicial` de los parámetros de proyección vigentes) hasta hoy
    (Bogotá) y toma el último saldo. Sin parámetros vigentes → abstención
    (`disponible=False`, `valor=None`). Sin movimientos en el rango → cae al
    ancla (`caja_inicial`), con `fecha_corte=vigente_desde`. Nunca inventa un
    número: toda cifra viaja con su Evidencia (fuente + fecha de corte + ref)."""
    vig = await params_service.obtener_vigente()
    if vig is None:
        return ResultadoCFO(
            concepto=_CONCEPTO,
            valor=None,
            unidad=_UNIDAD,
            disponible=False,
            evidencia=Evidencia(fuente=_FUENTE, fecha_corte=None, ref="sin-parametros"),
        )

    hasta = today_bogota().isoformat()
    data = await caja_service.caja_diaria(
        desde=vig.vigente_desde, hasta=hasta, caja_inicial=vig.caja_inicial
    )
    dias = data["dias"]
    if not dias:
        return ResultadoCFO(
            concepto=_CONCEPTO,
            valor=vig.caja_inicial,
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(
                fuente=_FUENTE, fecha_corte=vig.vigente_desde, ref="sin-movimientos"
            ),
        )

    ultimo = dias[-1]
    return ResultadoCFO(
        concepto=_CONCEPTO,
        valor=Decimal(ultimo["caja"]),
        unidad=_UNIDAD,
        disponible=True,
        evidencia=Evidencia(fuente=_FUENTE, fecha_corte=ultimo["fecha"], ref=hasta[:7]),
        detalle={"desde": vig.vigente_desde, "hasta": hasta},
    )
