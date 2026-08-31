# backend/app/cfo/vigilante/iva.py
"""FABS · vigilante — 4º job proactivo: tesorería de IVA (inc6 #1, spec §5.3). Espeja
`alerta.py`/`disparadores.py`/`alerta_texto.py` en un solo módulo (alcance de esta
pieza): evalúa los disparadores (cerca DIAN / descubierto), arma el texto
DETERMINISTA (plantilla + tokens `ivates_*` + `verificar` + `sustituir_tokens`,
reusando la calc pura `iva_tesoreria.armar_conceptos`) y entrega el borrador al
revisor. Orquestación (S1: NO vive en cfo/calc; lee proyeccion/facturas/cierre —
cfo/vigilante SÍ puede importar dominio, a diferencia de cfo/calc/agente/router, ver
`tests/cfo/test_s1_aislamiento.py`).

Disparo (spec §5.3, casos borde §8): cada línea exige que TODOS sus tokens tengan
evidencia disponible este turno — sin eso, abstención honesta (regla 7) en vez de una
línea a medias (nunca se manda un `[[token]]` sin respaldo, `verificar` lo rechazaría
igual). `reserva_objetivo` (`FondoMes.saldo` del mes actual) lo cita CADA línea, así
que sin fondo/config de proyección (`ProyeccionError` → `reserva_objetivo=None`)
NINGÚN disparo puede armar su texto: el proactivo se abstiene TOTAL, igual que el
advisory (§8: "el advisory y el proactivo se abstienen"). `dias<=ALERTA_IVA_DIAS` NO
depende del disponible (caja) — solo de la fecha DIAN + el objetivo de reserva; el
disponible (caja) solo alimenta el disparador 'descubierto'.

`periodo` de `AvisoVigilante` es 'YYYY-MM' aquí (el mes vigente) — a diferencia de
`alerta_caja`, que usa el día ('YYYY-MM-DD') porque su disparo es diario y sin
concepto de período fiscal. El job corre diario igual; supersede cualquier borrador
pendiente cuyo periodo no sea el mes actual (idempotencia MENSUAL, no diaria)."""

import logging
from dataclasses import dataclass
from decimal import Decimal

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cfo import config
from app.cfo.agente.conceptos import sustituir_tokens
from app.cfo.agente.verificador import verificar
from app.cfo.calc import iva as iva_calc
from app.cfo.calc.evidencia import ResultadoCFO
from app.cfo.calc.iva_tesoreria import armar_conceptos
from app.cfo.telegram.cliente import crear_cliente_telegram
from app.cfo.vigilante.modelos import AvisoVigilante
from app.cierre.service import CierreError, conciliacion
from app.configuracion.service import leer_alerta_iva_dias
from app.core.time import now_bogota, today_bogota
from app.domain.mes_control import EstadoMes, MesControl
from app.facturas import service as fact_service
from app.iva.liquidacion import periodo_de, proximo_pago
from app.proyeccion import service as proy_service
from app.proyeccion.service import ProyeccionError

logger = logging.getLogger(__name__)

_ENCABEZADO = "💰 Tesorería de IVA — FABS"

# Ninguna plantilla contiene un dígito crudo (chocaría con el verificador).
_LINEAS: dict[str, str] = {
    "dian_cerca": (
        "📅 El IVA del período vence pronto: [[ivates_proximo_pago]]. Objetivo de "
        "reserva a hoy: [[ivates_reserva_objetivo]]."
    ),
    "descubierto": (
        "🔴 Tu disponible no cubre la reserva de IVA: te faltan [[ivates_faltante]] "
        "para el objetivo [[ivates_reserva_objetivo]]."
    ),
}


class IvaTextoError(RuntimeError):
    """El verificador rechazó el texto de tesorería de IVA (no debería ocurrir: es
    determinista y sin cifras crudas). Fail-loud para no difundir algo sin verificar."""


