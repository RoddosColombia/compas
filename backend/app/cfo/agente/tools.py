# backend/app/cfo/agente/tools.py
"""FABS · tools de SOLO LECTURA que el modelo puede invocar. Cada tool envuelve uno o
más conceptos de `app.cfo.calc` y devuelve su(s) ResultadoCFO completo(s) (incl.
disponible y evidencia). El dispatcher es cerrado: una tool desconocida es error,
nunca se inventa. Serialización para el modelo (`resultado_a_dict`): sin `valor` ni
`detalle` (inc3 Pieza A) — el modelo cita conceptos con [[token]] y el servicio
sustituye el valor concept-bound tras verificar. El `ResultadoCFO` completo (con
`valor`) sigue viajando por el loop sin serializar.

`ejecutar_tool` (inc4 T4) acepta una `entrada` opcional (parámetros de la tool, p. ej.
el escenario de un impacto) y SIEMPRE devuelve `list[ResultadoCFO]`: las calcs de un
solo concepto (las 3 de cero args de hoy) se normalizan a `[r]`; las calcs de varios
conceptos (escenarios, inc4 más adelante) ya devuelven su propia lista y pasan
intacta. Se decide por la firma de la calc registrada en DISPATCH: sin parámetros se
llama sin `entrada` (las 3 tools actuales); con parámetros se le pasa `entrada`.

Las dos tools de escenario (inc4 T7) — `impacto_escenario` y
`motos_para_evitar_umbral` — comparten `input_schema` y el mismo envoltorio de
parseo (`_kwargs_escenario`): `naturaleza` se valida contra {gasto,ingreso} ANTES de
llamar la calc (`impactos._delta_flujo` trata cualquier valor ≠ 'gasto' como
'ingreso' SIN avisar — dejar pasar un valor fuera del enum sería un escenario
mal-signado sin error visible) y `monto` se parsea de string a Decimal (regla 1),
rechazando no-string y no-finito (mismo patrón que
`escenarios_impacto/router.py:_a_embebido`, que arma el mismo `Ajuste`). Sus
envoltorios en DISPATCH toman UN `entrada: dict` posicional — para calzar con
`calc(entrada or {})` arriba —, nunca `**kwargs`.

`real_vs_presupuesto` (inc4 rebanada 3, T8) es la primera tool CON parámetro pero
SIN nada que validar: `mes` es un string 'YYYY-MM' opcional sin enum ni Decimal
detrás (a diferencia de `_kwargs_tendencia`/`_kwargs_palanca`/`_kwargs_escenario`),
así que su envoltorio (`_real_vs_presupuesto`) solo extrae `entrada.get("mes")`
(None si se omite) y deja que `tendencias.real_vs_presupuesto` resuelva el default
del mes cerrado más reciente.

`composicion_gasto` (inc4 rebanada 4, sub-4a) vuelve al molde de
`_kwargs_tendencia`: un enum a validar (`ventana` ∈ {cerrado,acumulado,curso}),
ni Decimal ni fecha libre. Su envoltorio (`_kwargs_composicion_gasto`) rechaza
una ventana fuera del enum ANTES de llamar `ratios.composicion_gasto`, que
devuelve varios conceptos por grupo (`cop_<grupo>`/`pct_<grupo>`) más
`gasto_total_comp` -- el `%` de cada `pct_<grupo>` lo computa esa calc, nunca
el modelo; el modelo solo cita el token (ver `agente/prompt.py` y
`agente/verificador.py`)."""

import inspect
from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation

from app.cfo.calc import caja, escenario, iva, palanca, ratios, runway, tendencias
from app.cfo.calc.evidencia import ResultadoCFO

CalcSinArgs = Callable[[], Awaitable[ResultadoCFO]]
CalcConArgs = Callable[[dict], Awaitable[list[ResultadoCFO]]]

_NATURALEZAS = {"gasto", "ingreso"}
_PALANCAS = {"plazo_semanas", "cuota_inicial", "cuota_semanal"}
_MODELOS = {"Raider", "Apache", "Sport", "todos"}
_METRICAS_TENDENCIA = {"ingreso", "gasto", "caja"}
_VENTANAS_COMPOSICION = {"cerrado", "acumulado", "curso"}


