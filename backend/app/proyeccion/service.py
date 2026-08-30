# backend/app/proyeccion/service.py
"""Servicio de proyección (COCK-01) — orquesta el motor compute-only.

Carga los parámetros VIGENTES + el catálogo de modelos ACTIVOS, arma un
`ParametrosMotor`, aplica el escenario (presets de mora/recuperación) y llama a
`motor.proyectar()`. Serializa a JSON con montos como string (regla 1). No escribe
estado: es una lectura pura sobre la configuración vigente."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal

from app.cartera_previa import service as cartera_previa_service
from app.cierre.service import _caja_libro, _rubro_ajuste
from app.cierre.transito import transito_heredado
from app.configuracion.service import leer_umbral_atencion_activo
from app.core.money import money_str
from app.domain.configuracion import ClaveConfig, Configuracion
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.modelo_moto import ModeloMoto
from app.domain.obligacion import FacturaObligacion, Obligacion
from app.domain.parametros_proyeccion import (
    ParametrosProyeccion,
    costo_alistamiento_total,
)
from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
from app.domain.transaccion import Transaccion, pares_clasificacion
from app.facturas import service as facturas_service
from app.iva.liquidacion import (
    FacturaIva,
    liquidar,
    plan_fondo_provision,
    programar_egresos_iva,
)
from app.iva.proyectado import ModeloIva, facturas_iva_proyectadas
from app.modelos_moto import service as modelos_service
from app.obligaciones.reconciliacion import (
    FacturaReconciliar,
    ResultadoReconciliado,
    reconciliar,
)
from app.parametros_proyeccion import service as parametros_service
from app.proyeccion.ejecucion.guarda import marcas_origen, rubros_sin_mapear
from app.proyeccion.ejecucion.lectura import RubroInfo
from app.proyeccion.ejecucion.loader import (
    cargar_anclas,
    cargar_completitud_mes_en_curso,
)
from app.proyeccion.ejecucion.service import CERRADO, AnclaMes, anclar
from app.proyeccion.impactos import Ajuste, aplicar_impactos
from app.proyeccion.motor import (
    PRESETS_ESCENARIO,
    ModeloProyeccion,
    ParametrosMotor,
    ResultadoProyeccion,
    _estado_caja,
    _meses_del_horizonte,
    cartera_activa_mensual,
    cartera_por_anada_mensual,
    colocacion_mensual,
    proyectar,
)
from app.proyeccion.reparto import reparto_por_rubro
from app.proyeccion.solvers import (
    goal_seek,
    punto_de_quiebre,
    techo_gasto,
    techo_gasto_ventana,
)
from app.proyeccion.valles import Valle, detectar_valles

HORIZONTE_MAX = 240  # 20 años (RF-F10 · Fundacional §2, subido de 180)
_log = logging.getLogger(__name__)


class ProyeccionError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


def _modelo_a_lineas(m: ModeloMoto) -> list[ModeloProyeccion]:
    """PLAN-52 (CEO 2026-08-11): expande un modelo en UNA línea de motor por plan de
    pago, con mix = participación del modelo × peso del plan. El motor certificado no
    cambia (consume líneas como siempre); sin plan 2 la línea es IDÉNTICA a la de
    siempre — candado golden-master en test_modelos_planes."""
    base = ModeloProyeccion(
        nombre=m.nombre,
        cuota_semanal=m.cuota_semanal,
        cuota_inicial=m.cuota_inicial,
        plazo_semanas=m.plazo_semanas,
        mix=m.participacion_mix,
        costo_moto=m.costo_auteco,
    )
    if m.plan2_cuota_semanal is None or m.plan2_plazo_semanas is None:
        return [base]
    return [
        replace(
            base,
            nombre=f"{m.nombre} · {m.plazo_semanas} sem",
            mix=m.participacion_mix * m.peso_plan1,
        ),
        replace(
            base,
            nombre=f"{m.nombre} · {m.plan2_plazo_semanas} sem",
            cuota_semanal=m.plan2_cuota_semanal,
            plazo_semanas=m.plan2_plazo_semanas,
            mix=m.participacion_mix * (Decimal("1") - m.peso_plan1),
        ),
    ]


def _rampa_a_lista(
    rampa_unidades: dict[str, int], mes_inicio: tuple[int, int]
) -> list[int] | None:
    """FIX-L: mapea la rampa por mes (YYYY-MM → unidades) al `rampa` nativo del motor
    (lista posicional de los PRIMEROS meses desde `mes_inicio`). Toma el prefijo
    CONTIGUO desde mes_inicio; el primer mes ausente corta la rampa (el motor reinicia
    ahí en motos_base). {} o sin prefijo → None (sin rampa, comportamiento de hoy)."""
    if not rampa_unidades:
        return None
    y, m = mes_inicio
    out: list[int] = []
    while (ym := f"{y:04d}-{m:02d}") in rampa_unidades:
        out.append(rampa_unidades[ym])
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out or None


def _con_delta(preset: Decimal, delta: Decimal) -> Decimal:
    """SUP-1: pct del escenario + delta de los supuestos, acotado a [0, 1] (un pct de
    mora/recuperación fuera de rango no tiene sentido financiero)."""
    return min(Decimal("1"), max(Decimal("0"), preset + delta))


def _mora_del_escenario(
    params: ParametrosProyeccion, escenario: str
) -> tuple[Decimal, Decimal]:
    """(pct_mora, pct_recuperacion) EFECTIVOS del escenario. Una sola fuente para el
    motor y para lo que la pantalla muestra — si divergieran, el usuario vería unos
    supuestos y la curva usaría otros.

    SUP-2: si el CEO editó el escenario extremo, ese valor MANDA. Si no, se conserva
    el delta en puntos de SUP-1 sobre el preset. Escenario desconocido → los supuestos
    tal cual."""
    if escenario not in PRESETS_ESCENARIO:
        return params.pct_mora, params.pct_recuperacion
    editables = {
        "pesimista": (params.pct_mora_pesimista, params.pct_recuperacion_pesimista),
        "optimista": (params.pct_mora_optimista, params.pct_recuperacion_optimista),
    }
    mora_edit, recup_edit = editables.get(escenario, (None, None))
    mora = (
        mora_edit
        if mora_edit is not None
        else _con_delta(
            PRESETS_ESCENARIO[escenario]["pct_mora"],
            params.pct_mora - PRESETS_ESCENARIO["base"]["pct_mora"],
        )
    )
    recup = (
        recup_edit
        if recup_edit is not None
        else _con_delta(
            PRESETS_ESCENARIO[escenario]["pct_recuperacion"],
            params.pct_recuperacion - PRESETS_ESCENARIO["base"]["pct_recuperacion"],
        )
    )
    return mora, recup


def _supuestos_visibles(params: ParametrosProyeccion, escenario: str) -> dict:
    """SUP-5 (CEO 2026-08-23): los drivers que EXPLICAN la curva en pantalla, para que
    no haya que adivinar de dónde sale el resultado. Son los valores EFECTIVOS del
    escenario que se está viendo (con SUP-2 cada escenario tiene su propia mora).
    Porcentajes como string (regla 1)."""
    mora, recup = _mora_del_escenario(params, escenario)
    return {
        "pct_mora": str(mora),
        "pct_recuperacion": str(recup),
        "pct_default": str(params.pct_default),
        "pct_provision": str(params.pct_provision),
        "meses_rezago_recuperacion": params.meses_rezago_recuperacion,
        "pct_aval_recaudo": str(params.pct_aval_recaudo),
        # SUP-6: SOBRE QUÉ se aplica la mora (la cuota inicial es de contado).
        "mora_sobre_recaudo": params.mora_sobre_recaudo,
        "pct_prefondeo_iva": str(params.pct_prefondeo_iva),
        "motos_base": params.motos_base,
        "crec_pct_mensual": str(params.crec_pct_mensual),
        "crec_pct_mensual_2": (
            str(params.crec_pct_mensual_2)
            if params.crec_pct_mensual_2 is not None
            else None
        ),
        "crec_mes_corte": params.crec_mes_corte,
        "rampa_unidades": dict(params.rampa_unidades),
    }


def _guard_apache_por_mes(
    apache_por_mes: dict[int, int] | None, modelos: list[ModeloMoto]
) -> None:
    """B-1 del gate Kimi retroactivo (9.4, 2026-08-13). El motor certificado ancla el
    override de rampa `apache_por_mes` al ÍNDICE 1 de la lista de líneas ("el Apache
    real de un mes de rampa" — `_split_por_mix`). PLAN-52 expande cada modelo en una
    línea POR PLAN, así que con algún modelo a dos planes el índice 1 deja de ser
    Apache y el override caería en la línea equivocada EN SILENCIO.

    Hoy NINGÚN camino de producción alimenta `apache_por_mes` (solo fixtures del
    golden master, cuyo catálogo no tiene plan 2). Este guard cierra la puerta para
    siempre: quien lo alimente con el catálogo expandido recibe un error explícito
    en vez de una proyección mal indexada."""
    if not apache_por_mes:
        return
    con_plan2 = [m.nombre for m in modelos if m.plan2_plazo_semanas is not None]
    if con_plan2:
        raise ProyeccionError(
            "apache_por_mes ancla su override al índice 1 de la lista de líneas del "
            f"motor y hay modelos con segundo plan ({', '.join(con_plan2)}): la "
            "expansión por planes desplaza los índices y el override caería en la "
            "línea equivocada. Antes de usar este camino hay que rediseñar el "
            "override por NOMBRE de línea (CR).",
            422,
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
    # SUP-1/SUP-2/SUP-5: la resolución de la mora del escenario vive en
    # `_mora_del_escenario` — UNA sola fuente para el motor y para los supuestos que
    # la pantalla muestra (si divergieran, se verían unos y la curva usaría otros).
    pct_mora, pct_recuperacion = _mora_del_escenario(params, escenario)
    pm = ParametrosMotor(
        mes_inicio=mes_inicio,
        horizonte_meses=horizonte_meses,
        modelos=[ln for m in modelos for ln in _modelo_a_lineas(m)],
        motos_base=params.motos_base,
        crec_pct_mensual=params.crec_pct_mensual,
        rampa=_rampa_a_lista(params.rampa_unidades, mes_inicio),
        # SUP-1: segundo tramo de crecimiento (None/None = comportamiento histórico)
        crec_pct_mensual_2=params.crec_pct_mensual_2,
        crec_mes_corte=params.crec_mes_corte,
        # SUP-2: rezago de la recuperación de mora + fondo AVAL (ambos editables)
        meses_rezago_recuperacion=params.meses_rezago_recuperacion,
        pct_aval_recaudo=params.pct_aval_recaudo,
        mora_sobre_recaudo=params.mora_sobre_recaudo,
        # P3 del ciclo mensual: el arranque es el efectivo ANTERIOR al primer mes,
        # asi que su flujo si mueve su caja. El motor conserva False como default
        # (semantica del artefacto) para que el golden master siga bit a bit.
        primer_mes_acumula_flujo=True,
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
    # B-1 (gate Kimi 9.4): si algún día este armado alimenta apache_por_mes con el
    # catálogo expandido por planes, fallar EXPLÍCITO aquí — nunca indexar mal.
    _guard_apache_por_mes(pm.apache_por_mes, modelos)
    return pm


@dataclass(frozen=True)
class AnclajeMeta:
    """Metadato de origen de la proyección para el shape de P5 (aditivo). Vacío cuando
    no hay anclaje → la respuesta queda byte-idéntica a la de antes de P5."""

    meses_anclados: dict[str, str] = field(default_factory=dict)
    sin_mapear: list[str] = field(default_factory=list)
    mes_en_curso: dict | None = None
    # P2 del ciclo mensual — de dónde salió la plata con la que arranca la serie.
    arranque: "Arranque | None" = None


def _serializar(
    r: ResultadoProyeccion,
    escenario: str,
    caja_minima,
    fondo: list,
    rec: ResultadoReconciliado | None = None,
    *,
    meta: "AnclajeMeta | None" = None,
    caja_atencion: Decimal | None = None,
    supuestos: dict | None = None,
) -> dict:
    meses_ym = [f.mes for f in r.meses]
    meta = meta or AnclajeMeta()
    return {
        "escenario": escenario,
        # SUP-5 (CEO 2026-08-23): los drivers que EXPLICAN esta curva — los valores
        # EFECTIVOS del escenario en pantalla, no los del set base.
        "supuestos": supuestos or {},
        # P2 del ciclo mensual — la plata con la que arranca la serie y DE DÓNDE salió.
        # `origen`: 'ciclo' (efectivo real del cierre anterior) · 'semilla' (el
        # parámetro
        # `caja_inicial`, cuando el mes no está abierto en el ciclo) · 'override'
        # (re-anclaje explícito, COCK-09).
        "arranque": {
            "valor": money_str(meta.arranque.valor),
            "origen": meta.arranque.origen,
            "mes": meta.arranque.mes,
            "saldo_declarado": (
                money_str(meta.arranque.saldo_declarado)
                if meta.arranque.saldo_declarado is not None
                else None
            ),
            "transito_heredado": money_str(meta.arranque.transito_heredado),
        }
        if meta.arranque is not None
        else None,
        # P5 — origen de cada cifra (aditivo): marcas por mes, rubros sin concepto del
        # motor, y completitud del mes en curso (B13). Vacíos si no hay anclaje.
        "meses_anclados": dict(meta.meses_anclados),
        "sin_mapear": list(meta.sin_mapear),
        "mes_en_curso": meta.mes_en_curso,
        # D2 §4: ventana donde las facturas reales netean el Auteco paramétrico + el
        # interés de obligaciones separado por mes (None/{} si no hay facturas activas).
        "ventana_reconciliada": (
            list(rec.ventana) if rec is not None and rec.ventana else None
        ),
        "interes_obligaciones": rec.interes_por_mes if rec is not None else {},
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
        # RF-F3 · P3a — el segundo umbral (ámbar) para la banda de atención en el
        # frontend. None cuando no está configurado (banda no se pinta).
        "caja_atencion": (
            money_str(caja_atencion) if caja_atencion is not None else None
        ),
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
                "aval": money_str(f.aval),  # SUP-2: fondo AVAL propio
                # SUP-5: la explicación del ingreso (mora/recuperación/default), para
                # que la pantalla muestre QUÉ compone el resultado. En un mes anclado
                # a la ejecución real vienen en 0: su ingreso sale del libro.
                "mora": money_str(f.mora),
                "recuperacion": money_str(f.recuperacion),
                "default": money_str(f.default),
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


async def _compuerta_iva_activa() -> bool:
    """CR-E2-COMPUERTA: ¿el IVA de las facturas alimenta la proyección? Clave
    CONFIGURACION `IVA_ALIMENTA_PROYECCION`. Ausente o apagada → False (D-12: por
    defecto el IVA NO mueve la caja; encenderla es una decisión de dato del CEO)."""
    cfg = (
        await Configuracion.find(
            Configuracion.clave == ClaveConfig.IVA_ALIMENTA_PROYECCION
        )
        .sort(-Configuracion.vigente_desde)
        .limit(1)
        .to_list()
    )
    if cfg and cfg[0].valor_json:
        return bool(cfg[0].valor_json.get("activa", False))
    return False


async def _iva_plan(
    mes_inicio: tuple[int, int],
    horizonte: int,
    pct_prefondeo: Decimal = Decimal("1"),
    proyectadas: list[FacturaIva] | None = None,
) -> tuple[dict[int, object], list]:
    """Puente C11↔C7: liquida las facturas cargadas y devuelve (egreso_por_mes, fondo).
    `egreso_por_mes` = IVA neto de cada período en el índice de su fecha DIAN real
    (PR-2b, entra al motor). `fondo` = plan de provisión mes a mes (P1.4, informativo,
    NO entra al flujo del motor). Sin facturas → ({}, []).

    CR-E2-COMPUERTA: con la compuerta APAGADA (default) devuelve ({}, []) aunque haya
    facturas cargadas, de modo que E2 capture facturas y liquide el IVA SIN mover la
    proyección (D-12). `GET /proyeccion` queda idéntico bit a bit al estado previo.

    SUP-3: `proyectadas` son las `FacturaIva` sintéticas del IVA de las ventas FUTURAS
    (`iva.proyectado`). Entran al MISMO liquidador junto a las reales — sin ellas la
    proyección solo veía el IVA ya facturado y lo daba en cero hacia adelante."""
    if not await _compuerta_iva_activa():
        return {}, []
    facturas = await facturas_service.obtener_facturas_iva()
    facturas = facturas + list(proyectadas or [])
    if not facturas:
        return {}, []
    periodicidad = await facturas_service.obtener_periodicidad()
    calendario = await _calendario_dian()
    declarado = await facturas_service.obtener_saldo_favor_declarado()
    liquidaciones = liquidar(facturas, periodicidad, saldo_declarado=declarado)
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
        pct_prefondeo=pct_prefondeo,  # SUP-2: editable (1 = 100 %, como hasta hoy)
    )
    return egreso, fondo


async def _iva_proyectado(
    params: ParametrosProyeccion,
    modelos: list[ModeloMoto],
    mes_inicio: tuple[int, int],
    horizonte: int,
) -> list[FacturaIva]:
    """SUP-3: el IVA de las ventas FUTURAS, derivado de la colocación proyectada y del
    catálogo (precio de venta y costo Auteco, ambos con IVA), como en el modelo v9.1.

    Precisión: los meses que YA tienen su realidad NO se proyectan — un mes CERRADO,
    o uno con su `VENTAS-YYYY-MM` de IVA generado ya registrado. Su dato manda y nunca
    se suman las dos cosas (mismo principio del mes en curso que fijó el CEO)."""
    if not modelos:
        return []
    colocacion = colocacion_mensual(
        params.motos_base,
        params.crec_pct_mensual,
        horizonte,
        _rampa_a_lista(params.rampa_unidades, mes_inicio),
        params.crec_pct_mensual_2,
        params.crec_mes_corte,
    )
    meses_ym = _meses_del_horizonte(mes_inicio, horizonte)
    # meses con realidad: cerrados + los que ya tienen su IVA generado registrado
    reales: set[str] = set()
    async for mc in MesControl.find(MesControl.estado == EstadoMes.CERRADO):
        reales.add(str(mc.mes)[:7])
    for f in await facturas_service.listar_facturas(activo=True):
        if f.numero.startswith("VENTAS-"):
            reales.add(f.numero.removeprefix("VENTAS-")[:7])
    modelos_iva = [
        ModeloIva(
            nombre=m.nombre,
            precio_venta_con_iva=m.precio_venta_con_iva,
            costo_auteco_con_iva=m.costo_auteco,
            mix=m.participacion_mix,
        )
        for m in modelos
    ]
    tarifa = await facturas_service.obtener_tarifa_iva()
    return facturas_iva_proyectadas(
        colocacion_por_mes=colocacion,
        meses_ym=meses_ym,
        modelos=modelos_iva,
        tarifa=tarifa,
        meses_con_dato_real=reales,
    )


async def _facturas_reconciliar() -> list[FacturaReconciliar]:
    """Facturas activas + los términos de su obligación (facturación activa) aplanados
    para la reconciliación §4. Sin facturas → []. D2 §7: las pagadas por un TERCERO se
    excluyen — bajan la deuda pero NO tocan la caja de RODDOS; pendientes y las pagadas
    por roddos sí pesan en la caja."""
    facturas = await FacturaObligacion.find({"activo": True}).to_list()
    facturas = [f for f in facturas if f.pagada_desde != "tercero"]
    if not facturas:
        return []
    ids = list({f.obligacion_id for f in facturas})
    obls = {o.id: o for o in await Obligacion.find({"_id": {"$in": ids}}).to_list()}
    out: list[FacturaReconciliar] = []
    for f in facturas:
        o = obls.get(f.obligacion_id)
        if o is None or o.naturaleza != "facturacion" or not o.activo:
            continue
        out.append(
            FacturaReconciliar(
                fecha_factura=f.fecha_factura,
                valor=f.valor,
                plazo_elegido_dias=f.plazo_elegido_dias,
                plazo_base_dias=o.plazo_base_dias or 0,
                tasa_excedente_mensual=o.tasa_excedente_mensual or Decimal("0"),
            )
        )
    return out


@dataclass(frozen=True)
class Arranque:
    """P2 del ciclo mensual — de dónde sale la plata con la que arranca la proyección.

    Paso 0 del contrato (`docs/COMPAS_Ciclo_Mensual.md`): el efectivo real con el que
    cerró el mes anterior. Lo escribe el ciclo mensual: `saldo_inicial_caja` se DERIVA
    del consolidado bancario del predecesor (M-1/F-14) y se puede corregir a mano con
    motivo y evento de auditoría (`saldo_inicial.editado`, FIX-F) — COMPAS no hace
    arqueos, la diferencia se teclea con rastro (decisión CEO 2026-08-23).

    `origen`: 'ciclo' cuando el mes de inicio está abierto en el ciclo (el caso normal);
    'semilla' cuando no lo está y toca usar el parámetro `caja_inicial` (primer mes de
    la
    historia, o un mes_inicio fuera del ciclo). Se publica para que la pantalla pueda
    decir de dónde salió la cifra en vez de que el usuario adivine.
    """

    valor: Decimal
    origen: str  # 'ciclo' | 'semilla'
    mes: str | None  # 'YYYY-MM' del MesControl leído (None si semilla)
    saldo_declarado: Decimal | None  # el saldo del ciclo, sin el tránsito
    transito_heredado: Decimal  # CR-WAVA: cobrado que aún no está en el banco


async def _arranque_de_caja(
    params: ParametrosProyeccion, mes_inicio: tuple[int, int]
) -> Arranque:
    """Resuelve el Paso 0. La definición del valor es la MISMA que muestra la pantalla
    del ciclo (`caja_inicial_total` = saldo declarado + tránsito heredado): si las dos
    pantallas dieran números distintos para "la plata con la que arranco el mes", el
    tejido estaría roto."""
    y, m = mes_inicio
    clave = f"{y:04d}-{m:02d}-01"
    mc = await MesControl.find_one(MesControl.mes == clave)
    if mc is None:
        # Fail-soft honesto: no se inventa un arranque; se usa la semilla y se DECLARA.
        return Arranque(
            valor=params.caja_inicial,
            origen="semilla",
            mes=None,
            saldo_declarado=None,
            transito_heredado=Decimal("0.00"),
        )
    transito = await transito_heredado(clave)
    return Arranque(
        valor=mc.saldo_inicial_caja + transito,
        origen="ciclo",
        mes=clave[:7],
        saldo_declarado=mc.saldo_inicial_caja,
        transito_heredado=transito,
    )


async def _resultado_con(
    params: ParametrosProyeccion,
    modelos: list[ModeloMoto],
    *,
    escenario: str,
    mes_inicio: tuple[int, int],
    horizonte_meses: int | None,
    caja_inicial_override: object | None = None,
    facturas_override: list[FacturaReconciliar] | None = None,
    anclas_override: tuple[dict[str, AnclaMes], list[RubroInfo], set[str]]
    | None = None,
) -> tuple[
    ResultadoProyeccion,
    Decimal,  # caja_minima (crítico)
    object,  # fondo
    ResultadoReconciliado | None,
    AnclajeMeta,
    Decimal | None,  # caja_atencion (ámbar, RF-F3; None si no está configurado)
]:
    """La tubería completa sobre un set de parámetros DADO, en el orden de precedencia
    `motor → EJECUCIÓN (E1) → OBLIGACIONES (D2) → IMPACTOS (D1)`:

    1. `proyectar` — el motor paramétrico (R0, nunca se toca).
    2. **E1 (anclaje):** sobre-escribe las líneas de los meses cerrados/en ejecución con
       la ejecución real y re-acumula la caja (`ejecucion.service.anclar`). Composición
       con COCK-09: COCK-09 ancla la caja inicial; E1 ancla las LÍNEAS y re-acumula
       desde ahí — no hay doble anclaje. Con `anclas` vacío, la base bit a bit.
    3. **D2 (reconciliación):** netea el Auteco paramétrico contra las facturas reales,
       EXCLUYENDO los meses que E1 ya ancló (`meses_anclados`) para no contar dos veces.

    Devuelve el ResultadoProyeccion crudo (anclado + reconciliado) + umbral + fondo + la
    meta de reconciliación. Sin anclaje ni facturas es la base bit a bit (preview y
    vigente idénticos por test). `anclas_override`/`facturas_override` inyectan insumos
    deterministas en los tests (evitan Mongo)."""
    horizonte = horizonte_meses or params.horizonte_meses
    if horizonte < 1 or horizonte > HORIZONTE_MAX:
        raise ProyeccionError(
            f"horizonte_meses debe estar en [1, {HORIZONTE_MAX}]", 422
        )
    # P2 · Paso 0 — el arranque sale del CICLO (efectivo real del cierre anterior), no
    # del parámetro tecleado. `caja_inicial_override` explícito (COCK-09, rolling
    # forecast) sigue mandando sobre todo. Con `anclas_override` (tests herméticos) no
    # se
    # toca Mongo: se queda en la semilla.
    if caja_inicial_override is not None:
        arranque = Arranque(
            valor=Decimal(str(caja_inicial_override)),
            origen="override",
            mes=None,
            saldo_declarado=None,
            transito_heredado=Decimal("0.00"),
        )
    elif anclas_override is not None:
        arranque = Arranque(
            valor=params.caja_inicial,
            origen="semilla",
            mes=None,
            saldo_declarado=None,
            transito_heredado=Decimal("0.00"),
        )
    else:
        arranque = await _arranque_de_caja(params, mes_inicio)

    recaudo_previo, activos_previos = await cartera_previa_service.obtener_series()
    iva_egreso, fondo = await _iva_plan(
        mes_inicio,
        horizonte,
        params.pct_prefondeo_iva,
        # SUP-3: el IVA de las ventas futuras entra a la liquidación
        await _iva_proyectado(params, modelos, mes_inicio, horizonte),
    )
    pm = _armar_parametros(
        params,
        modelos,
        escenario,
        mes_inicio,
        horizonte,
        recaudo_previo,
        activos_previos,
        iva_egreso,
        arranque.valor,
    )
    r = proyectar(pm)

    # E1 (P3) — anclar a la ejecución real ANTES de la reconciliación D2.
    anclas, rubros_e1, neutros_e1 = (
        anclas_override
        if anclas_override is not None
        else await cargar_anclas(mes_inicio, horizonte)
    )
    meses_anclados: frozenset[str] = frozenset()
    marcas: dict[str, str] = {}
    sin_mapear: list[str] = []
    if anclas:
        aj = anclar(
            resultado=r,
            caja_minima=params.caja_minima,
            anclas=anclas,
            rubros=rubros_e1,
            neutros_ids=neutros_e1,
            primer_mes_acumula=True,
        )
        r = _kpis_a_resultado(aj)
        # D2 solo excluye los meses CERRADOS (el pasado es del libro; su factura ya no
        # está pendiente). E1 NO ancla Auteco (sus 5 conceptos no incluyen el Auteco),
        # así que en meses no-cerrados D2 SÍ aplica el pago real, sin doble conteo
        # (campos disjuntos, deltas aditivos).
        meses_anclados = frozenset(m for m, a in anclas.items() if a.estado == CERRADO)
        # P5 — marcas de origen (todas) + rubros sin concepto, para el shape aditivo.
        marcas = marcas_origen(anclas, rubros=rubros_e1, neutros_ids=neutros_e1)
        sin_mapear = rubros_sin_mapear(anclas, rubros=rubros_e1, neutros_ids=neutros_e1)
        # B10 (P4): log de los cerrados sospechosos (ejecutado << definido). Solo
        # observabilidad — la marca NUNCA cambia el régimen (un sospechoso sigue anclado
        # y excluido de D2, protege C-1).
        sospechosos = sorted(
            m for m, mk in marcas.items() if mk == "cerrado_sospechoso"
        )
        if sospechosos:
            _log.warning(
                "E1 B10: mes(es) cerrado(s) sospechoso(s) (ejecutado << definido): %s",
                sospechosos,
            )

    # P5/B13 — completitud del mes en curso (Mongo). None con anclas_override (tests) o
    # cuando ningún mes del horizonte está en ejecución. Independiente del anclaje.
    completitud = (
        None
        if anclas_override is not None
        else await cargar_completitud_mes_en_curso(mes_inicio, horizonte)
    )

    facturas = (
        facturas_override
        if facturas_override is not None
        else await _facturas_reconciliar()
    )
    rec: ResultadoReconciliado | None = None
    if facturas:
        rec = reconciliar(
            r,
            facturas,
            params.caja_minima,
            meses_anclados=meses_anclados,
            primer_mes_acumula=True,
        )
        r = _kpis_a_resultado(rec.ajustado)
    # P6 — el TERMÓMETRO se cierra aquí: el loader trajo la realidad (ingreso real,
    # ejecutado, colocaciones reales) y solo el servicio conoce la PROYECCIÓN del mes
    # (la fila de la serie). Se juntan para que la pantalla compare meta vs. realidad
    # sin recalcular nada — y sin que la realidad toque la curva (Paso 2 del contrato).
    if completitud is not None:
        fila = next((f for f in r.meses if f.mes == completitud["mes"]), None)
        if fila is not None:
            completitud = {
                **completitud,
                "colocaciones_meta": fila.motos,
                "ingreso_proyectado": money_str(fila.neto),
                "ingreso_proyectado_inicial": money_str(fila.cuotas_iniciales),
                "ingreso_proyectado_semanal": money_str(fila.recaudo_credito),
            }

    meta = AnclajeMeta(
        meses_anclados=marcas,
        sin_mapear=sin_mapear,
        mes_en_curso=completitud,
        arranque=arranque,
    )

    # RF-F3 · P3a — re-sella el `estado` de cada mes con el umbral de atención vigente.
    # Es capa aditiva (post-motor); la aritmética de flujos y saldos NO cambia. Sin
    # umbral configurado, `_estado_caja` con `None` reproduce ok/critico/negativo
    # exactamente igual (candado del golden-master).
    caja_atencion = await leer_umbral_atencion_activo(params.caja_minima)
    if caja_atencion is not None:
        meses_reestampados = [
            replace(
                m,
                estado=_estado_caja(m.caja, params.caja_minima, caja_atencion),
            )
            for m in r.meses
        ]
        r = replace(r, meses=meses_reestampados)

    return r, params.caja_minima, fondo, rec, meta, caja_atencion


async def _proyectar_con(
    params: ParametrosProyeccion,
    modelos: list[ModeloMoto],
    *,
    escenario: str,
    mes_inicio: tuple[int, int],
    horizonte_meses: int | None,
    caja_inicial_override: object | None = None,
) -> dict:
    """Serializa la proyección de `_resultado_con` (mismo shape que GET /proyeccion),
    marcando la ventana reconciliada y el interés de obligaciones (§4)."""
    r, caja_min, fondo, rec, meta, caja_atn = await _resultado_con(
        params,
        modelos,
        escenario=escenario,
        mes_inicio=mes_inicio,
        horizonte_meses=horizonte_meses,
        caja_inicial_override=caja_inicial_override,
    )
    return _serializar(
        r,
        escenario,
        caja_min,
        fondo,
        rec,
        meta=meta,
        caja_atencion=caja_atn,
        # SUP-5: los drivers efectivos de ESTA curva, para que la pantalla explique
        # el resultado en vez de pedirle al usuario que adivine.
        supuestos=_supuestos_visibles(params, escenario),
    )


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


async def proyectar_agregado(
    *,
    granularidad: str,
    escenario: str,
    mes_inicio: tuple[int, int],
    horizonte_meses: int | None,
) -> dict:
    """RF-F10 · Fundacional §2 — Serie proyectada agregada por trimestre/año.

    Corre el pipeline completo `proyectar → E1 → D2` y colapsa la serie mensual
    con `agregar_por_periodo` (capa post-motor pura; golden-master intacto). El
    endpoint `GET /proyeccion/agregada?granularidad=trimestre|anual` la expone.
    Para la serie MENSUAL, seguir usando `GET /proyeccion` (compat total).
    """
    from app.proyeccion.agregacion import agregar_por_periodo

    if granularidad not in ("trimestre", "anual"):
        raise ProyeccionError(
            f"granularidad no soportada: {granularidad!r} "
            "(usa 'trimestre' o 'anual'; la mensual va por GET /proyeccion)",
            422,
        )
    params, modelos = await _cargar_config_vigente()
    r, caja_min, _, _, _, caja_atn = await _resultado_con(
        params,
        modelos,
        escenario=escenario,
        mes_inicio=mes_inicio,
        horizonte_meses=horizonte_meses,
    )
    periodos = agregar_por_periodo(r.meses, granularidad=granularidad)
    return {
        "escenario": escenario,
        "granularidad": granularidad,
        "caja_minima": money_str(caja_min),
        "caja_atencion": money_str(caja_atn) if caja_atn is not None else None,
        "periodos": periodos,
    }


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


def _serializar_valle(v: Valle) -> dict:
    return {
        "mes": v.mes,
        "caja": money_str(v.caja),
        "distancia_al_umbral": money_str(v.distancia_al_umbral),
        "meses_para_prepararse": v.meses_para_prepararse,
        "causas": [
            {
                "concepto": c.concepto,
                "etiqueta": c.etiqueta,
                "monto": money_str(c.monto),
                "promedio": money_str(c.promedio),
                "vs_promedio": (
                    str(c.vs_promedio) if c.vs_promedio is not None else None
                ),
            }
            for c in v.causas
        ],
        # RF-F3 · P2 — caracterización del segmento (None sin umbral configurado).
        "entrada": v.entrada,
        "salida": v.salida,
        "duracion": v.duracion,
    }


def _kpis_a_resultado(aj) -> ResultadoProyeccion:
    """Envuelve la serie ajustada + sus KPIs en un ResultadoProyeccion para reusar
    `_serializar` (mismo shape que la base; el front pinta base vs. ajustada igual)."""
    return ResultadoProyeccion(
        meses=aj.meses,
        piso_caja=aj.kpis.piso_caja,
        mes_mas_ajustado=aj.kpis.mes_mas_ajustado,
        meses_bajo_minimo=aj.kpis.meses_bajo_minimo,
        caja_final=aj.kpis.caja_final,
        capital_requerido=aj.kpis.capital_requerido,
        runway_meses=aj.kpis.runway_meses,
    )


def _palancas_por_valle(
    r: ResultadoProyeccion,
    valle: dict,
    caja_minima: Decimal,
    caja_atencion: Decimal | None,
) -> dict:
    """RF-F5 · Fundacional §2 — Las 3 palancas de acción para UN valle:

    1. **recorte_gasto**: cuánto recortar/mes (goal_seek variable=gasto_absoluto)
       para que el piso quede en la `referencia` (atención cuando existe; crítico si
       no). Ver `solvers.goal_seek`.
    2. **ingreso_extra**: cuánto ingreso extra/mes (goal_seek ingreso_absoluto).
    3. **unidades_extra**: cuántas motos extra/mes; hoy es un stub (`disponible=False`)
       — la bisección entera vive en `cfo.calc.escenario.motos_para_evitar_umbral`,
       que consulta Mongo por iteración. El endpoint del cockpit no puede correr esa
       ruta síncrona; se expone el shape para que la UI muestre "en FABS" y el
       usuario navegue allá.

    Compute-only, sin escrituras. Motor sin tocar (usa `goal_seek` que va por
    `aplicar_impactos`). Todos los montos como string COP (regla 1)."""
    # Import diferido: solvers ya está importado arriba, pero hay que evitar ciclos.
    referencia = caja_atencion if caja_atencion is not None else caja_minima

    def _pal(variable: str) -> dict:
        g = goal_seek(
            r,
            caja_minima,
            variable=variable,
            objetivo_caja=referencia,
        )
        return {
            "monto": (
                money_str(g.valor) if g.valor is not None else money_str(Decimal("0"))
            ),
            "unidad": "COP/mes",
            "alcanzable": g.alcanzable,
            "referencia": money_str(referencia),
            "mensaje": g.mensaje,
        }

    return {
        "recorte_gasto": _pal("gasto_absoluto"),
        "ingreso_extra": _pal("ingreso_absoluto"),
        # Stub honesto: la palanca de unidades exige el pipeline completo y vive en
        # FABS (motos_para_evitar_umbral). Aquí se declara con `disponible=False`
        # para que la UI muestre el enlace correcto (no un cero engañoso).
        "unidades_extra": {
            "monto": None,
            "unidad": "motos/mes",
            "alcanzable": False,
            "disponible": False,
            "ver_en": "cfo.escenario.motos_para_evitar_umbral",
            # el mes del valle es la referencia natural para el usuario; incluirla
            # aunque no calculemos: la UI lo puede pasar al link
            "mes_referencia": valle.get("mes"),
        },
    }


async def _recomendaciones_recorte_por_impacto(
    monto_recorte: Decimal,
) -> list[dict]:
    """RF-F7 · Fundacional §2 — Recomendaciones por impacto: reparto del recorte
    por rubro (motor corrido al revés).

    Reusa lo mismo que el sugerido (§1.4.1): los 3 meses cerrados previos como
    ventana de referencia y `_ejecutados_por_rubro_mes` para el gasto por rubro.
    Filtra a rubros EGRESO activos no-sistema (los únicos donde tiene sentido
    "recortar"). El reparto puro (`reparto_por_rubro`) hace el ordenamiento por
    impacto + regla del 50%.

    Devuelve una lista serializada COP-string (regla 1) con `rubro_id`,
    `rubro_nombre`, `monto_recortar`, `gasto_actual` y `pct_de_su_gasto` (0.5000
    = 50%). Puede quedar corta contra el objetivo — el caller usa
    `sum(monto_recortar)` para saber si el reparto CUBRE el objetivo o hace falta
    otra palanca.
    """
    # Imports diferidos para evitar ciclos (presupuesto/rubros dependen de
    # proyeccion indirectamente por dominio compartido).
    from app.domain.rubro import Rubro
    from app.domain.rubro import TipoFlujo as _TF
    from app.presupuesto.service import (
        _ejecutados_por_rubro_mes,
        _meses_cerrados_previos,
    )

    if monto_recorte <= 0:
        return []
    # No conocemos aquí un "mes objetivo": el reparto usa la historia global (los
    # últimos 3 cerrados). Es la misma ventana del sugerido §1.4.1 — coherente.
    cerrados = await _meses_cerrados_previos(mes="9999-99")
    if not cerrados:
        return []
    # Solo EGRESO activos no-sistema (mismo criterio del sugerido; los rubros de
    # sistema — ej. IVA, cargue inicial — no son "recortables" por el CEO).
    rubros_egreso = await Rubro.find(
        Rubro.activo == True,  # noqa: E712 (Beanie construye el filtro)
        Rubro.es_sistema == False,  # noqa: E712
        Rubro.tipo_flujo == _TF.EGRESO,
    ).to_list()
    if not rubros_egreso:
        return []
    agg = await _ejecutados_por_rubro_mes(
        [mc.id for mc in cerrados], [r.id for r in rubros_egreso]
    )
    # Promedio N-cerrados por rubro (mismo cálculo que el sugerido, sin la
    # tendencia ni el %crec — el reparto pregunta "cuánto pesa en promedio").
    n = Decimal(str(len(cerrados)))
    gasto_por_rubro: dict[str, Decimal] = {}
    nombres: dict[str, str] = {}
    for rubro in rubros_egreso:
        total = sum(
            (agg.get((str(rubro.id), str(mc.id)), Decimal("0")) for mc in cerrados),
            Decimal("0"),
        )
        promedio = (total / n) if n else Decimal("0")
        if promedio <= 0:
            continue  # `reparto_por_rubro` los filtra también; salta aquí evita
            # ruido en el dict.
        rid = str(rubro.id)
        gasto_por_rubro[rid] = promedio
        nombres[rid] = rubro.nombre
    lineas = reparto_por_rubro(monto_recorte, gasto_por_rubro)
    return [
        {
            "rubro_id": ln["rubro_id"],
            "rubro_nombre": nombres.get(ln["rubro_id"], ""),
            "monto_recortar": money_str(ln["monto_recortar"]),
            "gasto_actual": money_str(ln["gasto_actual"]),
            "pct_de_su_gasto": str(ln["pct_de_su_gasto"]),
        }
        for ln in lineas
    ]


async def valles_vigente(
    *, escenario: str, mes_inicio: tuple[int, int], horizonte_meses: int | None
) -> dict:
    """D1 §3 — los valles (hitos) de la proyección vigente: mínimos de caja relevantes
    con sus causas. Lectura pura sobre la config vigente.

    RF-F5 · Fundacional §2 — cada valle llega con sus 3 palancas listas (recorte de
    gasto, ingreso extra, unidades extra) contra la referencia vigente (atención si
    está configurada, crítico si no)."""
    params, modelos = await _cargar_config_vigente()
    r, caja_min, _, _, _, caja_atn = await _resultado_con(
        params,
        modelos,
        escenario=escenario,
        mes_inicio=mes_inicio,
        horizonte_meses=horizonte_meses,
    )
    # RF-F3 · P2 — pasa el umbral de atención a `detectar_valles` para que la lista
    # traiga `entrada`/`salida`/`duracion`. Sin umbral configurado, comportamiento
    # idéntico al anterior (los 3 campos van en None).
    valles = detectar_valles(r.meses, caja_min, caja_atencion=caja_atn)
    valles_serial = [_serializar_valle(v) for v in valles]
    # RF-F5 · adjunta las palancas a cada valle. Compute-only.
    # RF-F7 · si la palanca `recorte_gasto` alcanza, adjunta el reparto por rubro
    # (motor corrido al revés): "de dónde saco ese recorte, ordenado por impacto".
    for v in valles_serial:
        palancas = _palancas_por_valle(r, v, caja_min, caja_atn)
        rg = palancas["recorte_gasto"]
        if rg["alcanzable"]:
            monto = Decimal(rg["monto"])
            rg["recomendaciones_por_rubro"] = (
                await _recomendaciones_recorte_por_impacto(monto)
            )
        v["palancas"] = palancas
    return {
        "escenario": escenario,
        "caja_minima": money_str(caja_min),
        "caja_atencion": money_str(caja_atn) if caja_atn is not None else None,
        "valles": valles_serial,
    }


async def proyectar_impactos(
    *,
    ajustes: list[Ajuste],
    escenario: str,
    mes_inicio: tuple[int, int],
    horizonte_meses: int | None,
) -> dict:
    """D1 §2 — proyección BASE vs. proyección CON AJUSTES, compute-only (SIMULAR NUNCA
    ESCRIBE). Devuelve ambas series con el shape de GET /proyeccion, los valles de cada
    una y el delta de flujo por mes. Con `ajustes` vacío, ajustada == base bit a bit."""
    params, modelos = await _cargar_config_vigente()
    r, caja_min, fondo, _, meta, _caja_atn = await _resultado_con(
        params,
        modelos,
        escenario=escenario,
        mes_inicio=mes_inicio,
        horizonte_meses=horizonte_meses,
    )
    ajustado = aplicar_impactos(r, ajustes, caja_min, primer_mes_acumula=True)
    r_aj = _kpis_a_resultado(ajustado)
    # SUP-5: los supuestos son los MISMOS para base y ajustada (un ajuste de D1 mueve
    # el flujo, no los drivers). Van en ambas para que `base` siga siendo GET
    # /proyeccion bit a bit — candado de test_impactos_endpoints.
    supuestos = _supuestos_visibles(params, escenario)
    return {
        "escenario": escenario,
        "base": _serializar(
            r, escenario, caja_min, fondo, meta=meta, supuestos=supuestos
        ),
        "ajustada": _serializar(
            r_aj, escenario, caja_min, fondo, meta=meta, supuestos=supuestos
        ),
        "valles_base": [
            _serializar_valle(v) for v in detectar_valles(r.meses, caja_min)
        ],
        "valles_ajustada": [
            _serializar_valle(v) for v in detectar_valles(ajustado.meses, caja_min)
        ],
        "delta_por_mes": [money_str(d) for d in ajustado.delta_por_mes],
    }


async def resolver(
    *,
    objetivo: str,
    ajustes: list[Ajuste],
    escenario: str,
    mes_inicio: tuple[int, int],
    horizonte_meses: int | None,
    colchon: Decimal = Decimal("0"),
    variable: str | None = None,
    objetivo_caja: Decimal | None = None,
    ventana_meses: int = 9,
) -> dict:
    """D1 §5 — solvers por bisección sobre la proyección vigente + los `ajustes` en
    pantalla. Compute-only. `objetivo` ∈ {techo_gasto, techo_gasto_ventana (RF-F4),
    goal_seek, punto_quiebre}."""
    params, modelos = await _cargar_config_vigente()
    r, caja_min, _, _, _, caja_atn = await _resultado_con(
        params,
        modelos,
        escenario=escenario,
        mes_inicio=mes_inicio,
        horizonte_meses=horizonte_meses,
    )
    if objetivo == "techo_gasto":
        t = techo_gasto(r, caja_min, ajustes_previos=ajustes, colchon=colchon)
        return {
            "objetivo": "techo_gasto",
            "techo_mensual": money_str(t.techo_mensual),
            "valle_limitante_mes": t.valle_limitante_mes,
            "piso_resultante": money_str(t.piso_resultante),
            "meta": money_str(t.meta),
            "colchon": money_str(t.colchon),
            "hay_holgura": t.hay_holgura,
        }
    if objetivo == "techo_gasto_ventana":
        # RF-F4 — techo mirando SOLO los primeros `ventana_meses` meses, contra el
        # umbral de ATENCIÓN (D-1) cuando está configurado; sin él cae al crítico.
        tv = techo_gasto_ventana(
            r,
            caja_min,
            ventana=ventana_meses,
            referencia=caja_atn,
            ajustes_previos=ajustes,
        )
        return {
            "objetivo": "techo_gasto_ventana",
            "techo_mensual": money_str(tv.techo_mensual),
            "valle_limitante_mes": tv.valle_limitante_mes,
            "piso_resultante": money_str(tv.piso_resultante),
            "referencia": money_str(tv.referencia),
            "ventana": tv.ventana,
            "hay_holgura": tv.hay_holgura,
            "perfora_atencion": tv.perfora_atencion,
        }
    if objetivo == "goal_seek":
        if variable is None or objetivo_caja is None:
            raise ProyeccionError("goal_seek requiere variable y objetivo_caja", 422)
        g = goal_seek(
            r,
            caja_min,
            variable=variable,
            objetivo_caja=objetivo_caja,
            ajustes_previos=ajustes,
        )
        return {
            "objetivo": "goal_seek",
            "variable": g.variable,
            # str() (no money_str): un % como 0.0345 no se puede cuantizar a 2 decimales
            "valor": (str(g.valor) if g.valor is not None else None),
            "alcanzable": g.alcanzable,
            "piso_resultante": (
                money_str(g.piso_resultante) if g.piso_resultante is not None else None
            ),
            "objetivo_caja": money_str(g.objetivo),
            "mensaje": g.mensaje,
        }
    if objetivo == "punto_quiebre":
        q = punto_de_quiebre(r, caja_min, ajustes_previos=ajustes)
        return {
            "objetivo": "punto_quiebre",
            "valor": (money_str(q.valor) if q.valor is not None else None),
            "mes": q.mes,
            "perfora": q.perfora,
        }
    raise ProyeccionError(f"objetivo no soportado: {objetivo}", 422)


async def simular_plazo(
    *,
    plazo_dias: int,
    escenario: str,
    mes_inicio: tuple[int, int],
    horizonte_meses: int | None,
) -> dict:
    """D2 §5 — simulador de política de plazos, compute-only: recomputa la proyección
    como si TODAS las facturas activas tomaran `plazo_dias` (clamp a ≥ plazo_base) y
    devuelve el piso, el valle y el costo financiero total. El front compara 90/120/150
    lado a lado. Aplicar la política de verdad = editar las facturas (explícito)."""
    params, modelos = await _cargar_config_vigente()
    reales = await _facturas_reconciliar()
    if not reales:
        raise ProyeccionError("no hay facturas activas para simular", 409)
    override = [
        replace(f, plazo_elegido_dias=max(plazo_dias, f.plazo_base_dias))
        for f in reales
    ]
    r, _caja, _fondo, rec, _, _ = await _resultado_con(
        params,
        modelos,
        escenario=escenario,
        mes_inicio=mes_inicio,
        horizonte_meses=horizonte_meses,
        facturas_override=override,
    )
    interes_total = sum(
        (Decimal(v) for v in (rec.interes_por_mes.values() if rec else [])),
        Decimal("0"),
    )
    return {
        "plazo_dias": plazo_dias,
        "piso_caja": money_str(r.piso_caja),
        "valle_mes": r.mes_mas_ajustado,
        "interes_total": money_str(interes_total),
    }


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
    modelos_m = [ln for m in modelos for ln in _modelo_a_lineas(m)]
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
                replace(m, cuota_semanal=m.cuota_semanal * factor) for m in pm.modelos
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
                crec_pct_mensual=max(_CERO, pm.crec_pct_mensual - Decimal("0.01"))
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
                costo_moto_nueva=max(_CERO, pm.costo_moto_nueva - Decimal("100000"))
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
                # PLAN-52: el segundo plan y su peso también invalidan el cache
                m.plan2_plazo_semanas,
                str(m.plan2_cuota_semanal),
                str(m.peso_plan1),
            )
            for m in modelos
        ),
    )


def _fingerprint_capas(anclas: dict, facturas: list[FacturaReconciliar]) -> tuple:
    """Huella de las capas E1/D2 para el cache del tornado: un cierre nuevo o una
    factura de obligación cambian el piso aunque los supuestos no cambien (bug CEO
    2026-08-11 — el cache servía el mundo sin la factura)."""
    return (
        tuple(sorted((mes, repr(a)) for mes, a in anclas.items())),
        tuple(
            (
                f.fecha_factura,
                str(f.valor),
                f.plazo_elegido_dias,
                f.plazo_base_dias,
                str(f.tasa_excedente_mensual),
            )
            for f in facturas
        ),
    )


async def sensibilidad_vigente(*, escenario: str, mes_inicio: tuple[int, int]) -> dict:
    """El tornado '¿qué mueve mi umbral?': 7 variables × ± → 14 corridas a 60 meses
    sobre el set vigente, cada una por la MISMA tubería que GET /proyeccion
    (motor → E1 anclaje → D2 reconciliación — bug CEO 2026-08-11: el motor crudo
    dejaba el piso clavado en la caja del arranque y todos los deltas en $0).
    Compute-only; cache por vigencia + huella de las capas."""
    params, modelos = await _cargar_config_vigente()
    anclas, rubros_e1, neutros_e1 = await cargar_anclas(
        mes_inicio, SENSIBILIDAD_HORIZONTE
    )
    facturas = await _facturas_reconciliar()
    clave = (
        _fingerprint(params, modelos),
        escenario,
        mes_inicio,
        _fingerprint_capas(anclas, facturas),
    )
    if clave in _sensibilidad_cache:
        return _sensibilidad_cache[clave]

    recaudo_previo, activos_previos = await cartera_previa_service.obtener_series()
    iva_egreso, _fondo = await _iva_plan(
        mes_inicio,
        SENSIBILIDAD_HORIZONTE,
        params.pct_prefondeo_iva,
        await _iva_proyectado(params, modelos, mes_inicio, SENSIBILIDAD_HORIZONTE),
    )
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

    def piso_con_capas(pm_x: ParametrosMotor):
        """Motor + E1 + D2 (mismo orden de precedencia de `_resultado_con`): el piso
        que ve la pantalla. Los meses anclados no responden a las variaciones — el
        pasado es del libro; el tornado mide el FUTURO, que es lo decidible."""
        r = proyectar(pm_x)
        meses_anclados: frozenset[str] = frozenset()
        if anclas:
            r = _kpis_a_resultado(
                anclar(
                    resultado=r,
                    caja_minima=params.caja_minima,
                    anclas=anclas,
                    rubros=rubros_e1,
                    neutros_ids=neutros_e1,
                    primer_mes_acumula=True,
                )
            )
            meses_anclados = frozenset(
                m for m, a in anclas.items() if a.estado == CERRADO
            )
        if facturas:
            rec = reconciliar(
                r,
                facturas,
                params.caja_minima,
                meses_anclados=meses_anclados,
                primer_mes_acumula=True,
            )
            r = _kpis_a_resultado(rec.ajustado)
        return r.piso_caja

    piso_base = piso_con_capas(pm)

    variables = []
    for v in _variaciones(pm):
        variables.append(
            {
                "variable": v["variable"],
                "etiqueta": v["etiqueta"],
                "variacion": v["variacion"],
                "piso_base": money_str(piso_base),
                "piso_mas": money_str(piso_con_capas(v["mas"])),
                "piso_menos": money_str(piso_con_capas(v["menos"])),
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


async def fabrica_proyectar_unidades(
    vig: ParametrosProyeccion,
    escenario: str,
    mes_inicio: tuple[int, int],
    horizonte_meses: int,
) -> Callable[[int], Awaitable[ResultadoProyeccion]]:
    """inc4 Task 6 (`cfo.calc.escenario.motos_para_evitar_umbral`) — arma el
    `proyectar_fn(n)` que exige `solver_unidades.resolver_unidades_para_umbral`: dado
    N (unidades extra/mes), devuelve el `ResultadoProyeccion` crudo de proyectar con
    `motos_base + N`.

    `cfo/calc` no puede importar `app.domain.*` ni `proyeccion.motor` directo
    (aislamiento S1, `test_s1_aislamiento.py`: ningún archivo de `cfo/calc/` puede
    contener esos imports): por eso la fábrica vive AQUÍ y
    `escenario._proyectar_fn_para` solo la LLAMA, opaco, sin importar sus tipos.

    Fix round 1 (revisión Opus del Task 6): `proyectar_fn` corre el MISMO pipeline
    COMPLETO que `proyectar_impactos`/`impacto_escenario` — `_resultado_con` (motor →
    E1 anclaje → D2 reconciliación), no solo el motor paramétrico. La versión anterior
    se detenía en `proyectar(pm)` (motor-only): como la caja se acumula mes a mes
    (`caja[m]=caja[m-1]+flujo[m]`), un delta de E1/D2 en los meses cercanos (la
    reconciliación de Auteco puede ser 100M+) se arrastra hasta el piso — el
    "cuántas motos" resultante podía SUBESTIMAR lo que realmente hace falta para
    cruzar el umbral (falsa confianza sobre el número exacto que el producto existe
    para proteger), y `impacto_escenario.piso_con` vs. este `piso_con_unidades@n=0`
    quedaban en bases DISTINTAS. `_resultado_con` se llama SIN `anclas_override` (a
    propósito: pasar ese override fuerza `arranque=semilla` y regresiona el arranque
    real del ciclo — P2 — que sí debe cargarse aquí).

    No se pasa `caja_inicial_override` ni `facturas_override` tampoco: exactamente
    el mismo shape de llamada que usa `proyectar_impactos` para su `_resultado_con`
    (`service.py` ~L918-924) — ambos caminos cargan la MISMA realidad de Mongo."""
    modelos = await modelos_service.listar_modelos(activo=True)
    if not modelos:
        raise ProyeccionError("no hay modelos de moto activos", 409)

    async def proyectar_fn(n: int) -> ResultadoProyeccion:
        params_n = vig.model_copy(update={"motos_base": vig.motos_base + n})
        # TODO fast-follow: cada candidato N (~14 por consulta, bisección) recarga
        # modelos/anclas/facturas/cartera-previa desde cero vía `_resultado_con` —
        # igual de costoso que 14 llamadas a `proyectar_impactos`. Aceptable para el
        # piloto (no es una ruta de alto tráfico); si se vuelve cuello de botella,
        # traer esos insumos UNA sola vez y repetir solo la parte pura por N, como
        # hace `sensibilidad_vigente`/`piso_con_capas` con sus 14 variaciones — pero
        # eso exige separar `_resultado_con` en fase async (una vez) + síncrona (por
        # N), un cambio más grande que no vale la pena sin evidencia real de que el
        # perf importa.
        r, _caja_min, _fondo, _rec, _meta, _caja_atn = await _resultado_con(
            params_n,
            modelos,
            escenario=escenario,
            mes_inicio=mes_inicio,
            horizonte_meses=horizonte_meses,
        )
        return r

    return proyectar_fn


_PALANCAS_ESCALARES = {"plazo_semanas", "cuota_inicial", "cuota_semanal"}


@dataclass(frozen=True)
class PalancaImpacto:
    """inc4 rebanada 2 (Task 1) — resultado crudo del what-if de una palanca de
    crédito (plazo/cuota inicial/cuota semanal) sobre uno o todos los modelos de
    moto. Solo tipos planos (Decimal/str): `cfo/calc` lo consume sin importar
    `app.domain.*` ni `proyeccion.motor` (aislamiento S1)."""

    piso_sin: Decimal
    piso_con: Decimal
    mes_quiebre: str  # 'YYYY-MM' o 'nunca'
    impacto: Decimal  # piso_con - piso_sin (lo computa COMPAS, no el motor)


def _mes_de_quiebre_raw(r: ResultadoProyeccion) -> str:
    return next((m.mes for m in r.meses if m.estado != "ok"), "nunca")


def _tipar_palanca(palanca: str, nuevo_valor: Decimal) -> int | Decimal:
    """Tipa el valor crudo según la palanca: `plazo_semanas` es entero > 0 (semanas
    no se fraccionan); `cuota_inicial`/`cuota_semanal` son Decimal ≥ 0 (Money)."""
    if palanca == "plazo_semanas":
        v = int(nuevo_valor)
        if v <= 0:
            raise ProyeccionError("plazo_semanas debe ser > 0", 422)
        return v
    if nuevo_valor < 0:  # cuota_inicial / cuota_semanal
        raise ProyeccionError(f"{palanca} no puede ser negativa", 422)
    return nuevo_valor


async def impacto_palanca_raw(
    *,
    palanca: str,
    nuevo_valor: Decimal,
    modelo: str = "todos",
    escenario: str,
    mes_inicio: tuple[int, int],
    horizonte_meses: int | None,
) -> PalancaImpacto:
    """inc4 rebanada 2 (Task 1) — el "what-if" de palancas de crédito que exige
    `cfo.calc.escenario` (rebanada 2): re-proyecta el pipeline COMPLETO dos veces
    (`_resultado_con`: motor → E1 anclaje → D2 reconciliación) — una vez tal cual
    (`piso_sin`) y otra con `palanca=nuevo_valor` aplicada al modelo objetivo (o a
    "todos", vía `ModeloMoto.model_copy`) — y devuelve el delta de piso + mes de
    quiebre en tipos planos (Decimal/str), igual que `fabrica_proyectar_unidades`
    hace para `motos_para_evitar_umbral`: `cfo/calc` no puede importar
    `app.domain.*` ni `proyeccion.motor` directo (aislamiento S1,
    `test_s1_aislamiento.py`), así que esta función carga params/modelos VIGENTES
    ella misma (fail-closed 409, vía `_cargar_config_vigente`) en vez de recibirlos
    del caller."""
    if palanca not in _PALANCAS_ESCALARES:
        raise ProyeccionError(f"palanca no soportada: {palanca}", 422)
    vig, modelos = await _cargar_config_vigente()
    if modelo != "todos" and not any(m.nombre == modelo for m in modelos):
        raise ProyeccionError(f"modelo desconocido: {modelo}", 422)
    valor = _tipar_palanca(palanca, nuevo_valor)

    def _override(m: ModeloMoto) -> ModeloMoto:
        if modelo == "todos" or m.nombre == modelo:
            return m.model_copy(update={palanca: valor})
        return m

    kw = dict(
        escenario=escenario, mes_inicio=mes_inicio, horizonte_meses=horizonte_meses
    )
    r_sin, *_ = await _resultado_con(vig, modelos, **kw)
    r_con, *_ = await _resultado_con(vig, [_override(m) for m in modelos], **kw)
    return PalancaImpacto(
        piso_sin=r_sin.piso_caja,
        piso_con=r_con.piso_caja,
        mes_quiebre=_mes_de_quiebre_raw(r_con),
        impacto=r_con.piso_caja - r_sin.piso_caja,
    )


ANCLA_MODOS = ("cerrado", "movimientos")


@dataclass(frozen=True)
class ActualMes:
    """FABS inc4 rebanada 3 (tendencias) — ingreso/gasto/caja REALES de un mes ya
    cargado (Transaccion), para que el cfo/calc de tendencias pueda comparar meses
    reales sin importar tipos de dominio (S1 isolation: solo Decimal/str)."""

    mes: str  # 'YYYY-MM'
    ingreso_real: Decimal
    gasto_real: Decimal
    caja_real: Decimal


async def _ingreso_real_mes(mes_id) -> Decimal:
    """Σ `valor` de las Transaccion INGRESO del mes (mongomock no soporta pipelines
    de agregación completos — se suma iterando `find`, como `_caja_libro`)."""
    total = Decimal("0")
    async for t in Transaccion.find(Transaccion.mes_id == mes_id):
        if t.tipo_flujo == TipoFlujo.INGRESO:
            total += t.valor
    return total


async def _egreso_real_mes(mes_id, rubro_ajuste_id) -> Decimal:
    """Σ `valor` de las Transaccion EGRESO del mes, excluyendo el rubro 'Ajuste de
    conciliación' por `rubro_id` PRIMARIO — mismo criterio que `_caja_libro` (el
    ajuste es un artefacto del cierre, no gasto real)."""
    total = Decimal("0")
    async for t in Transaccion.find(Transaccion.mes_id == mes_id):
        if t.tipo_flujo == TipoFlujo.EGRESO and t.rubro_id != rubro_ajuste_id:
            total += t.valor
    return total


async def actuals_mensuales(*, meses: int = 3) -> list[ActualMes]:
    """Los últimos `meses` MesControl CON movimientos, cronológico ascendente, con
    su ingreso/gasto/caja reales. Base de las preguntas de tendencia sobre datos
    REALES (FABS inc4 rebanada 3)."""
    rubro_aj = await _rubro_ajuste()
    todos = await MesControl.find_all().sort(+MesControl.mes).to_list()
    # meses con movimientos, los más recientes primero, hasta `meses`
    con_mov: list[MesControl] = []
    for mc in reversed(todos):
        if await Transaccion.find(Transaccion.mes_id == mc.id).count() > 0:
            con_mov.append(mc)
            if len(con_mov) >= meses:
                break
    out: list[ActualMes] = []
    for mc in reversed(con_mov):  # cronológico asc
        out.append(
            ActualMes(
                mes=mc.mes[:7],
                ingreso_real=await _ingreso_real_mes(mc.id),
                gasto_real=await _egreso_real_mes(mc.id, rubro_aj.id),
                caja_real=await _caja_libro(mc.id, rubro_aj.id, mc.saldo_inicial_caja),
            )
        )
    return out


_GRUPOS_GASTO = [g for g in RubroGrupo if g != RubroGrupo.INGRESOS_OPERATIVOS]


@dataclass(frozen=True)
class ComposicionGasto:
    """FABS inc4 rebanada 4 (ratios/mix) — egreso REAL agregado por RubroGrupo de
    gasto (los 5, sin ingresos_operativos), sobre los meses de una ventana. Valores
    planos (Decimal/str) para que cfo/calc compute el % después (S1); el % NO se
    calcula aquí."""

    ventana: str
    meses: list[str]  # 'YYYY-MM'
    por_grupo: dict[str, Decimal]  # RubroGrupo.value -> COP
    total: Decimal


async def _meses_de_ventana(ventana: str) -> list[MesControl]:
    """Los MesControl de la ventana pedida, cronológico ascendente. 'cerrado' = el
    último CERRADO; 'curso' = el último con movimientos; 'acumulado' = los últimos 3
    con movimientos. Ventana desconocida → 422 (fail-closed, no se adivina)."""
    todos = await MesControl.find_all().sort(+MesControl.mes).to_list()
    if ventana == "cerrado":
        cerrados = [mc for mc in todos if mc.estado == EstadoMes.CERRADO]
        return cerrados[-1:]
    con_mov: list[MesControl] = []
    for mc in reversed(todos):  # más recientes primero
        if await Transaccion.find(Transaccion.mes_id == mc.id).count() > 0:
            con_mov.append(mc)
    if ventana == "curso":
        return con_mov[:1]
    if ventana == "acumulado":
        return list(reversed(con_mov[:3]))
    raise ProyeccionError(f"ventana no soportada: {ventana}", 422)


async def composicion_gasto_real(*, ventana: str) -> ComposicionGasto:
    """Egreso REAL de la ventana, agregado por RubroGrupo, excluyendo el rubro de
    sistema 'Ajuste de conciliación' (mismo criterio que `_caja_libro` /
    `actuals_mensuales`) — tanto en el rubro PRIMARIO como en cada `parte` de una
    transacción dividida (PTS6-B). mongomock no soporta pipelines `$group`
    confiables: se agrega iterando `Transaccion.find` + `pares_clasificacion`, como
    el resto del módulo."""
    meses = await _meses_de_ventana(ventana)
    if not meses:
        raise ProyeccionError("sin meses con datos para la ventana", 409)
    rubro_aj = await _rubro_ajuste()
    grupo_de = {r.id: r.grupo for r in await Rubro.find_all().to_list()}
    por_grupo: dict[str, Decimal] = {g.value: Decimal("0") for g in _GRUPOS_GASTO}
    mes_ids = [mc.id for mc in meses]
    async for t in Transaccion.find(
        {"mes_id": {"$in": mes_ids}, "tipo_flujo": TipoFlujo.EGRESO.value}
    ):
        for rid, val in pares_clasificacion(t):
            if rid == rubro_aj.id:
                continue
            g = grupo_de.get(rid)
            if g is None or g == RubroGrupo.INGRESOS_OPERATIVOS:
                continue
            por_grupo[g.value] += val
    total = sum(por_grupo.values(), Decimal("0"))
    return ComposicionGasto(
        ventana=ventana,
        meses=[mc.mes[:7] for mc in meses],
        por_grupo=por_grupo,
        total=total,
    )


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
        # P3 del ciclo mensual: la caja del ancla es la del CIERRE de ese mes, o sea la
        # que existe ANTES del siguiente. Asi que el forecast arranca en el mes
        # SIGUIENTE: el tramo real termina en el ancla y el proyectado sigue desde ahi,
        # sin repetir el punto ni contar dos veces el flujo del mes ancla (antes el
        # primer mes tenia la caja fija y por eso el solape no se notaba).
        y_sig, m_sig = (y + 1, 1) if m == 12 else (y, m + 1)
        forecast = await proyectar_vigente(
            escenario=escenario,
            mes_inicio=(y_sig, m_sig),
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
        "forecast": [{"mes": f["mes"], "caja": f["caja"]} for f in forecast["meses"]],
    }
