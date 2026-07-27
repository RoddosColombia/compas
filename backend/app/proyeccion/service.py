# backend/app/proyeccion/service.py
"""Servicio de proyección (COCK-01) — orquesta el motor compute-only.

Carga los parámetros VIGENTES + el catálogo de modelos ACTIVOS, arma un
`ParametrosMotor`, aplica el escenario (presets de mora/recuperación) y llama a
`motor.proyectar()`. Serializa a JSON con montos como string (regla 1). No escribe
estado: es una lectura pura sobre la configuración vigente."""

from dataclasses import replace
from decimal import Decimal

from app.cartera_previa import service as cartera_previa_service
from app.cierre.service import _caja_libro, _rubro_ajuste
from app.core.money import money_str
from app.domain.configuracion import ClaveConfig, Configuracion
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.modelo_moto import ModeloMoto
from app.domain.parametros_proyeccion import (
    ParametrosProyeccion,
    costo_alistamiento_total,
)
from app.domain.transaccion import Transaccion
from app.facturas import service as facturas_service
from app.iva.liquidacion import liquidar, plan_fondo_provision, programar_egresos_iva
from app.modelos_moto import service as modelos_service
from app.parametros_proyeccion import service as parametros_service
from app.proyeccion.motor import (
    PRESETS_ESCENARIO,
    ModeloProyeccion,
    ParametrosMotor,
    ResultadoProyeccion,
    _meses_del_horizonte,
    cartera_activa_mensual,
    cartera_por_anada_mensual,
    colocacion_mensual,
    proyectar,
)

HORIZONTE_MAX = 180  # 15 años (tope de infraestructura)


class ProyeccionError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


def _modelo_a_motor(m: ModeloMoto) -> ModeloProyeccion:
    return ModeloProyeccion(
        nombre=m.nombre,
        cuota_semanal=m.cuota_semanal,
        cuota_inicial=m.cuota_inicial,
        plazo_semanas=m.plazo_semanas,
        mix=m.participacion_mix,
        costo_moto=m.costo_auteco,
    )


def _armar_parametros(
    params: ParametrosProyeccion,
    modelos: list[ModeloMoto],
    escenario: str,
    mes_inicio: tuple[int, int],
    horizonte_meses: int,
    recaudo_previo: dict[int, object] | None = None,
    activos_previos: dict[int, int] | None = None,
    iva_egreso_por_mes: dict[int, object] | None = None,
    caja_inicial_override: object | None = None,
) -> ParametrosMotor:
    pct_mora, pct_recuperacion = params.pct_mora, params.pct_recuperacion
    # el escenario (preset) sobrescribe mora/recuperación; el resto queda de params.
    if escenario in PRESETS_ESCENARIO:
        pct_mora = PRESETS_ESCENARIO[escenario]["pct_mora"]
        pct_recuperacion = PRESETS_ESCENARIO[escenario]["pct_recuperacion"]
    return ParametrosMotor(
        mes_inicio=mes_inicio,
        horizonte_meses=horizonte_meses,
        modelos=[_modelo_a_motor(m) for m in modelos],
        motos_base=params.motos_base,
        crec_pct_mensual=params.crec_pct_mensual,
        rampa=None,
        adelanto_auteco=params.adelanto_auteco,
        plazo_auteco_dias=params.plazo_auteco_dias,
        base_auteco_dias=params.base_auteco_dias,
        tasa_auteco=params.tasa_auteco,
        gastos_fijos=params.gastos_fijos,
        gps_moto=params.gps_moto,
        # CR-002: el motor recibe UN solo Decimal = Σ de los componentes ACTIVOS
        # (suma server-side; sin componentes manda el costo plano — compat).
        costo_moto_nueva=costo_alistamiento_total(
            params.componentes_alistamiento, params.costo_moto_nueva
        ),
        deuda=params.deuda,
        tasa_deuda=params.tasa_deuda,
        mes_inicio_deuda=params.mes_inicio_deuda,
        meses_deuda=params.meses_deuda,
        pct_mora=pct_mora,
        pct_recuperacion=pct_recuperacion,
        pct_default=params.pct_default,
        pct_provision=params.pct_provision,
        overrides_mora=None,
        overrides_default=None,
        caja_inicial=(
            params.caja_inicial
            if caja_inicial_override is None
            else caja_inicial_override
        ),
        caja_minima=params.caja_minima,
        recaudo_previo_por_semana=recaudo_previo,
        activos_previos_por_semana=activos_previos,
        iva_egreso_por_mes=iva_egreso_por_mes,
    )