def _kwargs_escenario(entrada: dict) -> dict:
    """Parsea/valida la `entrada` cruda del modelo (todo string, regla 1) a los
    kwargs keyword-only de `escenario.impacto_escenario`/`motos_para_evitar_umbral`.

    `naturaleza`: se exige ∈ {gasto,ingreso} ANTES de llegar a la calc — ver nota
    del módulo (arriba) sobre `impactos._delta_flujo`.
    `monto`: string→Decimal; rechaza no-string (regla 1: nunca aceptar un número
    crudo del JSON) y no-finito (Infinity/NaN envenenarían la caja, P1-8)."""
    naturaleza = entrada["naturaleza"]
    if naturaleza not in _NATURALEZAS:
        raise ValueError(
            "naturaleza debe ser 'gasto' o 'ingreso' (cualquier otro valor lo "
            f"trataría impactos._delta_flujo como 'ingreso' sin error); "
            f"recibido: {naturaleza!r}"
        )
    monto_raw = entrada["monto"]
    if not isinstance(monto_raw, str):
        raise ValueError(
            "monto debe ser string COP (regla 1: dinero nunca cruza como número "
            f"crudo), recibido: {type(monto_raw).__name__}"
        )
    try:
        monto = Decimal(monto_raw)
        if not monto.is_finite():
            raise InvalidOperation
    except InvalidOperation as e:
        raise ValueError(f"monto no es un decimal válido: {monto_raw!r}") from e
    return {
        "naturaleza": naturaleza,
        "monto": monto,
        "mes_inicio": entrada["mes_inicio"],
        "mes_fin": entrada.get("mes_fin"),
    }


async def _impacto_escenario(entrada: dict) -> list[ResultadoCFO]:
    return await escenario.impacto_escenario(**_kwargs_escenario(entrada))


async def _motos_para_evitar_umbral(entrada: dict) -> list[ResultadoCFO]:
    return await escenario.motos_para_evitar_umbral(**_kwargs_escenario(entrada))


def _kwargs_palanca(entrada: dict) -> dict:
    """Parsea/valida la `entrada` cruda del modelo a los kwargs keyword-only de
    `palanca.impacto_palanca`.

    `palanca`: se exige ∈ {plazo_semanas,cuota_inicial,cuota_semanal} — un valor
    fuera del enum se rechaza aquí en vez de dejar que llegue a la calc.
    `modelo`: se exige ∈ {Raider,Apache,Sport,todos}, default "todos" cuando se
    omite.
    `nuevo_valor`: string→Decimal (regla 1: nunca aceptar un número crudo del
    JSON); rechaza no-string y no-finito (mismo patrón que `_kwargs_escenario`)."""
    palanca_nombre = entrada["palanca"]
    if palanca_nombre not in _PALANCAS:
        raise ValueError(
            "palanca debe ser una de "
            f"{sorted(_PALANCAS)!r}; recibido: {palanca_nombre!r}"
        )
    modelo = entrada.get("modelo", "todos")
    if modelo not in _MODELOS:
        raise ValueError(
            f"modelo debe ser una de {sorted(_MODELOS)!r}; recibido: {modelo!r}"
        )
    nuevo_valor_raw = entrada["nuevo_valor"]
    if not isinstance(nuevo_valor_raw, str):
        raise ValueError(
            "nuevo_valor debe ser string (regla 1: dinero/cifras nunca cruzan "
            f"como número crudo), recibido: {type(nuevo_valor_raw).__name__}"
        )
    try:
        nuevo_valor = Decimal(nuevo_valor_raw)
        if not nuevo_valor.is_finite():
            raise InvalidOperation
    except InvalidOperation as e:
        raise ValueError(
            f"nuevo_valor no es un decimal válido: {nuevo_valor_raw!r}"
        ) from e
    return {"palanca": palanca_nombre, "nuevo_valor": nuevo_valor, "modelo": modelo}


async def _simular_palanca(entrada: dict) -> list[ResultadoCFO]:
    return await palanca.impacto_palanca(**_kwargs_palanca(entrada))


def _kwargs_tendencia(entrada: dict) -> dict:
    """Parsea/valida la `entrada` cruda del modelo a los kwargs keyword-only de
    `tendencias.tendencia_real`.

    `metrica`: se exige ∈ {ingreso,gasto,caja} — un valor fuera del enum se
    rechaza aquí, antes de llegar a la calc (mismo molde que
    `_kwargs_palanca`/`_kwargs_escenario`)."""
    metrica = entrada["metrica"]
    if metrica not in _METRICAS_TENDENCIA:
        raise ValueError(
            f"metrica debe ser una de {sorted(_METRICAS_TENDENCIA)!r}; "
            f"recibido: {metrica!r}"
        )
    return {"metrica": metrica}


