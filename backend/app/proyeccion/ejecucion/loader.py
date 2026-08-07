# backend/app/proyeccion/ejecucion/loader.py
"""E1 · P3 — loader de anclaje (la ÚNICA capa Mongo de E1).

Dado `(mes_inicio, horizonte)`, arma los insumos que `ejecucion.service.anclar` consume:
el dict `anclas: {'YYYY-MM': AnclaMes}`, la lista de `RubroInfo` y el set `neutros_ids`.
Traduce el estado del ciclo (`MesControl`) al régimen de anclaje del plan §1:

    CERRADO       → 'cerrado'      : ejecutado por rubro + ingreso_real (sin neutros)
    EN_EJECUCION  → 'en_ejecucion' : ejecutado real + presupuesto definido (Regla A)
    otro estado con definido vigente > 0 → 'presupuesto' : solo el definido
    sin MesControl / futuro sin definido → OMITIDO (el motor queda intacto)

`lectura.py` (P1) y `service.py` (P2) siguen PUROS (sin Mongo): esta es la capa que los
alimenta. Reusa las queries ya probadas —`_egresos_por_rubro`, `PresupuestoLinea`
vigente, `metas_ingreso.ingreso_real`, `rubros_neutros._ids_rubros_neutros`— sin
reinventar agregaciones.
"""

from __future__ import annotations

from decimal import Decimal

from beanie import PydanticObjectId
from beanie.operators import In

from app.control.service import _egresos_por_rubro
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.presupuesto import PresupuestoLinea
from app.domain.rubro import Rubro
from app.domain.rubros_neutros import _ids_rubros_neutros
from app.metas_ingreso.service import ingreso_real
from app.proyeccion.ejecucion.lectura import RubroInfo
from app.proyeccion.ejecucion.service import (
    CERRADO,
    EN_EJECUCION,
    PRESUPUESTO,
    AnclaMes,
)
from app.proyeccion.motor import _meses_del_horizonte

_CERO = Decimal("0")


async def _rubros_info() -> list[RubroInfo]:
    """Snapshot de la taxonomía → `RubroInfo` (id como str, grupo como valor plano)."""
    return [
        RubroInfo(
            id=str(r.id),
            codigo=r.codigo,
            grupo=r.grupo.value,
            nombre=r.nombre,
            es_sistema=r.es_sistema,
        )
        for r in await Rubro.find_all().to_list()
    ]


async def _definido_por_rubro(mes_id: PydanticObjectId) -> dict[str, Decimal]:
    """Presupuesto DEFINIDO vigente por rubro (magnitud POSITIVA). `{}` si aún no hay
    definido (líneas con `monto_definido` nulo o no positivas)."""
    lineas = await PresupuestoLinea.find(
        PresupuestoLinea.mes_id == mes_id,
        PresupuestoLinea.vigente == True,  # noqa: E712 — Beanie exige la comparación
    ).to_list()
    return {
        str(ln.rubro_id): ln.monto_definido
        for ln in lineas
        if ln.monto_definido is not None and ln.monto_definido > _CERO
    }


async def cargar_anclas(
    mes_inicio: tuple[int, int], horizonte: int
) -> tuple[dict[str, AnclaMes], list[RubroInfo], set[str]]:
    """Arma `(anclas, rubros, neutros_ids)` para `anclar`. Los meses sin MesControl o
    futuros sin presupuesto definido quedan fuera de `anclas` (el motor los cubre)."""
    meses = [f"{a:04d}-{m:02d}" for a, m in _meses_del_horizonte(mes_inicio, horizonte)]
    rubros = await _rubros_info()
    neutros_ids = {str(i) for i in await _ids_rubros_neutros()}

    # un solo query para los MesControl del horizonte
    claves = [f"{m}-01" for m in meses]
    por_mes = {
        mc.mes[:7]: mc
        for mc in await MesControl.find(In(MesControl.mes, claves)).to_list()
    }

    anclas: dict[str, AnclaMes] = {}
    for m in meses:
        mc = por_mes.get(m)
        if mc is None:
            continue  # sin ciclo → motor intacto
        if mc.estado == EstadoMes.CERRADO:
            anclas[m] = AnclaMes(
                estado=CERRADO,
                ejecutado_por_rubro_id=await _egresos_por_rubro(mc.id),
                definido_por_rubro_id={},
                ingreso_real=await ingreso_real(m),
            )
        elif mc.estado == EstadoMes.EN_EJECUCION:
            anclas[m] = AnclaMes(
                estado=EN_EJECUCION,
                ejecutado_por_rubro_id=await _egresos_por_rubro(mc.id),
                definido_por_rubro_id=await _definido_por_rubro(mc.id),
                ingreso_real=None,
            )
        else:
            definido = await _definido_por_rubro(mc.id)
            if definido:  # futuro con presupuesto definido vigente
                anclas[m] = AnclaMes(
                    estado=PRESUPUESTO,
                    ejecutado_por_rubro_id={},
                    definido_por_rubro_id=definido,
                    ingreso_real=None,
                )
            # futuro sin definido → omitido (motor)
    return anclas, rubros, neutros_ids