def _serializar(
    r: ResultadoProyeccion, escenario: str, caja_minima, fondo: list
) -> dict:
    meses_ym = [f.mes for f in r.meses]
    return {
        "escenario": escenario,
        # Fondo de provisión de IVA (P1.4): serie informativa mes a mes (NO es flujo del
        # motor; el egreso real ya está en `meses[].iva` en la fecha DIAN).
        "fondo_provision": [
            {
                "mes": meses_ym[f.mes_idx],
                "reserva": money_str(f.reserva),
                "pago": money_str(f.pago),
                "saldo": money_str(f.saldo),
            }
            for f in fondo
            if f.mes_idx < len(meses_ym)
        ],
        "caja_minima": money_str(caja_minima),  # el umbral (para la curva del front)
        "piso_caja": money_str(r.piso_caja),
        "mes_mas_ajustado": r.mes_mas_ajustado,
        "meses_bajo_minimo": r.meses_bajo_minimo,
        "caja_final": money_str(r.caja_final),
        "capital_requerido": money_str(r.capital_requerido),
        "runway_meses": (
            money_str(r.runway_meses) if r.runway_meses is not None else None
        ),
        "meses": [
            {
                "mes": f.mes,
                "motos": f.motos,
                "cartera": f.cartera,
                "recaudo_credito": money_str(f.recaudo_credito),
                "cuotas_iniciales": money_str(f.cuotas_iniciales),
                "ingreso_bruto": money_str(f.ingreso_bruto),
                "neto": money_str(f.neto),
                "provision": money_str(f.provision),
                "gastos_fijos": money_str(f.gastos_fijos),
                "gps": money_str(f.gps),
                "costo_nueva": money_str(f.costo_nueva),
                "adelanto": money_str(f.adelanto),
                "pago_inventario": money_str(f.pago_inventario),
                "fondeo": money_str(f.fondeo),
                "int_deuda": money_str(f.int_deuda),
                "iva": money_str(f.iva),
                "egresos": money_str(f.egresos),
                "flujo": money_str(f.flujo),
                "caja": money_str(f.caja),
                "estado": f.estado,
            }
            for f in r.meses
        ],
    }


async def _calendario_dian() -> dict:
    """Última vigencia de la clave CONFIGURACION `CALENDARIO_DIAN` (fechas reales de
    pago del IVA). Ausente → {} (la proyección simplemente no resta IVA; no se inventa
    ninguna fecha)."""
    cfg = (
        await Configuracion.find(Configuracion.clave == ClaveConfig.CALENDARIO_DIAN)
        .sort(-Configuracion.vigente_desde)
        .limit(1)
        .to_list()
    )
    return cfg[0].valor_json if cfg and cfg[0].valor_json else {}