async def _tendencia_real(entrada: dict) -> list[ResultadoCFO]:
    return await tendencias.tendencia_real(**_kwargs_tendencia(entrada))


async def _real_vs_presupuesto(entrada: dict) -> list[ResultadoCFO]:
    """`mes` es OPCIONAL (string 'YYYY-MM' o ausente) — a diferencia de
    `_kwargs_tendencia`/`_kwargs_palanca`/`_kwargs_escenario`, no hay enum ni
    Decimal que validar aquí: se extrae tal cual y se deja que
    `tendencias.real_vs_presupuesto` (que a su vez delega en
    `presupuesto.service.real_vs_presupuesto_mes`) resuelva el default (mes
    CERRADO más reciente con presupuesto aprobado) cuando se omite."""
    return await tendencias.real_vs_presupuesto(mes=entrada.get("mes"))


def _kwargs_composicion_gasto(entrada: dict) -> dict:
    """Parsea/valida la `entrada` cruda del modelo a los kwargs keyword-only de
    `ratios.composicion_gasto`.

    `ventana`: se exige ∈ {cerrado,acumulado,curso} -- un valor fuera del enum
    se rechaza aquí, antes de llegar a la calc (mismo molde que
    `_kwargs_tendencia`/`_kwargs_palanca`/`_kwargs_escenario`)."""
    ventana = entrada["ventana"]
    if ventana not in _VENTANAS_COMPOSICION:
        raise ValueError(
            f"ventana debe ser una de {sorted(_VENTANAS_COMPOSICION)!r}; "
            f"recibido: {ventana!r}"
        )
    return {"ventana": ventana}


async def _composicion_gasto(entrada: dict) -> list[ResultadoCFO]:
    return await ratios.composicion_gasto(**_kwargs_composicion_gasto(entrada))


DISPATCH: dict[str, CalcSinArgs | CalcConArgs] = {
    "caja_disponible_hoy": caja.caja_hoy,
    "runway_meses": runway.runway,
    "iva_del_cuatrimestre": iva.iva_cuatrimestre,
    "impacto_escenario": _impacto_escenario,
    "motos_para_evitar_umbral": _motos_para_evitar_umbral,
    "simular_palanca": _simular_palanca,
    "tendencia_real": _tendencia_real,
    "rumbo_caja": tendencias.rumbo_caja,
    "real_vs_presupuesto": _real_vs_presupuesto,
    "composicion_gasto": _composicion_gasto,
}

