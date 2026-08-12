"""FABS · concepto 'IVA del cuatrimestre'. Toma el neto a pagar del período fiscal
VIGENTE (el que contiene hoy) de la liquidación de COMPAS, con su fecha DIAN como
evidencia. Sin período vigente en la liquidación → abstención."""

from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.core.time import now_bogota
from app.facturas import service as fact_service


async def _liquidacion() -> dict:
    return await fact_service.liquidacion_iva()


def _periodo_vigente_idx() -> tuple[int, int]:
    ahora = now_bogota()
    idx = (ahora.month - 1) // 4 + 1  # 1..3 (cuatrimestral: ene-abr/may-ago/sep-dic)
    return (ahora.year, idx)


async def iva_cuatrimestre() -> ResultadoCFO:
    fuente = "facturas.service.liquidacion_iva"
    anio, idx = _periodo_vigente_idx()
    ref = f"{anio}-C{idx}"
    data = await _liquidacion()
    if data.get("periodicidad") != "cuatrimestral":
        # Fail-closed: el concepto asume cuatrimestral; con otra periodicidad el
        # índice y la etiqueta del período serían erróneos. Regla #1: antes que
        # publicar una cifra mal ubicada, se abstiene honestamente.
        return ResultadoCFO(
            concepto="iva_cuatrimestre",
            valor=None,
            unidad="COP",
            disponible=False,
            evidencia=Evidencia(
                fuente=fuente, fecha_corte=None, ref="periodicidad-no-cuatrimestral"
            ),
            detalle={"periodicidad": data.get("periodicidad")},
        )
    vig = next(
        (p for p in data["periodos"] if p["anio"] == anio and p["periodo"] == idx),
        None,
    )
    if vig is None:
        return ResultadoCFO(
            concepto="iva_cuatrimestre",
            valor=None,
            unidad="COP",
            disponible=False,
            evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref=ref),
        )
    pago = vig.get("proximo_pago")
    fecha_dian = pago["fecha"] if pago else None
    return ResultadoCFO(
        concepto="iva_cuatrimestre",
        valor=Decimal(vig["neto_a_pagar"]),
        unidad="COP",
        disponible=True,
        evidencia=Evidencia(fuente=fuente, fecha_corte=fecha_dian, ref=vig["etiqueta"]),
        detalle={
            "generado": vig.get("generado"),
            "descontable": vig.get("descontable"),
        },
    )
