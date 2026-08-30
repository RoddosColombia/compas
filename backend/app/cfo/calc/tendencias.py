"""FABS · tendencias (inc4 rebanada 3): compara data REAL en el tiempo. Envuelve
servicios de COMPAS que ya agregan actuals; NO recalcula, NO importa dominio ni el
proyector interno (aislamiento S1). La direccion (sube/baja/...) la computa COMPAS a
partir de las cifras y viaja en evidencia.ref; el modelo la relata, no la infiere."""

from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.core.time import now_bogota
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


async def rumbo_caja() -> list[ResultadoCFO]:
    """¿Vamos en rumbo? Narra la caja real hasta hoy (comparar_vigente) y hacia dónde
    apunta la proyeccion vigente: piso y primer mes que deja de estar 'ok' (quiebre).
    No recalcula nada: solo lee ambos servicios y arma la evidencia (regla 10)."""
    fuente = "proyeccion.service.comparar_vigente+proyectar_vigente"
    ahora = now_bogota()
    try:
        comp = await proy_service.comparar_vigente(
            escenario="base",
            ancla_modo="movimientos",
            horizonte_meses=None,
            mes_inicio_defecto=(ahora.year, ahora.month),
        )
        data = await proy_service.proyectar_vigente(
            escenario="base",
            mes_inicio=(ahora.year, ahora.month),
            horizonte_meses=None,
        )
    except ProyeccionError:
        return _abstencion("rumbo_caja", "sin-config", fuente)

    actuals = comp["actuals"]
    if not actuals:
        return _abstencion("rumbo_caja", "sin-historia", fuente)

    ult = actuals[-1]
    caja_ult = Decimal(ult["caja_real"])
    out: list[ResultadoCFO] = [
        ResultadoCFO(
            concepto="caja_real_ult",
            valor=caja_ult,
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref=ult["mes"]),
        )
    ]

    if len(actuals) >= 2:
        previo = actuals[-2]
        caja_previo = Decimal(previo["caja_real"])
        out.append(
            ResultadoCFO(
                concepto="caja_real_previo",
                valor=caja_previo,
                unidad=_UNIDAD,
                disponible=True,
                evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref=previo["mes"]),
            )
        )
        delta = caja_ult - caja_previo
        out.append(
            ResultadoCFO(
                concepto="delta_caja_rumbo",
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

    quiebre = next((m["mes"] for m in data["meses"] if m["estado"] != "ok"), "nunca")
    out.append(
        ResultadoCFO(
            concepto="piso_proyectado",
            valor=Decimal(data["piso_caja"]),
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(
                fuente=fuente, fecha_corte=None, ref=f"quiebre:{quiebre}"
            ),
        )
    )
    return out
