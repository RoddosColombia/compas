# backend/app/presupuesto/service.py
"""Generación del sugerido (F-07): crea las PresupuestoLinea vigentes de un mes a
partir del ejecutado de los meses CERRADOS anteriores (§1.4.1).

MARCADO PARA AUDITORÍA KIMI (motor del sugerido — fórmula celda a celda).

Alcance de este incremento: generar líneas en modo HISTÓRICO para los rubros
activos NO de sistema ('Por clasificar'/'Ajuste'/'Recaudo' se excluyen — no son
líneas presupuestables). El acotamiento (monto_definido) y la aprobación (→definido)
son incrementos siguientes; aquí toda línea nace `vigente`, version 1, sin definir.

E(i) = Σ valor de Transaccion (egreso) del rubro en el mes cerrado i. Se toman los 3
meses 'cerrado' inmediatamente anteriores al mes objetivo (los que existan)."""

from decimal import Decimal

from app.domain.mes_control import EstadoMes, MesControl
from app.domain.presupuesto import PresupuestoLinea
from app.domain.rubro import Rubro, TipoFlujo
from app.domain.transaccion import Transaccion
from app.presupuesto.motor import calcular_sugerido_historico


class SugeridoError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


async def _meses_cerrados_previos(mes: str, limite: int = 3) -> list[MesControl]:
    """Los `limite` meses en estado 'cerrado' con mes < objetivo, del más reciente
    al más antiguo (E(M-1), E(M-2), E(M-3))."""
    return (
        await MesControl.find(
            MesControl.estado == EstadoMes.CERRADO, MesControl.mes < mes
        )
        .sort(-MesControl.mes)
        .limit(limite)
        .to_list()
    )


async def _ejecutado(rubro_id, mes_id) -> Decimal:
    """Σ valor de las transacciones de EGRESO del rubro en ese mes cerrado."""
    total = Decimal("0")
    async for t in Transaccion.find(
        Transaccion.rubro_id == rubro_id,
        Transaccion.mes_id == mes_id,
        Transaccion.tipo_flujo == TipoFlujo.EGRESO,
    ):
        total += t.valor
    return total


async def generar_sugerido(
    *, mes: str, usuario_id: str, crec_pct: Decimal = Decimal("0")
) -> list[PresupuestoLinea]:
    objetivo = await MesControl.find_one(MesControl.mes == mes)
    if objetivo is None:
        raise SugeridoError(f"el mes {mes[:7]} no está abierto")
    if await PresupuestoLinea.find_one(PresupuestoLinea.mes_id == objetivo.id):
        raise SugeridoError(
            f"el mes {mes[:7]} ya tiene presupuesto generado", status=409
        )

    cerrados = await _meses_cerrados_previos(mes)
    rubros = await Rubro.find(
        Rubro.activo == True,  # noqa: E712 (Beanie construye el filtro)
        Rubro.es_sistema == False,  # noqa: E712
    ).to_list()

    creadas: list[PresupuestoLinea] = []
    for rubro in rubros:
        ejecutados = [await _ejecutado(rubro.id, mc.id) for mc in cerrados]
        comp = calcular_sugerido_historico(ejecutados, crec_pct)
        linea = PresupuestoLinea(
            mes_id=objetivo.id,
            rubro_id=rubro.id,
            monto_sugerido=comp.monto_sugerido,
            prom_3m=comp.prom_3m,
            tendencia_mes=comp.tendencia_mes,
            crec_pct=crec_pct,
            historia_incompleta=comp.historia_incompleta,
        )
        await linea.insert()
        creadas.append(linea)

    # DECISIÓN (Kimi): la generación NO emite evento. El catálogo cerrado (regla 11)
    # no tiene 'sugerido.generado'; usar presupuesto.acotado sería mal uso semántico
    # (acotar = ajustar una línea existente, no generarla). El sugerido es un
    # BORRADOR recomputable (monto_definido=null); los eventos reales llegan con el
    # acotamiento (presupuesto.acotado) y la aprobación (presupuesto.definido). Si el
    # gate exige rastro de generación → CR para 'presupuesto.sugerido_generado'.
    return creadas