async def _iva_plan(
    mes_inicio: tuple[int, int], horizonte: int
) -> tuple[dict[int, object], list]:
    """Puente C11↔C7: liquida las facturas cargadas y devuelve (egreso_por_mes, fondo).
    `egreso_por_mes` = IVA neto de cada período en el índice de su fecha DIAN real
    (PR-2b, entra al motor). `fondo` = plan de provisión mes a mes (P1.4, informativo,
    NO entra al flujo del motor). Sin facturas → ({}, [])."""
    facturas = await facturas_service.obtener_facturas_iva()
    if not facturas:
        return {}, []
    periodicidad = await facturas_service.obtener_periodicidad()
    calendario = await _calendario_dian()
    liquidaciones = liquidar(facturas, periodicidad)
    egreso = programar_egresos_iva(
        liquidaciones,
        calendario,
        mes_inicio=mes_inicio,
        horizonte_meses=horizonte,
        periodicidad=periodicidad,
    )
    fondo = plan_fondo_provision(
        liquidaciones,
        calendario,
        mes_inicio=mes_inicio,
        horizonte_meses=horizonte,
        periodicidad=periodicidad,
    )
    return egreso, fondo


async def _proyectar_con(
    params: ParametrosProyeccion,
    modelos: list[ModeloMoto],
    *,
    escenario: str,
    mes_inicio: tuple[int, int],
    horizonte_meses: int | None,
    caja_inicial_override: object | None = None,
) -> dict:
    """La tubería completa (cartera previa + IVA + motor) sobre un set de parámetros
    DADO — compartida por la proyección vigente y el preview de C3 (misma tubería =
    paridad al peso garantizada por test)."""
    horizonte = horizonte_meses or params.horizonte_meses
    if horizonte < 1 or horizonte > HORIZONTE_MAX:
        raise ProyeccionError(
            f"horizonte_meses debe estar en [1, {HORIZONTE_MAX}]", 422
        )
    recaudo_previo, activos_previos = await cartera_previa_service.obtener_series()
    iva_egreso, fondo = await _iva_plan(mes_inicio, horizonte)
    pm = _armar_parametros(
        params,
        modelos,
        escenario,
        mes_inicio,
        horizonte,
        recaudo_previo,
        activos_previos,
        iva_egreso,
        caja_inicial_override,
    )
    return _serializar(proyectar(pm), escenario, params.caja_minima, fondo)


async def proyectar_vigente(
    *,
    escenario: str,
    mes_inicio: tuple[int, int],
    horizonte_meses: int | None,
    caja_inicial_override: object | None = None,
) -> dict:
    """Proyección con los parámetros/modelos vigentes. Falla-cerrado si falta config
    (no se inventan cifras): 409 si no hay parámetros o no hay modelos activos.
    `caja_inicial_override` re-ancla la caja inicial (rolling forecast, COCK-09)."""
    params, modelos = await _cargar_config_vigente()
    return await _proyectar_con(
        params,
        modelos,
        escenario=escenario,
        mes_inicio=mes_inicio,
        horizonte_meses=horizonte_meses,
        caja_inicial_override=caja_inicial_override,
    )


async def proyectar_preview(
    *,
    campos: dict,
    escenario: str,
    mes_inicio: tuple[int, int],
    horizonte_meses: int | None,
) -> dict:
    """C3 §5.1 — preview COMPUTE-ONLY con un set de parámetros PROPUESTO: misma
    tubería que la proyección vigente (paridad al peso por test), sin escribir NADA.
    Los modelos siguen siendo los vigentes (el preview cubre los parámetros)."""
    modelos = await modelos_service.listar_modelos(activo=True)
    if not modelos:
        raise ProyeccionError("no hay modelos de moto activos", 409)
    # Documento EN MEMORIA, jamás insertado: solo transporta los campos al motor.
    params = ParametrosProyeccion(vigente_desde="1900-01-01", **campos)
    return await _proyectar_con(
        params,
        modelos,
        escenario=escenario,
        mes_inicio=mes_inicio,
        horizonte_meses=horizonte_meses,
    )


async def _cargar_config_vigente():
    """Carga params + modelos activos (fail-closed 409). Compartido por las vistas que
    parten del motor vigente."""
    params = await parametros_service.obtener_vigente()
    if params is None:
        raise ProyeccionError(
            "no hay parámetros de proyección configurados (cárguelos primero)", 409
        )
    modelos = await modelos_service.listar_modelos(activo=True)
    if not modelos:
        raise ProyeccionError("no hay modelos de moto activos", 409)
    return params, modelos


