# backend/app/gastos_recurrentes/service.py
"""CRUD + resumen de la plantilla de gastos recurrentes (decisión CEO 2026-07-26).

INFORMATIVO: no toca el motor (no altera `gastos_fijos`) → no es flujo crítico de
dinero. Sin eventos de auditoría (catálogo cerrado, regla 11: no se inventan eventos
sin CR). Dinero=Decimal (regla 1). Cada gasto valida que su `rubro_id` exista (regla
7 en espíritu: no se apunta a una categoría fantasma). El equivalente mensual y los
totales por grupo se calculan aquí (el cálculo financiero vive en el backend).
"""

from decimal import Decimal

from beanie import PydanticObjectId

from app.core.time import now_bogota
from app.domain.gasto_recurrente import Frecuencia, GastoRecurrente
from app.domain.rubro import Rubro


class GastosError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


def _oid(valor: str, etiqueta: str) -> PydanticObjectId:
    try:
        return PydanticObjectId(valor)
    except Exception:
        raise GastosError(f"{etiqueta} inválido", 422) from None


async def _obtener(gasto_id: str) -> GastoRecurrente:
    g = await GastoRecurrente.get(_oid(gasto_id, "gasto_id"))
    if g is None:
        raise GastosError("el gasto no existe", 404)
    return g


async def crear_gasto(
    *,
    rubro_id: str,
    descripcion: str,
    monto: Decimal,
    frecuencia: Frecuencia,
    dia_pago: int | None,
    notas: str | None,
    hasta: str | None = None,
    usuario_id: str,  # noqa: ARG001 — sin auditoría (regla 11); reservado a futuro CR
) -> GastoRecurrente:
    rid = _oid(rubro_id, "rubro_id")
    if await Rubro.get(rid) is None:
        raise GastosError("el rubro no existe", 404)
    ultimo = (
        await GastoRecurrente.find_all().sort(-GastoRecurrente.orden).first_or_none()
    )
    gasto = GastoRecurrente(
        rubro_id=rid,
        descripcion=descripcion,
        monto=monto,
        frecuencia=frecuencia,
        dia_pago=dia_pago,
        hasta=hasta,
        notas=notas,
        orden=(ultimo.orden if ultimo is not None else 0) + 1,
    )
    await gasto.insert()
    return gasto


async def listar_gastos(*, activo: bool | None = None) -> list[GastoRecurrente]:
    filtros = []
    if activo is not None:
        filtros.append(GastoRecurrente.activo == activo)
    return await GastoRecurrente.find(*filtros).sort(+GastoRecurrente.orden).to_list()


async def editar_gasto(
    *,
    gasto_id: str,
    rubro_id: str | None = None,
    descripcion: str | None = None,
    monto: Decimal | None = None,
    frecuencia: Frecuencia | None = None,
    dia_pago: int | None = None,
    dia_pago_set: bool = False,
    hasta: str | None = None,
    hasta_set: bool = False,
    notas: str | None = None,
    notas_set: bool = False,
    activo: bool | None = None,
) -> GastoRecurrente:
    """PATCH parcial. `*_set` distingue "poner en None" de "no tocar" en campos
    opcionales (dia_pago/hasta/notas)."""
    gasto = await _obtener(gasto_id)
    if rubro_id is not None:
        rid = _oid(rubro_id, "rubro_id")
        if await Rubro.get(rid) is None:
            raise GastosError("el rubro no existe", 404)
        gasto.rubro_id = rid
    if descripcion is not None:
        gasto.descripcion = descripcion
    if monto is not None:
        gasto.monto = monto
    if frecuencia is not None:
        gasto.frecuencia = frecuencia
    # aplicar si viene valor, o si el router pidió explícitamente ponerlo en None.
    if dia_pago is not None or dia_pago_set:
        gasto.dia_pago = dia_pago
    if hasta is not None or hasta_set:
        gasto.hasta = hasta
    if notas is not None or notas_set:
        gasto.notas = notas
    if activo is not None:
        gasto.activo = activo
    await gasto.save()
    return gasto


async def eliminar_gasto(*, gasto_id: str) -> None:
    gasto = await _obtener(gasto_id)
    await gasto.delete()


async def resumen_mensual(
    gastos: list[GastoRecurrente], *, mes_ref: str | None = None
) -> dict:
    """Total mensual (equivalente) global y por grupo del Plan de Cuentas.

    Cuenta gastos ACTIVOS y VIGENTES en `mes_ref` (YYYY-MM; por defecto el mes actual
    en Bogotá): un gasto con `hasta` anterior a `mes_ref` ya terminó y no suma. El
    grupo lo trae el rubro apuntado (el cruce con la arquitectura); un gasto cuyo rubro
    ya no exista se agrupa como 'sin_rubro'."""
    mes = mes_ref or now_bogota().strftime("%Y-%m")
    vigentes = [g for g in gastos if g.activo and (g.hasta is None or g.hasta >= mes)]
    activos = vigentes
    rubro_ids = {g.rubro_id for g in activos}
    rubros = {
        r.id: r for r in await Rubro.find({"_id": {"$in": list(rubro_ids)}}).to_list()
    }
    por_grupo: dict[str, Decimal] = {}
    total = Decimal("0.00")
    for g in activos:
        r = rubros.get(g.rubro_id)
        grupo = r.grupo.value if r is not None else "sin_rubro"
        por_grupo[grupo] = por_grupo.get(grupo, Decimal("0.00")) + g.monto_mensual
        total += g.monto_mensual
    return {"por_grupo": por_grupo, "total": total}
