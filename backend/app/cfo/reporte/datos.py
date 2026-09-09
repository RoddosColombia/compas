"""FABS · orquestación del reporte a inversionistas (inc6 #3, Task 3): lee los
mismos servicios vigentes de COMPAS que las tools de FABS (`cfo/agente/tools.py`)
para las cifras deterministas de las 4 secciones, y narra el resumen ejecutivo vía
`servicio.consultar()` — el modelo NUNCA escribe un número; solo texto ya
verificado/sustituido entra al reporte (mismo contrato anti-alucinación que el chat
y los vigilantes).

S1: `cfo/reporte/` NO está en el sweep de aislamiento
(`tests/cfo/test_s1_aislamiento.py` — igual que `cfo/vigilante/`): este módulo es
orquestación y puede leer servicios.
Deliberadamente NO importa `cfo/agente/tools` (esa frontera es del loop LLM<->tools);
en su lugar llama las mismas calcs de `cfo/calc` que `DISPATCH` usa ahí, o replica la
lectura de servicio cuando la calc no aplica (mismo patrón que
`cfo/vigilante/iva.py:_fondo_mes_actual`).

Cada lectura que falla o se abstiene arma una `Cifra("<etiqueta>", "sin datos")`
— nunca revienta el reporte (regla 7: abstención honesta, no se inventa)."""

from decimal import Decimal

from app.cfo.agente import servicio
from app.cfo.agente.cliente import crear_cliente
from app.cfo.calc import caja as caja_calc
from app.cfo.calc import escenario, iva, ratios, runway, tendencias
from app.cfo.calc.evidencia import ResultadoCFO
from app.cfo.reporte.modelos import Cifra, DatosReporte, RumboSerie, Seccion
from app.core.money import money_str
from app.core.time import now_bogota
from app.proyeccion import service as proy_service
from app.proyeccion.service import ProyeccionError

_SIN_DATOS = "sin datos"

_GRUPOS_GASTO = {
    "costo_producto": "Costo de producto",
    "operacion": "Operación",
    "nomina": "Nómina",
    "deudas": "Deudas y obligaciones",
    "otros": "Otros",
}


def _fmt(valor: Decimal, unidad: str) -> str:
    return money_str(valor) if unidad == "COP" else str(valor)


def _cifra(etiqueta: str, resultado: ResultadoCFO | None) -> Cifra:
    """Una `Cifra` a partir de un `ResultadoCFO` — "sin datos" si se abstuvo, no
    tiene valor, o la lectura ni siquiera devolvió el concepto (abstención total)."""
    if resultado is None or not resultado.disponible or resultado.valor is None:
        return Cifra(etiqueta=etiqueta, valor=_SIN_DATOS)
    return Cifra(etiqueta=etiqueta, valor=_fmt(resultado.valor, resultado.unidad))


def _buscar(resultados: list[ResultadoCFO], concepto: str) -> ResultadoCFO | None:
    return next((r for r in resultados if r.concepto == concepto), None)


def _prompt_reporte(periodo: str) -> str:
    return (
        f"Redactá el resumen ejecutivo del reporte a inversionistas de RODDOS para "
        f"{periodo}. Es factual y conservador: sin promesas ni afirmaciones que no "
        "vengan de una cifra citada. Cubrí, en orden y breve: (1) dónde está la caja "
        "hoy; (2) el rumbo proyectado de caja hacia el umbral mínimo de mayo-2027 "
        "(si la proyección lo cruza, en qué mes) y el runway; (3) un comentario "
        "breve sobre ventas/colocación (mix de modelos); (4) un comentario breve "
        "sobre el gasto del período. Citá CADA cifra con su token [[concepto]] — "
        "nunca escribas un número directamente. Si un dato no está disponible, "
        "omitilo con honestidad; nunca inventes una cifra."
    )


async def _seccion_caja(proy: dict | None) -> Seccion:
    disponible_hoy = await caja_calc.caja_hoy()
    rw = await runway.runway()
    cifras = [
        _cifra("Caja disponible hoy", disponible_hoy),
        _cifra("Runway (meses)", rw),
    ]
    if proy is not None:
        cifras.append(
            Cifra(
                etiqueta="Piso de caja proyectado",
                valor=money_str(Decimal(proy["piso_caja"])),
            )
        )
        quiebre = next(
            (m["mes"] for m in proy["meses"] if m["estado"] != "ok"), "nunca"
        )
        cifras.append(Cifra(etiqueta="Mes de quiebre del umbral", valor=quiebre))
    else:
        cifras.append(Cifra(etiqueta="Piso de caja proyectado", valor=_SIN_DATOS))
        cifras.append(Cifra(etiqueta="Mes de quiebre del umbral", valor=_SIN_DATOS))
    return Seccion(titulo="Caja y rumbo al umbral", cifras=cifras)