async def operacion_vigente(
    *, escenario: str, mes_inicio: tuple[int, int], horizonte_meses: int | None
) -> dict:
    """DASH-01 — agregación OPERATIVA (Dashboards): colocación mensual y cartera activa
    DESGLOSADA por AÑADA (cohorte de colocación), computadas por el motor sobre los
    parámetros/modelos vigentes. Determinista (no proyecta mora por tramo: eso exige
    aging real o supuestos aparte). Fail-closed igual que `/proyeccion`."""
    params, modelos = await _cargar_config_vigente()
    horizonte = horizonte_meses or params.horizonte_meses
    if horizonte < 1 or horizonte > HORIZONTE_MAX:
        raise ProyeccionError(
            f"horizonte_meses debe estar en [1, {HORIZONTE_MAX}]", 422
        )
    modelos_m = [_modelo_a_motor(m) for m in modelos]
    _, activos_previos = await cartera_previa_service.obtener_series()

    colocacion = colocacion_mensual(
        params.motos_base, params.crec_pct_mensual, horizonte, None
    )
    cartera = cartera_activa_mensual(
        colocacion, modelos_m, mes_inicio, activos_previos_por_semana=activos_previos
    )
    por_anada = cartera_por_anada_mensual(
        colocacion, modelos_m, mes_inicio, activos_previos_por_semana=activos_previos
    )
    ym = _meses_del_horizonte(mes_inicio, horizonte)
    etiquetas = [f"{y:04d}-{m:02d}" for (y, m) in ym]

    def _label(anada: int) -> str:
        return "previa" if anada < 0 else etiquetas[anada]

    return {
        "escenario": escenario,
        "meses": [
            {
                "mes": etiquetas[i],
                "colocacion": colocacion[i],
                "cartera": cartera[i],
                "por_anada": [
                    {"anada": _label(a), "activos": n}
                    for a, n in sorted(por_anada[i].items())
                ],
            }
            for i in range(horizonte)
        ],
    }


# ── C3 §5.2 — sensibilidad del umbral (tornado) ──────────────────────────────
# Variaciones NATURALES por variable, aplicadas al ParametrosMotor YA armado
# (post-preset de escenario: la mora del preset sobrescribe la de params, así que
# mutar los params crudos sería un placebo — se muta el motor directamente).

SENSIBILIDAD_HORIZONTE = 60  # el umbral del norte (may-2027) siempre queda dentro

_CERO = Decimal("0")


