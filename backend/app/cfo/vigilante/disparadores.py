# backend/app/cfo/vigilante/disparadores.py
"""FABS · vigilante — evalúa los disparadores de la alerta de caja. Orquestación
(lee servicios de COMPAS; S1: NO vive en cfo/calc). Las cifras SIEMPRE las computa
COMPAS (proyeccion/cierre); aquí solo se compara contra los umbrales vigentes y se
arma la evidencia. Dato incompleto/ambiguo ⇒ abstención (regla 7), nunca adivinar."""

import logging
from dataclasses import dataclass
from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.cierre.service import CierreError, conciliacion
from app.configuracion.service import (
    leer_alerta_horizonte_meses,
    leer_umbral_atencion_activo,
)
from app.core.time import now_bogota, today_bogota
from app.domain.mes_control import EstadoMes, MesControl
from app.parametros_proyeccion import service as parametros_service
from app.proyeccion import service as proy_service
from app.proyeccion.service import ProyeccionError

logger = logging.getLogger(__name__)

_UNIDAD = "COP"
_FUENTE_PROY = "proyeccion.service.proyectar_vigente"
_FUENTE_REAL = "cierre.service.conciliacion"


@dataclass(frozen=True)
class Disparo:
    tipo: str  # 'proyectado' | 'real'
    severidad: str  # 'ambar' | 'rojo'


@dataclass(frozen=True)
class ResultadoAlerta:
    disparos: list[Disparo]
    resultados: list[ResultadoCFO]

    @property
    def severidad(self) -> str:
        return "rojo" if any(d.severidad == "rojo" for d in self.disparos) else "ambar"


def _umbral_res(concepto: str, valor: Decimal, ref: str) -> ResultadoCFO:
    return ResultadoCFO(
        concepto=concepto,
        valor=valor,
        unidad=_UNIDAD,
        disponible=True,
        evidencia=Evidencia(fuente=_FUENTE_PROY, fecha_corte=None, ref=ref),
    )


def _disparador_proyectado(
    proy: dict, minima: Decimal, atencion: Decimal | None
) -> tuple[Disparo | None, list[ResultadoCFO]]:
    quiebre = next((m for m in proy["meses"] if m["estado"] != "ok"), None)
    if quiebre is None:
        return None, []
    severidad = "ambar" if quiebre["estado"] == "atencion" else "rojo"
    res = [
        ResultadoCFO(
            concepto="alerta_piso",
            valor=Decimal(proy["piso_caja"]),
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(
                fuente=_FUENTE_PROY, fecha_corte=None, ref=f"quiebre:{quiebre['mes']}"
            ),
        ),
        _umbral_res("alerta_umbral_critico", minima, "umbral:critico"),
    ]
    if atencion is not None:
        res.append(_umbral_res("alerta_umbral_atencion", atencion, "umbral:atencion"))
    return Disparo("proyectado", severidad), res


async def _disparador_real(
    minima: Decimal, atencion: Decimal | None
) -> tuple[Disparo | None, list[ResultadoCFO]]:
    mc = await MesControl.find_one(MesControl.estado == EstadoMes.EN_EJECUCION)
    if mc is None:
        return None, []
    try:
        con = await conciliacion(mc.mes)
    except CierreError:
        return None, []
    if con["sin_dato"]:  # dato incompleto: no falsa alarma
        logger.info("alerta real: bancos sin reportar %s; se abstiene", con["sin_dato"])
        return None, []
    disponible = Decimal(con["consolidado_reportado"])
    if disponible <= minima:
        severidad = "rojo"
    elif atencion is not None and disponible <= atencion:
        severidad = "ambar"
    else:
        return None, []
    hoy = today_bogota().isoformat()
    res = [
        ResultadoCFO(
            concepto="alerta_disponible_hoy",
            valor=disponible,
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(
                fuente=_FUENTE_REAL, fecha_corte=hoy, ref="disponible:hoy"
            ),
        ),
        _umbral_res("alerta_umbral_critico", minima, "umbral:critico"),
    ]
    if atencion is not None:
        res.append(_umbral_res("alerta_umbral_atencion", atencion, "umbral:atencion"))
    return Disparo("real", severidad), res


async def evaluar_disparadores() -> ResultadoAlerta | None:
    # Los umbrales se leen INDEPENDIENTES de la proyección: si `proyectar_vigente`
    # revienta (sin modelos activos, p.ej.) el disparador REAL debe poder seguir —
    # es justo la caja de hoy la que puede estar crítica en ese estado (spec §5.3/§8).
    params = await parametros_service.obtener_vigente()
    if params is None:
        return None  # sin params no hay umbral que comparar en ninguna vía
    minima = params.caja_minima
    atencion = await leer_umbral_atencion_activo(minima)

    ahora = now_bogota()
    try:
        proy = await proy_service.proyectar_vigente(
            escenario="base",
            mes_inicio=(ahora.year, ahora.month),
            horizonte_meses=await leer_alerta_horizonte_meses(),
        )
    except ProyeccionError:
        proy = None  # sin config de proyección: solo se abstiene la vía proyectada

    disparos: list[Disparo] = []
    resultados: list[ResultadoCFO] = []
    if proy is not None:
        d_proy, r_proy = _disparador_proyectado(proy, minima, atencion)
        if d_proy is not None:
            disparos.append(d_proy)
            resultados.extend(r_proy)
    d_real, r_real = await _disparador_real(minima, atencion)
    if d_real is not None:
        disparos.append(d_real)
        resultados.extend(r_real)

    if not disparos:
        return None
    # dedup de conceptos repetidos (umbrales aparecen en ambos disparos)
    vistos: dict[str, ResultadoCFO] = {}
    for r in resultados:
        vistos.setdefault(r.concepto, r)
    return ResultadoAlerta(disparos=disparos, resultados=list(vistos.values()))
