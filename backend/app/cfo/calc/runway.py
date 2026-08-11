"""FABS · concepto 'runway' (meses de caja al ritmo actual). Lee el KPI runway_meses
de la proyección vigente de COMPAS. Sin config (ProyeccionError) → abstención."""

from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.core.time import now_bogota
from app.proyeccion import service as proy_service
from app.proyeccion.service import ProyeccionError


async def _proyectar(**kw) -> dict:
    return await proy_service.proyectar_vigente(**kw)


async def runway() -> ResultadoCFO:
    fuente = "proyeccion.service.proyectar_vigente"
    ahora = now_bogota()
    ref = f"{ahora.year:04d}-{ahora.month:02d}"
    try:
        data = await _proyectar(
            escenario="base", mes_inicio=(ahora.year, ahora.month), horizonte_meses=None
        )
    except ProyeccionError:
        return ResultadoCFO(
            concepto="runway",
            valor=None,
            unidad="meses",
            disponible=False,
            evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref="sin-config"),
        )
    rm = data.get("runway_meses")
    if rm is None:
        return ResultadoCFO(
            concepto="runway",
            valor=None,
            unidad="meses",
            disponible=False,
            evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref=ref),
            detalle={"nota": "sin quema neta: runway no aplica"},
        )
    return ResultadoCFO(
        concepto="runway",
        valor=Decimal(rm),
        unidad="meses",
        disponible=True,
        evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref=ref),
    )
