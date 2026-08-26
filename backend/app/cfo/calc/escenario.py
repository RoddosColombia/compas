# backend/app/cfo/calc/escenario.py
"""FABS · concepto 'escenario' (impacto hipotético de un gasto/ingreso recurrente en
la caja + mes de quiebre). Envuelve proyeccion.service.proyectar_impactos: construye
UN Ajuste declarativo (D1) con el monto hipotético desde `mes_inicio` (hasta `mes_fin`
o el final del horizonte) y compara la proyección BASE vs. CON el ajuste sobre el
horizonte vigente (arranca en el mes de HOY, como runway.py). Compute-only (SIMULAR
NUNCA ESCRIBE): no persiste nada, es lectura + cálculo puro. Sin config vigente
(ProyeccionError) → abstención."""

from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.core.time import now_bogota
from app.proyeccion import service as proy_service
from app.proyeccion.impactos import Ajuste
from app.proyeccion.service import ProyeccionError

_FUENTE = "proyeccion.service.proyectar_impactos"
_UNIDAD = "COP"


def _mes_de_quiebre(meses: list[dict]) -> str:
    """Primer mes de la serie ajustada cuyo estado no es 'ok' (crítico o negativo).
    Sin ninguno, el escenario nunca rompe el piso dentro del horizonte."""
    return next((m["mes"] for m in meses if m["estado"] != "ok"), "nunca")


async def impacto_escenario(
    *,
    naturaleza: str,
    monto: Decimal,
    mes_inicio: str,
    mes_fin: str | None = None,
) -> list[ResultadoCFO]:
    """Compara el piso de caja proyectado BASE vs. CON un ajuste hipotético
    (`naturaleza` ∈ {gasto,ingreso}, `monto` COP recurrente desde `mes_inicio` hasta
    `mes_fin` o el final del horizonte). Devuelve 3 conceptos:
    - `piso_sin`: piso de caja de la proyección BASE (sin el ajuste).
    - `piso_con`: piso de caja CON el ajuste aplicado; su evidencia trae el mes de
      quiebre (`quiebre:<YYYY-MM>` o `quiebre:nunca`).
    - `impacto_mensual`: el monto mensual del ajuste hipotético.

    Sin config de proyección vigente (`ProyeccionError`) → un único
    `ResultadoCFO(disponible=False)` con `ref='sin-config'` (abstención, patrón de
    runway.py)."""
    ahora = now_bogota()
    ajuste = Ajuste(
        nombre="Escenario FABS",
        naturaleza=naturaleza,
        modo="absoluto",
        valor=monto,
        mes_inicio=mes_inicio,
        mes_fin=mes_fin,
    )
    try:
        data = await proy_service.proyectar_impactos(
            ajustes=[ajuste],
            escenario="base",
            mes_inicio=(ahora.year, ahora.month),
            horizonte_meses=None,
        )
    except ProyeccionError:
        return [
            ResultadoCFO(
                concepto="escenario",
                valor=None,
                unidad=_UNIDAD,
                disponible=False,
                evidencia=Evidencia(fuente=_FUENTE, fecha_corte=None, ref="sin-config"),
            )
        ]

    quiebre = _mes_de_quiebre(data["ajustada"]["meses"])
    return [
        ResultadoCFO(
            concepto="piso_sin",
            valor=Decimal(data["base"]["piso_caja"]),
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(fuente=_FUENTE, fecha_corte=None, ref=mes_inicio),
        ),
        ResultadoCFO(
            concepto="piso_con",
            valor=Decimal(data["ajustada"]["piso_caja"]),
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(
                fuente=_FUENTE, fecha_corte=None, ref=f"quiebre:{quiebre}"
            ),
        ),
        ResultadoCFO(
            concepto="impacto_mensual",
            valor=monto,
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(fuente=_FUENTE, fecha_corte=None, ref=mes_inicio),
        ),
    ]
