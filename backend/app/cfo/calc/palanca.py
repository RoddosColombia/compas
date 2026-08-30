"""FABS · concepto 'palanca' (inc4 rebanada 2) — what-if de una palanca de crédito
(plazo/cuota inicial/cuota semanal) sobre uno o todos los modelos de moto.

`impacto_palanca` envuelve `proyeccion.service.impacto_palanca_raw` (Task 1): esa
función ya re-corre el pipeline completo dos veces (base vs. con la palanca aplicada)
y devuelve un `PalancaImpacto` de tipos planos (Decimal/str). Este módulo solo lo
LLAMA y envuelve el resultado en `ResultadoCFO` con su `Evidencia` — mismo molde que
`cfo.calc.escenario.impacto_escenario`: NO recalcula nada, NO importa tipos de
dominio ni el módulo de cálculo interno (aislamiento S1, ver
`tests/cfo/test_s1_aislamiento.py`).

Sin config de proyección vigente, o palanca/modelo/valor inválido
(`ProyeccionError`) → abstención honesta: un único `ResultadoCFO(disponible=False)`."""

from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.core.time import now_bogota
from app.proyeccion import service as proy_service
from app.proyeccion.service import ProyeccionError

_FUENTE = "proyeccion.service.impacto_palanca_raw"
_UNIDAD = "COP"


def _abstencion() -> list[ResultadoCFO]:
    return [
        ResultadoCFO(
            concepto="impacto",
            valor=None,
            unidad=_UNIDAD,
            disponible=False,
            evidencia=Evidencia(fuente=_FUENTE, fecha_corte=None, ref="sin-config"),
        )
    ]


async def impacto_palanca(
    *,
    palanca: str,
    nuevo_valor: Decimal,
    modelo: str = "todos",
) -> list[ResultadoCFO]:
    """¿Qué pasa con el piso de caja proyectado si `palanca` (plazo_semanas,
    cuota_inicial o cuota_semanal) cambia a `nuevo_valor` en `modelo` (o "todos")?
    Devuelve 3 conceptos, todos COP:
    - `piso_sin`: piso de caja BASE (sin la palanca cambiada); ref = ancla de
      horizonte (mes de HOY, igual que `escenario.impacto_escenario`).
    - `piso_con`: piso de caja CON la palanca aplicada; su evidencia trae el mes de
      quiebre (`quiebre:<YYYY-MM>` o `quiebre:nunca`).
    - `impacto`: `piso_con - piso_sin`, tomado directo de `res.impacto` (NO se
      recalcula aquí); ref = ancla de horizonte.

    `detalle` lleva `{palanca, modelo, nuevo_valor}` para trazabilidad (no citable
    por el verificador anti-alucinación: no es una cifra, es metadata de la consulta).

    Sin config vigente, o palanca/modelo/valor inválido (`ProyeccionError`) → un
    único `ResultadoCFO(disponible=False)` (abstención, patrón de
    `escenario.impacto_escenario`)."""
    ahora = now_bogota()
    detalle = {"palanca": palanca, "modelo": modelo, "nuevo_valor": nuevo_valor}
    try:
        res = await proy_service.impacto_palanca_raw(
            palanca=palanca,
            nuevo_valor=nuevo_valor,
            modelo=modelo,
            escenario="base",
            mes_inicio=(ahora.year, ahora.month),
            horizonte_meses=None,
        )
    except ProyeccionError:
        return _abstencion()

    ref_horizonte = f"{ahora.year:04d}-{ahora.month:02d}"
    return [
        ResultadoCFO(
            concepto="piso_sin",
            valor=res.piso_sin,
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(fuente=_FUENTE, fecha_corte=None, ref=ref_horizonte),
            detalle=detalle,
        ),
        ResultadoCFO(
            concepto="piso_con",
            valor=res.piso_con,
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(
                fuente=_FUENTE, fecha_corte=None, ref=f"quiebre:{res.mes_quiebre}"
            ),
            detalle=detalle,
        ),
        ResultadoCFO(
            concepto="impacto",
            valor=res.impacto,
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(fuente=_FUENTE, fecha_corte=None, ref=ref_horizonte),
            detalle=detalle,
        ),
    ]