def _variaciones(pm: ParametrosMotor) -> list[dict]:
    """[{variable, etiqueta, variacion, mas, menos}] — mas/menos son ParametrosMotor
    mutados con dataclasses.replace (frozen → copia inmutable, motor intacto)."""

    def con(**c) -> ParametrosMotor:
        return replace(pm, **c)

    def cuotas(factor: Decimal) -> ParametrosMotor:
        return replace(
            pm,
            modelos=[
                replace(m, cuota_semanal=m.cuota_semanal * factor)
                for m in pm.modelos
            ],
        )

    return [
        {
            "variable": "motos_base",
            "etiqueta": "Colocación base",
            "variacion": "±10 %",
            "mas": con(motos_base=round(pm.motos_base * 1.1)),
            "menos": con(motos_base=round(pm.motos_base * 0.9)),
        },
        {
            "variable": "crec_pct_mensual",
            "etiqueta": "Crecimiento mensual",
            "variacion": "±1 punto",
            "mas": con(crec_pct_mensual=pm.crec_pct_mensual + Decimal("0.01")),
            "menos": con(
                crec_pct_mensual=max(
                    _CERO, pm.crec_pct_mensual - Decimal("0.01")
                )
            ),
        },
        {
            "variable": "cuota_semanal",
            "etiqueta": "Cuota semanal (todos los modelos)",
            "variacion": "±5 %",
            "mas": cuotas(Decimal("1.05")),
            "menos": cuotas(Decimal("0.95")),
        },
        {
            "variable": "gastos_fijos",
            "etiqueta": "Gastos fijos",
            "variacion": "±10 %",
            "mas": con(gastos_fijos=pm.gastos_fijos * Decimal("1.1")),
            "menos": con(gastos_fijos=pm.gastos_fijos * Decimal("0.9")),
        },
        {
            "variable": "pct_mora",
            "etiqueta": "% de mora",
            "variacion": "±1 punto",
            "mas": con(pct_mora=pm.pct_mora + Decimal("0.01")),
            "menos": con(pct_mora=max(_CERO, pm.pct_mora - Decimal("0.01"))),
        },
        {
            "variable": "plazo_auteco_dias",
            "etiqueta": "Plazo Auteco",
            "variacion": "±30 días",
            "mas": con(plazo_auteco_dias=pm.plazo_auteco_dias + 30),
            "menos": con(plazo_auteco_dias=max(0, pm.plazo_auteco_dias - 30)),
        },
        {
            "variable": "costo_alistamiento",
            "etiqueta": "Costos de alistamiento",
            "variacion": "±$ 100 mil/moto",
            "mas": con(costo_moto_nueva=pm.costo_moto_nueva + Decimal("100000")),
            "menos": con(
                costo_moto_nueva=max(
                    _CERO, pm.costo_moto_nueva - Decimal("100000")
                )
            ),
        },
    ]


# Cache por vigencia (recalcular solo cuando cambian los supuestos). Un solo
# proceso web (Render) → dict de módulo basta; el fingerprint incluye los modelos.
_sensibilidad_cache: dict[tuple, dict] = {}


def _fingerprint(params: ParametrosProyeccion, modelos: list[ModeloMoto]) -> tuple:
    # Los VALORES, no la identidad de la fila (QA C3): el guardado hace upsert
    # por vigente_desde — dos ediciones el mismo día comparten id/fecha/autor y
    # un fingerprint de identidad serviría el tornado de la versión anterior.
    campos = tuple(
        sorted((k, str(v)) for k, v in params.model_dump(exclude={"id"}).items())
    )
    return (
        campos,
        tuple(
            (
                m.nombre,
                str(m.cuota_semanal),
                str(m.cuota_inicial),
                m.plazo_semanas,
                str(m.participacion_mix),
                str(m.costo_auteco),
            )
            for m in modelos
        ),
    )


async def sensibilidad_vigente(
    *, escenario: str, mes_inicio: tuple[int, int]
) -> dict:
    """El tornado '¿qué mueve mi umbral?': 7 variables × ± → 14 corridas del motor
    puro a 60 meses sobre el set vigente. Compute-only; cache por vigencia."""
    params, modelos = await _cargar_config_vigente()
    clave = (_fingerprint(params, modelos), escenario, mes_inicio)
    if clave in _sensibilidad_cache:
        return _sensibilidad_cache[clave]

    recaudo_previo, activos_previos = await cartera_previa_service.obtener_series()
    iva_egreso, _fondo = await _iva_plan(mes_inicio, SENSIBILIDAD_HORIZONTE)
    pm = _armar_parametros(
        params,
        modelos,
        escenario,
        mes_inicio,
        SENSIBILIDAD_HORIZONTE,
        recaudo_previo,
        activos_previos,
        iva_egreso,
    )
    piso_base = proyectar(pm).piso_caja

    variables = []
    for v in _variaciones(pm):
        variables.append(
            {
                "variable": v["variable"],
                "etiqueta": v["etiqueta"],
                "variacion": v["variacion"],
                "piso_base": money_str(piso_base),
                "piso_mas": money_str(proyectar(v["mas"]).piso_caja),
                "piso_menos": money_str(proyectar(v["menos"]).piso_caja),
            }
        )

    out = {
        "escenario": escenario,
        "horizonte_meses": SENSIBILIDAD_HORIZONTE,
        "piso_base": money_str(piso_base),
        "variables": variables,
    }
    _sensibilidad_cache.clear()  # una sola vigencia viva: no acumular basura
    _sensibilidad_cache[clave] = out
    return out