@dataclass(frozen=True)
class Disparo:
    tipo: str  # 'dian_cerca' | 'descubierto'


@dataclass(frozen=True)
class ResultadoIva:
    disparos: list[Disparo]
    resultados: list[ResultadoCFO]


async def _fondo_mes_actual() -> tuple[Decimal | None, Decimal | None]:
    """`(reserva_objetivo, reserva_mes)` del `FondoMes` del mes ACTUAL (mismo cálculo
    que `agente/tools.py:_iva_tesoreria`, replicado aquí porque `cfo/agente` está en
    la frontera S1 y este módulo no debe depender de él). `ProyeccionError` o sin fila
    del mes actual ⇒ `(None, None)` — sin fondo configurado no hay objetivo que narrar
    (§8)."""
    ahora = now_bogota()
    mes_actual = f"{ahora.year:04d}-{ahora.month:02d}"
    try:
        proy = await proy_service.proyectar_vigente(
            escenario="base",
            mes_inicio=(ahora.year, ahora.month),
            horizonte_meses=None,
        )
    except ProyeccionError:
        return None, None
    fila = next(
        (f for f in proy.get("fondo_provision", []) if f["mes"] == mes_actual), None
    )
    if fila is None:
        return None, None
    return Decimal(fila["saldo"]), Decimal(fila["reserva"])


async def _proximo_dian() -> tuple[dict | None, Decimal | None]:
    """`(proximo, proximo_monto)`. `proximo` = `{fecha, dias}` del período fiscal
    VIGENTE vía `iva.liquidacion.proximo_pago` (periodicidad-agnóstico, lee
    `PERIODICIDAD_IVA`/`CALENDARIO_DIAN` de Configuración; sin fecha en el calendario
    ⇒ `None`, nunca se inventa — R5). `proximo_monto` reusa `iva.iva_cuatrimestre()`
    (la tool FABS ya existente); esa calc falla-cerrado a `disponible=False` si la
    periodicidad vigente no es cuatrimestral (ver su docstring) — entonces
    `proximo_monto` sale `None` y el disparador 'cerca DIAN' se abstiene (no puede
    citar `[[ivates_proximo_pago]]` sin evidencia)."""
    periodicidad = await fact_service.obtener_periodicidad()
    calendario = await fact_service.obtener_calendario_dian()
    anio, idx = periodo_de(today_bogota().isoformat(), periodicidad)
    proximo = proximo_pago(anio, idx, periodicidad, calendario)

    iva_res = await iva_calc.iva_cuatrimestre()
    proximo_monto = iva_res.valor if iva_res.disponible else None
    return proximo, proximo_monto


async def _disponible_real() -> Decimal | None:
    """Replica el patrón de `disparadores._disparador_real`: caja consolidada
    reportada del mes `EN_EJECUCION` de hoy. `None` sin mes en ejecución,
    `CierreError`, o algún banco `sin_dato` (dato incompleto: no se reporta una
    cobertura falsa)."""
    mc = await MesControl.find_one(MesControl.estado == EstadoMes.EN_EJECUCION)
    if mc is None:
        return None
    try:
        con = await conciliacion(mc.mes)
    except CierreError:
        return None
    if con["sin_dato"]:
        return None
    return Decimal(con["consolidado_reportado"])


async def evaluar_iva() -> ResultadoIva | None:
    reserva_objetivo, reserva_mes = await _fondo_mes_actual()
    proximo, proximo_monto = await _proximo_dian()
    disponible = await _disponible_real()

    disparos: list[Disparo] = []
    if (
        proximo is not None
        and reserva_objetivo is not None
        and proximo_monto is not None
        and proximo["dias"] <= await leer_alerta_iva_dias()
    ):
        disparos.append(Disparo("dian_cerca"))
    if (
        disponible is not None
        and reserva_objetivo is not None
        and disponible < reserva_objetivo
    ):
        disparos.append(Disparo("descubierto"))

    if not disparos:
        return None

    resultados = armar_conceptos(
        reserva_objetivo=reserva_objetivo,
        reserva_mes=reserva_mes,
        proximo_monto=proximo_monto,
        proximo_fecha=proximo["fecha"] if proximo is not None else None,
        disponible=disponible,
    )
    return ResultadoIva(disparos=disparos, resultados=resultados)


