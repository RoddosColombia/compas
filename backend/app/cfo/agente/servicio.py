# backend/app/cfo/agente/servicio.py
"""FABS · orquestador de una consulta (D2). Flujo: emite cfo.consulta → corre el loop
→ verifica cifra→evidencia → si falla, UN reintento correctivo → verifica → publica o
se abstiene (dura). Emite cfo.respuesta. La auditoría es fail-soft (lectura: no bloquea
la respuesta si la BD de auditoría falla; O1 rama no-crítica).

Nota de alcance — verificación por UNIDAD, no por CONCEPTO (decisión explícita T10,
hereda la nota de `verificador.verificar`):

(a) Límite: `verificar()` agrupa la evidencia disponible del turno por `unidad`
    (COP / meses), no por `concepto`. Como `caja_hoy` e `iva_cuatrimestre` comparten
    unidad COP, una cifra que el modelo etiquete mal (dice "la caja es X" pero en
    realidad citó el valor de IVA) pasaría el verificador si X cae en tolerancia de
    CUALQUIER resultado COP del turno — el control atrapa "número inventado", no
    "número real pero atribuido al concepto equivocado".
(b) Por qué es aceptable para inc2: el flag `CFO_ENABLED` sigue apagado (nadie
    depende de esto en producción todavía); con solo 3 conceptos hoy (caja_hoy,
    runway_meses en meses, iva_cuatrimestre en COP) una COLISIÓN de magnitud entre
    caja e IVA dentro de ±$1 COP es, en la práctica, virtualmente imposible (son
    series independientes con dominios de valores muy distintos); y el propio
    prompt (regla 1, SYSTEM_PROMPT) prohíbe al modelo calcular o mezclar cifras,
    lo que limita — sin eliminar — la probabilidad de esta confusión específica.
(c) Trazabilidad que SÍ queda, para que un humano pueda auditar el caso raro: cada
    `CifraPublicada` en `RespuestaCFO.cifras` viaja con su propia `Evidencia`
    (fuente + fecha_corte + ref) heredada del `ResultadoCFO` que la respaldó;
    `RespuestaCFO.conceptos_usados` lista todos los conceptos consultados en el
    turno; y la metadata de auditoría `cfo.respuesta` persiste ambos. Con eso un
    revisor puede cotejar a mano "¿la cifra que el texto atribuye a X coincide con
    la Evidencia/concepto que realmente la produjo?" — el sistema no lo hace solo,
    pero no deja el rastro incompleto.
(d) Pendiente, fuera de alcance aquí: verificación cifra→CONCEPTO (no solo
    cifra→valor), que exigiría o bien que el modelo cite estructuradamente
    (p. ej. `[[caja_hoy]]` inline) o NLP para atar cada número del texto a su
    concepto más cercano — ninguna de las dos se implementa en este archivo.
    Requiere CR para un incremento posterior; NO se aborda con un fix rápido acá.
"""

import logging

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cfo import config
from app.cfo.agente.cliente import ClienteLLM, crear_cliente
from app.cfo.agente.loop import ResultadoLoop, conversar
from app.cfo.agente.modelos import CifraPublicada, RespuestaCFO, UsoLLM
from app.cfo.agente.prompt import CORRECTIVO
from app.cfo.agente.verificador import verificar
from app.cfo.calc.evidencia import ResultadoCFO

logger = logging.getLogger(__name__)

_ABSTENCION = (
    "Con los datos disponibles no puedo confirmar esa cifra con evidencia. "
    "Prefiero no darte un número que no pueda respaldar."
)


async def _audit_soft(evento, metadata: dict, actor_id: str) -> None:
    try:
        await emit_audit(evento, entidad="cfo", actor_id=actor_id, metadata=metadata)
    except Exception:  # noqa: BLE001 — lectura: no bloquear la respuesta
        logger.exception("fallo al auditar %s", evento)


def _cifras(resultados: list[ResultadoCFO]) -> list[CifraPublicada]:
    return [
        CifraPublicada(valor=str(r.valor), unidad=r.unidad, evidencia=r.evidencia)
        for r in resultados
        if r.disponible and r.valor is not None
    ]