TOOLS_SCHEMA: list[dict] = [
    {
        "name": "caja_disponible_hoy",
        "description": (
            "Caja disponible HOY en COP: último saldo real de la serie diaria de "
            "COMPAS, con su fecha de corte. Si no hay datos, disponible=false."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "runway_meses",
        "description": (
            "Meses de caja restantes al ritmo de quema actual (KPI runway de la "
            "proyección vigente). Sin quema neta o sin configuración, disponible=false."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "iva_del_cuatrimestre",
        "description": (
            "IVA neto a pagar del cuatrimestre fiscal vigente en COP, con la fecha "
            "límite DIAN. Solo válido con periodicidad cuatrimestral; si no, "
            "disponible=false."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "impacto_escenario",
        "description": (
            "Compara la caja proyectada SIN vs. CON un gasto o ingreso hipotético "
            "recurrente desde un mes (p. ej. '¿qué pasa si el arriendo sube $3M "
            "desde septiembre?'). Devuelve piso_sin (piso de caja base), piso_con "
            "(piso con el ajuste aplicado; su evidencia trae el mes de quiebre si "
            "la caja llega a cruzar el umbral) e impacto_mensual (el monto mensual "
            "del ajuste, ecoado). Usa esta tool para preguntas '¿qué pasaría si...?' "
            "sobre un gasto/ingreso adicional. Es simulación de solo lectura: nunca "
            "escribe nada."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "naturaleza": {
                    "type": "string",
                    "enum": ["gasto", "ingreso"],
                    "description": (
                        "Tipo del ajuste: 'gasto' (sube el gasto, la caja baja) o "
                        "'ingreso' (sube el ingreso, la caja sube)."
                    ),
                },
                "monto": {
                    "type": "string",
                    "description": (
                        "Monto mensual del ajuste en COP, como string (p. ej. "
                        "'20000000' para $20.000.000)."
                    ),
                },
                "mes_inicio": {
                    "type": "string",
                    "description": (
                        "Mes en que arranca el ajuste, formato 'YYYY-MM' "
                        "(p. ej. '2026-09')."
                    ),
                },
                "mes_fin": {
                    "type": "string",
                    "description": (
                        "Mes en que termina el ajuste (inclusive), 'YYYY-MM'. Si "
                        "se omite, el ajuste corre hasta el final del horizonte "
                        "proyectado."
                    ),
                },
            },
            "required": ["naturaleza", "monto", "mes_inicio"],
            "additionalProperties": False,
        },
    },
    {
        "name": "motos_para_evitar_umbral",
        "description": (
            "Con el MISMO escenario hipotético de impacto_escenario (gasto/ingreso "
            "adicional desde un mes) ya aplicado encima, calcula cuántas motos "
            "EXTRA por mes hacen falta vender desde hoy para que el piso de caja "
            "proyectado NO cruce el umbral mínimo configurado. Devuelve "
            "unidades_extra (motos/mes adicionales) y piso_con_unidades (el piso "
            "de caja COP resultante con esas unidades). disponible=false si el "
            "solver no encuentra solución dentro de su tope — nunca inventa un "
            "número. Usa esta tool para preguntas '¿cuántas motos más necesito "
            "vender para cubrir...?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "naturaleza": {
                    "type": "string",
                    "enum": ["gasto", "ingreso"],
                    "description": (
                        "Tipo del ajuste hipotético que hay que compensar con "
                        "motos extra: 'gasto' o 'ingreso'."
                    ),
                },
                "monto": {
                    "type": "string",
                    "description": (
                        "Monto mensual del ajuste en COP, como string (p. ej. "
                        "'20000000')."
                    ),
                },
                "mes_inicio": {
                    "type": "string",
                    "description": "Mes en que arranca el ajuste, formato 'YYYY-MM'.",
                },
                "mes_fin": {
                    "type": "string",
                    "description": (
                        "Mes en que termina el ajuste (inclusive), 'YYYY-MM'. Si "
                        "se omite, corre hasta el final del horizonte."
                    ),
                },
            },
            "required": ["naturaleza", "monto", "mes_inicio"],
            "additionalProperties": False,
        },
    },
    {
        "name": "simular_palanca",
        "description": (
            "Compara el piso de caja proyectado SIN vs. CON un cambio en una "
            "palanca de crédito de motos: plazo (semanas), cuota inicial o cuota "
            "semanal (p. ej. '¿qué pasa si el plazo pasa a 78 semanas?' o '¿y si "
            "subo la cuota inicial a $500.000?'). Extrae la palanca, el nuevo "
            "valor y el modelo afectado (Raider/Apache/Sport) o 'todos' si no se "
            "especifica un modelo. Devuelve piso_sin_palanca, piso_con_palanca "
            "(con el mes de quiebre si la caja llega a cruzar el umbral) e "
            "impacto_palanca (piso_con_palanca - piso_sin_palanca). "
            "disponible=false si no hay configuración de proyección vigente. Es "
            "simulación de solo lectura: nunca escribe nada."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "palanca": {
                    "type": "string",
                    "enum": ["plazo_semanas", "cuota_inicial", "cuota_semanal"],
                    "description": (
                        "Cuál palanca de crédito cambia: 'plazo_semanas' (plazo "
                        "del crédito en semanas), 'cuota_inicial' (cuota inicial "
                        "en COP) o 'cuota_semanal' (cuota semanal en COP)."
                    ),
                },
                "nuevo_valor": {
                    "type": "string",
                    "description": (
                        "Nuevo valor de la palanca, como string: número de "
                        "semanas si palanca='plazo_semanas' (p. ej. '78'), o "
                        "monto en COP si palanca='cuota_inicial'/'cuota_semanal' "
                        "(p. ej. '500000')."
                    ),
                },
                "modelo": {
                    "type": "string",
                    "enum": ["Raider", "Apache", "Sport", "todos"],
                    "description": (
                        "Modelo de moto afectado por el cambio. Si se omite, "
                        "aplica a 'todos' los modelos."
                    ),
                },
            },
            "required": ["palanca", "nuevo_valor"],
            "additionalProperties": False,
        },
    },
    {
        "name": "tendencia_real",
        "description": (
            "Cómo viene el ingreso, el gasto o la caja REAL vs los últimos "
            "meses (p. ej. '¿cómo viene el gasto vs el mes pasado?'). Devuelve "
            "hasta TRES meses reales de la métrica pedida (metrica_real_m0 el "
            "más reciente, m1 y m2 los anteriores) y delta_metrica_real (la "
            "diferencia entre los dos últimos meses, con la dirección "
            "sube/baja/estable en su evidencia). disponible=false si no hay "
            "suficiente historia de actuals. Es de solo lectura: nunca escribe "
            "nada."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metrica": {
                    "type": "string",
                    "enum": ["ingreso", "gasto", "caja"],
                    "description": (
                        "Qué métrica real consultar: 'ingreso', 'gasto' o 'caja'."
                    ),
                },
            },
            "required": ["metrica"],
            "additionalProperties": False,
        },
    },
    {
        "name": "rumbo_caja",
        "description": (
            "¿Vamos en rumbo? Compara la caja real de los últimos dos meses "
            "con hacia dónde apunta la proyección vigente (p. ej. '¿voy en "
            "rumbo?' o '¿hacia dónde va la caja?'). Devuelve caja_real_ult y "
            "caja_real_previo (los dos últimos meses de caja real), "
            "delta_caja_rumbo (la diferencia entre ambos, con la dirección "
            "sube/baja/estable en su evidencia) y piso_proyectado (el piso de "
            "caja de la proyección vigente, con el mes de quiebre del umbral "
            "en su evidencia si lo cruza). Sin configuración o sin historia de "
            "actuals, disponible=false. Es de solo lectura: nunca escribe nada."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "real_vs_presupuesto",
        "description": (
            "¿Gasté más o menos de lo presupuestado este mes? Compara el "
            "gasto REAL de un mes cerrado con su presupuesto aprobado (p. "
            "ej. '¿gasté más de lo presupuestado en julio?'). Devuelve TRES "
            "conceptos: gasto_real_mes, presupuesto_mes y "
            "desvio_presupuesto (gasto_real_mes - presupuesto_mes; su "
            "evidencia trae la dirección sobre/bajo/en-linea). Sin mes "
            "cerrado con presupuesto aprobado, disponible=false. Es de solo "
            "lectura: nunca escribe nada."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mes": {
                    "type": "string",
                    "description": (
                        "Mes 'YYYY-MM' (opcional; por defecto el último mes cerrado)."
                    ),
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "composicion_gasto",
        "description": (
            "¿Qué % de mi gasto es nómina/deuda/operación? Devuelve la "
            "composición del gasto REAL total por grupo (costo de producto, "
            "operación, nómina, deudas y obligaciones, otros) para una "
            "ventana: 'cerrado' (último mes cerrado), 'acumulado' (año "
            "corrido) o 'curso' (mes en curso). Devuelve gasto_total_comp "
            "(el gasto total en COP) y, por cada grupo, DOS conceptos: "
            "cop_<grupo> (su monto en COP) y pct_<grupo> (su % de "
            "participación, YA CALCULADO por COMPAS). Sin gasto en la "
            "ventana, disponible=false. Es de solo lectura: nunca escribe "
            "nada."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ventana": {
                    "type": "string",
                    "enum": ["cerrado", "acumulado", "curso"],
                    "description": (
                        "Qué ventana de meses componer: 'cerrado' (último mes "
                        "cerrado), 'acumulado' (año corrido) o 'curso' (mes en "
                        "curso)."
                    ),
                },
            },
            "required": ["ventana"],
            "additionalProperties": False,
        },
    },
]


async def ejecutar_tool(nombre: str, entrada: dict | None = None) -> list[ResultadoCFO]:
    # Dispatcher cerrado: `nombre` desconocido → KeyError, jamás se inventa una tool.
    calc = DISPATCH[nombre]
    if inspect.signature(calc).parameters:
        resultado = await calc(entrada or {})
    else:
        resultado = await calc()
    # Normaliza a lista: las calcs de un solo concepto (hoy: las 3 de cero args)
    # devuelven UN ResultadoCFO; las de varios conceptos ya devuelven su lista.
    return resultado if isinstance(resultado, list) else [resultado]


def resultado_a_dict(r: ResultadoCFO) -> dict:
    # El modelo NO ve valores: cita conceptos con [[token]] y el servicio sustituye el
    # valor concept-bound tras verificar (inc3 Pieza A). Sin `valor` no puede fabricar,
    # mal-etiquetar ni calcular.
    return {
        "concepto": r.concepto,
        "disponible": r.disponible,
        "unidad": r.unidad,
        "evidencia": {
            "fuente": r.evidencia.fuente,
            "fecha_corte": r.evidencia.fecha_corte,
            "ref": r.evidencia.ref,
        },
    }
