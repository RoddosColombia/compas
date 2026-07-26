# backend/app/proyeccion/service.py
"""Servicio de proyección (COCK-01) — orquesta el motor compute-only.

Carga los parámetros VIGENTES + el catálogo de modelos ACTIVOS, arma un
`ParametrosMotor`, aplica el escenario (presets de mora/recuperación) y llama a
`motor.proyectar()`. Serializa a JSON con montos como string (regla 1). No escribe
estado: es una lectura pura sobre la configuración vigente."""

from app.cartera_previa import service as cartera_previa_service
from app.core.money import money_str
from app.domain.configuracion import ClaveConfig, Configuracion
from app.domain.modelo_moto import ModeloMoto
from app.domain.parametros_proyeccion import ParametrosProyeccion
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
        costo_moto_nueva=params.costo_moto_nueva,
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
        caja_inicial=params.caja_inicial,
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


async def proyectar_vigente(
    *, escenario: str, mes_inicio: tuple[int, int], horizonte_meses: int | None
) -> dict:
    """Proyección con los parámetros/modelos vigentes. Falla-cerrado si falta config
    (no se inventan cifras): 409 si no hay parámetros o no hay modelos activos."""
    params = await parametros_service.obtener_vigente()
    if params is None:
        raise ProyeccionError(
            "no hay parámetros de proyección configurados (cárguelos primero)", 409
        )
    modelos = await modelos_service.listar_modelos(activo=True)
    if not modelos:
        raise ProyeccionError("no hay modelos de moto activos", 409)
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
    )
    return _serializar(proyectar(pm), escenario, params.caja_minima, fondo)


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
