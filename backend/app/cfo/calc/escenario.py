# backend/app/cfo/calc/escenario.py
"""FABS · concepto 'escenario' (impacto hipotético de un gasto/ingreso recurrente en
la caja + mes de quiebre + cuántas motos extra evitan cruzar el umbral).

`impacto_escenario` envuelve proyeccion.service.proyectar_impactos: construye UN
Ajuste declarativo (D1) con el monto hipotético desde `mes_inicio` (hasta `mes_fin` o
el final del horizonte) y compara la proyección BASE vs. CON el ajuste sobre el
horizonte vigente (arranca en el mes de HOY, como runway.py).

`motos_para_evitar_umbral` (Task 6, inc4) responde "¿cuántas motos de más por mes
hacen falta para que el piso no cruce el umbral, con ese mismo escenario encima?":
envuelve `solver_unidades.resolver_unidades_para_umbral` (Task 1) — bisección ENTERA
que RE-CORRE el cálculo completo de proyección por cada candidato N (las unidades
fluyen por cartera/mora/GPS; no es un ajuste directo de caja como D1). El cierre que
recorre esa proyección vive en `proyeccion.service.fabrica_proyectar_unidades`, NO
aquí: `cfo/calc` no puede importar tipos de dominio ajenos ni el módulo interno de
cálculo puro (aislamiento S1, ver `tests/cfo/test_s1_aislamiento.py`) — este módulo
solo LLAMA esa fábrica, opaco.

Ambas son compute-only (SIMULAR NUNCA ESCRIBE): no persisten nada, es lectura +
cálculo puro. Sin config vigente → abstención (mismo patrón en las dos). Fix round 1
(Task 6): el solver de unidades corre sobre el MISMO pipeline completo (paramétrico →
E1 → D2) que `impacto_escenario`, así que los dos reconcilian en la misma base — por
eso `resolver_unidades_para_umbral` y la fábrica que arma su `proyectar_fn` son
ASYNC."""

from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.core.time import now_bogota
from app.parametros_proyeccion import service as params_service
from app.proyeccion import service as proy_service
from app.proyeccion.impactos import Ajuste
from app.proyeccion.service import ProyeccionError
from app.proyeccion.solver_unidades import (
    UnidadesResultado,
    resolver_unidades_para_umbral,
)

_FUENTE = "proyeccion.service.proyectar_impactos"
_FUENTE_ENTRADA = "escenario (entrada)"
_FUENTE_SOLVER = "proyeccion.solver_unidades.resolver_unidades_para_umbral"
_UNIDAD = "COP"
_UNIDAD_MOTOS = "unidades"


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

    # Ancla de reproducibilidad del horizonte de la PROYECCIÓN (arranca en el mes de
    # HOY, igual que runway.py:19) — NO el mes_inicio del ajuste hipotético. piso_sin
    # es la proyección BASE, calculada sin el ajuste: su ref no puede sugerir que
    # depende del mes en que arranca el escenario.
    ref_horizonte = f"{ahora.year:04d}-{ahora.month:02d}"
    quiebre = _mes_de_quiebre(data["ajustada"]["meses"])
    return [
        ResultadoCFO(
            concepto="piso_sin",
            valor=Decimal(data["base"]["piso_caja"]),
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(fuente=_FUENTE, fecha_corte=None, ref=ref_horizonte),
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
            # No es un valor que proyectar_impactos calculó: es el monto de entrada
            # del caller, ecoado. La fuente debe decir eso, no atribuirlo al cálculo
            # de proyección.
            evidencia=Evidencia(
                fuente=_FUENTE_ENTRADA, fecha_corte=None, ref=ref_horizonte
            ),
        ),
    ]


def _abstencion(*, ref: str) -> ResultadoCFO:
    """Único concepto `unidades_extra` no disponible — abstención honesta: sin config,
    sin modelos activos, o el solver no encontró solución dentro del tope."""
    return ResultadoCFO(
        concepto="unidades_extra",
        valor=None,
        unidad=_UNIDAD_MOTOS,
        disponible=False,
        evidencia=Evidencia(fuente=_FUENTE_SOLVER, fecha_corte=None, ref=ref),
    )


