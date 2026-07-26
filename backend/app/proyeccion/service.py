# backend/app/proyeccion/service.py
"""Servicio de proyección (COCK-01) — orquesta el motor compute-only.

Carga los parámetros VIGENTES + el catálogo de modelos ACTIVOS, arma un
`ParametrosMotor`, aplica el escenario (presets de mora/recuperación) y llama a
`motor.proyectar()`. Serializa a JSON con montos como string (regla 1). No escribe
estado: es una lectura pura sobre la configuración vigente."""

from app.cartera_previa import service as cartera_previa_service
from app.core.money import money_str
from app.domain.modelo_moto import ModeloMoto
from app.domain.parametros_proyeccion import ParametrosProyeccion
from app.modelos_moto import service as modelos_service
from app.parametros_proyeccion import service as parametros_service
from app.proyeccion.motor import (
    PRESETS_ESCENARIO,
    ModeloProyeccion,
    ParametrosMotor,
    ResultadoProyeccion,
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
    )


def _serializar(r: ResultadoProyeccion, escenario: str, caja_minima) -> dict:
    return {
        "escenario": escenario,
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
                "egresos": money_str(f.egresos),
                "flujo": money_str(f.flujo),
                "caja": money_str(f.caja),
                "estado": f.estado,
            }
            for f in r.meses
        ],
    }


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
    pm = _armar_parametros(
        params,
        modelos,
        escenario,
        mes_inicio,
        horizonte,
        recaudo_previo,
        activos_previos,
    )
    return _serializar(proyectar(pm), escenario, params.caja_minima)
