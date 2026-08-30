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
            concepto="palanca",
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
    Devuelve 3 conceptos, todos COP (nombres NAMESPACED con sufijo `_palanca` para
    que nunca colisionen con `piso_sin`/`piso_con` de `escenario.impacto_escenario`
    cuando ambas tools se disparan en el mismo turno — `sustituir_tokens` arma
    `{r.concepto: r}` sobre TODOS los resultados del turno, last-wins):
    - `piso_sin_palanca`: piso de caja BASE (sin la palanca cambiada); ref = ancla de
      horizonte (mes de HOY, igual que `escenario.impacto_escenario`).
    - `piso_con_palanca`: piso de caja CON la palanca aplicada; su evidencia trae el
      mes de quiebre (`quiebre:<YYYY-MM>` o `quiebre:nunca`).
    - `impacto_palanca`: `piso_con - piso_sin`, tomado directo de `res.impacto` (NO
      se recalcula aquí); ref = ancla de horizonte, SALVO plazo con impacto 0, donde
      ref = 'plazo-sin-efecto-horizonte' (señal para que el prompt explique que el
      efecto del plazo es de largo plazo, no un "$0" a secas).

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
    # Salvedad del PLAZO (fast-follow 2026-08-29): cambiar el plazo no mueve el piso
    # de caja DENTRO de un horizonte corto (ninguna cohorte alcanza aún la semana de
    # su plazo original) -> impacto == 0. Marcamos el ref de impacto_palanca para que
    # el prompt le diga a FABS que explique que el efecto del plazo es de largo plazo,
    # no un "$0" a secas. Solo el plazo: las palancas de cuota (inicial/semanal) mueven
    # el piso de inmediato, así que un impacto 0 ahí es un 0 real, sin salvedad.
    ref_impacto = ref_horizonte
    if palanca == "plazo_semanas" and res.impacto == 0:
        ref_impacto = "plazo-sin-efecto-horizonte"
    return [
        ResultadoCFO(
            concepto="piso_sin_palanca",
            valor=res.piso_sin,
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(fuente=_FUENTE, fecha_corte=None, ref=ref_horizonte),
            detalle=detalle,
        ),
        ResultadoCFO(
            concepto="piso_con_palanca",
            valor=res.piso_con,
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(
                fuente=_FUENTE, fecha_corte=None, ref=f"quiebre:{res.mes_quiebre}"
            ),
            detalle=detalle,
        ),
        ResultadoCFO(
            concepto="impacto_palanca",
            valor=res.impacto,
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(fuente=_FUENTE, fecha_corte=None, ref=ref_impacto),
            detalle=detalle,
        ),
    ]