async def _proyectar_fn_para(
    vig,
    escenario: str,
    mes_inicio: tuple[int, int],
    horizonte: int,
):
    """Arma el `proyectar_fn(n)` que exige `resolver_unidades_para_umbral` (Task 1,
    módulo `solver_unidades`): un callable ASYNC que, dado N (unidades extra/mes),
    devuelve el resultado de proyección CRUDO de calcular con `motos_base + N` sobre
    el pipeline COMPLETO (paramétrico → E1 anclaje → D2 reconciliación — Fix round 1:
    la misma base que usa `impacto_escenario`, para que los dos reconcilien).

    La fábrica real vive en `proyeccion.service.fabrica_proyectar_unidades` — no
    aquí: `cfo/calc` no puede importar tipos de dominio ajenos ni el módulo interno de
    cálculo puro directo (aislamiento S1, `tests/cfo/test_s1_aislamiento.py`). Esta
    función solo la LLAMA, opaca a sus tipos (ver la docstring de la fábrica para el
    detalle exacto del pipeline)."""
    return await proy_service.fabrica_proyectar_unidades(
        vig, escenario, mes_inicio, horizonte
    )


async def motos_para_evitar_umbral(
    *,
    naturaleza: str,
    monto: Decimal,
    mes_inicio: str,
    mes_fin: str | None = None,
) -> list[ResultadoCFO]:
    """¿Cuántas motos EXTRA por mes (desde HOY) hacen falta para que el piso de caja
    proyectado no cruce el umbral, con el mismo escenario hipotético de
    `impacto_escenario` (`naturaleza`/`monto`/`mes_inicio`/`mes_fin`) ya aplicado
    encima? Envuelve `solver_unidades.resolver_unidades_para_umbral` (Task 1): bisecta
    sobre N re-corriendo el pipeline COMPLETO de proyección (paramétrico → E1 → D2,
    Fix round 1) con `motos_base + N` (`_proyectar_fn_para`; el horizonte ancla en el
    mes de HOY, igual que `impacto_escenario`) y, sobre CADA candidato, mide el piso
    con el mismo `Ajuste` declarativo (D1) aplicado encima — misma base que
    `impacto_escenario`, así que `piso_con_unidades@n=0` y su `piso_con` reconcilian.

    Devuelve 2 conceptos:
    - `unidades_extra`: N (unidad "unidades"). `disponible=False` si el solver no
      encuentra solución dentro de su tope (abstención honesta — nunca se inventa un
      número).
    - `piso_con_unidades`: el piso de caja (COP) que resulta con esas N unidades.

    Sin config de proyección vigente, o sin modelos activos (`ProyeccionError` de
    `_proyectar_fn_para`) → un único `ResultadoCFO(disponible=False)` con
    `ref='sin-config'` (mismo patrón de abstención que `impacto_escenario`)."""
    ahora = now_bogota()
    ref_horizonte = f"{ahora.year:04d}-{ahora.month:02d}"
    vig = await params_service.obtener_vigente()
    if vig is None:
        return [_abstencion(ref="sin-config")]
    ajuste = Ajuste(
        nombre="Escenario FABS",
        naturaleza=naturaleza,
        modo="absoluto",
        valor=monto,
        mes_inicio=mes_inicio,
        mes_fin=mes_fin,
    )
    try:
        # Fix round 1: `_proyectar_fn_para` y `resolver_unidades_para_umbral` son
        # ambas async ahora (el pipeline completo por candidato exige I/O) — se
        # awaitean directo, sin el puente síncrono que hacía falta cuando el solver
        # solo corría el cálculo paramétrico sin E1/D2.
        proyectar_fn = await _proyectar_fn_para(
            vig, "base", (ahora.year, ahora.month), vig.horizonte_meses
        )
        resultado: UnidadesResultado = await resolver_unidades_para_umbral(
            proyectar_fn, [ajuste], caja_minima=vig.caja_minima
        )
    except ProyeccionError:
        return [_abstencion(ref="sin-config")]
    if not resultado.alcanzable:
        return [_abstencion(ref=f"no-alcanzable:{ref_horizonte}")]
    return [
        ResultadoCFO(
            concepto="unidades_extra",
            valor=Decimal(resultado.unidades_extra),
            unidad=_UNIDAD_MOTOS,
            disponible=True,
            evidencia=Evidencia(
                fuente=_FUENTE_SOLVER, fecha_corte=None, ref=ref_horizonte
            ),
        ),
        ResultadoCFO(
            concepto="piso_con_unidades",
            valor=resultado.piso_resultante,
            unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(
                fuente=_FUENTE_SOLVER, fecha_corte=None, ref=ref_horizonte
            ),
        ),
    ]
