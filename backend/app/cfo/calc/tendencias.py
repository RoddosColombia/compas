"""FABS · tendencias (inc4 rebanada 3): compara data REAL en el tiempo. Envuelve
servicios de COMPAS que ya agregan actuals; NO recalcula, NO importa dominio ni el
proyector interno (aislamiento S1). La direccion (sube/baja/...) la computa COMPAS a
partir de las cifras y viaja en evidencia.ref; el modelo la relata, no la infiere."""

from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.proyeccion import service as proy_service
from app.proyeccion.service import ProyeccionError

_UNIDAD = "COP"
_METRICAS = {"ingreso": "ingreso_real", "gasto": "gasto_real", "caja": "caja_real"}


def _dir(delta: Decimal, pos: str, neg: str, zero: str) -> str:
    if delta > 0:
        return pos
    if delta < 0:
        return neg
    return zero


def _abstencion(concepto: str, ref: str, fuente: str) -> list[ResultadoCFO]:
    return [
        ResultadoCFO(
            concepto=concepto,
            valor=None,
            unidad=_UNIDAD,
            disponible=False,
            evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref=ref),
        )
    ]


async def tendencia_real(*, metrica: str) -> list[ResultadoCFO]:
    fuente = "proyeccion.service.actuals_mensuales"
    if metrica not in _METRICAS:
        raise ValueError(f"metrica no soportada: {metrica}")
    campo = _METRICAS[metrica]
    try:
        serie = await proy_service.actuals_mensuales(meses=3)
    except ProyeccionError:
        return _abstencion(f"{metrica}_real", "sin-config", fuente)
    if len(serie) < 2:
        return _abstencion(f"{metrica}_real", "sin-historia", fuente)
    recientes = serie[::-1]  # m0 = más reciente
    out: list[ResultadoCFO] = []
    for i, a in enumerate(recientes[:3]):
        out.append(
            ResultadoCFO(
                concepto=f"{metrica}_real_m{i}",
                valor=getattr(a, campo),
                unidad=_UNIDAD,
                disponible=True,
                evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref=a.mes),
            )
        )
    delta = getattr(recientes[0], campo) - getattr(recientes[1], campo)
    out.append(
        ResultadoCFO(
            concepto=f"delta_{metrica}_real",
            valor=delta,
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(
                fuente=fuente,
                fecha_corte=None,
                ref=f"direccion:{_dir(delta, 'sube', 'baja', 'estable')}",
            ),
        )
    )
    return out