def _abstencion(motivo: str, res: ResultadoLoop | None, actor_id: str) -> RespuestaCFO:
    uso = UsoLLM(
        modelo=config.cfo_model(),
        tokens_in=res.tokens_in if res else 0,
        tokens_out=res.tokens_out if res else 0,
        iteraciones=res.iteraciones if res else 0,
    )
    return RespuestaCFO(
        texto=_ABSTENCION,
        abstuvo=True,
        motivo=motivo,
        conceptos_usados=[],
        cifras=[],
        uso=uso,
    )


def _meta(r: RespuestaCFO) -> dict:
    return {
        "abstuvo": r.abstuvo,
        "motivo": r.motivo,
        "conceptos_usados": r.conceptos_usados,
        "cifras": [
            {
                "valor": c.valor,
                "unidad": c.unidad,
                "evidencia": c.evidencia.model_dump(),
            }
            for c in r.cifras
        ],
        "uso": r.uso.model_dump(),
    }


async def consultar(
    pregunta: str, *, actor_id: str, cliente: ClienteLLM | None = None
) -> RespuestaCFO:
    await _audit_soft(
        AuditEvento.cfo_consulta, {"pregunta": pregunta, "canal": "api"}, actor_id
    )

    if cliente is None:
        cliente = crear_cliente()
    if cliente is None:
        r = _abstencion("sin_api_key", None, actor_id)
        await _audit_soft(AuditEvento.cfo_respuesta, _meta(r), actor_id)
        return r

    try:
        res = await conversar(
            cliente,
            [{"role": "user", "content": pregunta}],
            max_iter=config.cfo_max_iter(),
        )
    except Exception:  # noqa: BLE001 — fallo del LLM
        logger.exception("fallo del LLM en FABS")
        r = _abstencion("error_llm", None, actor_id)
        await _audit_soft(AuditEvento.cfo_respuesta, _meta(r), actor_id)
        return r

    if res.texto is None:
        r = _abstencion("tope_iter", res, actor_id)
        await _audit_soft(AuditEvento.cfo_respuesta, _meta(r), actor_id)
        return r

    # Ver nota de alcance del módulo (arriba): `verificar()` respalda cifra->valor
    # por unidad, no cifra->concepto. Aceptado para inc2 (flag off + colisión de
    # magnitud entre caja/IVA prácticamente imposible); CR aparte para cerrarlo.
    veredicto = verificar(res.texto, res.resultados)
    if not veredicto.ok:
        # UN reintento correctivo con los valores válidos
        valores = (
            "; ".join(
                f"{r.concepto}={r.valor} {r.unidad}"
                for r in res.resultados
                if r.disponible and r.valor is not None
            )
            or "(ninguno disponible)"
        )
        correccion = CORRECTIVO.format(
            cifras=", ".join(veredicto.cifras_sin_evidencia), valores=valores
        )
        mensajes = [
            {"role": "user", "content": pregunta},
            {"role": "assistant", "content": res.texto},
            {"role": "user", "content": correccion},
        ]
        try:
            res2 = await conversar(cliente, mensajes, max_iter=config.cfo_max_iter())
        except Exception:  # noqa: BLE001
            logger.exception("fallo del LLM en reintento FABS")
            r = _abstencion("error_llm", res, actor_id)
            await _audit_soft(AuditEvento.cfo_respuesta, _meta(r), actor_id)
            return r
        # acumular resultados/uso de ambas conversaciones para las cifras/evidencia
        # y para que el `uso` reportado (éxito o abstención) refleje el costo real
        # de las DOS llamadas al LLM, no solo la primera.
        res.resultados.extend(res2.resultados)
        res.tokens_in += res2.tokens_in
        res.tokens_out += res2.tokens_out
        res.iteraciones += res2.iteraciones
        if res2.texto is None or not verificar(res2.texto, res.resultados).ok:
            r = _abstencion("verificacion", res, actor_id)
            await _audit_soft(AuditEvento.cfo_respuesta, _meta(r), actor_id)
            return r
        texto_final = res2.texto
    else:
        texto_final = res.texto

    r = RespuestaCFO(
        texto=texto_final,
        abstuvo=False,
        motivo=None,
        conceptos_usados=[x.concepto for x in res.resultados],
        cifras=_cifras(res.resultados),
        uso=UsoLLM(
            modelo=config.cfo_model(),
            tokens_in=res.tokens_in,
            tokens_out=res.tokens_out,
            iteraciones=res.iteraciones,
        ),
    )
    await _audit_soft(AuditEvento.cfo_respuesta, _meta(r), actor_id)
    return r