async def _seccion_ventas(periodo: str) -> Seccion:
    mix = await ratios.mix_modelos()
    cifras: list[Cifra] = []
    for r in mix:
        if r.disponible and r.concepto.startswith("mix_"):
            modelo = r.concepto.removeprefix("mix_").replace("_", " ").title()
            cifras.append(_cifra(f"Mix {modelo}", r))
    if not cifras:
        cifras.append(Cifra(etiqueta="Mix de modelos", valor=_SIN_DATOS))

    motos = await escenario.motos_para_evitar_umbral(
        naturaleza="gasto", monto=Decimal("0"), mes_inicio=periodo
    )
    cifras.append(
        _cifra(
            "Motos extra/mes para evitar el umbral",
            _buscar(motos, "unidades_extra"),
        )
    )
    return Seccion(titulo="Ventas / colocación", cifras=cifras)


async def _seccion_gasto() -> Seccion:
    comp = await ratios.composicion_gasto(ventana="cerrado")
    cifras = [_cifra("Gasto total (mes cerrado)", _buscar(comp, "gasto_total_comp"))]
    for suf, etiqueta in _GRUPOS_GASTO.items():
        cifras.append(_cifra(etiqueta, _buscar(comp, f"cop_{suf}")))

    rvp = await tendencias.real_vs_presupuesto(mes=None)
    cifras.append(
        _cifra("Gasto real (último mes cerrado)", _buscar(rvp, "gasto_real_mes"))
    )
    cifras.append(_cifra("Presupuesto aprobado", _buscar(rvp, "presupuesto_mes")))
    cifras.append(_cifra("Desvío vs. presupuesto", _buscar(rvp, "desvio_presupuesto")))
    return Seccion(titulo="Gasto y eficiencia", cifras=cifras)


async def _seccion_deuda() -> Seccion:
    iva_res = await iva.iva_cuatrimestre()
    if iva_res.disponible and iva_res.valor is not None:
        cifras = [
            Cifra(etiqueta="IVA próximo a pagar", valor=money_str(iva_res.valor)),
            Cifra(
                etiqueta="Fecha límite DIAN",
                valor=iva_res.evidencia.fecha_corte or _SIN_DATOS,
            ),
        ]
    else:
        cifras = [
            Cifra(etiqueta="IVA próximo a pagar", valor=_SIN_DATOS),
            Cifra(etiqueta="Fecha límite DIAN", valor=_SIN_DATOS),
        ]
    return Seccion(titulo="Deuda / obligaciones", cifras=cifras)


async def reunir_datos(periodo: str | None) -> DatosReporte:
    """Arma `DatosReporte`: la misma proyección vigente alimenta el rumbo, la
    sección de caja y (indirectamente, vía las tools) el resumen narrado — por eso
    tablas y narrativa siempre coinciden (spec §5.3)."""
    ahora = now_bogota()
    periodo = periodo or ahora.strftime("%Y-%m")

    try:
        proy = await proy_service.proyectar_vigente(
            escenario="base",
            mes_inicio=(ahora.year, ahora.month),
            horizonte_meses=None,
        )
    except ProyeccionError:
        proy = None

    rumbo: RumboSerie | None = None
    if proy is not None:
        rumbo = RumboSerie(
            meses=[m["mes"] for m in proy["meses"]],
            caja=[m["caja"] for m in proy["meses"]],
            caja_minima=proy["caja_minima"],
            caja_atencion=proy.get("caja_atencion"),
        )

    secciones = [
        await _seccion_caja(proy),
        await _seccion_ventas(periodo),
        await _seccion_gasto(),
        await _seccion_deuda(),
    ]

    resp = await servicio.consultar(
        _prompt_reporte(periodo), actor_id="reporte", cliente=crear_cliente()
    )

    return DatosReporte(
        periodo=periodo,
        resumen_ejecutivo=resp.texto,
        secciones=secciones,
        rumbo=rumbo,
    )
