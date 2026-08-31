"""FABS · calc PURO de la tesorería del IVA (S1: aislado).

Recibe números, arma ResultadoCFO. El objetivo de reserva es el saldo acumulado
del fondo del mes actual (computado del plan). Cada insumo ausente ⇒ abstención
de lo que depende.
"""

from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO

_UNIDAD = "COP"
_FUENTE = "iva.liquidacion.plan_fondo_provision+conciliacion"


def _res(
    concepto: str, valor: Decimal | None, ref: str, fecha: str | None = None
) -> ResultadoCFO:
    return ResultadoCFO(
        concepto=concepto,
        valor=valor,
        unidad=_UNIDAD,
        disponible=valor is not None,
        evidencia=Evidencia(fuente=_FUENTE, fecha_corte=fecha, ref=ref),
    )


def armar_conceptos(
    *,
    reserva_objetivo: Decimal | None,
    reserva_mes: Decimal | None,
    proximo_monto: Decimal | None,
    proximo_fecha: str | None,
    disponible: Decimal | None,
) -> list[ResultadoCFO]:
    neto = (
        (disponible - reserva_objetivo)
        if (disponible is not None and reserva_objetivo is not None)
        else None
    )
    faltante = (
        max(Decimal("0"), reserva_objetivo - disponible)
        if (disponible is not None and reserva_objetivo is not None)
        else None
    )
    return [
        _res("ivates_reserva_objetivo", reserva_objetivo, "objetivo:acumulado"),
        _res("ivates_reserva_mes", reserva_mes, "aporte:mes"),
        _res("ivates_proximo_pago", proximo_monto, "proximo:pago", fecha=proximo_fecha),
        _res("ivates_disponible_neto", neto, "neto:iva"),
        _res("ivates_faltante", faltante, "cobertura"),
    ]