def construir_texto_iva(res: ResultadoIva) -> tuple[str, str]:
    cuerpo = "\n".join(_LINEAS[d.tipo] for d in res.disparos)
    crudo = f"{_ENCABEZADO}\n\n{cuerpo}"
    ver = verificar(crudo, res.resultados)
    if not ver.ok:
        raise IvaTextoError(
            f"tesorería IVA rechazada por el verificador: "
            f"cifras={ver.cifras_sin_evidencia} tokens_invalidos={ver.tokens_invalidos}"
        )
    return crudo, sustituir_tokens(crudo, res.resultados)


async def _audit_soft(evento, entidad_id: str, metadata: dict) -> None:
    try:
        await emit_audit(
            evento,
            entidad="vigilante",
            entidad_id=entidad_id,
            actor_id="vigilante",
            metadata=metadata,
        )
    except Exception:  # noqa: BLE001 — job proactivo: no reventar por auditoría
        logger.exception("fallo al auditar %s", evento)


async def _superar_borradores_iva(excepto: str | None) -> None:
    """Marca 'superado' todo borrador de tesorería de IVA pendiente cuyo periodo !=
    `excepto`."""
    pendientes = await AvisoVigilante.find(
        AvisoVigilante.tipo == "iva_tesoreria", AvisoVigilante.estado == "borrador"
    ).to_list()
    for a in pendientes:
        if excepto is None or a.periodo != excepto:
            a.estado = "superado"
            await a.save()


async def generar_y_entregar_iva() -> AvisoVigilante | None:
    ahora = now_bogota()
    periodo = f"{ahora.year:04d}-{ahora.month:02d}"
    res = await evaluar_iva()
    if res is None:
        await _superar_borradores_iva(excepto=None)  # retira todo pendiente
        logger.info("tesorería de IVA: ningún disparador; nada que enviar")
        return None

    await _superar_borradores_iva(excepto=periodo)  # deja solo el de este mes
    crudo, texto = construir_texto_iva(res)
    conceptos = [r.concepto for r in res.resultados]

    aviso = await AvisoVigilante.find_one(
        AvisoVigilante.tipo == "iva_tesoreria", AvisoVigilante.periodo == periodo
    )
    if aviso is None:
        aviso = AvisoVigilante(
            tipo="iva_tesoreria",
            periodo=periodo,
            texto=texto,
            texto_crudo=crudo,
            estado="borrador",
            generado_at=now_bogota(),
            conceptos_usados=conceptos,
        )
        await aviso.insert()
    else:  # refresca el de este mes (idempotencia mensual)
        aviso.texto, aviso.texto_crudo = texto, crudo
        aviso.estado, aviso.generado_at = "borrador", now_bogota()
        aviso.conceptos_usados = conceptos
        await aviso.save()

    await _audit_soft(
        AuditEvento.vigilante_iva_generado,
        periodo,
        {
            "periodo": periodo,
            "disparadores": [d.tipo for d in res.disparos],
            "conceptos_usados": conceptos,
        },
    )

    revisor = config.vigilante_revisor_telegram_id()
    if revisor is None:
        logger.warning(
            "VIGILANTE_REVISOR_TELEGRAM_ID sin configurar; tesorería IVA no enviada"
        )
        return aviso
    cliente_tg = crear_cliente_telegram()
    if cliente_tg is not None:
        await cliente_tg.enviar(
            revisor,
            aviso.texto + "\n\nRespondé 'publicar iva' para difundirla al comité.",
        )
    return aviso