ANCLA_MODOS = ("cerrado", "movimientos")


async def _actuals_por_mes(rubro_ajuste_id) -> list[tuple[MesControl, object]]:
    """Caja REAL de libro por mes (COCK-09), en orden cronológico. Cada MesControl con
    su `_caja_libro` (saldo_inicial + Σ movimientos, excluyendo el ajuste)."""
    meses = await MesControl.find_all().sort(+MesControl.mes).to_list()
    out: list[tuple[MesControl, object]] = []
    for mc in meses:
        caja = await _caja_libro(mc.id, rubro_ajuste_id, mc.saldo_inicial_caja)
        out.append((mc, caja))
    return out


async def _elegir_ancla(
    actuals: list[tuple[MesControl, object]], modo: str
) -> tuple[MesControl, object] | None:
    """Último mes que sirve de ancla del rolling forecast: CERRADO (histórico firme) o
    con MOVIMIENTOS (al día, aún sin conciliar). None si no hay ninguno."""
    if modo == "cerrado":
        cerrados = [t for t in actuals if t[0].estado is EstadoMes.CERRADO]
        return cerrados[-1] if cerrados else None
    # 'movimientos': el último mes con al menos una transacción
    for mc, caja in reversed(actuals):
        if await Transaccion.find(Transaccion.mes_id == mc.id).count() > 0:
            return (mc, caja)
    return None


async def comparar_vigente(
    *,
    escenario: str,
    ancla_modo: str,
    horizonte_meses: int | None,
    mes_inicio_defecto: tuple[int, int],
) -> dict:
    """COCK-09 — actuals (caja real de los bancos ya cargados) vs proyección + rolling
    forecast: la proyección se RE-ANCLA a la caja real del mes ancla (configurable:
    último cerrado / último con movimientos) y arranca desde ahí. Sin ancla → proyección
    normal desde el mes por defecto. Montos como string (regla 1)."""
    if ancla_modo not in ANCLA_MODOS:
        raise ProyeccionError(f"ancla_modo debe ser uno de {ANCLA_MODOS}", 422)
    rubro_aj = await _rubro_ajuste()
    actuals = await _actuals_por_mes(rubro_aj.id)
    ancla = await _elegir_ancla(actuals, ancla_modo)

    if ancla is None:
        forecast = await proyectar_vigente(
            escenario=escenario,
            mes_inicio=mes_inicio_defecto,
            horizonte_meses=horizonte_meses,
        )
        ancla_out = None
        actuals_out = actuals  # todos los reales que haya (puede ser [])
    else:
        mc_a, caja_a = ancla
        y, m = int(mc_a.mes[:4]), int(mc_a.mes[5:7])
        forecast = await proyectar_vigente(
            escenario=escenario,
            mes_inicio=(y, m),
            horizonte_meses=horizonte_meses,
            caja_inicial_override=caja_a,
        )
        ancla_out = {"mes": mc_a.mes[:7], "caja_real": money_str(caja_a)}
        # actuals hasta el ancla inclusive (el tramo real de la curva)
        actuals_out = [t for t in actuals if t[0].mes <= mc_a.mes]

    return {
        "escenario": escenario,
        "ancla_modo": ancla_modo,
        "ancla": ancla_out,
        "actuals": [
            {"mes": mc.mes[:7], "caja_real": money_str(caja)}
            for mc, caja in actuals_out
        ],
        "forecast": [
            {"mes": f["mes"], "caja": f["caja"]} for f in forecast["meses"]
        ],
    }
